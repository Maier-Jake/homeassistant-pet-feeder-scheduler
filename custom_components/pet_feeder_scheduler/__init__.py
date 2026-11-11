"""Pet Feeder Scheduler: write on-device schedules to Aqara Pet Feeder C1s on ZHA.

This file is the Home Assistant glue. It registers one action,
``pet_feeder_scheduler.set_schedule``, turns the action's fields into meals,
finds each feeder through ZHA, and hands the work to ``zigbee.py``.
"""

from __future__ import annotations

import logging
from datetime import time
from typing import Any

import voluptuous as vol
from homeassistant.components.zha.helpers import async_get_zha_device_proxy
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_DEVICE_ID,
    ATTR_FEEDER_CLOCK,
    ATTR_SET_SCHEDULE_MODE,
    DOMAIN,
    FEEDER_CLOCK_UTC,
    FEEDER_CLOCKS,
    MEAL_SLOTS,
    SERVICE_SET_SCHEDULE,
    meal_portions_field,
    meal_time_field,
)
from .schedule import MAX_PORTIONS, MIN_PORTIONS, Meal, shift_to_feeder_clock
from .zigbee import FeederWriteError, find_feeder_cluster, write_schedule

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_PORTIONS = vol.All(vol.Coerce(int), vol.Range(min=MIN_PORTIONS, max=MAX_PORTIONS))

SET_SCHEDULE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): vol.All(cv.ensure_list, [cv.string]),
        **{
            vol.Optional(meal_time_field(slot)): cv.time
            for slot in range(1, MEAL_SLOTS + 1)
        },
        **{
            vol.Optional(meal_portions_field(slot)): _PORTIONS
            for slot in range(1, MEAL_SLOTS + 1)
        },
        vol.Optional(ATTR_FEEDER_CLOCK, default=FEEDER_CLOCK_UTC): vol.In(
            FEEDER_CLOCKS
        ),
        vol.Optional(ATTR_SET_SCHEDULE_MODE, default=True): cv.boolean,
    }
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the set_schedule action."""
    # Starts at 0 on every Home Assistant start. The feeder accepted every
    # sequence number we tried, so it does not need to survive restarts.
    sequence = 0

    async def async_set_schedule(call: ServiceCall) -> ServiceResponse:
        nonlocal sequence
        local_meals = _meals_from_call(call.data)
        feeder_clock = call.data[ATTR_FEEDER_CLOCK]
        if feeder_clock == FEEDER_CLOCK_UTC:
            offset = dt_util.now().utcoffset()
            feeder_meals = shift_to_feeder_clock(local_meals, offset)
        else:
            feeder_meals = local_meals

        # Look up every feeder before writing to any, so a typo in one device
        # doesn't leave the others half-updated.
        targets = []
        for device_id in call.data[ATTR_DEVICE_ID]:
            name = _device_name(hass, device_id)
            targets.append((device_id, name, _feeder_cluster(hass, device_id, name)))

        written: list[dict[str, Any]] = []
        failed: list[str] = []
        for device_id, name, cluster in targets:
            sequence = (sequence + 1) % 256
            try:
                value = await write_schedule(
                    cluster,
                    feeder_meals,
                    sequence,
                    set_schedule_mode=call.data[ATTR_SET_SCHEDULE_MODE],
                )
            except FeederWriteError as err:
                _LOGGER.error("Could not write schedule to %s: %s", name, err)
                failed.append(f"{name}: {err}")
                continue
            written.append(
                {
                    "device_id": device_id,
                    "name": name,
                    "feeder_clock": feeder_clock,
                    "meals_as_entered": [_describe(meal) for meal in local_meals],
                    "meals_on_feeder": [_describe(meal) for meal in feeder_meals],
                    "attribute_value": value.hex(),
                }
            )

        if failed:
            done = ", ".join(entry["name"] for entry in written) or "none"
            raise HomeAssistantError(
                f"Schedule not written to: {'; '.join(failed)}. Written to: {done}."
            )
        return {"devices": written} if call.return_response else None

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_SCHEDULE,
        async_set_schedule,
        schema=SET_SCHEDULE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Nothing to set up per entry; the config entry only makes the action available."""
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Nothing to unload."""
    return True


def _meals_from_call(data: dict[str, Any]) -> list[Meal]:
    """Build meals from the meal_N_time / meal_N_portions fields."""
    meals: list[Meal] = []
    for slot in range(1, MEAL_SLOTS + 1):
        meal_time: time | None = data.get(meal_time_field(slot))
        portions: int | None = data.get(meal_portions_field(slot))
        if meal_time is None and portions is None:
            continue
        if meal_time is None or portions is None:
            raise ServiceValidationError(
                f"Meal {slot} needs both a time and a number of portions."
            )
        if meal_time.second:
            raise ServiceValidationError(
                f"Meal {slot}: the feeder schedules whole minutes, not seconds."
            )
        meals.append(
            Meal(hour=meal_time.hour, minute=meal_time.minute, portions=portions)
        )
    if not meals:
        raise ServiceValidationError("Give at least one meal time.")
    times = [(meal.hour, meal.minute) for meal in meals]
    if len(set(times)) != len(times):
        raise ServiceValidationError("Two meals are scheduled for the same time.")
    return meals


def _feeder_cluster(hass: HomeAssistant, device_id: str, name: str) -> Any:
    """Return the feeder's Aqara cluster through ZHA's device lookup."""
    # async_get_zha_device_proxy is not a documented public API. It raises
    # KeyError for unknown devices and ZHA groups, ValueError when ZHA is not
    # running, and StopIteration for devices that ZHA does not own.
    try:
        proxy = async_get_zha_device_proxy(hass, device_id)
    except (KeyError, ValueError, StopIteration) as err:
        raise ServiceValidationError(f"{name} is not a ZHA device.") from err
    try:
        return find_feeder_cluster(proxy.device.device)
    except FeederWriteError as err:
        raise ServiceValidationError(f"{name}: {err}") from err


def _device_name(hass: HomeAssistant, device_id: str) -> str:
    """Return a readable device name for messages."""
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        return device_id
    return device.name_by_user or device.name or device_id


def _describe(meal: Meal) -> str:
    """Describe a meal as e.g. ``12:10 x5``."""
    return f"{meal.hour:02d}:{meal.minute:02d} x{meal.portions}"

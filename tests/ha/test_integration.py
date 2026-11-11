"""Tests of the config flow and the set_schedule action inside Home Assistant.

ZHA is not running in these tests. ``async_get_zha_device_proxy`` is replaced
with a fake that returns a fake feeder, so the tests check what the action
would write without any Zigbee hardware.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry
from zigpy.zcl import foundation

from custom_components.pet_feeder_scheduler.const import DOMAIN, SERVICE_SET_SCHEDULE

FEEDER_MODEL = "aqara.feeder.acn001"
LOOKUP = "custom_components.pet_feeder_scheduler.async_get_zha_device_proxy"

SUCCESS = [[foundation.WriteAttributesStatusRecord(status=foundation.Status.SUCCESS)]]
FAILURE = [[foundation.WriteAttributesStatusRecord(status=foundation.Status.FAILURE)]]

# The schedule bytes verified on hardware (see tests/test_schedule.py), minus
# the 3-byte prefix that holds the sequence number.
HARDWARE_THREE_MEALS_AFTER_SEQUENCE = (
    bytes([8, 0, 8, 200, 33]) + b"7f0c0a0500,7f12000500,7f17000500\x00"
)


class FakeCluster:
    """Records writes; returns scripted results (success by default)."""

    def __init__(self, result: Any = None) -> None:
        self.result = SUCCESS if result is None else result
        self.writes: list[dict[str, Any]] = []

    async def write_attributes(self, attributes: dict[str, Any], **kwargs: Any) -> Any:
        self.writes.append(attributes)
        return self.result


def fake_proxy(cluster: FakeCluster, model: str = FEEDER_MODEL) -> SimpleNamespace:
    """Mimic ZHADeviceProxy -> zha Device -> zigpy device -> endpoint 1."""
    zigpy_device = SimpleNamespace(
        model=model,
        endpoints={1: SimpleNamespace(in_clusters={0xFCC0: cluster})},
    )
    return SimpleNamespace(device=SimpleNamespace(device=zigpy_device))


@pytest.fixture
async def setup(hass: HomeAssistant) -> None:
    """Set up the integration in US Central time on 2026-11-10 (UTC-6)."""
    await hass.config.async_set_time_zone("America/Chicago")
    MockConfigEntry(domain=DOMAIN).add_to_hass(hass)
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()


MEALS = {
    "meal_1_time": "06:10:00",
    "meal_1_portions": 5,
    "meal_2_time": "12:00:00",
    "meal_2_portions": 5,
    "meal_3_time": "17:00:00",
    "meal_3_portions": 5,
}


async def call(hass: HomeAssistant, data: dict[str, Any], **kwargs: Any) -> Any:
    return await hass.services.async_call(
        DOMAIN, SERVICE_SET_SCHEDULE, data, blocking=True, **kwargs
    )


# --- Config flow ----------------------------------------------------------------


async def test_config_flow_creates_one_entry(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


# --- set_schedule ---------------------------------------------------------------


@pytest.mark.freeze_time("2026-11-11T01:44:00+00:00")
async def test_writes_hardware_schedule_in_utc(
    hass: HomeAssistant, setup: None
) -> None:
    cluster = FakeCluster()
    with patch(LOOKUP, return_value=fake_proxy(cluster)):
        response = await call(
            hass, {"device_id": "feeder_one", **MEALS}, return_response=True
        )

    value = cluster.writes[0]["feeder_attr"]
    assert value[3:] == HARDWARE_THREE_MEALS_AFTER_SEQUENCE
    assert cluster.writes[1] == {"feeding_mode": 1}
    device = response["devices"][0]
    assert device["meals_as_entered"] == ["06:10 x5", "12:00 x5", "17:00 x5"]
    assert device["meals_on_feeder"] == ["12:10 x5", "18:00 x5", "23:00 x5"]


@pytest.mark.freeze_time("2027-07-01T12:00:00+00:00")
async def test_daylight_time_uses_todays_offset(
    hass: HomeAssistant, setup: None
) -> None:
    cluster = FakeCluster()
    with patch(LOOKUP, return_value=fake_proxy(cluster)):
        response = await call(
            hass,
            {"device_id": "f", "meal_1_time": "06:10:00", "meal_1_portions": 5},
            return_response=True,
        )
    assert response["devices"][0]["meals_on_feeder"] == ["11:10 x5"]


async def test_local_clock_writes_times_unchanged(
    hass: HomeAssistant, setup: None
) -> None:
    cluster = FakeCluster()
    with patch(LOOKUP, return_value=fake_proxy(cluster)):
        response = await call(
            hass,
            {"device_id": "f", "feeder_clock": "local", **MEALS},
            return_response=True,
        )
    assert response["devices"][0]["meals_on_feeder"] == [
        "06:10 x5",
        "12:00 x5",
        "17:00 x5",
    ]


async def test_can_leave_mode_alone(hass: HomeAssistant, setup: None) -> None:
    cluster = FakeCluster()
    with patch(LOOKUP, return_value=fake_proxy(cluster)):
        await call(hass, {"device_id": "f", "set_schedule_mode": False, **MEALS})
    assert len(cluster.writes) == 1


async def test_writes_every_feeder(hass: HomeAssistant, setup: None) -> None:
    clusters = {"one": FakeCluster(), "two": FakeCluster()}
    with patch(LOOKUP, side_effect=lambda _hass, dev: fake_proxy(clusters[dev])):
        await call(hass, {"device_id": ["one", "two"], **MEALS})
    sequences = [c.writes[0]["feeder_attr"][2] for c in clusters.values()]
    assert all(len(c.writes) == 2 for c in clusters.values())
    assert sequences[0] != sequences[1]


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"meal_1_time": "06:10:00"}, "both a time and a number of portions"),
        ({"meal_2_portions": 3}, "both a time and a number of portions"),
        ({"meal_1_time": "06:10:30", "meal_1_portions": 1}, "whole minutes"),
        (
            {
                "meal_1_time": "06:10:00",
                "meal_1_portions": 1,
                "meal_2_time": "06:10:00",
                "meal_2_portions": 2,
            },
            "same time",
        ),
        ({}, "at least one meal"),
    ],
)
async def test_rejects_bad_meals(
    hass: HomeAssistant, setup: None, data: dict[str, Any], message: str
) -> None:
    cluster = FakeCluster()
    with (
        patch(LOOKUP, return_value=fake_proxy(cluster)),
        pytest.raises(ServiceValidationError, match=message),
    ):
        await call(hass, {"device_id": "f", **data})
    assert cluster.writes == []


async def test_rejects_too_many_portions(hass: HomeAssistant, setup: None) -> None:
    with pytest.raises(vol.Invalid, match="value must be at most 10"):
        await call(
            hass, {"device_id": "f", "meal_1_time": "06:00", "meal_1_portions": 11}
        )


async def test_rejects_non_zha_device(hass: HomeAssistant, setup: None) -> None:
    with (
        patch(LOOKUP, side_effect=KeyError("not found")),
        pytest.raises(ServiceValidationError, match="not a ZHA device"),
    ):
        await call(hass, {"device_id": "f", **MEALS})


async def test_rejects_other_models(hass: HomeAssistant, setup: None) -> None:
    with (
        patch(LOOKUP, return_value=fake_proxy(FakeCluster(), model="lumi.plug")),
        pytest.raises(ServiceValidationError, match="expected"),
    ):
        await call(hass, {"device_id": "f", **MEALS})


async def test_bad_device_stops_before_any_write(
    hass: HomeAssistant, setup: None
) -> None:
    good = FakeCluster()

    def lookup(_hass: HomeAssistant, device_id: str) -> SimpleNamespace:
        if device_id == "bad":
            raise KeyError(device_id)
        return fake_proxy(good)

    with (
        patch(LOOKUP, side_effect=lookup),
        pytest.raises(ServiceValidationError),
    ):
        await call(hass, {"device_id": ["good", "bad"], **MEALS})
    assert good.writes == []


async def test_write_failure_names_the_feeder(hass: HomeAssistant, setup: None) -> None:
    clusters = {"good": FakeCluster(), "broken": FakeCluster(FAILURE)}
    with (
        patch(LOOKUP, side_effect=lambda _hass, dev: fake_proxy(clusters[dev])),
        pytest.raises(HomeAssistantError, match=r"not written to: broken.*to: good"),
    ):
        await call(hass, {"device_id": ["good", "broken"], **MEALS})
    assert len(clusters["good"].writes) == 2

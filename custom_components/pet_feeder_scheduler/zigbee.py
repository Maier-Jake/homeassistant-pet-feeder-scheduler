"""Write a schedule to a feeder's Aqara cluster.

This module depends on zigpy only, not Home Assistant. It is handed the
feeder's cluster object by ``__init__.py`` and is tested with a fake cluster in
``tests/test_zigbee.py``.

The cluster is the ``OppleCluster`` that ZHA's device quirk for
``aqara.feeder.acn001`` installs (zha-quirks, ``zhaquirks/xiaomi/aqara/feeder.py``).
That quirk defines the attribute names used below:

* ``feeder_attr`` (0xFFF1): raw octet string, manufacturer code 0x115F. The quirk
  passes values for it through unchanged.
* ``feeding_mode``: the quirk turns this into the feeder's own "mode" message
  (0 = manual, 1 = schedule). It is the same write the Mode select entity in
  Home Assistant makes.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any, Protocol

from zigpy.zcl import foundation

from .schedule import Meal, build_attribute_value

_LOGGER = logging.getLogger(__name__)

FEEDER_MODEL = "aqara.feeder.acn001"
FEEDER_ENDPOINT_ID = 1
AQARA_CLUSTER_ID = 0xFCC0

FEEDER_ATTRIBUTE = "feeder_attr"
FEEDING_MODE_ATTRIBUTE = "feeding_mode"
FEEDING_MODE_SCHEDULE = 1

WRITE_ATTEMPTS = 3


class FeederWriteError(Exception):
    """The feeder did not accept a write."""


class WritableCluster(Protocol):
    """The part of a zigpy cluster this module uses."""

    async def write_attributes(self, attributes: dict[str, Any], **kwargs: Any) -> Any:
        """Write attributes and return zigpy's status records."""


def find_feeder_cluster(zigpy_device: Any) -> WritableCluster:
    """Return the feeder's Aqara cluster, or raise ``FeederWriteError``."""
    if zigpy_device.model != FEEDER_MODEL:
        raise FeederWriteError(
            f"device model is {zigpy_device.model!r}, expected {FEEDER_MODEL!r}"
        )
    try:
        return zigpy_device.endpoints[FEEDER_ENDPOINT_ID].in_clusters[AQARA_CLUSTER_ID]
    except KeyError as err:
        raise FeederWriteError(
            "feeder has no Aqara cluster 0xFCC0 on endpoint 1; is the ZHA quirk loaded?"
        ) from err


async def write_schedule(
    cluster: WritableCluster,
    meals: list[Meal],
    sequence: int,
    *,
    set_schedule_mode: bool,
) -> bytes:
    """Write ``meals`` to the feeder and return the bytes that were written.

    The meal times must already be in the feeder's clock (see
    ``schedule.shift_to_feeder_clock``). With ``set_schedule_mode`` the feeder
    is also switched to schedule mode, which it needs to follow the schedule.
    """
    value = build_attribute_value(meals, sequence)
    _LOGGER.debug("Writing schedule %s", value.hex())
    await _write(cluster, {FEEDER_ATTRIBUTE: value})
    if set_schedule_mode:
        await _write(cluster, {FEEDING_MODE_ATTRIBUTE: FEEDING_MODE_SCHEDULE})
    return value


async def _write(cluster: WritableCluster, attributes: dict[str, Any]) -> None:
    """Write attributes, retrying a failed attempt up to ``WRITE_ATTEMPTS`` times."""
    name = ", ".join(attributes)
    problem = "no attempt made"
    for attempt in range(1, WRITE_ATTEMPTS + 1):
        try:
            result = await cluster.write_attributes(attributes)
        # zigpy and the radio libraries raise several unrelated exception types
        # for delivery failures and timeouts, so any exception counts as a
        # failed attempt. The last one is reported if all attempts fail.
        except Exception as err:  # noqa: BLE001
            problem = f"{type(err).__name__}: {err}"
        else:
            failed = _failed_statuses(result)
            if not failed:
                return
            problem = f"feeder answered {', '.join(failed)}"
        _LOGGER.debug("Write of %s, attempt %d failed: %s", name, attempt, problem)
    raise FeederWriteError(
        f"writing {name} failed after {WRITE_ATTEMPTS} attempts: {problem}"
    )


def _failed_statuses(result: Any) -> list[str]:
    """Return the names of every non-success status in a zigpy write result."""
    return [
        getattr(record.status, "name", str(record.status))
        for record in _flatten(result)
        if record.status != foundation.Status.SUCCESS
    ]


def _flatten(result: Any) -> Iterable[Any]:
    """Yield status records from zigpy's nested result lists."""
    if isinstance(result, (list, tuple)):
        for item in result:
            yield from _flatten(item)
    else:
        yield result

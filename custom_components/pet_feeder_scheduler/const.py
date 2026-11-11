"""Constants for Pet Feeder Scheduler."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "pet_feeder_scheduler"

SERVICE_SET_SCHEDULE: Final = "set_schedule"

ATTR_DEVICE_ID: Final = "device_id"
ATTR_FEEDER_CLOCK: Final = "feeder_clock"
ATTR_SET_SCHEDULE_MODE: Final = "set_schedule_mode"

MEAL_SLOTS: Final = 4
"""Number of meal fields the action offers. Matches schedule.MAX_MEALS."""


def meal_time_field(slot: int) -> str:
    """Return the action field name for a meal's time, e.g. ``meal_1_time``."""
    return f"meal_{slot}_time"


def meal_portions_field(slot: int) -> str:
    """Return the action field name for a meal's portions, e.g. ``meal_1_portions``."""
    return f"meal_{slot}_portions"


FEEDER_CLOCK_UTC: Final = "utc"
"""The feeder keeps UTC (what we observed on ZHA). Meal times are converted
using today's UTC offset, so they stay at a fixed absolute time all year."""

FEEDER_CLOCK_LOCAL: Final = "local"
"""Write meal times exactly as entered, for a feeder whose clock is local time."""

FEEDER_CLOCKS: Final = [FEEDER_CLOCK_UTC, FEEDER_CLOCK_LOCAL]

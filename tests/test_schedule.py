"""Tests for schedule.py.

The three ``HARDWARE_*`` byte lists below were written to real Aqara Pet Feeder
C1s through ZHA Toolkit on 2026-11-10, and each feeder dispensed food at the
expected times. The encoder must reproduce them byte for byte.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from pet_feeder_scheduler.schedule import (
    EVERY_DAY,
    MAX_MEALS,
    Meal,
    build_attribute_value,
    decode_attribute_value,
    encode_payload,
    shift_to_feeder_clock,
)

# Every day at 12:10, 18:00 and 23:00 (feeder clock, UTC), 5 portions each.
# Sequence 49. This is a long-running schedule on two feeders.
HARDWARE_THREE_MEALS = [
    0, 2, 49, 8, 0, 8, 200, 33,
    55, 102, 48, 99, 48, 97, 48, 53, 48, 48, 44,
    55, 102, 49, 50, 48, 48, 48, 53, 48, 48, 44,
    55, 102, 49, 55, 48, 48, 48, 53, 48, 48, 0,
]  # fmt: skip

# Every day at 18:46 and 00:47 UTC, 1 portion each. Sequence 32. The 00:47
# meal fired at 18:47 US Central (UTC-6), which showed the clock is UTC.
HARDWARE_TWO_MEALS = [
    0, 2, 32, 8, 0, 8, 200, 22,
    55, 102, 49, 50, 50, 101, 48, 49, 48, 48, 44,
    55, 102, 48, 48, 50, 102, 48, 49, 48, 48, 0,
]  # fmt: skip

# The three meals above plus 01:58 UTC, 5 portions. Sequence 51. Shows that a
# 4-meal schedule is accepted.
HARDWARE_FOUR_MEALS = [
    0, 2, 51, 8, 0, 8, 200, 44,
    55, 102, 48, 99, 48, 97, 48, 53, 48, 48, 44,
    55, 102, 49, 50, 48, 48, 48, 53, 48, 48, 44,
    55, 102, 49, 55, 48, 48, 48, 53, 48, 48, 44,
    55, 102, 48, 49, 51, 97, 48, 53, 48, 48, 0,
]  # fmt: skip

THREE_MEALS_UTC = [Meal(12, 10, 5), Meal(18, 0, 5), Meal(23, 0, 5)]

CENTRAL = ZoneInfo("America/Chicago")


def offset_on(day: datetime) -> timedelta:
    """Return the UTC offset in effect at ``day``."""
    offset = day.utcoffset()
    assert offset is not None
    return offset


# --- Encoding matches the bytes verified on hardware ---------------------------


def test_three_meals_match_hardware() -> None:
    assert list(build_attribute_value(THREE_MEALS_UTC, 49)) == HARDWARE_THREE_MEALS


def test_two_meals_match_hardware() -> None:
    meals = [Meal(18, 46, 1), Meal(0, 47, 1)]
    assert list(build_attribute_value(meals, 32)) == HARDWARE_TWO_MEALS


def test_four_meals_match_hardware() -> None:
    meals = [*THREE_MEALS_UTC, Meal(1, 58, 5)]
    assert list(build_attribute_value(meals, 51)) == HARDWARE_FOUR_MEALS


def test_payload_text() -> None:
    assert encode_payload([Meal(12, 10, 5)]) == b"7f0c0a0500\x00"


def test_meal_order_is_kept() -> None:
    # The hardware-verified 2-meal schedule was not in time order.
    text = encode_payload([Meal(18, 46, 1), Meal(0, 47, 1)])
    assert text == b"7f122e0100,7f002f0100\x00"


# --- Decoding -------------------------------------------------------------------


@pytest.mark.parametrize(
    "value", [HARDWARE_THREE_MEALS, HARDWARE_TWO_MEALS, HARDWARE_FOUR_MEALS]
)
def test_decode_round_trip(value: list[int]) -> None:
    meals = decode_attribute_value(bytes(value))
    assert list(build_attribute_value(meals, value[2])) == value


def test_decode_reads_fields() -> None:
    assert decode_attribute_value(bytes(HARDWARE_TWO_MEALS)) == [
        Meal(18, 46, 1, EVERY_DAY),
        Meal(0, 47, 1, EVERY_DAY),
    ]


def test_decode_rejects_wrong_code() -> None:
    value = bytearray(HARDWARE_TWO_MEALS)
    value[6] = 0xC9
    with pytest.raises(ValueError, match="not a schedule"):
        decode_attribute_value(bytes(value))


def test_decode_rejects_wrong_length() -> None:
    with pytest.raises(ValueError, match="length byte"):
        decode_attribute_value(bytes(HARDWARE_TWO_MEALS[:-1]))


# --- Validation -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"hour": 24, "minute": 0, "portions": 1}, "hour"),
        ({"hour": -1, "minute": 0, "portions": 1}, "hour"),
        ({"hour": 0, "minute": 60, "portions": 1}, "minute"),
        ({"hour": 0, "minute": 0, "portions": 0}, "portions"),
        ({"hour": 0, "minute": 0, "portions": 11}, "portions"),
        ({"hour": 0, "minute": 0, "portions": 1, "days": 0}, "days"),
        ({"hour": 0, "minute": 0, "portions": 1, "days": 0x80}, "days"),
    ],
)
def test_meal_rejects_bad_values(kwargs: dict[str, int], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        Meal(**kwargs)


def test_needs_at_least_one_meal() -> None:
    with pytest.raises(ValueError, match="1-4 meals"):
        encode_payload([])


def test_rejects_too_many_meals() -> None:
    meals = [Meal(hour, 0, 1) for hour in range(MAX_MEALS + 1)]
    with pytest.raises(ValueError, match="1-4 meals"):
        encode_payload(meals)


def test_rejects_duplicate_times() -> None:
    with pytest.raises(ValueError, match="same time"):
        encode_payload([Meal(6, 0, 1), Meal(6, 0, 2)])


@pytest.mark.parametrize("sequence", [-1, 256])
def test_rejects_bad_sequence(sequence: int) -> None:
    with pytest.raises(ValueError, match="sequence"):
        build_attribute_value([Meal(6, 0, 1)], sequence)


# --- Converting wall-clock times to the feeder's UTC clock ------------------------


def test_central_standard_time_matches_hardware_schedule() -> None:
    # 6:10 AM, noon and 5 PM in US Central Standard Time (Nov 10, 2026).
    offset = offset_on(datetime(2026, 11, 10, 19, 44, tzinfo=CENTRAL))
    assert offset == timedelta(hours=-6)
    local = [Meal(6, 10, 5), Meal(12, 0, 5), Meal(17, 0, 5)]
    assert shift_to_feeder_clock(local, offset) == THREE_MEALS_UTC


def test_central_daylight_time() -> None:
    offset = offset_on(datetime(2027, 7, 1, 12, 0, tzinfo=CENTRAL))
    assert offset == timedelta(hours=-5)
    assert shift_to_feeder_clock([Meal(6, 10, 5)], offset) == [Meal(11, 10, 5)]


def test_wraps_past_midnight() -> None:
    # 7:58 PM CST is 01:58 UTC the next day.
    assert shift_to_feeder_clock([Meal(19, 58, 5)], timedelta(hours=-6)) == [
        Meal(1, 58, 5)
    ]


def test_positive_offset_with_half_hour() -> None:
    # India (UTC+5:30): 03:00 local is 21:30 UTC the previous day.
    assert shift_to_feeder_clock([Meal(3, 0, 2)], timedelta(hours=5, minutes=30)) == [
        Meal(21, 30, 2)
    ]


def test_zero_offset_keeps_times() -> None:
    meals = [Meal(6, 10, 5, days=0x01)]
    assert shift_to_feeder_clock(meals, timedelta(0)) == meals


def test_day_of_week_meals_cannot_be_shifted() -> None:
    with pytest.raises(ValueError, match="every-day"):
        shift_to_feeder_clock([Meal(6, 0, 1, days=0x01)], timedelta(hours=-6))


def test_rejects_partial_minute_offset() -> None:
    with pytest.raises(ValueError, match="whole number of minutes"):
        shift_to_feeder_clock([Meal(6, 0, 1)], timedelta(hours=-6, seconds=30))

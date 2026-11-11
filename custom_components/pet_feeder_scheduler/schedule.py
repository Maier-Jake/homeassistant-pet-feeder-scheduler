"""Build the schedule message for the Aqara Pet Feeder C1 (aqara.feeder.acn001).

This module is plain Python with no Home Assistant or zigpy imports, so it can
be unit-tested on its own and reused by ``scripts/encode_schedule.py``.

Wire format
-----------
The feeder takes all of its settings through one manufacturer-specific
attribute, 0xFFF1 on cluster 0xFCC0 (manufacturer code 0x115F), with
octet-string type (0x41). The value written to that attribute is:

    00 02 <seq> <code: 4 bytes, big-endian> <len> <payload: len bytes>

* ``seq`` is a 1-byte counter. The feeder accepted every value we tried.
* ``code`` is 0x080008C8 for "feeding schedule".
* ``payload`` is ASCII text: each meal as 10 hex digits, meals joined with
  commas, followed by one NUL byte. Each meal is the 5 bytes
  ``days, hour, minute, portions, 0`` written as hex, so "every day at 12:10,
  5 portions" is the text ``7f0c0a0500``.

The format comes from the open-source Zigbee2MQTT converters
(zigbee-herdsman-converters, MIT license). The byte strings in
``tests/test_schedule.py`` were written to real feeders and dispensed food.

Clock
-----
The feeder compares meal times against its own clock. On ZHA that clock ran on
UTC in our testing, not local time. ``shift_to_feeder_clock`` converts
wall-clock meal times by a fixed UTC offset. Using today's offset keeps meals
at the same absolute time all year, so the wall-clock time they happen at
moves by an hour when daylight saving time starts or ends.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

SCHEDULE_CODE = 0x080008C8
"""Feeder-internal code for the feeding-schedule setting."""

EVERY_DAY = 0x7F
"""Day bitmask for every day: bit 0 is Monday ... bit 6 is Sunday."""

MAX_MEALS = 4
"""Most meals allowed in one schedule. 4 is the most we have tested on hardware."""

MIN_PORTIONS = 1
MAX_PORTIONS = 10
"""Upper portion limit per meal. Matches the 1-10 range Zigbee2MQTT allows for
the feeder's manual serving size; we have tested up to 5 on hardware."""

MINUTES_PER_DAY = 24 * 60


@dataclass(frozen=True)
class Meal:
    """One scheduled meal."""

    hour: int
    minute: int
    portions: int
    days: int = EVERY_DAY

    def __post_init__(self) -> None:
        """Reject values the feeder could not store or would misread."""
        if not 0 <= self.hour <= 23:
            raise ValueError(f"hour must be 0-23, got {self.hour}")
        if not 0 <= self.minute <= 59:
            raise ValueError(f"minute must be 0-59, got {self.minute}")
        if not MIN_PORTIONS <= self.portions <= MAX_PORTIONS:
            raise ValueError(
                f"portions must be {MIN_PORTIONS}-{MAX_PORTIONS}, got {self.portions}"
            )
        if not 1 <= self.days <= EVERY_DAY:
            raise ValueError(f"days must be a bitmask from 1 to 0x7F, got {self.days}")

    def to_text(self) -> str:
        """Return the meal as the feeder's 10-hex-digit text, e.g. ``7f0c0a0500``."""
        return bytes([self.days, self.hour, self.minute, self.portions, 0]).hex()


def encode_payload(meals: list[Meal]) -> bytes:
    """Return the schedule payload: comma-joined meal text plus a NUL byte."""
    if not 1 <= len(meals) <= MAX_MEALS:
        raise ValueError(f"a schedule needs 1-{MAX_MEALS} meals, got {len(meals)}")
    times = [(meal.days, meal.hour, meal.minute) for meal in meals]
    if len(set(times)) != len(times):
        raise ValueError("two meals are scheduled for the same time")
    return ",".join(meal.to_text() for meal in meals).encode("ascii") + b"\x00"


def build_attribute_value(meals: list[Meal], sequence: int) -> bytes:
    """Return the full value to write to attribute 0xFFF1."""
    if not 0 <= sequence <= 0xFF:
        raise ValueError(f"sequence must be 0-255, got {sequence}")
    payload = encode_payload(meals)
    # MAX_MEALS keeps this far below 255; the check guards future changes.
    if len(payload) > 0xFF:
        raise ValueError("schedule payload is too long")
    header = (
        bytes([0x00, 0x02, sequence])
        + SCHEDULE_CODE.to_bytes(4, "big")
        + bytes([len(payload)])
    )
    return header + payload


def decode_attribute_value(value: bytes) -> list[Meal]:
    """Parse a schedule value; the inverse of ``build_attribute_value``.

    Used by the tests and for debugging. Raises ``ValueError`` on anything that
    isn't a schedule.
    """
    if len(value) < 8 or value[0:2] != b"\x00\x02":
        raise ValueError("not a feeder attribute value")
    if int.from_bytes(value[3:7], "big") != SCHEDULE_CODE:
        raise ValueError("not a schedule value")
    length = value[7]
    payload = value[8:]
    if len(payload) != length:
        raise ValueError(f"length byte says {length}, payload has {len(payload)}")
    text = payload.rstrip(b"\x00").decode("ascii")
    meals = []
    for item in text.split(","):
        raw = bytes.fromhex(item)
        if len(raw) != 5:
            raise ValueError(f"meal entry {item!r} is not 5 bytes")
        meals.append(Meal(hour=raw[1], minute=raw[2], portions=raw[3], days=raw[0]))
    return meals


def shift_to_feeder_clock(meals: list[Meal], utc_offset: timedelta) -> list[Meal]:
    """Convert wall-clock meal times to UTC by subtracting ``utc_offset``.

    ``utc_offset`` is the local offset from UTC, e.g. -6 hours for US Central
    Standard Time, so 06:10 local becomes 12:10 UTC.

    Only every-day meals can be shifted. A shift can move a meal across
    midnight, which would put a day-of-week meal on the wrong day.
    """
    offset_minutes, remainder = divmod(utc_offset, timedelta(minutes=1))
    if remainder:
        raise ValueError("UTC offset must be a whole number of minutes")
    shifted = []
    for meal in meals:
        if meal.days != EVERY_DAY and offset_minutes:
            raise ValueError("only every-day meals can be converted to UTC")
        total = (meal.hour * 60 + meal.minute - offset_minutes) % MINUTES_PER_DAY
        shifted.append(
            Meal(
                hour=total // 60,
                minute=total % 60,
                portions=meal.portions,
                days=meal.days,
            )
        )
    return shifted

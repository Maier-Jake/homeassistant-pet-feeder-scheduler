#!/usr/bin/env python3
"""Print the attr_val list for writing a feeder schedule with ZHA Toolkit.

For the manual method in docs/manual-method.md. Needs only Python 3.10 or newer, not
Home Assistant. Times are given exactly as the feeder should store them; on ZHA
that means UTC (see the docs).

Example, every day at 12:10, 18:00 and 23:00 UTC with 5 portions each:

    python3 scripts/encode_schedule.py 12:10x5 18:00x5 23:00x5
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

SCHEDULE_PY = (
    Path(__file__).resolve().parent.parent
    / "custom_components"
    / "pet_feeder_scheduler"
    / "schedule.py"
)


def load_schedule_module():
    """Load schedule.py directly so the integration's __init__ (and HA) isn't needed."""
    spec = importlib.util.spec_from_file_location("feeder_schedule", SCHEDULE_PY)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses needs the module registered
    spec.loader.exec_module(module)
    return module


def parse_meal(text: str, meal_class):
    """Parse ``HH:MMxN``, e.g. ``12:10x5``."""
    try:
        clock, portions = text.lower().split("x")
        hour, minute = clock.split(":")
        return meal_class(hour=int(hour), minute=int(minute), portions=int(portions))
    except ValueError as err:
        raise argparse.ArgumentTypeError(f"{text!r}: {err}") from err


def main() -> int:
    schedule = load_schedule_module()
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "meals", nargs="+", help="meals as HH:MMxPORTIONS in the feeder's clock"
    )
    parser.add_argument(
        "--sequence",
        type=int,
        default=1,
        help="message sequence number, 0-255 (default 1)",
    )
    args = parser.parse_args()

    try:
        meals = [parse_meal(text, schedule.Meal) for text in args.meals]
        value = schedule.build_attribute_value(meals, args.sequence)
    except (ValueError, argparse.ArgumentTypeError) as err:
        parser.error(str(err))

    print(list(value))
    return 0


if __name__ == "__main__":
    sys.exit(main())

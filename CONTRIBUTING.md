# Contributing and review

## How changes get in

All changes go through a pull request, including the owner's and the AI
assistant's. Nothing is pushed straight to `main`. A pull request is merged
only after a human has read every changed line and the checks pass.

Much of this code is written by an AI assistant. Review it as you would code
from a new contributor you haven't worked with before: check claims against
sources, and don't assume a comment is true because it sounds confident.

## Review checklist

- **Does it match the hardware facts?** The byte format and the UTC clock are
  documented in [docs/how-it-works.md](docs/how-it-works.md), along with what
  was tested and what is still open. New claims about the feeder need a
  hardware test or a source.
- **Could it feed a pet wrong?** For example: a wrong time conversion, a
  portion count off by one, or a schedule silently not written. These matter
  most.
- **Is anything copied?** No code may be copied from other projects unless its
  license allows it under MIT and it's credited. In particular, nothing from
  ZHA Toolkit (GPL-3.0).
- **Are the tests honest?** Tests that hand-copy the code's own output prove
  nothing. Expected bytes should come from hardware or from an independent
  source.
- **No personal data.** No real device IEEE addresses, device IDs, names or
  locations.

## Layout

| Path | What it is | Needs Home Assistant? |
| --- | --- | --- |
| `custom_components/pet_feeder_scheduler/schedule.py` | Builds the schedule bytes; converts times to UTC | No |
| `custom_components/pet_feeder_scheduler/zigbee.py` | Writes to the feeder's cluster, with retries | No (zigpy only) |
| `custom_components/pet_feeder_scheduler/__init__.py` | The action: input checks, finding feeders through ZHA | Yes |
| `custom_components/pet_feeder_scheduler/config_flow.py` | The empty setup screen | Yes |
| `tests/test_*.py` | Tests for the two modules above that don't need Home Assistant | No |
| `tests/ha/` | Tests inside a test Home Assistant | Yes |
| `scripts/encode_schedule.py` | Prints bytes for the manual ZHA Toolkit method | No |

## Running the checks

Quick tests (no Home Assistant):

```sh
pip install pytest pytest-asyncio zigpy ruff
pytest
ruff check . && ruff format --check .
```

Everything, including the tests inside Home Assistant (Python 3.13):

```sh
pip install -r requirements-test-ha.txt
pytest
```

GitHub Actions runs both, plus Home Assistant's `hassfest` manifest check and
the HACS check, on every pull request.

## Testing on a real feeder

If you change anything about what's sent to the feeder:

1. Install the branch on a test Home Assistant (HACS can install a branch).
2. Write a schedule with one 1-portion meal 3 minutes ahead.
3. Confirm food comes out and *Last feeding source* shows **Schedule**.
4. Put the results in the pull request: Home Assistant version, feeder
   firmware if known, and what you saw.

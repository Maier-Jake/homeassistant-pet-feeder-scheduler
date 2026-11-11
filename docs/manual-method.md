# Manual method: writing the schedule with ZHA Toolkit

This is how the schedule was first written to two feeders by hand. It is a
working alternative to installing the integration, and it is how the byte
format was tested on real hardware.

You will:

1. Install ZHA Toolkit.
2. Work out the meal times in UTC.
3. Turn the meals into bytes.
4. Write the bytes to the feeder.
5. Switch the feeder to Schedule mode.
6. Test it.

## 1. Install ZHA Toolkit

[ZHA Toolkit](https://github.com/mdeweerd/zha-toolkit) adds low-level Zigbee
actions to Home Assistant. ZHA's own `zha.set_zigbee_cluster_attribute` action
can't do this job: it can't send the octet-string value the feeder needs.

1. Install **ZHA Toolkit** from HACS.
2. Add this line to `configuration.yaml`:

   ```yaml
   zha_toolkit:
   ```

3. Restart Home Assistant. Actions starting with `zha_toolkit.` should now be
   listed under **Tools → Actions**.

## 2. Work out the meal times in UTC

On ZHA the feeder runs on UTC, not your local time (see
[how-it-works.md](how-it-works.md#the-feeders-clock-is-utc)). Convert each meal
from your clock to UTC using **today's** offset.

Example, US Central Standard Time (UTC−6):

| Meal | Local | UTC |
| --- | --- | --- |
| Breakfast | 6:10 AM | 12:10 |
| Lunch | 12:00 PM | 18:00 |
| Dinner | 5:00 PM | 23:00 |

Because the feeder ignores daylight saving time, these meals happen at the same
moment all year. Under Central Daylight Time your clock shows them at
7:10 AM, 1:00 PM and 6:00 PM.

## 3. Turn the meals into bytes

Run the script from this repository. It needs Python 3.10 or newer, and
nothing else:

```sh
python3 scripts/encode_schedule.py 12:10x5 18:00x5 23:00x5
```

`12:10x5` means "12:10 UTC, 5 portions". The script prints a list of numbers.
That list is the value you'll send in the next step:

```
[0, 2, 1, 8, 0, 8, 200, 33, 55, 102, 48, 99, ...]
```

[how-it-works.md](how-it-works.md#message-format) explains what the numbers
mean, if you'd rather build them by hand.

## 4. Write the bytes to the feeder

Find the feeder's IEEE address: open the feeder's device page, then
**Zigbee info**. It looks like `54:ef:44:10:00:xx:xx:xx`.

In **Tools → Actions**, switch to YAML mode and run:

```yaml
action: zha_toolkit.attr_write
data:
  ieee: "54:ef:44:10:00:xx:xx:xx" # your feeder
  endpoint: 1
  cluster: 64704 # 0xFCC0, Aqara's cluster
  attribute: 65521 # 0xFFF1, the feeder's settings attribute
  attr_type: 65 # 0x41, octet string
  manf: 4447 # 0x115F, Aqara's manufacturer code
  attr_val: [0, 2, 1, 8, 0, 8, 200, 33, ...] # the full list from step 3
  read_before_write: false
  read_after_write: false
  tries: 3
  fail_exception: true
```

Leave `read_before_write` and `read_after_write` at `false`. That's how the
write was tested; reading this attribute isn't needed and hasn't been tried.

## 5. Switch the feeder to Schedule mode

Set the feeder's **Mode** entity (a select created by ZHA) to **Schedule**. In
**Manual** mode the feeder ignores its schedule.

## 6. Test it

Before trusting the real schedule, do a test run:

1. Repeat steps 3–4 with one extra meal of 1 portion, 3 minutes from now in
   UTC.
2. When it's due, look in the bowl. The feeder's **Last feeding source**
   entity should change to **Schedule**.
3. If the source says **Schedule** but no food came out, the feeder isn't
   primed. A freshly filled C1 can dispense empty for the first portion or
   two. Press the front button until food comes out, then test again.
4. Write the real schedule again without the test meal.

If the test meal fires an hour or more off, your feeder may not be on UTC.
Note the time difference and adjust. Please open an issue if this happens, so
the docs can be corrected.

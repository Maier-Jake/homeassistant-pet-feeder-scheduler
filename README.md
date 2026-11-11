# Pet Feeder Scheduler for Home Assistant

Write a feeding schedule into the memory of an **Aqara Pet Feeder C1** that is
paired with Home Assistant's built-in **ZHA** Zigbee integration. The feeder
then keeps serving meals on its own, even when Home Assistant, your Wi-Fi or
your internet is down.

ZHA already gives you a Feed button, a mode switch and dispense counters for
this feeder, but no way to set its built-in schedule. Without this, your only
options are the Aqara app (which needs an Aqara hub instead of ZHA) or Home
Assistant automations (which stop when Home Assistant stops). This integration
adds one action, **Set feeder schedule**, that fills that gap.

> [!WARNING]
> **Status: under review.** This is a first version. Its byte format and the
> manual method behind it were tested on real feeders, but the integration
> itself has so far only run in automated tests. See
> [What has been tested](#what-has-been-tested).

## AI-written code

The code and documentation in this repository were written by an AI assistant
(Claude, by Anthropic) working with the repository owner. Humans review every
change in a pull request before it is merged. See
[CONTRIBUTING.md](CONTRIBUTING.md) for how review works.

## Not affiliated with Aqara

This is an independent community project. It is not affiliated with, endorsed
by, or supported by Aqara or Lumi United Technology. "Aqara" is only used to
say which device this works with.

## Safety

Your pets depend on this working. After setting or changing a schedule, watch
the first meal or two come out, keep the feeder's backup batteries in, and
don't treat any automatic feeder as a replacement for checking on your
animals. The software comes with no warranty (see [LICENSE](LICENSE)).

---

## Requirements

- Home Assistant 2026.2 or newer, using the built-in **ZHA** integration.
  Zigbee2MQTT users don't need this; Zigbee2MQTT already has a schedule
  setting for this feeder.
- An Aqara Pet Feeder C1 (model `aqara.feeder.acn001`) paired to ZHA. If ZHA
  shows entities such as *Portions dispensed today* and *Mode* for the feeder,
  its device quirk is loaded and you're set.

## Install

Through [HACS](https://hacs.xyz/) as a custom repository:

1. In HACS, open the **⋮** menu, choose **Custom repositories**, and add
   `https://github.com/Maier-Jake/homeassistant-pet-feeder-scheduler` with
   type **Integration**.
2. Find **Pet Feeder Scheduler** in HACS, download it, and restart Home
   Assistant.
3. Go to **Settings → Devices & services → Add integration** and add
   **Pet Feeder Scheduler**. There is nothing to configure.

Manual install: copy `custom_components/pet_feeder_scheduler` into your
`config/custom_components/` folder, restart, and do step 3.

## Set a schedule

Open **Tools → Actions** (**Developer tools → Actions** before Home Assistant
2026.8), pick **Pet Feeder Scheduler: Set feeder schedule**, choose your
feeders, and fill in up to four meals. You can also call it from a script or
automation:

```yaml
action: pet_feeder_scheduler.set_schedule
data:
  device_id:
    - <your feeder's device id>
  meal_1_time: "06:10:00"
  meal_1_portions: 5
  meal_2_time: "12:00:00"
  meal_2_portions: 5
  meal_3_time: "17:00:00"
  meal_3_portions: 5
```

Each call **replaces** the feeder's whole schedule. Every meal runs every day.
By default the action also switches the feeder to **Schedule** mode, because
in **Manual** mode it ignores its schedule.

To see exactly what was written, run the action with **Return response**
turned on (`response_variable` in a script). It lists the meals as you entered
them, the meals as stored on the feeder, and the raw bytes.

### Meal times and daylight saving time

Enter meal times as your clock reads **today**. On ZHA the feeder keeps time
in **UTC**, so the action converts your times using today's offset from UTC.
The feeder then serves each meal at the same moment every day of the year:

- Your pets' routine never jumps an hour.
- Your clock's reading of meal times does move by an hour when daylight saving
  time starts or ends. Set 6:10 AM in winter, and it shows as 7:10 AM in
  summer.

If you want meals to follow your clock instead, run the action again after
each change, entering the times you want.

Choose **Feeder clock: Local** only if a test (below) shows your feeder
running on local time. Then times are written exactly as entered.

### Check that it works

The feeder can't tell whether food actually came out. Its counters only count
how often the motor turned. So test with your eyes:

1. Set a short schedule with one meal of 1 portion a few minutes from now.
2. When it's due, check that food came out and that the feeder's
   *Last feeding source* entity in Home Assistant shows **Schedule**.
3. If the source says Schedule but nothing came out, the feeder probably isn't
   primed yet. A newly filled C1 can dispense empty for the first portion or
   two. Press the button on the front a few times until food comes out, then
   test again.
4. Set your real schedule.

## Limits

- **ZHA only.** It finds the feeder through ZHA's internal device lookup.
- **Up to 4 meals**, the most tested on hardware.
- **1–10 portions** per meal. Up to 5 has been tested on hardware.
- **Every day only.** The feeder can store day-of-week meals, but converting
  them to UTC can move a meal to a different day, so this version doesn't
  offer them.
- **Can't read back** the schedule stored on the feeder. The action's response
  shows what was sent.
- The feeder's *Portions dispensed today* counter seems to restart at
  **midnight UTC**, not local midnight.

## Missed-meal alerts

Because the schedule runs on the feeder, Home Assistant doesn't know a meal is
due. [docs/automations.md](docs/automations.md) has an example automation that
alerts you if a feeder didn't dispense at meal time, or reports a problem.

## Without this integration

The integration automates the steps we first did by hand with
[ZHA Toolkit](https://github.com/mdeweerd/zha-toolkit).
[docs/manual-method.md](docs/manual-method.md) walks through that method. It
also works if you'd rather not install this integration.

## What has been tested

| What | How |
| --- | --- |
| Schedule byte format, UTC clock, Schedule mode, food dispensing | Two real feeders on Home Assistant 2026.11 with ZHA, written by hand with ZHA Toolkit (the [manual method](docs/manual-method.md)). |
| The encoder produces those exact bytes | Unit tests in `tests/test_schedule.py`, using the bytes from the hardware tests. |
| The integration's action, validation and errors | Tests in `tests/ha/` inside a test Home Assistant 2026.2.3, with ZHA's device lookup replaced by a fake feeder. |
| ZHA's quirk sends the same Zigbee frames as ZHA Toolkit did | `tests/ha/test_quirk.py`, with zha-quirks 0.0.157 and also checked by hand with zha-quirks 2.4.1. |
| **The integration on a real Home Assistant with real feeders** | **Not yet.** |

## How it works

[docs/how-it-works.md](docs/how-it-works.md) explains the feeder's message
format, how we learned the feeder runs on UTC, and the open questions.

## Credits

- The schedule message format comes from
  [Zigbee2MQTT's converters](https://github.com/Koenkk/zigbee-herdsman-converters)
  (MIT license). No code was copied; this is a separate Python implementation.
- The integration writes through the feeder quirk in
  [ZHA's device handlers](https://github.com/zigpy/zha-device-handlers)
  (Apache-2.0), which ships with Home Assistant.
- [ZHA Toolkit](https://github.com/mdeweerd/zha-toolkit) (GPL-3.0) was used to
  test the format on hardware. This project does not include or call it.

## License

[MIT](LICENSE)

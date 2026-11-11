# How it works

## Message format

The Aqara Pet Feeder C1 (`aqara.feeder.acn001`) takes almost all of its
settings through **one** Zigbee attribute:

| | |
| --- | --- |
| Cluster | `0xFCC0` (Aqara's manufacturer-specific cluster), endpoint 1 |
| Attribute | `0xFFF1` |
| Type | `0x41`, octet string (the value is sent with a 1-byte length prefix) |
| Manufacturer code | `0x115F` |

The value written to that attribute has an 8-byte header, then the setting:

```
00 02 <seq> <code: 4 bytes> <len> <payload: len bytes>
```

- `00 02` is constant.
- `seq` is a 1-byte counter. The feeder accepted every value we sent.
- `code` says which setting this is. Schedule is `08 00 08 C8`. Mode is
  `04 18 00 55`, with payload `00` for manual or `01` for schedule.
- `len` is the payload length.

For the schedule, the payload is **text**. Each meal is 5 bytes, written as 10
hex digits:

| Byte | Meaning | Example |
| --- | --- | --- |
| 1 | Days, as a bitmask. Bit 0 is Monday ... bit 6 is Sunday; `7f` = every day | `7f` |
| 2 | Hour, 0–23, in the feeder's clock | `0c` = 12 |
| 3 | Minute | `0a` = 10 |
| 4 | Portions | `05` |
| 5 | Always 0 | `00` |

Meals are joined with commas, and the text ends with a NUL byte. "Every day at
12:10, 18:00 and 23:00, 5 portions each" becomes:

```
7f0c0a0500,7f12000500,7f17000500\0
```

That text is 33 bytes long, so the full value with sequence number 49 is:

```
00 02 31 08 00 08 c8 21 37 66 30 63 30 61 30 35 30 30 2c ... 30 30 00
```

This format comes from Zigbee2MQTT's open-source converters
(`zigbee-herdsman-converters`, file `src/lib/lumi.ts`, MIT license). The bytes
above were written to two real feeders, and the feeders served those meals.

### How the integration sends it

ZHA loads a *quirk* for this feeder: code from
[zha-device-handlers](https://github.com/zigpy/zha-device-handlers) that
describes the feeder's non-standard cluster. The quirk names attribute `0xFFF1`
`feeder_attr` and passes values written to it straight through. It also offers
a `feeding_mode` attribute that it turns into the mode message above. That's
the same path the **Mode** select entity in Home Assistant uses.

The integration:

1. Builds the schedule value (`schedule.py`).
2. Finds the feeder's cluster through ZHA (`__init__.py`).
3. Writes `feeder_attr`, then `feeding_mode = 1` (`zigbee.py`).

`tests/ha/test_quirk.py` checks that the quirk turns those writes into the same
Zigbee frames ZHA Toolkit sent during the hardware tests.

## The feeder's clock is UTC

The feeder compares meal times against its own clock, which it sets from
Zigbee. On ZHA that clock ran on **UTC**, not local time. Here is how that was
found, on 2026-11-10, in US Central Standard Time (UTC−6):

1. A meal set for 18:38 (the local time) didn't fire at 6:38 PM.
2. A test schedule with two meals was written: one at 18:46, one at 00:47.
3. The 00:47 meal fired at **6:47 PM local**, which is 00:47 UTC.
4. A second feeder, paired separately, fired a 01:50 meal at 7:50 PM local,
   and a 01:58 meal at 7:58 PM local. So it runs on UTC too.

A likely explanation: the feeder sets its clock from the standard Zigbee Time
cluster, which ZHA's coordinator serves. That cluster carries both UTC and
local time, and the feeder seems to use the UTC value.

What this means:

- **Meals happen at the same absolute time all year.** Daylight saving time
  doesn't move them; your clock's reading of them moves by an hour instead.
  For pets that's usually what you want.
- **Entered times have to be converted.** The integration subtracts today's UTC
  offset. Day-of-week meals aren't offered, because the conversion can push a
  meal across midnight onto another day.
- **The daily counter resets at midnight UTC.** *Portions dispensed today*
  seemed to restart at 6 PM Central Standard Time.

Other feeder firmware, or another Zigbee stack, might behave differently.
That's why the integration has a **Feeder clock: Local** option, and why the
docs ask you to test with one meal first.

## What happens when Home Assistant is down

The schedule lives in the feeder, so it keeps running. Not yet tested: what the
feeder does if it loses power with no backup batteries while Home Assistant is
also down. It may not know the time until it can ask the coordinator again.
Keep batteries in it.

## Open questions

- **How many meals can the feeder hold?** 4 works. More has not been tried.
- **Largest portion count per meal?** 5 works. The integration allows up to 10,
  the same range Zigbee2MQTT allows for the feeder's manual serving size.
- **Can the schedule be read back?** The feeder seems to report its schedule:
  Zigbee2MQTT decodes such a report, and ZHA's quirk has a placeholder that
  logs and ignores it. A future version could decode it
  (`schedule.decode_attribute_value` already parses the format).
- **Does the integration need ZHA internals?** Yes:
  `homeassistant.components.zha.helpers.async_get_zha_device_proxy` isn't a
  documented public API, and could change in a future Home Assistant release.
  The best long-term home for this feature is the ZHA quirk itself, so it
  would work without a custom integration.

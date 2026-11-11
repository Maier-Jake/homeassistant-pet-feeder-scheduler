"""Check the real ZHA quirk turns our writes into the expected Zigbee frames.

``zigbee.py`` writes through the cluster class from ZHA's device quirk. Here
that real class is created with a fake endpoint, and the outgoing frames are
compared with what ZHA Toolkit sent when the schedule was proven on hardware:
a manufacturer-specific (0x115F) Write Attributes for 0xFFF1, type 0x41.
"""

from __future__ import annotations

import importlib
from unittest.mock import AsyncMock, MagicMock

import pytest
from zigpy.zcl import foundation

from custom_components.pet_feeder_scheduler.schedule import Meal
from custom_components.pet_feeder_scheduler.zigbee import write_schedule


def load_quirk():
    """Return the feeder quirk module; its file was renamed in later zha-quirks."""
    for name in (
        "zhaquirks.xiaomi.aqara.feeder",
        "zhaquirks.xiaomi.aqara.feeder_acn001",
    ):
        try:
            return importlib.import_module(name)
        except ModuleNotFoundError:
            continue
    pytest.skip("zha-quirks feeder quirk not installed")


SUCCESS = [[foundation.WriteAttributesStatusRecord(status=foundation.Status.SUCCESS)]]

# ZCL header for a manufacturer-specific frame: frame control 0x04, then the
# manufacturer code 0x115F little-endian. A 1-byte transaction number follows.
MANUFACTURER_HEADER = b"\x04\x5f\x11"
WRITE_ATTRIBUTES = b"\x02"
ATTRIBUTE_0XFFF1_OCTET_STRING = b"\xf1\xff\x41"


async def test_frames_match_zha_toolkit_write() -> None:
    quirk = load_quirk()
    endpoint = MagicMock()
    endpoint.device.manufacturer = "LUMI"
    endpoint.request = AsyncMock(return_value=SUCCESS)
    cluster = quirk.OppleCluster(endpoint)

    meals = [Meal(12, 10, 5), Meal(18, 0, 5), Meal(23, 0, 5)]
    value = await write_schedule(cluster, meals, 49, set_schedule_mode=True)

    schedule_frame, mode_frame = (
        call.kwargs["data"] for call in endpoint.request.call_args_list
    )

    # Schedule: our bytes go out unchanged, with a length prefix (octet string).
    assert schedule_frame[:3] == MANUFACTURER_HEADER
    assert schedule_frame[4:] == (
        WRITE_ATTRIBUTES + ATTRIBUTE_0XFFF1_OCTET_STRING + bytes([len(value)]) + value
    )

    # Mode: the quirk builds 00 02 <seq> 04180055 01 01, i.e. mode = 1 (schedule).
    assert mode_frame[:3] == MANUFACTURER_HEADER
    assert mode_frame[4:8] == WRITE_ATTRIBUTES + ATTRIBUTE_0XFFF1_OCTET_STRING
    assert mode_frame[-6:] == bytes.fromhex("041800550101")

"""Tests for zigbee.py, using a fake cluster in place of a real feeder."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from zigpy.zcl import foundation

from pet_feeder_scheduler.schedule import Meal
from pet_feeder_scheduler.zigbee import (
    AQARA_CLUSTER_ID,
    FEEDER_MODEL,
    WRITE_ATTEMPTS,
    FeederWriteError,
    find_feeder_cluster,
    write_schedule,
)

SUCCESS = foundation.WriteAttributesStatusRecord(
    status=foundation.Status.SUCCESS, attrid=0xFFF1
)
FAILURE = foundation.WriteAttributesStatusRecord(
    status=foundation.Status.FAILURE, attrid=0xFFF1
)


class FakeCluster:
    """Records writes and plays back scripted results or exceptions."""

    def __init__(self, *outcomes: Any) -> None:
        self.outcomes = list(outcomes)
        self.writes: list[dict[str, Any]] = []

    async def write_attributes(self, attributes: dict[str, Any], **kwargs: Any) -> Any:
        self.writes.append(attributes)
        outcome = self.outcomes.pop(0) if self.outcomes else [[SUCCESS]]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


MEALS = [Meal(12, 10, 5)]


async def test_writes_schedule_then_mode() -> None:
    cluster = FakeCluster()
    value = await write_schedule(cluster, MEALS, 7, set_schedule_mode=True)
    assert cluster.writes == [{"feeder_attr": value}, {"feeding_mode": 1}]
    assert value[:3] == bytes([0x00, 0x02, 7])


async def test_can_skip_mode() -> None:
    cluster = FakeCluster()
    await write_schedule(cluster, MEALS, 7, set_schedule_mode=False)
    assert len(cluster.writes) == 1


async def test_retries_after_exception() -> None:
    cluster = FakeCluster(TimeoutError("no ack"), [[SUCCESS]])
    await write_schedule(cluster, MEALS, 1, set_schedule_mode=False)
    assert len(cluster.writes) == 2


async def test_retries_after_failure_status() -> None:
    cluster = FakeCluster([[FAILURE]], [[SUCCESS]])
    await write_schedule(cluster, MEALS, 1, set_schedule_mode=False)
    assert len(cluster.writes) == 2


async def test_gives_up_after_all_attempts() -> None:
    cluster = FakeCluster(*([[FAILURE]] * WRITE_ATTEMPTS))
    with pytest.raises(FeederWriteError, match="FAILURE"):
        await write_schedule(cluster, MEALS, 1, set_schedule_mode=False)
    assert len(cluster.writes) == WRITE_ATTEMPTS


async def test_mode_failure_is_reported() -> None:
    cluster = FakeCluster([[SUCCESS]], *([[FAILURE]] * WRITE_ATTEMPTS))
    with pytest.raises(FeederWriteError, match="feeding_mode"):
        await write_schedule(cluster, MEALS, 1, set_schedule_mode=True)


async def test_accepts_flat_result_list() -> None:
    cluster = FakeCluster([SUCCESS])
    await write_schedule(cluster, MEALS, 1, set_schedule_mode=False)
    assert len(cluster.writes) == 1


def make_device(model: str, clusters: dict[int, Any]) -> SimpleNamespace:
    return SimpleNamespace(
        model=model, endpoints={1: SimpleNamespace(in_clusters=clusters)}
    )


def test_finds_cluster() -> None:
    cluster = FakeCluster()
    device = make_device(FEEDER_MODEL, {AQARA_CLUSTER_ID: cluster})
    assert find_feeder_cluster(device) is cluster


def test_rejects_other_models() -> None:
    device = make_device("lumi.sensor_magnet", {AQARA_CLUSTER_ID: FakeCluster()})
    with pytest.raises(FeederWriteError, match="expected"):
        find_feeder_cluster(device)


def test_reports_missing_cluster() -> None:
    with pytest.raises(FeederWriteError, match="quirk"):
        find_feeder_cluster(make_device(FEEDER_MODEL, {}))

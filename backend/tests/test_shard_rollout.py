"""Unit tests for production shard rollout."""

from datetime import UTC, datetime, timedelta

import pytest

from automunki.models.munki import ShardRolloutStatus
from automunki.services.shard_rollout import (
    compute_shard_percent,
    derive_deployment_status,
    installable_condition_for_percent,
    parse_shard_percent_from_condition,
)


def test_compute_shard_percent_day_one_four_day_rollout():
    started = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    now = datetime(2026, 6, 1, 18, 0, tzinfo=UTC)
    assert compute_shard_percent(started, 4, now=now) == 25


def test_compute_shard_percent_day_four_reaches_100():
    started = datetime(2026, 6, 1, tzinfo=UTC)
    now = datetime(2026, 6, 4, tzinfo=UTC)
    assert compute_shard_percent(started, 4, now=now) == 100


def test_compute_shard_percent_day_five_capped_at_100():
    started = datetime(2026, 6, 1, tzinfo=UTC)
    now = datetime(2026, 6, 10, tzinfo=UTC)
    assert compute_shard_percent(started, 4, now=now) == 100


def test_compute_shard_percent_with_channel_multiplier():
    started = datetime(2026, 6, 1, tzinfo=UTC)
    now = datetime(2026, 6, 2, tzinfo=UTC)
    assert compute_shard_percent(started, 4, channel_multiplier=2.5, now=now) == 20


def test_installable_condition_for_percent():
    assert installable_condition_for_percent(75) == "shard <= 75"
    assert installable_condition_for_percent(100) is None


def test_parse_shard_percent_from_condition():
    assert parse_shard_percent_from_condition("shard <= 75") == 75
    assert parse_shard_percent_from_condition("  SHARD <= 50  ") == 50
    assert parse_shard_percent_from_condition("other") is None
    assert parse_shard_percent_from_condition(None) is None


@pytest.mark.parametrize(
    ("in_production", "status", "percent", "expected"),
    [
        (False, ShardRolloutStatus.none, None, "not_in_production"),
        (True, ShardRolloutStatus.pending_approval, None, "pending_rollout"),
        (True, ShardRolloutStatus.active, 50, "sharding"),
        (True, ShardRolloutStatus.active, 100, "fully_deployed"),
        (True, ShardRolloutStatus.complete, 100, "fully_deployed"),
        (True, ShardRolloutStatus.paused, 75, "paused"),
    ],
)
def test_derive_deployment_status(in_production, status, percent, expected):
    assert (
        derive_deployment_status(
            in_production=in_production,
            shard_rollout_status=status,
            shard_percent=percent,
        )
        == expected
    )


def test_compute_shard_percent_zero_rollout_days():
    started = datetime(2026, 6, 1, tzinfo=UTC)
    now = started + timedelta(days=1)
    assert compute_shard_percent(started, 0, now=now) == 100

from datetime import UTC, date, datetime

from automunki.api.routes.pkginfo import (
    UNKNOWN_INSTALL_VERSION,
    _build_install_timeline_by_version,
    _filled_daily_counts,
)

FIXED_END = date(2024, 6, 3)


def test_filled_daily_counts_includes_zero_days():
    rows = [
        (datetime(2024, 6, 1, 12, tzinfo=UTC), 3),
        (datetime(2024, 6, 3, 12, tzinfo=UTC), 1),
    ]
    series = _filled_daily_counts(rows, days=3, end=FIXED_END)
    assert len(series) == 3
    assert series[0]["date"] == "2024-06-01"
    assert series[0]["count"] == 3
    assert series[1]["date"] == "2024-06-02"
    assert series[1]["count"] == 0
    assert series[2]["count"] == 1


def test_build_install_timeline_by_version_groups_and_sorts():
    rows = [
        (datetime(2024, 6, 1, tzinfo=UTC), "1.0.0", 2),
        (datetime(2024, 6, 1, tzinfo=UTC), "2.0.0", 5),
        (datetime(2024, 6, 2, tzinfo=UTC), None, 1),
    ]
    versions, timeline = _build_install_timeline_by_version(rows, days=3, end=FIXED_END)
    assert versions == ["2.0.0", "1.0.0", UNKNOWN_INSTALL_VERSION]
    assert timeline["2.0.0"][0]["count"] == 5
    assert timeline["1.0.0"][0]["count"] == 2
    assert timeline[UNKNOWN_INSTALL_VERSION][1]["count"] == 1


def test_build_install_timeline_by_version_fills_missing_days():
    rows = [(date(2024, 6, 2), "1.0.0", 4)]
    _, timeline = _build_install_timeline_by_version(rows, days=2, end=FIXED_END)
    assert len(timeline["1.0.0"]) == 2
    assert timeline["1.0.0"][0]["date"] == "2024-06-02"
    assert timeline["1.0.0"][0]["count"] == 4
    assert timeline["1.0.0"][1]["count"] == 0

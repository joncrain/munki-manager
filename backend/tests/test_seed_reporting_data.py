import random
from datetime import UTC, datetime, timedelta

from automunki.services.seed_reporting_data import (
    SoftwareVersion,
    _chronological_install_reports,
    _random_apple_serial,
    _version_sort_key,
)


def test_random_apple_serial_format():
    rng = random.Random(42)
    serials = {_random_apple_serial(rng) for _ in range(200)}
    assert len(serials) == 200
    for serial in serials:
        assert 10 <= len(serial) <= 12
        assert serial.isalnum()
        assert serial.upper() == serial


def test_version_sort_key_orders_chrome_builds():
    versions = ["148.0.7778.97", "149.0.7827.54", "149.0.7827.156"]
    assert sorted(versions, key=_version_sort_key) == versions


def test_chronological_install_reports_never_install_newer_before_older():
    rng = random.Random(7)
    machine_id = __import__("uuid").uuid4()
    chrome_path = "/Applications/Google Chrome.app"
    chain = [
        SoftwareVersion("GoogleChrome", "148.0.7778.97", "Google Chrome", "com.google.Chrome", chrome_path),
        SoftwareVersion("GoogleChrome", "149.0.7827.54", "Google Chrome", "com.google.Chrome", chrome_path),
        SoftwareVersion("GoogleChrome", "149.0.7827.156", "Google Chrome", "com.google.Chrome", chrome_path),
    ]
    start = datetime(2025, 1, 1, tzinfo=UTC)
    end = datetime(2026, 1, 1, tzinfo=UTC)
    reports = _chronological_install_reports(
        rng,
        machine_id,
        [chain],
        window_start=start,
        window_end=end,
    )
    installed = [r for r in reports if r.status == "installed"]
    assert len(installed) == 3
    assert [r.item_version for r in installed] == ["148.0.7778.97", "149.0.7827.54", "149.0.7827.156"]
    dates = [r.install_date for r in installed]
    assert all(d is not None for d in dates)
    assert dates == sorted(dates)
    assert dates[0] >= start
    assert dates[-1] <= end + timedelta(days=1)

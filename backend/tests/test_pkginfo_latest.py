from automunki.services.pkginfo_latest import (
    compute_latest_version_by_name,
    is_latest_version,
)


def test_compute_latest_version_by_name():
    rows = [
        ("Arc", "1.80.0"),
        ("Arc", "1.85.0"),
        ("Arc", "1.90.0"),
        ("Firefox", "128.0"),
        ("Firefox", "127.0.2"),
    ]
    latest = compute_latest_version_by_name(rows)
    assert latest == {"Arc": "1.90.0", "Firefox": "128.0"}
    assert is_latest_version("Arc", "1.90.0", latest)
    assert not is_latest_version("Arc", "1.85.0", latest)


def test_compute_latest_version_handles_patch_levels():
    rows = [("App", "8.9.10"), ("App", "8.11.1"), ("App", "8.9.1")]
    latest = compute_latest_version_by_name(rows)
    assert latest["App"] == "8.11.1"

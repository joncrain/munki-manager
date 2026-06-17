from automunki.services.loose_version import (
    LooseVersion,
    compare_loose_versions,
    loose_version_key,
    parse_loose_version,
)


def test_parse_numeric_segments():
    assert parse_loose_version("8.11.1") == [8, 11, 1]
    assert parse_loose_version("8.9.1") == [8, 9, 1]


def test_compare_patch_levels():
    assert compare_loose_versions("8.9.1", "8.11.1") < 0
    assert compare_loose_versions("8.11.1", "8.9.1") > 0


def test_sort_mixed_versions():
    versions = ["8.11.1", "8.9.1", "10.0", "9.0.1", "8.9.10"]
    assert sorted(versions, key=loose_version_key) == [
        "8.9.1",
        "8.9.10",
        "8.11.1",
        "9.0.1",
        "10.0",
    ]


def test_loose_version_class_matches_cmp():
    assert LooseVersion("1.2.3") < LooseVersion("1.10.0")
    assert LooseVersion("1.10.0") == LooseVersion("1.10.0")

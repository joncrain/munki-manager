"""Pkginfo audit helpers."""

from automunki.services.pkginfo_audit import (
    audit_values_equal,
    build_audit_field_changes,
    snapshot_copy,
)


def test_build_audit_field_changes_omits_no_ops():
    before = {"category": "tools", "display_name": "Firefox"}
    changes = build_audit_field_changes(before, {"category": "tools", "display_name": "Firefox ESR"})
    assert changes == {
        "display_name": {"before": "Firefox", "after": "Firefox ESR"},
    }


def test_build_audit_field_changes_detects_list_changes():
    before = {"requires": ["macOS 12"]}
    changes = build_audit_field_changes(before, {"requires": ["macOS 13"]})
    assert changes == {"requires": {"before": ["macOS 12"], "after": ["macOS 13"]}}


def test_snapshot_copy_detaches_nested_json():
    nested = {"items": [{"id": 1}]}
    before = {"installs": nested}
    copied = snapshot_copy(before)
    nested["items"][0]["id"] = 2
    assert copied["installs"]["items"][0]["id"] == 1


def test_audit_values_equal_compares_json_structures():
    assert audit_values_equal(["a"], ["a"]) is True
    assert audit_values_equal(["a"], ["b"]) is False
    assert audit_values_equal({"x": 1}, {"x": 1}) is True

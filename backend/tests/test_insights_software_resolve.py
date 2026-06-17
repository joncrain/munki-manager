"""Tests for fuzzy software resolution in AI insights."""

from __future__ import annotations

from automunki.services.insights.software_resolve import (
    KNOWN_SOFTWARE_ALIASES,
    _labels_from_terms,
    software_entry_matches,
)


def test_munki_aliases_include_managed_software_center():
    labels = _labels_from_terms(["munki"])
    assert "Managed Software Center" in labels
    assert "ManagedSoftwareCenter" in labels
    assert "munkitools" in labels


def test_munkitools_expands_to_managed_software_center():
    labels = _labels_from_terms(["munkitools"])
    assert "Managed Software Center" in labels


def test_inventory_matches_managed_software_center_display_name():
    entry = {
        "name": "Munki",
        "version": "7.1.2",
        "bundle_id": "ManagedSoftwareCenter",
    }
    matchers = [label.lower() for label in _labels_from_terms(["munki"])]
    assert software_entry_matches(entry, matchers)


def test_inventory_matches_via_display_name_tokens():
    entry = {
        "name": "Managed Software Center",
        "version": "7.1.2",
        "bundle_id": "ManagedSoftwareCenter",
    }
    matchers = [label.lower() for label in _labels_from_terms(["munki"])]
    assert software_entry_matches(entry, ["managed software center"])
    assert software_entry_matches(entry, matchers)


def test_chrome_aliases_present():
    assert "Google Chrome" in KNOWN_SOFTWARE_ALIASES["chrome"]

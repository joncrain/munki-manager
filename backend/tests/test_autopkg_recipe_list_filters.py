"""Unit tests for AutoPkg recipe list filter helpers."""

from __future__ import annotations

from automunki.api.routes.autopkg import _recipe_catalog_filter_clause


def test_recipe_catalog_filter_clause_empty_returns_none() -> None:
    assert _recipe_catalog_filter_clause("") is None
    assert _recipe_catalog_filter_clause("   ") is None


def test_recipe_catalog_filter_clause_returns_boolean_clause() -> None:
    clause = _recipe_catalog_filter_clause("testing")
    assert clause is not None

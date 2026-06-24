"""Coverage for workflow-failure reporting on AutoPkg runs."""

from __future__ import annotations

from types import SimpleNamespace

from automunki.api.routes.autopkg import _run_has_recipe_results
from automunki.models.autopkg import RunStatus


def test_run_has_recipe_results_from_total_recipes() -> None:
    run = SimpleNamespace(results=[], total_recipes=3)
    assert _run_has_recipe_results(run) is True


def test_run_has_recipe_results_from_results_list() -> None:
    run = SimpleNamespace(results=[object()], total_recipes=None)
    assert _run_has_recipe_results(run) is True


def test_run_has_recipe_results_empty() -> None:
    run = SimpleNamespace(results=[], total_recipes=None)
    assert _run_has_recipe_results(run) is False


def test_failed_status_value_available() -> None:
    assert RunStatus.failed.value == "failed"

"""Metadata cache key alignment with cloud-autopkg-runner."""

from automunki.api.routes.pkginfo import _metadata_cache_key_candidates


def test_cache_key_candidates_include_filename_form():
    assert _metadata_cache_key_candidates("local.munki.1Password") == [
        "local.munki.1Password",
        "local.munki.1Password.munki.recipe",
    ]


def test_cache_key_candidates_preserve_full_recipe_name():
    assert _metadata_cache_key_candidates("1Password.munki.recipe") == ["1Password.munki.recipe"]

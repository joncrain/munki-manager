"""Munki-compatible loose version comparison (distutils.version.LooseVersion)."""

from __future__ import annotations

import re
from functools import total_ordering
from typing import Any

_COMPONENT_RE = re.compile(r"(\d+|[a-z]+|\.)", re.VERBOSE)


def parse_loose_version(vstring: str | None) -> list[int | str]:
    """Split a version string into comparable components."""
    if not vstring:
        return []
    components: list[int | str] = []
    for part in _COMPONENT_RE.split(vstring):
        if not part or part == ".":
            continue
        try:
            components.append(int(part))
        except ValueError:
            components.append(part)
    return components


def compare_loose_versions(left: str | None, right: str | None) -> int:
    """Return -1, 0, or 1 (like ``cmp``) for two version strings."""
    l_parts = parse_loose_version(left)
    r_parts = parse_loose_version(right)
    if l_parts == r_parts:
        return 0
    if l_parts < r_parts:
        return -1
    return 1


def loose_version_key(vstring: str | None) -> tuple[Any, ...]:
    """Sort key for ``sorted(..., key=loose_version_key)``."""
    return tuple(parse_loose_version(vstring))


@total_ordering
class LooseVersion:
    """Thin wrapper matching Munki's loose version ordering."""

    def __init__(self, vstring: str | None) -> None:
        self.vstring = vstring or ""
        self.version = parse_loose_version(vstring)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, LooseVersion):
            return NotImplemented
        return self.version == other.version

    def __lt__(self, other: LooseVersion) -> bool:
        return self.version < other.version

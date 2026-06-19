"""Match fleet machines by hardware product name or model identifier."""

from __future__ import annotations

import re

from automunki.models.client import ClientMachine


def machine_matches_hardware(machine: ClientMachine, hardware_query: str | None) -> bool:
    """Return True when ``hardware_query`` is empty or matches machine hardware fields."""
    if not hardware_query or not hardware_query.strip():
        return True

    q = hardware_query.strip().lower()
    hw = machine.hardware_info if isinstance(machine.hardware_info, dict) else {}

    candidates = [
        machine.machine_model or "",
        str(hw.get("product_name") or ""),
        str(hw.get("machine_model") or ""),
        str(hw.get("apple_image_family") or ""),
        str(hw.get("machine_name") or ""),
    ]
    combined = " ".join(candidates).lower()

    if q in combined:
        return True

    tokens = [t for t in re.split(r"[^a-z0-9]+", q) if len(t) >= 2]
    if not tokens:
        return False
    return all(token in combined for token in tokens)

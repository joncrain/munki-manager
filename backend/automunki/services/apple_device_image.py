"""Apple Find My–style device thumbnails (same CDN as MunkiReport).

MunkiReport resolves icons via ``get_model_icon`` using iCloud static URLs; see
https://github.com/munkireport/machine/blob/master/machine_controller.php

The plist field ``machine_name`` (stored as ``machine_name`` in MR) drives the first FMIP path
segment — not ``product_name``. The PHP app’s default ``APPLE_HARDWARE_ICON_URL`` uses
``securedImage.jsp?configcode=…`` as an alternate; we use that when FMIP cannot be derived.

Agents sometimes send ``product_name`` as "Intel Mac" (compact ``IntelMac``) or
``apple_image_family`` as "IntelMac" / "Macmini(M1,2020)" — those are not valid FMIP folder
names; we normalize and fall back to the ``machine_model`` prefix (e.g. ``MacBookPro``).
"""

from __future__ import annotations

import re
from urllib.parse import quote

# e.g. Mac15,3 — digit-based prefix logic yields "Mac", which is not a valid FMIP family folder.
_MARKETING_MODEL_ID = re.compile(r"^Mac\d+,\d+$")

# sysctl sometimes reports "Intel Mac" → compact "IntelMac"; Apple CDN has no such folder.
_GARBAGE_COMPACT_NAMES = frozenset({"IntelMac"})


def normalize_fmip_family_segment(s: str) -> str:
    """Strip parenthetical suffixes and spaces (``Macmini(M1,2020)`` → ``Macmini``)."""
    pn = str(s).strip()
    if "(" in pn:
        pn = pn.split("(", 1)[0].strip()
    return "".join(pn.split())


def marketing_name_for_icon(hardware_info: dict | None) -> str | None:
    """Prefer ``machine_name``, then ``product_name`` (MunkiReport uses ``machine_name`` for icons)."""
    if not isinstance(hardware_info, dict):
        return None
    for key in ("machine_name", "product_name"):
        raw = hardware_info.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None


def derive_apple_image_family(marketing_name: str | None, machine_model: str | None) -> str:
    """First path segment for FMIP deviceImages (spaces removed from marketing name, or model-id prefix).

    Apple’s CDN uses short folder names (e.g. ``MacBookPro``), not the full catalog string with
    screen size/year in parentheses — those URLs 302 away from the PNG.
    """
    mm = (machine_model or "").strip()
    if mm == "iMacPro1,1":
        return "iMac"
    if marketing_name:
        compact = normalize_fmip_family_segment(marketing_name)
        if compact and compact not in _GARBAGE_COMPACT_NAMES:
            return compact
    for i, c in enumerate(mm):
        if c.isdigit():
            prefix = mm[:i] or mm
            if prefix == "Mac" and _MARKETING_MODEL_ID.match(mm):
                return ""
            return prefix
    return mm


def support_configcode_image_url(serial_number: str) -> str | None:
    """Apple KB image redirect (same idea as munkireport-php ``apple_hardware_icon_url``)."""
    sn = serial_number.strip()
    if not sn or sn != sn.upper():
        return None
    n = len(sn)
    if n == 11:
        cc = sn[-3:]
    elif n >= 12:
        cc = sn[-4:]
    else:
        return None
    return f"https://km.support.apple.com/kb/securedImage.jsp?configcode={quote(cc)}&size=240x240"


def apple_fmip_device_image_url(
    serial_number: str,
    machine_model: str | None,
    hardware_info: dict | None,
) -> str | None:
    """Return a PNG URL, or None if we cannot build one."""
    if not serial_number or not serial_number.strip():
        return None

    hw = hardware_info if isinstance(hardware_info, dict) else {}
    mm = (machine_model or "").strip()
    if not mm:
        raw = hw.get("machine_model")
        if isinstance(raw, str) and raw.strip():
            mm = raw.strip()
            machine_model = mm

    sn = serial_number.strip()
    # MunkiReport: mixed-case serial → VM / non-hardware; use support image servlet.
    if sn != sn.upper():
        return f"https://km.support.apple.com/kb/securedImage.jsp?productid={quote(sn)}&size=240x240"

    family: str | None = None
    raw_family = hw.get("apple_image_family")
    if isinstance(raw_family, str) and raw_family.strip():
        norm = normalize_fmip_family_segment(raw_family)
        if norm and norm not in _GARBAGE_COMPACT_NAMES:
            family = norm

    if family is None:
        marketing = marketing_name_for_icon(hw)
        family = derive_apple_image_family(marketing, machine_model)

    mm = (machine_model or "").strip()
    if mm == "iMacPro1,1":
        family = "iMac"

    if family and mm:
        base = "https://statici.icloud.com/fmipmobile/deviceImages-9.0"
        return f"{base}/{quote(family, safe='')}/{quote(mm, safe='')}/online-infobox__2x.png"

    return support_configcode_image_url(sn)

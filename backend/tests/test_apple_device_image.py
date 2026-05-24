"""Apple FMIP thumbnail URL construction."""

from urllib.parse import unquote

from automunki.services.apple_device_image import (
    apple_fmip_device_image_url,
    derive_apple_image_family,
    marketing_name_for_icon,
)


def test_derive_family_strips_parenthetical_screen_year():
    assert derive_apple_image_family("MacBook Pro (16-inch, 2024)", "MacBookPro18,1") == "MacBookPro"


def test_derive_family_imac_with_size():
    assert derive_apple_image_family("iMac (24-inch, M1, 2021)", "iMac21,1") == "iMac"


def test_derive_family_mac15_model_id_without_marketing_returns_empty():
    assert derive_apple_image_family(None, "Mac15,3") == ""


def test_fmip_url_uses_short_family_not_full_product_string():
    url = apple_fmip_device_image_url(
        "C02ABCDEFGH",
        "MacBookPro18,1",
        {"product_name": "MacBook Pro (16-inch, 2024)"},
    )
    assert url is not None
    assert "MacBookPro18%2C1" in url or "MacBookPro18,1" in unquote(url)
    assert "16-inch" not in url
    assert "(" not in url


def test_fmip_mac15_without_marketing_falls_back_to_configcode():
    url = apple_fmip_device_image_url(
        "C02ABCDEFGH",
        "Mac15,3",
        {},
    )
    assert url is not None
    assert "configcode=" in url
    assert "FGH" in url


def test_marketing_name_prefers_machine_name():
    assert (
        marketing_name_for_icon(
            {"machine_name": "MacBook Pro", "product_name": "ignore me"},
        )
        == "MacBook Pro"
    )


def test_fmip_uses_machine_name_first():
    url = apple_fmip_device_image_url(
        "C02ABCDEFGH",
        "MacBookPro18,1",
        {"machine_name": "MacBook Pro", "product_name": "Wrong"},
    )
    assert url is not None
    assert "/MacBookPro/" in url


def test_intel_mac_product_name_falls_back_to_model_prefix():
    """sysctl reports \"Intel Mac\" for some Intel Macs — not a valid FMIP folder."""
    assert derive_apple_image_family("Intel Mac", "MacBookPro16,1") == "MacBookPro"


def test_intelmac_apple_image_family_override_ignored():
    url = apple_fmip_device_image_url(
        "C02DG17PMD6W",
        "MacBookPro16,1",
        {
            "product_name": "Intel Mac",
            "machine_model": "MacBookPro16,1",
            "apple_image_family": "IntelMac",
        },
    )
    assert url is not None
    assert "/MacBookPro/" in url
    assert "IntelMac" not in url


def test_macmini_parenthetical_apple_image_family_normalized():
    url = apple_fmip_device_image_url(
        "H2WGG14LQ6NY",
        "Macmini9,1",
        {
            "product_name": "Mac mini (M1, 2020)",
            "machine_model": "Macmini9,1",
            "apple_image_family": "Macmini(M1,2020)",
        },
    )
    assert url is not None
    assert "/Macmini/" in url
    assert "(" not in url

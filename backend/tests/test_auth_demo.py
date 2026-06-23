"""Read-only demo auth (POST /auth/demo)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from automunki.api.routes.auth import _demo_enabled, start_demo_session
from automunki.core.page_keys import PageKey
from automunki.core.rbac_middleware import DEMO_USER_ID, _is_public_path
from automunki.core.security import get_demo_jwt_strategy
from automunki.services.permissions import can_access


def test_auth_demo_post_is_public() -> None:
    assert _is_public_path("/api/v1/auth/demo", "POST") is True


def test_demo_enabled_requires_flag_and_non_disabled_mode(monkeypatch) -> None:
    monkeypatch.setattr("automunki.api.routes.auth.settings.auth_demo_enabled", True)
    monkeypatch.setattr("automunki.api.routes.auth.settings.auth_mode", "jwt")
    assert _demo_enabled() is True

    monkeypatch.setattr("automunki.api.routes.auth.settings.auth_mode", "disabled")
    assert _demo_enabled() is False

    monkeypatch.setattr("automunki.api.routes.auth.settings.auth_mode", "jwt")
    monkeypatch.setattr("automunki.api.routes.auth.settings.auth_demo_enabled", False)
    assert _demo_enabled() is False


def test_viewer_permissions_allow_read_block_write() -> None:
    pk = PageKey.munki_software.value
    perms = {pk: "read"}
    assert can_access(perms, pk, need_write=False) is True
    assert can_access(perms, pk, need_write=True) is False


def test_demo_jwt_strategy_uses_shorter_lifetime_when_configured(monkeypatch) -> None:
    monkeypatch.setattr("automunki.core.security.settings.demo_jwt_lifetime_seconds", 3600)
    monkeypatch.setattr("automunki.core.security.settings.jwt_lifetime_seconds", 28800)
    strategy = get_demo_jwt_strategy()
    assert strategy.lifetime_seconds == 3600


def test_demo_jwt_strategy_falls_back_to_default_lifetime(monkeypatch) -> None:
    monkeypatch.setattr("automunki.core.security.settings.demo_jwt_lifetime_seconds", None)
    monkeypatch.setattr("automunki.core.security.settings.jwt_lifetime_seconds", 28800)
    strategy = get_demo_jwt_strategy()
    assert strategy.lifetime_seconds == 28800


@pytest.mark.asyncio
async def test_start_demo_session_rejects_when_disabled(monkeypatch) -> None:
    monkeypatch.setattr("automunki.api.routes.auth._demo_enabled", lambda: False)
    session = AsyncMock()
    with pytest.raises(HTTPException) as exc:
        await start_demo_session(session=session)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_start_demo_session_issues_token(monkeypatch) -> None:
    monkeypatch.setattr("automunki.api.routes.auth._demo_enabled", lambda: True)
    user = SimpleNamespace(id=DEMO_USER_ID, is_active=True)
    session = AsyncMock()
    session.get = AsyncMock(return_value=user)

    strategy = MagicMock()
    strategy.write_token = AsyncMock(return_value="demo-jwt-token")

    with patch("automunki.api.routes.auth.get_demo_jwt_strategy", return_value=strategy):
        response = await start_demo_session(session=session)

    assert response.access_token == "demo-jwt-token"
    strategy.write_token.assert_awaited_once_with(user)


def test_demo_user_id_is_distinct_from_dev_user() -> None:
    from automunki.core.rbac_middleware import DEV_USER_ID

    assert DEMO_USER_ID != DEV_USER_ID
    assert DEMO_USER_ID == uuid.UUID("00000000-0000-4000-8000-000000000002")

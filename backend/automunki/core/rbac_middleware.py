"""Enforce JWT authentication and per-page RBAC on ``/api/v1`` routes."""

from __future__ import annotations

import hmac
import uuid
from types import SimpleNamespace

from fastapi.responses import JSONResponse
from fastapi_users.db import SQLAlchemyUserDatabase
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from automunki.core.audit_context import audit_user_email_ctx, audit_user_id_ctx
from automunki.core.config import settings
from automunki.core.db import async_session_factory
from automunki.core.page_keys import ALL_PAGE_KEYS, api_path_to_page_key
from automunki.core.security import UserManager, get_jwt_strategy
from automunki.models.user import User
from automunki.services.permissions import can_access, get_effective_permissions

# Synthetic identity for audit when ``auth_mode=disabled``.
# Use example.com so Pydantic email validation accepts the placeholder (.local is reserved).
DEV_USER_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")
DEV_USER_EMAIL = "dev@example.com"
LOCAL_RUNNER_AUDIT_EMAIL = "local-runner@automunki.internal"

# When ``auth_mode=disabled``, route handlers that read ``request.state.user`` (e.g. RBAC
# delete-user) still need a principal with superuser so audits and guards match ``/auth/me``.
DEV_USER_PRINCIPAL = SimpleNamespace(
    id=DEV_USER_ID,
    email=DEV_USER_EMAIL,
    is_active=True,
    is_superuser=True,
)


def _path_is_local_runner_get_run_id(path: str, method: str) -> bool:
    """``GET /api/v1/autopkg/runs/{run_id}`` so the local shell can read ``recipe_filter``."""
    if method != "GET":
        return False
    p = path.rstrip("/")
    if not p.startswith("/api/v1/autopkg/runs/"):
        return False
    rest = p[len("/api/v1/autopkg/runs/") :]
    if not rest or "/" in rest:
        return False
    try:
        uuid.UUID(rest)
    except (ValueError, TypeError, AttributeError):
        return False
    return True


def _local_runner_authenticated_path(path: str, method: str) -> bool:
    """Allow ``LOCAL_RUNNER_TOKEN`` for AutoPkg daemon + one-shot script API calls.

    These are the endpoints AutoPkg runners (cloud + local) call without an
    interactive user JWT. Every one of them used to be on the public allowlist
    in ``_is_public_path`` — that was a security hole (any internet caller
    could plant a ``PkgInfo`` row, mark runs complete, etc.). Now they require
    either a Bearer matching ``settings.local_runner_token`` or a real user JWT.
    """
    p = path.rstrip("/")
    if p == "/api/v1/autopkg/metadata-cache" and method in ("GET", "PUT"):
        return True
    if p.startswith("/api/v1/autopkg/runs/config") and method == "GET":
        return True
    if p == "/api/v1/autopkg/runs/claim-next-local" and method == "POST":
        return True
    if _path_is_local_runner_get_run_id(path, method):
        return True
    if p == "/api/v1/autopkg/pkginfo/ingest" and method == "POST":
        return True
    if p == "/api/v1/autopkg/icons/ingest" and method == "POST":
        return True
    # Runner streams pkg/dmg bytes here; same Bearer model as the other ingest paths.
    if p.startswith("/api/v1/autopkg/runs/") and p.endswith("/pkgs") and method == "POST":
        return True
    # Per-recipe results, run completion, and GitHub Actions context updates
    # are runner-driven webhooks; they used to be on the public allowlist.
    if p.startswith("/api/v1/autopkg/runs/") and method == "POST":
        if p.endswith("/results") or p.endswith("/complete") or p.endswith("/github-context"):
            return True
    return False


def _is_public_path(path: str, method: str) -> bool:
    if path in ("/health", "/ready", "/metrics"):
        return True
    if path.startswith("/repo"):
        return True
    if path.startswith("/api/docs") or path in ("/api/openapi.json", "/openapi.json"):
        return True
    if path.rstrip("/") == "/api/v1/autopkg/schedules/run-due" and method == "POST":
        return True
    if path.rstrip("/") == "/api/v1/autopkg/promotions/run-due" and method == "POST":
        return True
    if path.startswith("/api/v1/auth/oidc"):
        return True
    if path.startswith("/api/v1/auth/"):
        p = path.rstrip("/")
        if p == "/api/v1/auth/me":
            return False
        return True
    # Fleet agent / AutoPkg runner (no interactive user JWT)
    if path.rstrip("/") == "/api/v1/reports/checkin" and method == "POST":
        return True
    # Software icons: GETs are public so <img src="/icons/<name>.png"> works
    # without a bearer token (the browser can't attach one). The same PNG is
    # already served anonymously at /repo/icons/... for Munki clients, so
    # gating the UI copy would be defense-in-depth against nothing. Uploads
    # (POST /api/v1/icons/upload) stay RBAC-protected.
    if path.startswith("/api/v1/icons/") and method == "GET":
        return True
    # Public enrollment: status advert + token-gated profile download.
    # Token management (POST/GET/DELETE /api/v1/enroll/tokens) stays RBAC-protected.
    p = path.rstrip("/")
    if p == "/api/v1/enroll/status" and method == "GET":
        return True
    if p == "/api/v1/enroll/profile" and method == "POST":
        return True
    # NOTE: AutoPkg runner ingest endpoints used to be unconditionally public
    # here (``/runs/{id}/results``, ``/runs/{id}/complete``,
    # ``/runs/{id}/github-context``, ``/pkginfo/ingest``, ``/icons/ingest``).
    # That allowed any internet caller to plant a ``PkgInfo`` row whose
    # ``installer_item_location`` they controlled, mark arbitrary runs
    # complete, and overwrite icons. They now require either
    # ``settings.local_runner_token`` (see ``_local_runner_authenticated_path``)
    # or an interactive user JWT.
    return False


def _needs_write(method: str) -> bool:
    return method not in ("GET", "HEAD", "OPTIONS")


class RBACMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if not path.startswith("/api/v1"):
            return await call_next(request)

        if request.method == "OPTIONS":
            return await call_next(request)

        if _is_public_path(path, request.method):
            return await call_next(request)

        if (
            request.method == "POST"
            and path.rstrip("/") == "/api/v1/auth/register"
            and not settings.auth_registration_open
        ):
            return JSONResponse(status_code=403, content={"detail": "Registration is closed"})

        if settings.auth_mode == "disabled":
            request.state.user = DEV_USER_PRINCIPAL
            request.state.rbac_user_id = DEV_USER_ID
            request.state.effective_permissions = {k: "write" for k in ALL_PAGE_KEYS}
            tid = audit_user_id_ctx.set(DEV_USER_ID)
            tem = audit_user_email_ctx.set(DEV_USER_EMAIL)
            try:
                return await call_next(request)
            finally:
                audit_user_id_ctx.reset(tid)
                audit_user_email_ctx.reset(tem)

        auth = request.headers.get("Authorization")
        token = None
        if auth and auth.startswith("Bearer "):
            token = auth[7:].strip()

        _lr = settings.local_runner_token
        _lr_ok = bool(token) and bool(_lr) and len(token) == len(_lr) and hmac.compare_digest(token, _lr)
        if _lr_ok and _local_runner_authenticated_path(path, request.method):
            request.state.user = DEV_USER_PRINCIPAL
            request.state.rbac_user_id = DEV_USER_ID
            request.state.effective_permissions = {k: "write" for k in ALL_PAGE_KEYS}
            tid = audit_user_id_ctx.set(DEV_USER_ID)
            tem = audit_user_email_ctx.set(LOCAL_RUNNER_AUDIT_EMAIL)
            try:
                return await call_next(request)
            finally:
                audit_user_id_ctx.reset(tid)
                audit_user_email_ctx.reset(tem)

        if not token:
            return JSONResponse(status_code=401, content={"detail": "Not authenticated"})

        page_key = api_path_to_page_key(path)
        need_write = _needs_write(request.method)

        async with async_session_factory() as session:
            strategy = get_jwt_strategy()
            user_db = SQLAlchemyUserDatabase(session, User)
            user_manager = UserManager(user_db)
            user = await strategy.read_token(token, user_manager)
            if user is None or not user.is_active:
                return JSONResponse(status_code=401, content={"detail": "Not authenticated"})

            perms = await get_effective_permissions(session, user)

        request.state.user = user
        request.state.rbac_user_id = user.id
        request.state.effective_permissions = perms

        tid = audit_user_id_ctx.set(user.id)
        tem = audit_user_email_ctx.set(user.email)
        try:
            if page_key is None:
                return await call_next(request)

            if not can_access(perms, page_key, need_write):
                return JSONResponse(status_code=403, content={"detail": "Forbidden"})

            return await call_next(request)
        finally:
            audit_user_id_ctx.reset(tid)
            audit_user_email_ctx.reset(tem)

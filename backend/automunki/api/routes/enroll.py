"""Mac client enrollment API.

Two audiences:

- **Admins** (signed in, ``admin.settings`` write): create, list, revoke
  one-time tokens. Plaintext is returned only once at creation.
- **End users** with a token: redeem it (public endpoint) and download a
  tailored ``.mobileconfig`` that configures Munki to talk to this server.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from automunki.api.deps import get_session
from automunki.services.enrollment import (
    build_profile,
    clear_embedded_secret,
    create_token,
    list_tokens,
    redeem_token,
    revoke_token,
)
from automunki.services.munki_repo_basic_auth import resolve_effective_auth

router = APIRouter(prefix="/enroll", tags=["enroll"])


# ---------------------------------------------------------------------------
# Admin: token management
# ---------------------------------------------------------------------------


class EnrollmentTokenCreate(BaseModel):
    label: str | None = Field(None, description="Human label, e.g. 'jon MBP'")
    manifest_name: str | None = Field(
        None,
        description="Munki ClientIdentifier to bake into the profile. Empty = use hostname on the Mac.",
    )
    ttl_hours: int | None = Field(None, gt=0, le=24 * 30, description="Lifetime in hours; server default is 24.")
    repo_password: str | None = Field(
        None,
        description=(
            "Current repo Basic auth password. Required in DB-mode Basic auth; "
            "ignored when env-mode is active (server already has the plaintext) "
            "or Basic auth is off."
        ),
    )


class EnrollmentTokenCreated(BaseModel):
    id: uuid.UUID
    #: Plaintext token — shown once, not retrievable afterward.
    token: str
    label: str | None
    manifest_name: str | None
    expires_at: datetime | None
    created_at: datetime
    #: Convenience URL for the walkthrough page. Admins hand this to the user.
    enroll_url: str
    #: True when the downloaded profile will include ``AdditionalHttpHeaders``.
    embeds_basic_auth: bool


class EnrollmentTokenRead(BaseModel):
    id: uuid.UUID
    label: str | None
    manifest_name: str | None
    expires_at: datetime | None
    redeemed_at: datetime | None
    created_at: datetime


def _enroll_url(request: Request, plain: str) -> str:
    base = str(request.base_url).rstrip("/")
    if base.endswith("/api") or "/api/" in base:
        base = base.split("/api", 1)[0]
    return f"{base}/enroll?token={plain}"


@router.post("/tokens", response_model=EnrollmentTokenCreated, status_code=201)
async def create_enrollment_token(
    body: EnrollmentTokenCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> EnrollmentTokenCreated:
    user = getattr(request.state, "user", None)
    created_by = getattr(user, "id", None) if user is not None else None

    try:
        token = await create_token(
            session,
            label=body.label,
            manifest_name=body.manifest_name,
            ttl_hours=body.ttl_hours,
            created_by_user_id=created_by,
            repo_password=body.repo_password,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return EnrollmentTokenCreated(
        id=token.id,
        token=token.plain,
        label=token.label,
        manifest_name=token.manifest_name,
        expires_at=token.expires_at,
        created_at=token.created_at,
        enroll_url=_enroll_url(request, token.plain),
        embeds_basic_auth=token.embeds_basic_auth,
    )


@router.get("/tokens", response_model=list[EnrollmentTokenRead])
async def list_enrollment_tokens(session: AsyncSession = Depends(get_session)) -> list[EnrollmentTokenRead]:
    rows = await list_tokens(session)
    return [
        EnrollmentTokenRead(
            id=r.id,
            label=r.label,
            manifest_name=r.manifest_name,
            expires_at=r.expires_at,
            redeemed_at=r.redeemed_at,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.delete("/tokens/{token_id}", status_code=204)
async def delete_enrollment_token(
    token_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> Response:
    ok = await revoke_token(session, token_id)
    if not ok:
        raise HTTPException(status_code=404, detail="token not found")
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Public: redeem + download
# ---------------------------------------------------------------------------


class EnrollmentStatus(BaseModel):
    """Advertised to the walkthrough page before the user redeems.

    Does **not** accept or validate the user's token — that happens at
    download time. This is just server info.
    """

    server_base_url: str
    repo_basic_auth_enabled: bool
    #: When True, the server can embed the ``Authorization`` header in the
    #: profile (env-configured credentials). When False but auth is enabled,
    #: the admin must distribute the credentials separately.
    profile_embeds_basic_auth: bool


@router.get("/status", response_model=EnrollmentStatus)
async def enrollment_status(session: AsyncSession = Depends(get_session)) -> EnrollmentStatus:
    from automunki.core.config import settings

    base = (settings.api_public_url or settings.public_app_url or "").strip().rstrip("/")
    resolved = await resolve_effective_auth(session)
    return EnrollmentStatus(
        server_base_url=base,
        repo_basic_auth_enabled=resolved.active,
        profile_embeds_basic_auth=resolved.active and resolved.env_plain_password is not None,
    )


class EnrollmentProfileRequest(BaseModel):
    token: str
    #: Optional override if the user wants a specific Munki ClientIdentifier.
    manifest_name: str | None = None


@router.post("/profile")
async def download_profile(
    body: EnrollmentProfileRequest,
    session: AsyncSession = Depends(get_session),
) -> Response:
    try:
        row = await redeem_token(session, body.token)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    manifest = (body.manifest_name or "").strip() or row.manifest_name

    try:
        profile_bytes = await build_profile(session, manifest_name=manifest, token=row)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    await clear_embedded_secret(session, row.id)

    filename = "munki-manager-enroll.mobileconfig"
    return Response(
        content=profile_bytes,
        media_type="application/x-apple-aspen-config",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

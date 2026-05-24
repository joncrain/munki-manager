from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from automunki.api.deps import get_session
from automunki.core.config import settings
from automunki.models.munki_repo_basic_auth import MunkiRepoBasicAuth
from automunki.services.munki_repo_basic_auth import (
    SINGLETON_ID,
    build_client_authorization_header_value,
    env_override_active,
    get_singleton_row,
    hash_password,
)
from automunki.services.munki_repo_urls import (
    resolve_repo_urls,
    update_repo_urls,
)

router = APIRouter(prefix="/settings", tags=["settings"])


class UiSettingsRead(BaseModel):
    github_repo: str
    autopkg_runner_mode: str


@router.get("/ui", response_model=UiSettingsRead)
async def get_ui_settings() -> UiSettingsRead:
    """Read-only UI config. Same access model as other read routes (no JWT required)."""
    return UiSettingsRead(
        github_repo=(settings.github_repo or "").strip(),
        autopkg_runner_mode=settings.autopkg_runner_mode,
    )


class MunkiRepoBasicAuthRead(BaseModel):
    enabled: bool
    username: str
    env_override_active: bool


class MunkiRepoBasicAuthUpdate(BaseModel):
    enabled: bool
    username: str = ""
    password: str | None = Field(None, description="New password; omit to keep existing hash")


class MunkiRepoBasicAuthPatchResponse(BaseModel):
    enabled: bool
    username: str
    env_override_active: bool
    client_authorization_header: str | None = None


@router.get("/munki-repo-basic-auth", response_model=MunkiRepoBasicAuthRead)
async def get_munki_repo_basic_auth(session: AsyncSession = Depends(get_session)) -> MunkiRepoBasicAuthRead:
    if env_override_active():
        u = (settings.munki_repo_basic_auth_user or "").strip()
        return MunkiRepoBasicAuthRead(enabled=True, username=u, env_override_active=True)

    row = await get_singleton_row(session)
    if row is None:
        return MunkiRepoBasicAuthRead(enabled=False, username="", env_override_active=False)

    return MunkiRepoBasicAuthRead(
        enabled=bool(row.enabled),
        username=(row.username or "").strip(),
        env_override_active=False,
    )


@router.patch("/munki-repo-basic-auth", response_model=MunkiRepoBasicAuthPatchResponse)
async def patch_munki_repo_basic_auth(
    body: MunkiRepoBasicAuthUpdate,
    session: AsyncSession = Depends(get_session),
) -> MunkiRepoBasicAuthPatchResponse:
    if env_override_active():
        raise HTTPException(
            status_code=409,
            detail="Munki repo basic auth is configured via MUNKI_REPO_BASIC_AUTH_USER / "
            "MUNKI_REPO_BASIC_AUTH_PASSWORD; clear those to manage credentials in the database.",
        )

    row = await get_singleton_row(session)
    if row is None:
        row = MunkiRepoBasicAuth(id=SINGLETON_ID, enabled=False, username="", password_hash="")
        session.add(row)
        await session.flush()

    username = (body.username or "").strip()

    if body.password is not None:
        if body.password == "":
            row.password_hash = ""
        else:
            row.password_hash = hash_password(body.password)

    if body.enabled:
        if not username:
            raise HTTPException(status_code=400, detail="username is required when enabled is true")
        if not (row.password_hash or "").strip():
            raise HTTPException(
                status_code=400,
                detail="password is required when enabling (no stored password yet)",
            )
        row.enabled = True
        row.username = username
    else:
        row.enabled = False
        row.username = username

    await session.commit()
    await session.refresh(row)

    client_header: str | None = None
    if body.password and body.password != "" and body.enabled and username:
        client_header = build_client_authorization_header_value(username, body.password)

    return MunkiRepoBasicAuthPatchResponse(
        enabled=bool(row.enabled),
        username=(row.username or "").strip(),
        env_override_active=False,
        client_authorization_header=client_header,
    )


# ---------------------------------------------------------------------------
# External Munki URLs (PackageURL / ClientResourceURL)
# ---------------------------------------------------------------------------


def _validate_https_url(value: str) -> str:
    """Allow empty, otherwise require ``http://`` or ``https://``.

    We do *not* force HTTPS here because some deployments use internal-only
    hosts on plain HTTP. Munki's ``FollowHTTPRedirects`` guard doesn't
    apply since this isn't a redirect target anymore — the client goes
    direct.
    """
    v = (value or "").strip()
    if not v:
        return ""
    if not (v.startswith("http://") or v.startswith("https://")):
        raise ValueError("must start with http:// or https://")
    return v.rstrip("/")


class MunkiRepoUrlsRead(BaseModel):
    package_url: str
    client_resource_url: str
    package_url_env_override: bool
    client_resource_url_env_override: bool
    client_resource_url_derived: bool


class MunkiRepoUrlsUpdate(BaseModel):
    package_url: str | None = Field(
        None,
        description="External PackageURL (e.g. https://cdn.example.com/pkgs). "
        "Empty string clears. Omit to leave unchanged.",
    )
    client_resource_url: str | None = Field(
        None,
        description="External ClientResourceURL. Empty string clears (falls back to deriving from package_url).",
    )

    @field_validator("package_url", "client_resource_url")
    @classmethod
    def _check_url(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return _validate_https_url(v)


@router.get("/munki-repo-urls", response_model=MunkiRepoUrlsRead)
async def get_munki_repo_urls(session: AsyncSession = Depends(get_session)) -> MunkiRepoUrlsRead:
    resolved = await resolve_repo_urls(session)
    return MunkiRepoUrlsRead(
        package_url=resolved.package_url,
        client_resource_url=resolved.client_resource_url,
        package_url_env_override=resolved.package_url_env_override,
        client_resource_url_env_override=resolved.client_resource_url_env_override,
        client_resource_url_derived=resolved.client_resource_url_derived,
    )


@router.patch("/munki-repo-urls", response_model=MunkiRepoUrlsRead)
async def patch_munki_repo_urls(
    body: MunkiRepoUrlsUpdate,
    session: AsyncSession = Depends(get_session),
) -> MunkiRepoUrlsRead:
    pre = await resolve_repo_urls(session)

    if body.package_url is not None and pre.package_url_env_override:
        raise HTTPException(
            status_code=409,
            detail="package_url is pinned by MUNKI_REPO_PKG_BASE_URL; unset that env var to manage it here.",
        )
    if body.client_resource_url is not None and pre.client_resource_url_env_override:
        raise HTTPException(
            status_code=409,
            detail=(
                "client_resource_url is pinned by MUNKI_REPO_CLIENT_RESOURCES_BASE_URL; "
                "unset that env var to manage it here."
            ),
        )

    await update_repo_urls(
        session,
        package_url=body.package_url,
        client_resource_url=body.client_resource_url,
    )

    post = await resolve_repo_urls(session)
    return MunkiRepoUrlsRead(
        package_url=post.package_url,
        client_resource_url=post.client_resource_url,
        package_url_env_override=post.package_url_env_override,
        client_resource_url_env_override=post.client_resource_url_env_override,
        client_resource_url_derived=post.client_resource_url_derived,
    )

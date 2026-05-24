"""Mac client enrollment: one-time tokens + `.mobileconfig` generation.

Flow:

1. Admin creates a token (UI). Plaintext is returned **once**; only the SHA-256
   is persisted. If repo HTTP Basic auth is enabled, the admin either relies
   on env-var mode (password known to the server) or supplies the password at
   token-creation time. Either way an ``Authorization: Basic …`` header is
   Fernet-encrypted onto the token row.
2. User visits ``/enroll?token=...`` (or pastes the token). The page POSTs to
   ``/api/v1/enroll/profile``; the server decrypts any embedded header and
   returns a ``.mobileconfig`` wired up for this server.
3. User double-clicks the profile; macOS installs it into the
   ``ManagedInstalls`` preference domain so Munki picks it up on next run.

The profile sets:

* **`SoftwareRepoURL`** — required. Catalogs, manifests, icons, and
  ``_icon_hashes.plist`` are served from this app.
* **`ClientIdentifier`** — optional (Munki manifest name).
* **`PackageURL`** — when configured, Munki fetches ``pkgs/*`` directly
  from this URL. We use this instead of server-side 302 redirects because
  Munki's underlying downloader (``gurl``) drops ``Authorization`` headers
  on cross-origin redirects, which broke downloads whenever the pkg host
  was a different hostname than the app.
* **`ClientResourceURL`** — same story as ``PackageURL`` but for the
  per-manifest ``client_resources/*.zip`` bundles. Omitted when unset;
  Munki then falls back to ``<SoftwareRepoURL>/client_resources``.
* **`AdditionalHttpHeaders`** — only when HTTP Basic is enabled on ``/repo``;
  carries the pre-baked ``Authorization`` header. Sent to the app *and* to
  the ``PackageURL`` / ``ClientResourceURL`` hosts (Munki sends these
  headers on every request), so those hosts must either accept the same
  credentials or ignore the header.
"""

from __future__ import annotations

import hashlib
import plistlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from automunki.core.config import settings
from automunki.core.secret_box import decrypt_for, encrypt_for
from automunki.models.enrollment import EnrollmentToken
from automunki.services.munki_repo_basic_auth import (
    build_client_authorization_header_value,
    resolve_effective_auth,
    verify_password_against_hash,
)
from automunki.services.munki_repo_urls import resolve_repo_urls

#: Token lifetime when the admin does not override it.
DEFAULT_TTL = timedelta(hours=24)

#: Profile identifier prefix. Appears in System Settings → Device Management.
PROFILE_IDENTIFIER_PREFIX = "com.munkimanager.enroll"

#: secret_box purpose string for the embedded Basic auth header. Changing this
#: invalidates all previously-stored ciphertexts (tokens are short-lived so
#: this is low cost).
_SECRET_PURPOSE_BASIC_AUTH = "enrollment.basic_auth"


def _hash_token(plain: str) -> str:
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


def generate_token() -> str:
    """24-char URL-safe token; ~142 bits of entropy."""
    return secrets.token_urlsafe(18)


@dataclass(frozen=True)
class CreatedToken:
    """Returned to the admin once. ``plain`` is never persisted."""

    id: uuid.UUID
    plain: str
    label: str | None
    manifest_name: str | None
    expires_at: datetime | None
    created_at: datetime
    #: True when the token's profile will include ``AdditionalHttpHeaders``.
    embeds_basic_auth: bool


async def _resolve_embedded_header(
    session: AsyncSession,
    *,
    repo_password: str | None,
) -> str | None:
    """Build the ``Authorization: Basic …`` line to embed on the token, or ``None``.

    Priority:

    1. Env-var mode active → use the plaintext the server already has.
    2. DB-mode active and the admin supplied ``repo_password`` that matches the
       stored Argon2 hash → use that.
    3. Otherwise → no embedded header (profile will be generated without one).
    """
    resolved = await resolve_effective_auth(session)
    if not resolved.active:
        return None

    if resolved.env_plain_password is not None:
        return build_client_authorization_header_value(resolved.username, resolved.env_plain_password)

    password = (repo_password or "").strip()
    if not password:
        return None
    if not verify_password_against_hash(resolved.password_hash, password):
        raise ValueError("repo password does not match the configured credentials")
    return build_client_authorization_header_value(resolved.username, password)


async def create_token(
    session: AsyncSession,
    *,
    label: str | None,
    manifest_name: str | None,
    ttl_hours: int | None,
    created_by_user_id: uuid.UUID | None,
    repo_password: str | None = None,
) -> CreatedToken:
    plain = generate_token()
    ttl = timedelta(hours=ttl_hours) if ttl_hours and ttl_hours > 0 else DEFAULT_TTL
    expires_at = datetime.now(UTC) + ttl

    header_value = await _resolve_embedded_header(session, repo_password=repo_password)
    encrypted = encrypt_for(_SECRET_PURPOSE_BASIC_AUTH, header_value) if header_value else None

    row = EnrollmentToken(
        token_hash=_hash_token(plain),
        label=(label or "").strip() or None,
        manifest_name=(manifest_name or "").strip() or None,
        expires_at=expires_at,
        created_by_user_id=created_by_user_id,
        embedded_basic_auth_enc=encrypted,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)

    return CreatedToken(
        id=row.id,
        plain=plain,
        label=row.label,
        manifest_name=row.manifest_name,
        expires_at=row.expires_at,
        created_at=row.created_at,
        embeds_basic_auth=encrypted is not None,
    )


async def list_tokens(session: AsyncSession) -> list[EnrollmentToken]:
    r = await session.execute(select(EnrollmentToken).order_by(EnrollmentToken.created_at.desc()))
    return list(r.scalars().all())


async def revoke_token(session: AsyncSession, token_id: uuid.UUID) -> bool:
    r = await session.execute(select(EnrollmentToken).where(EnrollmentToken.id == token_id))
    row = r.scalar_one_or_none()
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True


async def redeem_token(session: AsyncSession, plain: str) -> EnrollmentToken:
    """Consume a token, atomically. Raises ``ValueError`` on any failure mode.

    On success, the row's ``redeemed_at`` is set and returned. The caller
    should then immediately generate the profile; the encrypted header (if
    any) remains on the row for that single call and is wiped by
    :func:`clear_embedded_secret` once the download has been built.
    """
    plain = (plain or "").strip()
    if not plain:
        raise ValueError("token is required")

    r = await session.execute(select(EnrollmentToken).where(EnrollmentToken.token_hash == _hash_token(plain)))
    row = r.scalar_one_or_none()
    if row is None:
        raise ValueError("invalid token")

    now = datetime.now(UTC)
    if row.redeemed_at is not None:
        raise ValueError("token already used")
    if row.expires_at is not None and row.expires_at < now:
        raise ValueError("token expired")

    row.redeemed_at = now
    await session.commit()
    await session.refresh(row)
    return row


async def clear_embedded_secret(session: AsyncSession, token_id: uuid.UUID) -> None:
    """Remove the encrypted header after a successful profile download."""
    r = await session.execute(select(EnrollmentToken).where(EnrollmentToken.id == token_id))
    row = r.scalar_one_or_none()
    if row is None or row.embedded_basic_auth_enc is None:
        return
    row.embedded_basic_auth_enc = None
    await session.commit()


# ---------------------------------------------------------------------------
# .mobileconfig generation
# ---------------------------------------------------------------------------


def _server_base_url(override: str | None = None) -> str:
    """HTTPS origin that Munki will hit. Never returns a trailing slash."""
    raw = (override or settings.api_public_url or settings.public_app_url or "").strip()
    return raw.rstrip("/")


def _decrypt_embedded_header(ciphertext: str | None) -> str | None:
    if not ciphertext:
        return None
    return decrypt_for(_SECRET_PURPOSE_BASIC_AUTH, ciphertext)


async def build_profile(
    session: AsyncSession,
    *,
    manifest_name: str | None,
    server_base_url: str | None = None,
    profile_uuid: str | None = None,
    token: EnrollmentToken | None = None,
) -> bytes:
    """Return a ``.mobileconfig`` (XML plist) for this server.

    The payload installs settings into the ``ManagedInstalls`` preference
    domain — exactly what Munki reads via CFPreferences. When ``token`` is
    provided and carries an encrypted ``Authorization`` header, it is
    preferred over the server's env-var credentials (which may not be active
    for this instance).
    """
    base = _server_base_url(server_base_url)
    if not base:
        raise ValueError(
            "Server base URL is not configured. Set API_PUBLIC_URL (or PUBLIC_APP_URL) "
            "to the HTTPS origin clients will reach (e.g. https://munki.example.com).",
        )

    repo_url = f"{base}/repo"

    # Build the inner ManagedInstalls payload. Modern style: one payload
    # whose ``PayloadType`` is literally ``ManagedInstalls``, with each
    # Munki pref as a sibling key at the top level of that payload. No
    # ``com.apple.ManagedClient.preferences`` wrapper, no ``Forced`` array,
    # no ``mcx_preference_settings`` dict. Munki reads these directly via
    # CFPreferences. See Munki wiki → Preferences.
    payload_uuid = str(uuid.uuid4()).upper()
    profile_uuid_value = (profile_uuid or str(uuid.uuid4())).upper()

    managed_installs_payload: dict[str, object] = {
        "PayloadType": "ManagedInstalls",
        "PayloadVersion": 1,
        "PayloadEnabled": True,
        "PayloadIdentifier": f"{PROFILE_IDENTIFIER_PREFIX}.managed-installs.{payload_uuid}",
        "PayloadUUID": payload_uuid,
        "PayloadDisplayName": "Munki",
        "PayloadDescription": "Settings for Munki",
        "PayloadOrganization": settings.app_name,
        "SoftwareRepoURL": repo_url,
    }
    if manifest_name:
        managed_installs_payload["ClientIdentifier"] = manifest_name

    # PackageURL / ClientResourceURL: point Munki directly at the external
    # host(s) so package downloads never go through a cross-origin redirect.
    # See the module docstring for why we can't rely on a 302 here.
    repo_urls = await resolve_repo_urls(session)
    if repo_urls.package_url:
        managed_installs_payload["PackageURL"] = repo_urls.package_url
    if repo_urls.client_resource_url:
        managed_installs_payload["ClientResourceURL"] = repo_urls.client_resource_url

    header_value: str | None = None
    if token is not None:
        header_value = _decrypt_embedded_header(token.embedded_basic_auth_enc)

    if header_value is None:
        # Fallback: current env-var creds. Covers both "no token provided"
        # (e.g. tests) and "token created before embedding landed".
        resolved = await resolve_effective_auth(session)
        if resolved.active and resolved.env_plain_password is not None:
            header_value = build_client_authorization_header_value(
                resolved.username,
                resolved.env_plain_password,
            )

    if header_value:
        managed_installs_payload["AdditionalHttpHeaders"] = [header_value]

    profile: dict[str, object] = {
        "PayloadType": "Configuration",
        "PayloadVersion": 1,
        "PayloadIdentifier": f"{PROFILE_IDENTIFIER_PREFIX}.{profile_uuid_value}",
        "PayloadUUID": profile_uuid_value,
        "PayloadDisplayName": "Munki Manager client settings",
        "PayloadDescription": f"Points Munki at {base}",
        "PayloadOrganization": settings.app_name,
        # System-scoped because Munki runs as root and reads from
        # /Library/Preferences/ManagedInstalls.plist.
        "PayloadScope": "System",
        "PayloadContent": [managed_installs_payload],
    }

    return plistlib.dumps(profile, fmt=plistlib.FMT_XML, sort_keys=False)

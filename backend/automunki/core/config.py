from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _repo_root_env_file() -> str | None:
    """Prefer the monorepo root `.env` (next to `backend/`), not `backend/.env`.

    Layout: <repo>/backend/automunki/core/config.py → load <repo>/.env only.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "backend").is_dir() and (parent / ".env").is_file():
            return str(parent / ".env")
    legacy = here.parents[3] / ".env"
    return str(legacy) if legacy.is_file() else None


_env_file = _repo_root_env_file()
_settings_kwargs: dict = {"extra": "ignore"}
if _env_file:
    _settings_kwargs["env_file"] = _env_file
    _settings_kwargs["env_file_encoding"] = "utf-8"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(**_settings_kwargs)

    app_name: str = "Munki Manager"
    debug: bool = False

    database_url: str = "postgresql+asyncpg://automunki:automunki@localhost:5432/automunki"
    database_echo: bool = False

    secret_key: str = "change-me-in-production"
    #: How long an issued JWT remains valid. Default is 8 hours (one workday)
    #: because there is no refresh-token flow yet — when the token expires the
    #: SPA bounces the user to /login. The previous 1-hour default fired in
    #: the middle of the workday and looked like a backend cold start.
    #: Bump higher (e.g. 86400 = 24h, 604800 = 7d) for longer-lived sessions
    #: at the cost of stolen-token blast radius.
    jwt_lifetime_seconds: int = 28800

    github_token: str = ""
    github_repo: str = ""

    #: Storage backend selector for the auto-uploader that pushes AutoPkg run
    #: outputs to object storage. ``none`` = no backend (default; serve pkgs
    #: from whatever URL ``munki_repo_pkg_base_url`` points at). ``s3`` and
    #: ``azure_blob`` are parallel options that both materialise files at
    #: ``munki_repo_pkg_base_url`` for Munki clients. See
    #: ``docs/storage-backends.md``.
    storage_backend: Literal["none", "s3", "azure_blob"] = "none"

    #: AWS S3 / CloudFront — used when ``storage_backend == "s3"``. Also accepted
    #: as documentation for environments that point ``munki_repo_pkg_base_url``
    #: at an S3+CloudFront URL today (no backend code uses these yet).
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "us-east-1"
    aws_s3_bucket: str = ""
    cloudfront_distribution_id: str = ""

    #: Azure Blob Storage — used when ``storage_backend == "azure_blob"``. Either
    #: provide ``azure_storage_connection_string`` (full connection string), or
    #: ``azure_storage_account_name`` + a SAS token in ``azure_storage_sas_token``,
    #: or rely on managed identity when running in Azure (leave both empty and the
    #: SDK will use ``DefaultAzureCredential``).
    azure_storage_account_name: str = ""
    azure_storage_container: str = "munki-repo"
    azure_storage_connection_string: str = ""
    azure_storage_sas_token: str = ""
    #: Optional Azure CDN / Front Door endpoint to invalidate after upload (future).
    azure_cdn_profile: str = ""
    azure_cdn_endpoint: str = ""

    #: External URL written into enrolled clients' ``PackageURL``. When set,
    #: this env var pins the value and the Settings UI cannot override it.
    #: Empty = managed at runtime via ``/settings/munki-repo-urls``. Munki
    #: fetches installers directly from this URL (not via a redirect) because
    #: its downloader drops ``Authorization`` on cross-origin 302s.
    munki_repo_pkg_base_url: str = ""
    munki_repo_icon_base_url: str = ""
    #: External URL written into enrolled clients' ``ClientResourceURL``.
    #: Empty = managed at runtime (or auto-derived from ``munki_repo_pkg_base_url``
    #: by swapping the trailing path segment — ``.../pkgs`` → ``.../client_resources``).
    munki_repo_client_resources_base_url: str = ""

    #: When both are non-empty, ``/repo`` uses these for HTTP Basic (overrides DB).
    munki_repo_basic_auth_user: str = ""
    munki_repo_basic_auth_password: str = ""

    #: User profile avatars. Empty = ``<repo>/backend/data/user-avatars``.
    user_avatars_directory: str = ""

    api_public_url: str = ""

    #: Default AutoPkg execution target when the UI does not send ``runner``:
    #: ``github`` = dispatch GitHub Actions; ``local`` = create run only (execute on a Mac).
    autopkg_runner_mode: Literal["github", "local"] = "github"

    #: Shared secret for the local AutoPkg daemon (``poll_local_autopkg.sh``). When set,
    #: ``Authorization: Bearer <token>`` is accepted for claim, metadata-cache, run config,
    #: GET run by id, ``POST /autopkg/pkginfo/ingest``, and ``POST /autopkg/icons/ingest``
    #: (see RBAC middleware).
    local_runner_token: str = ""

    @field_validator("local_runner_token", mode="before")
    @classmethod
    def _normalize_local_runner_token(cls, v: object) -> str:
        if v is None or isinstance(v, bool):
            return ""
        s = str(v).replace("\r", "").strip()
        if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
            s = s[1:-1]
        return s

    #: When True, the API runs a background loop that fires due AutoPkg schedules every minute.
    #: Set False on all but one replica if you run multiple API instances.
    scheduler_enabled: bool = True

    #: Optional secret for ``POST /autopkg/schedules/run-due`` (e.g. GitHub Actions cron).
    #: Empty = endpoint disabled.
    schedule_webhook_secret: str = ""

    @field_validator("autopkg_runner_mode", mode="before")
    @classmethod
    def _normalize_autopkg_runner_mode(cls, v: object) -> str:
        if v in ("github", "local"):
            return str(v)
        return "github"

    slack_webhook_url: str = ""

    cors_origins: list[str] = ["http://localhost:3000"]

    #: ``disabled`` = dev bypass (full access, no login). ``jwt`` = local users only. ``oidc`` = OIDC + local.
    auth_mode: Literal["disabled", "jwt", "oidc"] = "disabled"

    #: When False, ``POST /auth/register`` returns 403 (use with ``auth_mode`` jwt or oidc).
    auth_registration_open: bool = True

    #: OIDC (used when ``auth_mode`` is ``oidc``)
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_authorization_endpoint: str = ""
    oidc_token_endpoint: str = ""
    oidc_userinfo_endpoint: str = ""
    oidc_redirect_url: str = ""
    #: Issuer string stored with ``oidc_sub`` (e.g. ``https://your-org.okta.com``).
    oidc_issuer: str = ""
    #: Space-separated OIDC scopes (e.g. ``openid email profile``).
    oidc_scopes: str = "openid email profile"

    #: Browser redirect target after OIDC login (must match IdP app registration).
    public_app_url: str = "http://localhost:3000"


settings = Settings()

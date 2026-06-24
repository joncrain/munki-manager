from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class AutoPkgRecipeBase(BaseModel):
    identifier: str
    name: str
    parent_recipe: str | None = None
    is_enabled: bool = True
    extract_icon_enabled: bool = False
    auto_promote: bool = False


class AutoPkgRecipeCreate(AutoPkgRecipeBase):
    source_repo_full_name: str | None = None
    override_data: dict | None = None
    trust_info: dict | None = None
    input_variables: dict | None = None
    github_repo: str | None = None
    recipe_path: str | None = None


class AutoPkgRecipeImportOverrideRequest(BaseModel):
    """Paste or upload an existing AutoPkg recipe override (plist XML, binary base64, or YAML/JSON)."""

    content: str
    name: str | None = None
    source_repo_full_name: str | None = None
    is_enabled: bool = True
    auto_promote: bool = False
    #: When true, resolve parent recipes on GitHub and populate ``trust_info`` (recommended).
    refresh_trust: bool = True


class AutoPkgRecipeUpdate(BaseModel):
    identifier: str | None = None
    name: str | None = None
    parent_recipe: str | None = None
    source_repo_full_name: str | None = None
    is_enabled: bool | None = None
    extract_icon_enabled: bool | None = None
    auto_promote: bool | None = None
    promotion_channel_id: UUID | None = None
    override_data: dict | None = None
    trust_info: dict | None = None
    input_variables: dict | None = None


class AutoPkgRecipeRead(AutoPkgRecipeBase):
    id: UUID
    promotion_channel_id: UUID | None = None
    source_repo_full_name: str | None = None
    override_data: dict | None = None
    trust_info: dict | None = None
    input_variables: dict | None = None
    trust_status: str = "unknown"
    trust_verified_at: datetime | None = None
    trust_approved_by: str | None = None
    trust_approved_at: datetime | None = None
    last_run_at: datetime | None = None
    last_run_status: str | None = None
    created_at: datetime
    updated_at: datetime
    #: Resolved from ``PkgInfo`` by the same key as the UI (``Input.NAME`` or recipe file name).
    pkginfo_display_name: str | None = None
    pkginfo_icon_name: str | None = None

    model_config = {"from_attributes": True}


class TriggerRunRequest(BaseModel):
    recipe_names: list[str] | None = None
    #: ``github`` = trigger GitHub Actions; ``local`` = register run for a local Mac only.
    runner: Literal["github", "local"] | None = None

    @field_validator("recipe_names", mode="before")
    @classmethod
    def _empty_recipe_list_to_none(cls, v: object) -> object:
        if v == []:
            return None
        return v


class VerifyTrustForRunRequest(BaseModel):
    """Same ``recipe_names`` semantics as ``TriggerRunRequest`` (``None`` = all runnable)."""

    recipe_names: list[str] | None = None

    @field_validator("recipe_names", mode="before")
    @classmethod
    def _empty_recipe_list_to_none(cls, v: object) -> object:
        if v == []:
            return None
        return v


class VerifyTrustForRunRecipeResult(BaseModel):
    recipe_id: str
    name: str
    status: str
    diff: dict | None = None
    error: str | None = None


class VerifyTrustForRunResponse(BaseModel):
    results: list[VerifyTrustForRunRecipeResult]
    rate_limited: bool = False


class AutoPkgScheduleCreate(BaseModel):
    name: str
    cron_expression: str
    timezone: str = "UTC"
    recipe_names: list[str] | None = None
    runner: Literal["github", "local"] = "github"
    enabled: bool = True

    @field_validator("recipe_names", mode="before")
    @classmethod
    def _empty_recipe_list_to_none(cls, v: object) -> object:
        if v == []:
            return None
        return v


class AutoPkgScheduleUpdate(BaseModel):
    name: str | None = None
    cron_expression: str | None = None
    timezone: str | None = None
    recipe_names: list[str] | None = None
    runner: Literal["github", "local"] | None = None
    enabled: bool | None = None

    @field_validator("recipe_names", mode="before")
    @classmethod
    def _empty_recipe_list_to_none(cls, v: object) -> object:
        if v == []:
            return None
        return v


class AutoPkgScheduleRead(BaseModel):
    id: UUID
    name: str
    cron_expression: str
    timezone: str
    recipe_names: list[str] | None = None
    runner_type: str
    enabled: bool
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RunResultCreate(BaseModel):
    recipe_identifier: str
    recipe_name: str
    status: str
    imported_version: str | None = None
    imported_display_name: str | None = None
    imported_pkg_path: str | None = None
    imported_pkg_url: str | None = None
    imported_pkginfo_path: str | None = None
    imported_catalogs: list[str] | None = None
    virustotal_results: dict | None = None
    trust_info_diff: dict | None = None
    log_output: str | None = None
    error_message: str | None = None
    duration_seconds: int | None = None


class RunResultRead(BaseModel):
    id: UUID
    recipe_identifier: str
    recipe_name: str
    status: str
    imported_version: str | None = None
    imported_display_name: str | None = None
    imported_pkg_path: str | None = None
    imported_pkg_url: str | None = None
    imported_pkginfo_path: str | None = None
    imported_catalogs: list[str] | None = None
    virustotal_results: dict | None = None
    trust_info_diff: dict | None = None
    approval_status: str
    approved_by: str | None = None
    approved_at: datetime | None = None
    approval_comment: str | None = None
    log_output: str | None = None
    error_message: str | None = None
    duration_seconds: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class GitHubRunContextUpdate(BaseModel):
    """Posted by the GitHub Actions runner so the UI can link to the workflow run."""

    github_run_id: str
    github_run_url: str


class AutoPkgRunFailUpdate(BaseModel):
    """Posted when the GitHub Actions job aborts before a normal ``/complete``."""

    error_message: str
    failed_step: str | None = None


class AutoPkgRunRead(BaseModel):
    id: UUID
    status: str
    trigger_type: str
    triggered_by: str | None = None
    runner_type: str = "github"
    github_run_id: str | None = None
    github_run_url: str | None = None
    recipe_filter: list[str] | None = None
    total_recipes: int | None = None
    recipes_succeeded: int | None = None
    recipes_failed: int | None = None
    recipes_imported: int | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    results: list[RunResultRead] = []
    schedule_id: UUID | None = None
    schedule_name: str | None = None

    model_config = {"from_attributes": True}


class ApprovalRequest(BaseModel):
    approved: bool
    comment: str | None = None


# ── Trust change request schemas ─────────────────────────────────────────


class TrustChangeRequestRead(BaseModel):
    id: UUID
    recipe_id: UUID
    old_trust_info: dict | None = None
    new_trust_info: dict | None = None
    diff: dict | None = None
    status: str
    requested_at: datetime
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    comment: str | None = None

    model_config = {"from_attributes": True}


class TrustPendingCountResponse(BaseModel):
    """Count of trust change requests awaiting review."""

    count: int


class RecipeTrustSummaryResponse(BaseModel):
    """Counts of recipe overrides per ``trust_status`` (dashboard)."""

    verified: int = 0
    failed: int = 0
    pending_approval: int = 0
    unknown: int = 0


class TrustApprovalRequest(BaseModel):
    approved: bool
    comment: str | None = None


class TrustCommitResolveRequest(BaseModel):
    """Resolve a Git commit that introduced a trust file hash change."""

    github_repo: str
    github_path: str
    new_sha256: str
    old_sha256: str | None = None


class TrustCommitResolveResponse(BaseModel):
    commit_sha: str | None = None
    commit_url: str | None = None


# ── GitHub recipe cache schemas ──────────────────────────────────────────


class GitHubRecipeRepoRead(BaseModel):
    id: UUID
    full_name: str
    name: str
    html_url: str
    clone_url: str | None = None
    description: str | None = None
    stars: int = 0
    updated_at: str | None = None
    default_branch: str | None = None
    synced_at: datetime
    is_custom: bool = False
    cached_recipes: list["GitHubRecipeRead"] = []

    model_config = {"from_attributes": True}


class GitHubCustomRepoAdd(BaseModel):
    """GitHub ``owner/repo`` to add to the local discover cache (any public repo)."""

    full_name: str

    @field_validator("full_name")
    @classmethod
    def strip_full_name(cls, v: str) -> str:
        return v.strip()


class GitHubRecipeRead(BaseModel):
    id: UUID
    repo_id: UUID
    name: str
    filename: str
    path: str
    identifier_guess: str
    url: str

    model_config = {"from_attributes": True}


# ── Pkginfo ingestion schema ────────────────────────────────────────────


class PkgInfoIngest(BaseModel):
    """Accepts the full pkginfo plist content as a dict for ingestion."""

    pkginfo: dict
    recipe_identifier: str | None = Field(
        default=None,
        description=(
            "When set, Input.pkginfo from that AutoPkg recipe is merged over the plist "
            "(authoritative except name/version, which stay on the ingested plist)."
        ),
    )


# ── Metadata cache schemas ───────────────────────────────────────────────


class MetadataCacheRead(BaseModel):
    cache_data: dict
    updated_at: datetime

    model_config = {"from_attributes": True}


class MetadataCacheWrite(BaseModel):
    cache_data: dict

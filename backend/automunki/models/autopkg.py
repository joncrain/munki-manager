import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from automunki.models.base import Base, UUIDMixin


class RunStatus(enum.StrEnum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class RunTriggerType(enum.StrEnum):
    scheduled = "scheduled"
    manual_ui = "manual_ui"
    manual_api = "manual_api"
    workflow_dispatch = "workflow_dispatch"


class RecipeResultStatus(enum.StrEnum):
    success = "success"
    imported = "imported"
    no_change = "no_change"
    failed = "failed"
    trust_failed = "trust_failed"


class ApprovalStatus(enum.StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    auto_approved = "auto_approved"


class GitHubRecipeRepo(UUIDMixin, Base):
    """Locally cached GitHub autopkg recipe repository metadata."""

    __tablename__ = "github_recipe_repo"

    full_name: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    html_url: Mapped[str] = mapped_column(Text, nullable=False)
    clone_url: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    stars: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[str | None] = mapped_column(Text)
    default_branch: Mapped[str | None] = mapped_column(Text)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    is_custom: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    cached_recipes: Mapped[list["GitHubRecipe"]] = relationship(
        back_populates="repo", cascade="all, delete-orphan", lazy="selectin"
    )


class GitHubRecipe(UUIDMixin, Base):
    """Locally cached recipe file from a GitHub autopkg repo."""

    __tablename__ = "github_recipe"

    repo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("github_recipe_repo.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    identifier_guess: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)

    repo: Mapped["GitHubRecipeRepo"] = relationship(back_populates="cached_recipes")


class TrustStatus(enum.StrEnum):
    unknown = "unknown"
    verified = "verified"
    failed = "failed"
    pending_approval = "pending_approval"


class AutoPkgRecipe(UUIDMixin, Base):
    __tablename__ = "autopkg_recipe"

    identifier: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    parent_recipe: Mapped[str | None] = mapped_column(Text)
    source_repo_full_name: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    override_data: Mapped[dict | None] = mapped_column(JSONB)
    trust_info: Mapped[dict | None] = mapped_column(JSONB)
    input_variables: Mapped[dict | None] = mapped_column(JSONB)

    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    #: When true, runner plist sets ``Input.extract_icon`` so MunkiImporter extracts a PNG.
    extract_icon_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    auto_promote: Mapped[bool] = mapped_column(Boolean, default=False)

    promotion_channel_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("munki_promotion_channel.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    trust_status: Mapped[str] = mapped_column(Text, default="unknown", server_default="unknown")
    trust_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trust_approved_by: Mapped[str | None] = mapped_column(Text)
    trust_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_run_status: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    trust_change_requests: Mapped[list["TrustChangeRequest"]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan", lazy="selectin"
    )


class TrustChangeRequestStatus(enum.StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class TrustChangeRequest(UUIDMixin, Base):
    __tablename__ = "autopkg_trust_change_request"

    recipe_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("autopkg_recipe.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    old_trust_info: Mapped[dict | None] = mapped_column(JSONB)
    new_trust_info: Mapped[dict | None] = mapped_column(JSONB)
    diff: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(Text, default="pending", server_default="pending")
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reviewed_by: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    comment: Mapped[str | None] = mapped_column(Text)

    recipe: Mapped["AutoPkgRecipe"] = relationship(back_populates="trust_change_requests")


class AutoPkgSchedule(UUIDMixin, Base):
    """Cron schedule for AutoPkg runs (GitHub Actions or local runner)."""

    __tablename__ = "autopkg_schedule"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    cron_expression: Mapped[str] = mapped_column(Text, nullable=False)
    timezone: Mapped[str] = mapped_column(Text, nullable=False, server_default="UTC")
    recipe_names: Mapped[list | None] = mapped_column(JSONB)
    runner_type: Mapped[str] = mapped_column(Text, nullable=False, server_default="github")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    runs: Mapped[list["AutoPkgRun"]] = relationship(back_populates="schedule")


class AutoPkgRun(UUIDMixin, Base):
    __tablename__ = "autopkg_run"

    schedule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("autopkg_schedule.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    status: Mapped[RunStatus] = mapped_column(
        Enum(RunStatus, name="run_status_enum", native_enum=True),
        nullable=False,
        default=RunStatus.pending,
    )
    trigger_type: Mapped[RunTriggerType] = mapped_column(
        Enum(RunTriggerType, name="run_trigger_type_enum", native_enum=True),
        nullable=False,
    )
    triggered_by: Mapped[str | None] = mapped_column(Text)
    # github = GitHub Actions; local = Mac runner (see docs/local-autopkg-runner.md)
    runner_type: Mapped[str] = mapped_column(Text, nullable=False, default="github", server_default="github")
    github_run_id: Mapped[str | None] = mapped_column(Text)
    github_run_url: Mapped[str | None] = mapped_column(Text)

    recipe_filter: Mapped[list | None] = mapped_column(JSONB)
    total_recipes: Mapped[int | None] = mapped_column(Integer)
    recipes_succeeded: Mapped[int | None] = mapped_column(Integer)
    recipes_failed: Mapped[int | None] = mapped_column(Integer)
    recipes_imported: Mapped[int | None] = mapped_column(Integer)

    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    schedule: Mapped["AutoPkgSchedule | None"] = relationship(back_populates="runs")

    results: Mapped[list["AutoPkgRunResult"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", lazy="selectin"
    )


class AutoPkgRunResult(UUIDMixin, Base):
    __tablename__ = "autopkg_run_result"

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("autopkg_run.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    recipe_identifier: Mapped[str] = mapped_column(Text, nullable=False)
    recipe_name: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[RecipeResultStatus] = mapped_column(
        Enum(RecipeResultStatus, name="recipe_result_status_enum", native_enum=True),
        nullable=False,
    )

    imported_version: Mapped[str | None] = mapped_column(Text)
    imported_display_name: Mapped[str | None] = mapped_column(Text)
    imported_pkg_path: Mapped[str | None] = mapped_column(Text)
    #: Public URL the storage backend returned after streaming the pkg/dmg bytes
    #: into S3/Azure Blob. Set by ``POST /autopkg/runs/{id}/pkgs`` and read by
    #: ``pkginfo/ingest`` so ``installer_item_location`` follows the actual upload
    #: rather than ``MUNKI_REPO_PKG_BASE_URL + relative path`` heuristics.
    imported_pkg_url: Mapped[str | None] = mapped_column(Text)
    imported_pkginfo_path: Mapped[str | None] = mapped_column(Text)
    imported_catalogs: Mapped[list | None] = mapped_column(JSONB)

    virustotal_results: Mapped[dict | None] = mapped_column(JSONB)
    trust_info_diff: Mapped[dict | None] = mapped_column(JSONB)

    approval_status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus, name="approval_status_enum", native_enum=True),
        nullable=False,
        default=ApprovalStatus.auto_approved,
    )
    approved_by: Mapped[str | None] = mapped_column(Text)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approval_comment: Mapped[str | None] = mapped_column(Text)

    log_output: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)

    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    run: Mapped["AutoPkgRun"] = relationship(back_populates="results")


class AutoPkgMetadataCacheEntry(UUIDMixin, Base):
    """Per-recipe metadata cache (ETags, paths) for the cloud AutoPkg runner."""

    __tablename__ = "autopkg_metadata_cache_entry"

    recipe_key: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    entry: Mapped[dict] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

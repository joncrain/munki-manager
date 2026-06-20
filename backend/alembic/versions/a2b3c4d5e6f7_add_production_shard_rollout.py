"""Add production shard rollout columns.

Revision ID: a2b3c4d5e6f7
Revises: a1b2c3d4e5f7
Create Date: 2026-06-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a2b3c4d5e6f7"
down_revision: str | None = "a1b2c3d4e5f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

shard_rollout_status_enum = sa.Enum(
    "none",
    "pending_approval",
    "active",
    "complete",
    "paused",
    "skipped",
    name="shard_rollout_status_enum",
)
shard_override_enum = sa.Enum("pause", "force_complete", name="shard_override_enum")
net_new_shard_policy_enum = sa.Enum(
    "skip_until_approved",
    "immediate_full",
    "same_as_upgrades",
    name="net_new_shard_policy_enum",
)


def upgrade() -> None:
    shard_rollout_status_enum.create(op.get_bind(), checkfirst=True)
    shard_override_enum.create(op.get_bind(), checkfirst=True)
    net_new_shard_policy_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "munki_pkginfo",
        sa.Column(
            "shard_rollout_status",
            shard_rollout_status_enum,
            nullable=False,
            server_default="none",
        ),
    )
    op.add_column(
        "munki_pkginfo",
        sa.Column("shard_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "munki_pkginfo",
        sa.Column("shard_percent", sa.Integer(), nullable=True),
    )
    op.add_column(
        "munki_pkginfo",
        sa.Column("shard_override", shard_override_enum, nullable=True),
    )

    op.add_column(
        "app_workflow_preferences",
        sa.Column("production_shard_days", sa.Integer(), nullable=False, server_default="4"),
    )
    op.add_column(
        "app_workflow_preferences",
        sa.Column("production_shard_enabled", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.add_column(
        "app_workflow_preferences",
        sa.Column(
            "net_new_shard_policy",
            net_new_shard_policy_enum,
            nullable=False,
            server_default="skip_until_approved",
        ),
    )


def downgrade() -> None:
    op.drop_column("app_workflow_preferences", "net_new_shard_policy")
    op.drop_column("app_workflow_preferences", "production_shard_enabled")
    op.drop_column("app_workflow_preferences", "production_shard_days")

    op.drop_column("munki_pkginfo", "shard_override")
    op.drop_column("munki_pkginfo", "shard_percent")
    op.drop_column("munki_pkginfo", "shard_started_at")
    op.drop_column("munki_pkginfo", "shard_rollout_status")

    net_new_shard_policy_enum.drop(op.get_bind(), checkfirst=True)
    shard_override_enum.drop(op.get_bind(), checkfirst=True)
    shard_rollout_status_enum.drop(op.get_bind(), checkfirst=True)

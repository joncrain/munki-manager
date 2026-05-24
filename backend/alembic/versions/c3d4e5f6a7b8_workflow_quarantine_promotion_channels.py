"""Quarantine catalog flag, pending import catalogs, promotion channels, workflow prefs.

Revision ID: c3d4e5f6a7b8
Revises: a1b2c3d4e5f6
Create Date: 2026-04-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "munki_promotion_channel",
        sa.Column(
            "id",
            sa.UUID(),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_munki_promotion_channel")),
        sa.UniqueConstraint("name", name=op.f("uq_munki_promotion_channel_name")),
    )

    op.create_table(
        "munki_promotion_channel_step",
        sa.Column(
            "id",
            sa.UUID(),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("channel_id", sa.UUID(), nullable=False),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column("source_catalog_id", sa.UUID(), nullable=False),
        sa.Column("target_catalog_id", sa.UUID(), nullable=False),
        sa.Column("dwell_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("requires_manual_approval", sa.Boolean(), nullable=False, server_default="false"),
        sa.ForeignKeyConstraint(
            ["channel_id"],
            ["munki_promotion_channel.id"],
            name=op.f("fk_munki_promotion_channel_step_channel_id_munki_promotion_channel"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_catalog_id"],
            ["munki_catalog.id"],
            name=op.f("fk_munki_promotion_channel_step_source_catalog_id_munki_catalog"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_catalog_id"],
            ["munki_catalog.id"],
            name=op.f("fk_munki_promotion_channel_step_target_catalog_id_munki_catalog"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_munki_promotion_channel_step")),
        sa.UniqueConstraint(
            "channel_id",
            "step_order",
            name=op.f("uq_munki_promotion_channel_step_channel_step"),
        ),
    )
    op.create_index(
        op.f("ix_munki_promotion_channel_step_channel_id"),
        "munki_promotion_channel_step",
        ["channel_id"],
        unique=False,
    )

    op.create_table(
        "app_workflow_preferences",
        sa.Column("id", sa.SmallInteger(), nullable=False),
        sa.Column("default_promotion_channel_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(
            ["default_promotion_channel_id"],
            ["munki_promotion_channel.id"],
            name=op.f("fk_app_workflow_preferences_default_promotion_channel_id"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_app_workflow_preferences")),
    )
    op.execute(
        sa.text(
            "INSERT INTO app_workflow_preferences (id, default_promotion_channel_id) VALUES (1, NULL)"
        )
    )

    op.add_column(
        "autopkg_recipe",
        sa.Column("promotion_channel_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_autopkg_recipe_promotion_channel_id_munki_promotion_channel"),
        "autopkg_recipe",
        "munki_promotion_channel",
        ["promotion_channel_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_autopkg_recipe_promotion_channel_id"),
        "autopkg_recipe",
        ["promotion_channel_id"],
        unique=False,
    )

    op.add_column(
        "munki_catalog",
        sa.Column(
            "is_quarantine",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )

    op.add_column(
        "munki_pkginfo",
        sa.Column("pending_catalog_names", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    op.add_column(
        "munki_pkginfo_catalog",
        sa.Column(
            "entered_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("munki_pkginfo_catalog", "entered_at")
    op.drop_column("munki_pkginfo", "pending_catalog_names")
    op.drop_column("munki_catalog", "is_quarantine")

    op.drop_index(op.f("ix_autopkg_recipe_promotion_channel_id"), table_name="autopkg_recipe")
    op.drop_constraint(
        op.f("fk_autopkg_recipe_promotion_channel_id_munki_promotion_channel"),
        "autopkg_recipe",
        type_="foreignkey",
    )
    op.drop_column("autopkg_recipe", "promotion_channel_id")

    op.drop_table("app_workflow_preferences")

    op.drop_index(
        op.f("ix_munki_promotion_channel_step_channel_id"),
        table_name="munki_promotion_channel_step",
    )
    op.drop_table("munki_promotion_channel_step")
    op.drop_table("munki_promotion_channel")

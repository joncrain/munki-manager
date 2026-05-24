"""Add autopkg_schedule and autopkg_run.schedule_id.

Revision ID: u6v7w8x9y0z1
Revises: t5u6v7w8x9y0
Create Date: 2026-03-25

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "u6v7w8x9y0z1"
down_revision: str | None = "t5u6v7w8x9y0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "autopkg_schedule",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("cron_expression", sa.Text(), nullable=False),
        sa.Column("timezone", sa.Text(), nullable=False, server_default="UTC"),
        sa.Column("recipe_names", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("runner_type", sa.Text(), nullable=False, server_default="github"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_autopkg_schedule_enabled"), "autopkg_schedule", ["enabled"], unique=False)
    op.add_column(
        "autopkg_run",
        sa.Column("schedule_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(op.f("ix_autopkg_run_schedule_id"), "autopkg_run", ["schedule_id"], unique=False)
    op.create_foreign_key(
        "fk_autopkg_run_schedule_id_autopkg_schedule",
        "autopkg_run",
        "autopkg_schedule",
        ["schedule_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_autopkg_run_schedule_id_autopkg_schedule", "autopkg_run", type_="foreignkey")
    op.drop_index(op.f("ix_autopkg_run_schedule_id"), table_name="autopkg_run")
    op.drop_column("autopkg_run", "schedule_id")
    op.drop_index(op.f("ix_autopkg_schedule_enabled"), table_name="autopkg_schedule")
    op.drop_table("autopkg_schedule")

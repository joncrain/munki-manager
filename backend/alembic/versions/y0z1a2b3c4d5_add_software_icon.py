"""Add software_icon table for DB-backed icon hosting.

Revision ID: y0z1a2b3c4d5
Revises: x9y0z1a2b3c4
Create Date: 2026-04-16

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "y0z1a2b3c4d5"
down_revision: str | None = "x9y0z1a2b3c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "software_icon",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False, server_default="image/png"),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
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
        sa.UniqueConstraint("name", name="uq_software_icon_name"),
    )
    op.create_index("ix_software_icon_name", "software_icon", ["name"])
    op.create_index("ix_software_icon_sha256", "software_icon", ["sha256"])


def downgrade() -> None:
    op.drop_index("ix_software_icon_sha256", table_name="software_icon")
    op.drop_index("ix_software_icon_name", table_name="software_icon")
    op.drop_table("software_icon")

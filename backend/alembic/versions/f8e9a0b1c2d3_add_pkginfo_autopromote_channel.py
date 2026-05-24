"""Store per-pkginfo AutoPkg promotion (channel + auto_promote) for scheduler + UI.

Revision ID: f8e9a0b1c2d3
Revises: e1f2a3b4c5d6
Create Date: 2026-04-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f8e9a0b1c2d3"
down_revision: str | None = "e1f2a3b4c5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "munki_pkginfo",
        sa.Column("auto_promote", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "munki_pkginfo",
        sa.Column(
            "promotion_channel_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("munki_promotion_channel.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_munki_pkginfo_promotion_channel_id", "munki_pkginfo", ["promotion_channel_id"])


def downgrade() -> None:
    op.drop_index("ix_munki_pkginfo_promotion_channel_id", table_name="munki_pkginfo")
    op.drop_column("munki_pkginfo", "promotion_channel_id")
    op.drop_column("munki_pkginfo", "auto_promote")

"""Add per-pkginfo manual shard percent override.

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-06-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b3c4d5e6f7a8"
down_revision: str | None = "a2b3c4d5e6f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "munki_pkginfo",
        sa.Column("shard_percent_override", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("munki_pkginfo", "shard_percent_override")

"""Drop redundant is_override from autopkg_recipe (all rows are managed overrides).

Revision ID: e1f2a3b4c5d6
Revises: d4e5f6a7b8c9
Create Date: 2026-04-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e1f2a3b4c5d6"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("autopkg_recipe", "is_override")


def downgrade() -> None:
    op.add_column(
        "autopkg_recipe",
        sa.Column("is_override", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.execute("UPDATE autopkg_recipe SET is_override = true")
    op.alter_column("autopkg_recipe", "is_override", server_default=None)

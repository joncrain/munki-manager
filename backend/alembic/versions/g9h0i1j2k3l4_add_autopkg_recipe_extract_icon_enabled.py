"""Add extract_icon_enabled to autopkg_recipe.

Revision ID: g9h0i1j2k3l4
Revises: f8e9a0b1c2d3
Create Date: 2026-04-24

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "g9h0i1j2k3l4"
down_revision = "f8e9a0b1c2d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "autopkg_recipe",
        sa.Column(
            "extract_icon_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.alter_column("autopkg_recipe", "extract_icon_enabled", server_default=None)


def downgrade() -> None:
    op.drop_column("autopkg_recipe", "extract_icon_enabled")

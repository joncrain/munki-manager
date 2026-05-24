"""Add imported_pkg_url to autopkg_run_result.

Revision ID: a7c8e9f0a1b2
Revises: g9h0i1j2k3l4
Create Date: 2026-05-09

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a7c8e9f0a1b2"
down_revision = "g9h0i1j2k3l4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "autopkg_run_result",
        sa.Column("imported_pkg_url", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("autopkg_run_result", "imported_pkg_url")

"""Add pending_metadata flag to munki_pkginfo.

Revision ID: a8c9e0f1a2b3
Revises: a7c8e9f0a1b2
Create Date: 2026-05-09

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a8c9e0f1a2b3"
down_revision = "a7c8e9f0a1b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "munki_pkginfo",
        sa.Column(
            "pending_metadata",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.alter_column("munki_pkginfo", "pending_metadata", server_default=None)


def downgrade() -> None:
    op.drop_column("munki_pkginfo", "pending_metadata")

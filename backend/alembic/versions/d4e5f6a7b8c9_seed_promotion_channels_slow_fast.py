"""Seed default promotion channel names (no steps).

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-04-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO munki_promotion_channel (name, description, created_at, updated_at)
            SELECT 'slow', 'Slower catalog transitions (add steps under Catalogs / Approvals).', now(), now()
            WHERE NOT EXISTS (SELECT 1 FROM munki_promotion_channel WHERE name = 'slow')
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO munki_promotion_channel (name, description, created_at, updated_at)
            SELECT 'fast', 'Faster catalog transitions (add steps with shorter dwell).', now(), now()
            WHERE NOT EXISTS (SELECT 1 FROM munki_promotion_channel WHERE name = 'fast')
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM munki_promotion_channel WHERE name IN ('slow', 'fast')"))

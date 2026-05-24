"""Add embedded_basic_auth_enc to enrollment_token.

Revision ID: x9y0z1a2b3c4
Revises: w8x9y0z1a2b3
Create Date: 2026-04-16

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "x9y0z1a2b3c4"
down_revision: str | None = "w8x9y0z1a2b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "enrollment_token",
        sa.Column("embedded_basic_auth_enc", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("enrollment_token", "embedded_basic_auth_enc")

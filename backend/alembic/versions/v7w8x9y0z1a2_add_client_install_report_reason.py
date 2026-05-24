"""Add install_reason to client_install_report.

Revision ID: v7w8x9y0z1a2
Revises: u6v7w8x9y0z1
Create Date: 2026-03-26

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "v7w8x9y0z1a2"
down_revision: str | None = "u6v7w8x9y0z1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "client_install_report",
        sa.Column("install_reason", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("client_install_report", "install_reason")

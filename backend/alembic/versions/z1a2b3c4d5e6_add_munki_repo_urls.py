"""Add munki_repo_urls singleton table.

Revision ID: z1a2b3c4d5e6
Revises: y0z1a2b3c4d5
Create Date: 2026-04-16

Holds external ``PackageURL`` and ``ClientResourceURL`` written into the
client ``.mobileconfig``. Starts with a single pre-seeded row (id=1) with
both columns empty.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "z1a2b3c4d5e6"
down_revision: str | None = "y0z1a2b3c4d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "munki_repo_urls",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("package_url", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "client_resource_url",
            sa.Text(),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        sa.text(
            "INSERT INTO munki_repo_urls (id, package_url, client_resource_url) "
            "VALUES (1, '', '')"
        )
    )


def downgrade() -> None:
    op.drop_table("munki_repo_urls")

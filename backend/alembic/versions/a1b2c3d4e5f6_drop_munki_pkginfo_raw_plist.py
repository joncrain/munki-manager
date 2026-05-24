"""Drop redundant raw_plist column from munki_pkginfo.

The column duplicated ``_pkginfo_to_dict`` output; catalogs and exports always
use normalized columns.

Revision ID: a1b2c3d4e5f6
Revises: z1a2b3c4d5e6
Create Date: 2026-04-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "z1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("munki_pkginfo", "raw_plist")


def downgrade() -> None:
    op.add_column(
        "munki_pkginfo",
        sa.Column("raw_plist", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

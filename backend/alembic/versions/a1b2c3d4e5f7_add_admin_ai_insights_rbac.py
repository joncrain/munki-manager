"""Add admin.ai_insights RBAC page key permissions.

Revision ID: a1b2c3d4e5f7
Revises: b9d0f1a2b3c4
Create Date: 2026-06-17

"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

revision: str = "a1b2c3d4e5f7"
down_revision: str | None = "b9d0f1a2b3c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLE_VIEWER = "a1111111-1111-4111-8111-111111111101"
ROLE_EDITOR = "a1111111-1111-4111-8111-111111111102"
ROLE_ADMIN = "a1111111-1111-4111-8111-111111111103"

PAGE_KEY = "admin.ai_insights"


def upgrade() -> None:
    conn = op.get_bind()
    ins = text(
        """
        INSERT INTO role_permission (role_id, page_key, access_level)
        VALUES (:rid, :pk, CAST(:al AS access_level_enum))
        ON CONFLICT (role_id, page_key) DO NOTHING
        """
    )
    for rid, al in (
        (ROLE_VIEWER, "none"),
        (ROLE_EDITOR, "none"),
        (ROLE_ADMIN, "write"),
    ):
        conn.execute(ins, {"rid": rid, "pk": PAGE_KEY, "al": al})


def downgrade() -> None:
    op.execute(
        text("DELETE FROM role_permission WHERE page_key = :pk").bindparams(pk=PAGE_KEY)
    )

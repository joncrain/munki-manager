"""Seed read-only demo user with Viewer role.

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-06-23

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision: str = "c4d5e6f7a8b9"
down_revision: str | None = "b3c4d5e6f7a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEMO_USER_ID = "00000000-0000-4000-8000-000000000002"
DEMO_USER_EMAIL = "demo@automunki.internal"
ROLE_VIEWER = "a1111111-1111-4111-8111-111111111101"
# Argon2 hash of a random secret — demo access is only via POST /auth/demo.
DEMO_HASHED_PASSWORD = (
    "$argon2id$v=19$m=65536,t=3,p=4$GzeVAXPxw5X1Kpm9ii3H0g$Ss1eN+E1eXE4bRTgbAJT7CUHIddQe57jDw6h/BaGTrM"
)


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        text(
            """
            INSERT INTO "user" (
                id, email, hashed_password, is_active, is_superuser, is_verified,
                role, display_name
            )
            VALUES (
                CAST(:uid AS uuid), :email, :hash, true, false, true,
                'viewer', 'Demo viewer'
            )
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {
            "uid": DEMO_USER_ID,
            "email": DEMO_USER_EMAIL,
            "hash": DEMO_HASHED_PASSWORD,
        },
    )
    conn.execute(
        text(
            """
            INSERT INTO user_role (user_id, role_id)
            VALUES (CAST(:uid AS uuid), CAST(:rid AS uuid))
            ON CONFLICT (user_id, role_id) DO NOTHING
            """
        ),
        {"uid": DEMO_USER_ID, "rid": ROLE_VIEWER},
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        text("DELETE FROM user_role WHERE user_id = CAST(:uid AS uuid)").bindparams(uid=DEMO_USER_ID)
    )
    conn.execute(text('DELETE FROM "user" WHERE id = CAST(:uid AS uuid)').bindparams(uid=DEMO_USER_ID))

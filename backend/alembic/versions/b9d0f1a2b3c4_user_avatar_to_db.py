"""Move user avatars from on-disk storage to Postgres.

Revision ID: b9d0f1a2b3c4
Revises: a8c9e0f1a2b3
Create Date: 2026-05-25

Avatars used to live under ``USER_AVATARS_DIRECTORY`` on the backend
container's local filesystem. On Azure Container Apps that's an ephemeral
overlay: every revision restart wipes the upload, and uploads from one
replica are invisible to the others. Locally with a single uvicorn
process and a real disk it appeared to work — masking the production bug.

Storing 1 MB-or-less PNG/JPEG bytes inline in Postgres is the simplest
correct fix. ``user`` is small (single-digit row count for a typical
deployment), every user has at most one avatar, and TOAST handles the
out-of-page storage transparently. We add ``avatar_data`` (bytea) and
``avatar_media_type`` (text) and drop ``avatar_filename`` — the on-disk
files were never persistent on Azure, so there is nothing to migrate
forward. Existing operators will see their avatars revert and need to
re-upload once.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b9d0f1a2b3c4"
down_revision = "a8c9e0f1a2b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user", sa.Column("avatar_data", sa.LargeBinary(), nullable=True))
    op.add_column("user", sa.Column("avatar_media_type", sa.Text(), nullable=True))
    op.drop_column("user", "avatar_filename")


def downgrade() -> None:
    op.add_column("user", sa.Column("avatar_filename", sa.Text(), nullable=True))
    op.drop_column("user", "avatar_media_type")
    op.drop_column("user", "avatar_data")

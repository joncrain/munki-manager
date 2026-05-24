"""One-time Mac client enrollment tokens.

A token is created by an admin in the UI, handed to the user, and redeemed once
to download a configuration profile that points Munki at this server. Tokens
are **hashed at rest** (SHA-256) and never stored in plaintext after creation.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from automunki.models.base import Base, UUIDMixin


class EnrollmentToken(UUIDMixin, Base):
    __tablename__ = "enrollment_token"

    #: SHA-256 hex digest of the raw token. Unique so lookups are O(1).
    token_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)

    #: Optional human label (e.g. "jon's MacBook Pro" or "finance team batch").
    label: Mapped[str | None] = mapped_column(Text)

    #: Optional default Munki ClientIdentifier (manifest name) to bake into the profile.
    #: When empty, the generated profile omits it and Munki falls back to hostname.
    manifest_name: Mapped[str | None] = mapped_column(Text)

    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    #: Encrypted (Fernet, keyed off ``SECRET_KEY``) ``Authorization: Basic …``
    #: header. Populated only when the admin supplies the repo Basic auth
    #: password at token creation (or when env-var mode was active so the
    #: server already held the plaintext). Cleared on redeem.
    embedded_basic_auth_enc: Mapped[str | None] = mapped_column(Text)

    #: User that created the token (admin). Nullable so `AUTH_MODE=disabled` still works.
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

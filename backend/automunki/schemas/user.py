import uuid
from datetime import datetime

from fastapi_users import schemas
from pydantic import ConfigDict, model_validator


class UserRead(schemas.BaseUser[uuid.UUID]):
    """Wire-format user record returned by ``/auth/me`` and the users router.

    ``has_avatar`` is the only avatar-related field on the wire. The bytes
    themselves live in ``user.avatar_data`` (deferred-loaded ``LargeBinary``)
    and are only ever fetched by the dedicated ``GET /users/me/avatar``
    endpoint — we never serialize them inline. The boolean is derived from
    ``avatar_media_type`` because (a) it's tiny so it's safe to load on every
    request and (b) it's the most authoritative signal that a usable image
    was stored.
    """

    model_config = ConfigDict(from_attributes=True)

    display_name: str | None = None
    role: str = "viewer"
    updated_at: datetime | None = None
    has_avatar: bool = False

    @model_validator(mode="before")
    @classmethod
    def _derive_has_avatar(cls, data: object) -> object:
        # ``model_validate(orm_user)`` hands us the SQLAlchemy row; pull the
        # private indicator without forcing the deferred bytes column to load.
        if hasattr(data, "avatar_media_type"):
            return {
                **{c: getattr(data, c) for c in cls.model_fields if hasattr(data, c) and c != "has_avatar"},
                "has_avatar": getattr(data, "avatar_media_type", None) is not None,
            }
        return data


class UserCreate(schemas.BaseUserCreate):
    display_name: str | None = None


class UserUpdate(schemas.BaseUserUpdate):
    display_name: str | None = None

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from automunki.api.deps import get_session
from automunki.api.routes.oidc import router as oidc_router
from automunki.core.config import settings
from automunki.core.page_keys import ALL_PAGE_KEYS
from automunki.core.rbac_middleware import DEV_USER_EMAIL, DEV_USER_ID
from automunki.core.security import auth_backend, current_active_user, fastapi_users
from automunki.models.user import User
from automunki.schemas.auth_config import AuthConfigResponse
from automunki.schemas.auth_me import MeResponse
from automunki.schemas.user import UserCreate, UserRead, UserUpdate
from automunki.services.permissions import get_effective_permissions
from automunki.services.user_avatars import detect_image

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/config", response_model=AuthConfigResponse)
async def auth_config():
    """Expose ``AUTH_MODE`` so the SPA can read it at runtime."""
    registration_open = settings.auth_registration_open and settings.auth_mode != "disabled"
    return AuthConfigResponse(
        auth_mode=settings.auth_mode,
        registration_open=registration_open,
    )


@router.get("/me", response_model=MeResponse)
async def read_me(request: Request, session: AsyncSession = Depends(get_session)):
    if settings.auth_mode == "disabled":
        return MeResponse(
            user=UserRead(
                id=DEV_USER_ID,
                email=DEV_USER_EMAIL,
                is_active=True,
                is_superuser=True,
                is_verified=True,
                display_name="Dev user",
                role="admin",
                updated_at=datetime.now(UTC),
                has_avatar=False,
            ),
            permissions={k: "write" for k in ALL_PAGE_KEYS},
            auth_mode=settings.auth_mode,
        )
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    perms = await get_effective_permissions(session, user)
    return MeResponse(
        user=UserRead.model_validate(user),
        permissions=perms,
        auth_mode=settings.auth_mode,
    )


router.include_router(oidc_router)
router.include_router(fastapi_users.get_auth_router(auth_backend))
router.include_router(fastapi_users.get_register_router(UserRead, UserCreate))

users_router = APIRouter(prefix="/users", tags=["users"])


@users_router.post("/me/avatar", status_code=204)
async def upload_my_avatar(
    file: UploadFile = File(...),
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_session),
):
    """Replace the current user's avatar with the uploaded PNG/JPEG.

    Bytes are stored in ``user.avatar_data`` (Postgres bytea) so they
    survive Container App revision restarts and are visible across
    replicas — the previous on-disk approach silently lost uploads on
    every Azure deploy.
    """
    raw = await file.read()
    try:
        media_type = detect_image(raw)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    u = await session.get(User, user.id)
    if u is None:
        raise HTTPException(status_code=404, detail="User not found")
    u.avatar_data = raw
    u.avatar_media_type = media_type
    await session.commit()


@users_router.delete("/me/avatar", status_code=204)
async def delete_my_avatar(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_session),
):
    u = await session.get(User, user.id)
    if u is None:
        raise HTTPException(status_code=404, detail="User not found")
    u.avatar_data = None
    u.avatar_media_type = None
    await session.commit()


@users_router.get("/me/avatar")
async def get_my_avatar(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_session),
):
    """Return the current user's avatar bytes inline.

    Loaded with ``undefer(User.avatar_data)`` because the column is
    deferred in the model — every other code path that touches a User
    row should not pay the cost of dragging up to 1 MB of bytes into
    the session identity map for nothing.
    """
    row = (
        await session.execute(select(User).where(User.id == user.id).options(undefer(User.avatar_data)))
    ).scalar_one_or_none()
    if row is None or row.avatar_data is None:
        raise HTTPException(status_code=404, detail="No avatar")
    return Response(
        content=row.avatar_data,
        media_type=row.avatar_media_type or "application/octet-stream",
    )


users_router.include_router(fastapi_users.get_users_router(UserRead, UserUpdate))

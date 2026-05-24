"""Upload and serve software icons (PNG) from the database."""

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from automunki.api.deps import get_session
from automunki.core.security import current_optional_user
from automunki.models.user import User
from automunki.services.ui_icons import (
    get_icon_by_name,
    store_icon,
)

router = APIRouter(prefix="/icons", tags=["icons"])


class IconUploadResponse(BaseModel):
    icon_name: str
    filename: str


@router.post("/upload", response_model=IconUploadResponse)
async def upload_icon(
    file: UploadFile = File(...),
    icon_name: str = Form(""),
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(current_optional_user),
):
    """Store a PNG as ``{icon_name}.png`` in the software_icon table.

    *icon_name* is the Munki pkginfo ``icon_name`` (no ``.png`` suffix). If
    omitted, the upload filename stem is used (if safe).
    """
    raw = await file.read()
    stem = icon_name.strip()
    if not stem and file.filename:
        stem = file.filename.rsplit("/", 1)[-1]
        stem = stem.rsplit(".", 1)[0] if "." in stem else stem
    if not stem:
        raise HTTPException(
            status_code=422,
            detail="icon_name is required (or provide a filename on the upload)",
        )
    try:
        icon_stem, filename = await store_icon(session, stem, raw)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    return IconUploadResponse(icon_name=icon_stem, filename=filename)


@router.get("/{basename}")
async def get_icon_file(
    basename: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Serve a PNG from the DB. Next.js rewrites ``/icons/<name>.png`` here."""
    stem = basename.removesuffix(".png")
    blob = await get_icon_by_name(session, stem)
    if blob is None:
        raise HTTPException(status_code=404, detail="Icon not found")

    etag = f'"{blob.sha256}"'
    if (request.headers.get("if-none-match") or "").strip() == etag:
        return Response(status_code=304, headers={"ETag": etag, "Cache-Control": "public, max-age=300"})

    return Response(
        content=blob.data,
        media_type=blob.content_type,
        headers={"ETag": etag, "Cache-Control": "public, max-age=300"},
    )

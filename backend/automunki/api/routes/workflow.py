from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from automunki.api.deps import get_session
from automunki.core.security import current_optional_user
from automunki.models.munki import PromotionChannel, WorkflowPreferences
from automunki.models.user import User
from automunki.schemas.munki import WorkflowPreferencesRead, WorkflowPreferencesUpdate
from automunki.services.audit import create_audit_entry

router = APIRouter(prefix="/workflow", tags=["workflow"])


@router.get("/preferences", response_model=WorkflowPreferencesRead)
async def get_workflow_preferences(session: AsyncSession = Depends(get_session)):
    wp = await session.get(WorkflowPreferences, 1)
    if not wp:
        raise HTTPException(status_code=500, detail="Workflow preferences not initialized")
    return WorkflowPreferencesRead(default_promotion_channel_id=wp.default_promotion_channel_id)


@router.patch("/preferences", response_model=WorkflowPreferencesRead)
async def patch_workflow_preferences(
    data: WorkflowPreferencesUpdate,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(current_optional_user),
):
    wp = await session.get(WorkflowPreferences, 1)
    if not wp:
        raise HTTPException(status_code=500, detail="Workflow preferences not initialized")
    patch = data.model_dump(exclude_unset=True)
    if "default_promotion_channel_id" in patch:
        ch_id = patch["default_promotion_channel_id"]
        if ch_id is not None:
            ch = await session.get(PromotionChannel, ch_id)
            if not ch:
                raise HTTPException(status_code=400, detail="Promotion channel not found")
        wp.default_promotion_channel_id = ch_id
    await create_audit_entry(
        session,
        action="update",
        entity_type="workflow_preferences",
        entity_id="1",
        entity_name="workflow_preferences",
        user_id=user.id if user else None,
        user_email=user.email if user else None,
        changes=patch,
    )
    await session.commit()
    await session.refresh(wp)
    return WorkflowPreferencesRead(default_promotion_channel_id=wp.default_promotion_channel_id)

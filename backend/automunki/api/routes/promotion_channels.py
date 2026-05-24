import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from automunki.api.deps import get_session
from automunki.core.security import current_optional_user
from automunki.models.munki import PromotionChannel, PromotionChannelStep
from automunki.models.user import User
from automunki.schemas.munki import (
    PromotionChannelCreate,
    PromotionChannelRead,
    PromotionChannelStepCreate,
    PromotionChannelStepRead,
    PromotionChannelUpdate,
)
from automunki.services.audit import create_audit_entry

router = APIRouter(prefix="/promotion-channels", tags=["promotion-channels"])


def _to_read(ch: PromotionChannel) -> PromotionChannelRead:
    steps = sorted(ch.steps, key=lambda s: s.step_order)
    return PromotionChannelRead(
        id=ch.id,
        name=ch.name,
        description=ch.description,
        created_at=ch.created_at,
        updated_at=ch.updated_at,
        steps=[PromotionChannelStepRead.model_validate(s) for s in steps],
    )


@router.get("", response_model=list[PromotionChannelRead])
async def list_promotion_channels(session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(PromotionChannel).options(selectinload(PromotionChannel.steps)).order_by(PromotionChannel.name)
    )
    return [_to_read(c) for c in result.scalars().all()]


@router.post("", response_model=PromotionChannelRead)
async def create_promotion_channel(
    data: PromotionChannelCreate,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(current_optional_user),
):
    existing = await session.execute(select(PromotionChannel).where(PromotionChannel.name == data.name.strip()))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Channel name already exists")
    ch = PromotionChannel(name=data.name.strip(), description=data.description)
    session.add(ch)
    await session.flush()
    await create_audit_entry(
        session,
        action="create",
        entity_type="promotion_channel",
        entity_id=str(ch.id),
        entity_name=ch.name,
        user_id=user.id if user else None,
        user_email=user.email if user else None,
    )
    await session.commit()
    await session.refresh(ch)
    result = await session.execute(
        select(PromotionChannel).options(selectinload(PromotionChannel.steps)).where(PromotionChannel.id == ch.id)
    )
    return _to_read(result.scalar_one())


@router.get("/{channel_id}", response_model=PromotionChannelRead)
async def get_promotion_channel(
    channel_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(PromotionChannel).options(selectinload(PromotionChannel.steps)).where(PromotionChannel.id == channel_id)
    )
    ch = result.scalar_one_or_none()
    if not ch:
        raise HTTPException(status_code=404, detail="Promotion channel not found")
    return _to_read(ch)


async def _replace_steps(
    session: AsyncSession,
    channel_id: uuid.UUID,
    steps: list[PromotionChannelStepCreate],
) -> None:
    await session.execute(delete(PromotionChannelStep).where(PromotionChannelStep.channel_id == channel_id))
    for s in steps:
        session.add(
            PromotionChannelStep(
                channel_id=channel_id,
                step_order=s.step_order,
                source_catalog_id=s.source_catalog_id,
                target_catalog_id=s.target_catalog_id,
                dwell_days=s.dwell_days,
                requires_manual_approval=s.requires_manual_approval,
            )
        )


@router.patch("/{channel_id}", response_model=PromotionChannelRead)
async def update_promotion_channel(
    channel_id: uuid.UUID,
    data: PromotionChannelUpdate,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(current_optional_user),
):
    result = await session.execute(
        select(PromotionChannel).options(selectinload(PromotionChannel.steps)).where(PromotionChannel.id == channel_id)
    )
    ch = result.scalar_one_or_none()
    if not ch:
        raise HTTPException(status_code=404, detail="Promotion channel not found")

    patch = data.model_dump(exclude_unset=True)
    steps_payload = patch.pop("steps", None)
    if "name" in patch and patch["name"] is not None:
        new_name = patch["name"].strip()
        patch["name"] = new_name
        if new_name != ch.name:
            taken = await session.execute(select(PromotionChannel).where(PromotionChannel.name == new_name))
            if taken.scalar_one_or_none():
                raise HTTPException(status_code=409, detail="Channel name already exists")
    for k, v in patch.items():
        setattr(ch, k, v)
    if steps_payload is not None:
        parsed = [PromotionChannelStepCreate.model_validate(s) for s in steps_payload]
        await _replace_steps(session, channel_id, parsed)

    await create_audit_entry(
        session,
        action="update",
        entity_type="promotion_channel",
        entity_id=str(channel_id),
        entity_name=ch.name,
        user_id=user.id if user else None,
        user_email=user.email if user else None,
        changes=data.model_dump(exclude_unset=True),
    )
    await session.commit()
    result = await session.execute(
        select(PromotionChannel).options(selectinload(PromotionChannel.steps)).where(PromotionChannel.id == channel_id)
    )
    return _to_read(result.scalar_one())


@router.delete("/{channel_id}", status_code=204)
async def delete_promotion_channel(
    channel_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(current_optional_user),
):
    ch = await session.get(PromotionChannel, channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail="Promotion channel not found")
    await create_audit_entry(
        session,
        action="delete",
        entity_type="promotion_channel",
        entity_id=str(channel_id),
        entity_name=ch.name,
        user_id=user.id if user else None,
        user_email=user.email if user else None,
    )
    await session.delete(ch)
    await session.commit()
    return Response(status_code=204)

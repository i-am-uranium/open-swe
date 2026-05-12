"""Webhook event dedupe helpers."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .models import WebhookEvent


async def record_webhook_event(
    session: AsyncSession,
    *,
    provider: str,
    provider_event_id: str,
    payload_hash: str,
    status: str,
) -> WebhookEvent:
    event = WebhookEvent(
        provider=provider,
        provider_event_id=provider_event_id,
        payload_hash=payload_hash,
        status=status,
    )
    session.add(event)
    try:
        await session.commit()
        await session.refresh(event)
        return event
    except IntegrityError:
        await session.rollback()
        result = await session.execute(
            select(WebhookEvent).where(
                WebhookEvent.provider == provider,
                WebhookEvent.provider_event_id == provider_event_id,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is None:
            raise
        return existing

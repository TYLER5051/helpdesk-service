"""Inbound helpdesk webhook router with idempotency support."""

import logging

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Ticket, TicketStatus, WebhookEvent
from app.schemas import WebhookPayload
from app.services.helpdesk import process_ticket_background

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/helpdesk")
async def receive_helpdesk_webhook(
    payload: WebhookPayload,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Accept a helpdesk webhook event exactly once.

    Responds immediately (SLA < 2s) and defers the LLM drafting work to a
    background task. Events carrying an already-seen ``event_id`` are logged
    and silently ignored so retries by the provider do not create duplicates.
    """
    existing = await db.scalar(
        select(WebhookEvent).where(WebhookEvent.event_id == payload.event_id)
    )
    if existing is not None:
        logger.info("Duplicate webhook event %r ignored", payload.event_id)
        return {"status": "duplicate_ignored"}

    db.add(WebhookEvent(event_id=payload.event_id))
    db.add(
        Ticket(
            ticket_id=payload.ticket_id,
            customer_email=payload.customer_email,
            message=payload.message,
            reply_url=payload.reply_url,
            status=TicketStatus.PENDING,
        )
    )

    try:
        await db.commit()
    except IntegrityError:
        # Lost a race against a concurrent request with the same event_id.
        await db.rollback()
        logger.warning(
            "Webhook event %r collided on insert; treating as duplicate",
            payload.event_id,
        )
        return {"status": "duplicate_ignored"}

    background_tasks.add_task(process_ticket_background, payload.ticket_id)
    logger.info(
        "Accepted webhook event %r for ticket %r",
        payload.event_id,
        payload.ticket_id,
    )
    return {"status": "accepted", "ticket_id": payload.ticket_id}

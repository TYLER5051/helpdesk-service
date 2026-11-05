"""Helpdesk ticket business logic (background drafting and reply delivery)."""

import asyncio
import logging

import httpx
from sqlalchemy import select

from app.database import async_session
from app.models import Ticket, TicketStatus, utc_now
from app.schemas import HelpdeskReplyPayload
from app.services.llm import generate_draft_reply

logger = logging.getLogger(__name__)

DELIVERY_TIMEOUT_SECONDS = 5.0
DELIVERY_ATTEMPTS = 3


async def process_ticket_background(ticket_id: str) -> None:
    """Generate and persist an LLM draft reply for the given ticket.

    Runs outside of the webhook request lifecycle in its own database session
    so a slow LLM call (mock latency or upstream API) never delays responses.
    """
    try:
        async with async_session() as session:
            ticket = await session.scalar(
                select(Ticket).where(Ticket.ticket_id == ticket_id)
            )
            if ticket is None:
                logger.error("Background task: ticket %r not found", ticket_id)
                return

            draft_reply = await generate_draft_reply(ticket.message)
            ticket.draft_reply = draft_reply
            ticket.status = TicketStatus.DRAFTED
            await session.commit()
            logger.info("Background task: draft ready for ticket %r", ticket_id)
    except Exception:
        logger.exception("Background task failed for ticket %r", ticket_id)


async def send_ticket_reply(ticket_id: str) -> bool:
    """Deliver an approved draft reply to the helpdesk provider.

    Implements at-most-once semantics: the reply is only sent while the ticket
    is in ``DRAFTED`` state and ``sent_at`` is still unset. The ticket is moved
    to ``SENDING`` before any network I/O (inside a row lock) so concurrent
    approve clicks cannot trigger duplicate delivery. It reaches ``SENT``
    (with ``sent_at`` stamped) only after a 200/201 response. Transient
    failures — 5xx responses, timeouts and transport errors — are retried a
    bounded number of times and then leave the ticket back in ``DRAFTED`` for
    the operator to retry, never marking it as sent.

    Returns ``True`` when the provider accepted the reply, ``False`` otherwise.
    """
    async with async_session() as session:
        ticket = await session.scalar(
            select(Ticket)
            .where(Ticket.ticket_id == ticket_id)
            .with_for_update()
        )
        if ticket is None:
            logger.error("send_ticket_reply: ticket %r not found", ticket_id)
            return False

        if ticket.status != TicketStatus.DRAFTED:
            logger.warning(
                "Reply for ticket %r not sent: status is %s (expected DRAFTED)",
                ticket_id,
                ticket.status.value,
            )
            return False

        if ticket.sent_at is not None:
            logger.warning(
                "Reply for ticket %r already sent at %s; skipping",
                ticket_id,
                ticket.sent_at,
            )
            return False

        if not ticket.draft_reply:
            logger.error("Ticket %r has no draft reply; sending aborted", ticket_id)
            return False

        # Publish our intent before any network I/O so concurrent approve
        # requests observe SENDING and back off (at-most-once delivery).
        ticket.status = TicketStatus.SENDING
        await session.commit()

        payload = HelpdeskReplyPayload(
            ticket_id=ticket.ticket_id,
            message=ticket.draft_reply,
        )
        timeouts = httpx.Timeout(DELIVERY_TIMEOUT_SECONDS)

        for attempt in range(1, DELIVERY_ATTEMPTS + 1):
            try:
                async with httpx.AsyncClient(timeout=timeouts) as client:
                    response = await client.post(
                        ticket.reply_url,
                        json=payload.model_dump(),
                    )
            except httpx.RequestError as exc:
                logger.error(
                    "Attempt %d: reply delivery for ticket %r failed: %s",
                    attempt,
                    ticket_id,
                    exc,
                )
                if attempt < DELIVERY_ATTEMPTS:
                    await asyncio.sleep(0.5 * attempt)
                    continue
                ticket.status = TicketStatus.DRAFTED
                await session.commit()
                return False

            if response.status_code in (200, 201):
                ticket.status = TicketStatus.SENT
                ticket.sent_at = utc_now()
                await session.commit()
                logger.info(
                    "Reply for ticket %r delivered (HTTP %d)",
                    ticket_id,
                    response.status_code,
                )
                return True

            if response.status_code >= 500:
                logger.error(
                    "Attempt %d: helpdesk provider returned HTTP %d for ticket %r",
                    attempt,
                    response.status_code,
                    ticket_id,
                )
                if attempt < DELIVERY_ATTEMPTS:
                    await asyncio.sleep(0.5 * attempt)
                    continue
                ticket.status = TicketStatus.DRAFTED
                await session.commit()
                return False

            # 4xx/3xx — permanent refusal, no retries and never marked as sent.
            logger.error(
                "Reply for ticket %r rejected by helpdesk (HTTP %d): %s",
                ticket_id,
                response.status_code,
                response.text[:500],
            )
            ticket.status = TicketStatus.DRAFTED
            await session.commit()
            return False

        return False  # pragma: no cover - loop always returns


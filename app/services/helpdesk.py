"""Helpdesk ticket business logic (background draft generation)."""

import logging

from sqlalchemy import select

from app.database import async_session
from app.models import Ticket, TicketStatus
from app.services.llm import generate_draft_reply

logger = logging.getLogger(__name__)


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

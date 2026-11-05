"""Operator UI router: draft moderation and reply delivery."""

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import PROJECT_ROOT
from app.database import get_db
from app.models import Ticket, TicketStatus
from app.schemas import TicketResponse
from app.services.helpdesk import send_ticket_reply

logger = logging.getLogger(__name__)

router = APIRouter(tags=["operator"])

templates = Jinja2Templates(directory=str(PROJECT_ROOT / "templates"))


@router.get("/operator", response_class=HTMLResponse)
async def operator_page(request: Request) -> HTMLResponse:
    """Render the operator moderation dashboard."""
    return templates.TemplateResponse(request=request, name="operator.html")


@router.get("/api/operator/tickets", response_model=list[TicketResponse])
async def operator_tickets(db: AsyncSession = Depends(get_db)) -> list[Ticket]:
    """Return all tickets (newest first) for the operator dashboard."""
    rows = (
        await db.execute(
            select(Ticket).order_by(Ticket.created_at.desc(), Ticket.id.desc())
        )
    ).scalars().all()
    return list(rows)


@router.post("/api/operator/tickets/{ticket_id}/approve")
async def approve_ticket(ticket_id: str) -> dict[str, str]:
    """Approve the draft and deliver the reply to the helpdesk provider."""
    delivered = await send_ticket_reply(ticket_id)
    if delivered:
        return {"status": "sent", "ticket_id": ticket_id}
    return {"status": "not_sent", "ticket_id": ticket_id}


@router.post("/api/operator/tickets/{ticket_id}/reject")
async def reject_ticket(
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Mark a ticket as rejected; no reply is delivered."""
    ticket = await db.scalar(select(Ticket).where(Ticket.ticket_id == ticket_id))
    if ticket is None:
        return {"status": "not_found", "ticket_id": ticket_id}
    if ticket.status == TicketStatus.SENT:
        logger.warning("Ticket %r already sent; cannot reject it", ticket_id)
        return {"status": "already_sent", "ticket_id": ticket_id}
    ticket.status = TicketStatus.REJECTED
    await db.commit()
    logger.info("Ticket %r marked as rejected", ticket_id)
    return {"status": "rejected", "ticket_id": ticket_id}

"""Pydantic schemas for webhook payloads and API responses."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import TicketStatus


class WebhookPayload(BaseModel):
    """Inbound webhook body describing a new helpdesk ticket."""

    event_id: str = Field(min_length=1)
    ticket_id: str = Field(min_length=1)
    customer_email: str = Field(min_length=1)
    message: str = Field(min_length=1)
    reply_url: str = Field(min_length=1)


class HelpdeskReplyPayload(BaseModel):
    """Outbound reply delivered back to the helpdesk provider."""

    ticket_id: str = Field(min_length=1)
    message: str = Field(min_length=1)


class TicketResponse(BaseModel):
    """Ticket representation exposed to the operator UI."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_id: str
    customer_email: str
    message: str
    reply_url: str
    draft_reply: str | None = None
    sent_at: datetime | None = None
    status: TicketStatus
    created_at: datetime
    updated_at: datetime

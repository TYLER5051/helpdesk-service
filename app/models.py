"""SQLAlchemy ORM models for the helpdesk service."""

from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import DateTime, Enum as SAEnum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utc_now() -> datetime:
    """Return the current UTC datetime (timezone-aware)."""
    return datetime.now(timezone.utc)


class TicketStatus(str, Enum):
    """Lifecycle status of an inbound helpdesk ticket."""

    PENDING = "PENDING"
    DRAFTED = "DRAFTED"
    SENDING = "SENDING"
    SENT = "SENT"
    REJECTED = "REJECTED"


class WebhookEvent(Base):
    """A raw webhook event received from the helpdesk provider."""

    __tablename__ = "webhook_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[str] = mapped_column(
        String, unique=True, index=True, nullable=False
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )


class Ticket(Base):
    """A support ticket created from an inbound webhook event."""

    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[str] = mapped_column(
        String, unique=True, index=True, nullable=False
    )
    customer_email: Mapped[str] = mapped_column(String, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    reply_url: Mapped[str] = mapped_column(String, nullable=False)
    draft_reply: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[TicketStatus] = mapped_column(
        SAEnum(TicketStatus, name="ticket_status"),
        default=TicketStatus.PENDING,
        server_default=TicketStatus.PENDING.value,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class KnowledgeArticle(Base):
    """A knowledge base article used as seed data for RAG."""

    __tablename__ = "knowledge_articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_id: Mapped[str] = mapped_column(
        String, unique=True, index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)

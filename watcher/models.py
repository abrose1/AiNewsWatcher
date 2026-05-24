from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SeedItem(Base):
    __tablename__ = "seed_items"
    __table_args__ = (UniqueConstraint("category", "key", name="uq_seed_items_category_key"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    seed_notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    added_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)

    sent_facts: Mapped[list["SentFact"]] = relationship(back_populates="seed_item")


class SentFact(Base):
    __tablename__ = "sent_facts"
    __table_args__ = (
        Index("ix_sent_facts_seed_item_id", "seed_item_id"),
        Index("ix_sent_facts_news_dedupe_key", "news_dedupe_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fact_kind: Mapped[str] = mapped_column(String(16), nullable=False)  # 'seed' | 'news'
    seed_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("seed_items.id"), nullable=True
    )
    news_dedupe_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    sms_body: Mapped[str] = mapped_column(Text, nullable=False)
    link: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)

    seed_item: Mapped[SeedItem | None] = relationship(back_populates="sent_facts")


class SendLog(Base):
    __tablename__ = "send_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)  # 'sent' | 'skipped' | 'error'
    fact_kind: Mapped[str | None] = mapped_column(String(16), nullable=True)
    twilio_sid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)

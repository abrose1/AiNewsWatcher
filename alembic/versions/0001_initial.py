"""initial schema: seed_items, sent_facts, send_log

Revision ID: 0001
Revises:
Create Date: 2026-05-23

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "seed_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("display_name", sa.String(256), nullable=False),
        sa.Column("seed_notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("category", "key", name="uq_seed_items_category_key"),
    )

    op.create_table(
        "sent_facts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("fact_kind", sa.String(16), nullable=False),
        sa.Column("seed_item_id", UUID(as_uuid=True), sa.ForeignKey("seed_items.id"), nullable=True),
        sa.Column("news_dedupe_key", sa.Text(), nullable=True),
        sa.Column("sms_body", sa.Text(), nullable=False),
        sa.Column("link", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_sent_facts_seed_item_id", "sent_facts", ["seed_item_id"])
    op.create_index("ix_sent_facts_news_dedupe_key", "sent_facts", ["news_dedupe_key"])

    op.create_table(
        "send_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("fact_kind", sa.String(16), nullable=True),
        sa.Column("twilio_sid", sa.String(64), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("send_log")
    op.drop_index("ix_sent_facts_news_dedupe_key", table_name="sent_facts")
    op.drop_index("ix_sent_facts_seed_item_id", table_name="sent_facts")
    op.drop_table("sent_facts")
    op.drop_table("seed_items")

"""sms_threads table for inbound reply conversations

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-23

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sms_threads",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "root_sent_fact_id",
            UUID(as_uuid=True),
            sa.ForeignKey("sent_facts.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("transcript", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("sms_threads")

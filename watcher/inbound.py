from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from watcher.config import load_config
from watcher.db import session_scope
from watcher.judge import generate_reply
from watcher.models import SentFact, SmsThread

log = logging.getLogger(__name__)


def _normalize_phone(num: str) -> str:
    """Lowercase + strip whitespace; keeps `+` prefix. Twilio sends E.164."""
    return num.strip()


def handle_inbound(from_number: str, body: str) -> str | None:
    """Handle an inbound SMS. Returns the reply text to send, or None to ignore.

    Threading model: every reply is associated with the most recent SentFact
    sent to the user (regardless of age). A new outbound fact implicitly starts
    a new thread.
    """
    cfg = load_config()
    from_norm = _normalize_phone(from_number)
    expected = _normalize_phone(cfg.sms.to_number)

    if from_norm != expected:
        log.warning("Inbound from non-whitelisted number: %r (expected %r)", from_norm, expected)
        return None

    body = body.strip()
    if not body:
        return None

    with session_scope() as session:
        most_recent = session.execute(
            select(SentFact).order_by(SentFact.sent_at.desc()).limit(1)
        ).scalar_one_or_none()

        if most_recent is None:
            return "I haven't sent you any facts yet — once the daily job runs, replies will work."

        thread = session.execute(
            select(SmsThread).where(SmsThread.root_sent_fact_id == most_recent.id)
        ).scalar_one_or_none()

        if thread is None:
            thread = SmsThread(root_sent_fact_id=most_recent.id, transcript=[])
            session.add(thread)
            session.flush()

        transcript = list(thread.transcript or [])
        transcript.append({"role": "user", "content": body})

        try:
            reply = generate_reply(
                fact_body=most_recent.sms_body,
                transcript=transcript,
                api_key=cfg.secrets.anthropic_api_key,
                brave_api_key=cfg.secrets.brave_api_key,
                model=cfg.llm.model,
            )
        except Exception:
            log.exception("generate_reply failed")
            return "Sorry — something broke on my end. Try again in a minute."

        transcript.append({"role": "assistant", "content": reply})
        thread.transcript = transcript
        flag_modified(thread, "transcript")
        thread.last_message_at = datetime.now(timezone.utc)

        return reply

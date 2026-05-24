from __future__ import annotations

import logging

from twilio.rest import Client

log = logging.getLogger(__name__)

# GSM-7 encodable chars. Anything outside this set forces UCS-2 (70-char segments).
_GSM7_CHARS = set(
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ ÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
    "^{}\\[~]|€"
)

# Hard cap for the SMS body — comfortably within 2 segments of UCS-2 (140 chars)
# or 3 segments of GSM-7 (459 chars). We aim short.
_HARD_CAP = 280


def is_gsm7(text: str) -> bool:
    return all(c in _GSM7_CHARS for c in text)


def truncate_text(text: str, max_chars: int) -> str:
    """Truncate to max_chars at a word boundary when possible, appending an ellipsis."""
    if len(text) <= max_chars:
        return text
    cut = text[: max_chars - 1]
    last_space = cut.rfind(" ")
    if last_space > max_chars * 0.6:
        cut = cut[:last_space]
    return cut.rstrip() + "…"


def compose_sms(body: str, link: str | None, *, hard_cap: int = _HARD_CAP) -> str:
    """Combine body + optional link, preserving the full link by truncating body if needed."""
    if not link:
        return truncate_text(body, hard_cap)
    suffix = f" {link}"
    budget = hard_cap - len(suffix)
    if budget < 20:  # link alone is huge; just send what fits and skip the link
        return truncate_text(body, hard_cap)
    return truncate_text(body, budget) + suffix


def send_sms(
    body: str,
    *,
    link: str | None = None,
    to: str,
    from_: str,
    account_sid: str,
    auth_token: str,
) -> str:
    """Send via Twilio. Returns the message SID."""
    final = compose_sms(body, link)
    encoding = "GSM-7" if is_gsm7(final) else "UCS-2"
    log.info("Sending SMS (%s, %s chars): %s", encoding, len(final), final[:80])
    client = Client(account_sid, auth_token)
    msg = client.messages.create(body=final, from_=from_, to=to)
    log.info("Twilio SID: %s", msg.sid)
    return msg.sid

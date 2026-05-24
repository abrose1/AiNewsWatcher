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

# Hard cap = Twilio's API maximum (1600 chars). At this size Twilio splits
# into ~11 concatenated SMS segments, which Google Messages on Android
# reassembles into a single bubble. The prompts in judge.py target much
# shorter lengths (~260 for daily facts, ~320 for replies) for readability;
# this cap is only a safety net against runaway LLM output.
_HARD_CAP = 1600


def is_gsm7(text: str) -> bool:
    return all(c in _GSM7_CHARS for c in text)


def truncate_text(text: str, max_chars: int = _HARD_CAP) -> str:
    """Safety-net truncation at a word boundary. Body should fit naturally;
    if this kicks in, the prompt budget needs tightening."""
    if len(text) <= max_chars:
        return text
    cut = text[: max_chars - 1]
    last_space = cut.rfind(" ")
    if last_space > max_chars * 0.6:
        cut = cut[:last_space]
    return cut.rstrip() + "…"


def send_sms(
    body: str,
    *,
    to: str,
    from_: str,
    account_sid: str,
    auth_token: str,
) -> str:
    """Send a single SMS via Twilio. Returns the message SID."""
    body = truncate_text(body)
    encoding = "GSM-7" if is_gsm7(body) else "UCS-2"
    log.info("Sending SMS (%s, %s chars): %s", encoding, len(body), body[:80])
    client = Client(account_sid, auth_token)
    msg = client.messages.create(body=body, from_=from_, to=to)
    log.info("Twilio SID: %s", msg.sid)
    return msg.sid

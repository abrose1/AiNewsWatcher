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


def truncate_for_sms(body: str, *, hard_cap: int = _HARD_CAP) -> str:
    """Truncate body to the hard cap, preferring whole-word boundaries.

    Does not attempt to preserve trailing URLs — formatter should handle that
    by composing body+URL within the cap upstream.
    """
    if len(body) <= hard_cap:
        return body
    cut = body[: hard_cap - 1]
    last_space = cut.rfind(" ")
    if last_space > hard_cap * 0.6:
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
    """Send via Twilio. Returns the message SID."""
    body = truncate_for_sms(body)
    encoding = "GSM-7" if is_gsm7(body) else "UCS-2"
    log.info("Sending SMS (%s, %s chars): %s", encoding, len(body), body[:80])
    client = Client(account_sid, auth_token)
    msg = client.messages.create(body=body, from_=from_, to=to)
    log.info("Twilio SID: %s", msg.sid)
    return msg.sid

from __future__ import annotations

import logging
import os

from fastapi import BackgroundTasks, FastAPI, Form, HTTPException, Request
from fastapi.responses import PlainTextResponse
from twilio.request_validator import RequestValidator

from watcher.config import load_config
from watcher.inbound import handle_inbound
from watcher.jobs import daily_fact
from watcher.notify import send_sms

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(title="AI News Watcher webhook")


@app.get("/")
def health() -> dict:
    return {"status": "ok"}


def _process_inbound_and_reply(from_number: str, body: str) -> None:
    """Runs in a background task so the webhook returns to Twilio immediately."""
    cfg = load_config()
    try:
        reply = handle_inbound(from_number, body)
    except Exception:
        log.exception("handle_inbound failed for %s", from_number)
        return

    if not reply:
        return

    if not (cfg.secrets.twilio_account_sid and cfg.secrets.twilio_auth_token and cfg.sms.from_number):
        log.warning("Twilio creds incomplete — cannot send reply. Reply was: %s", reply)
        return

    try:
        send_sms(
            reply,
            to=from_number,
            from_=cfg.sms.from_number,
            account_sid=cfg.secrets.twilio_account_sid,
            auth_token=cfg.secrets.twilio_auth_token,
        )
    except Exception:
        log.exception("Failed to send reply SMS")


@app.post("/trigger/daily")
async def trigger_daily(request: Request, background_tasks: BackgroundTasks) -> dict:
    secret = os.environ.get("TRIGGER_SECRET", "")
    if not secret or request.headers.get("X-Trigger-Secret") != secret:
        raise HTTPException(status_code=403, detail="forbidden")
    background_tasks.add_task(daily_fact.run)
    return {"status": "triggered"}


@app.post("/sms/inbound", response_class=PlainTextResponse)
async def sms_inbound(
    request: Request,
    background_tasks: BackgroundTasks,
    From: str = Form(...),
    Body: str = Form(...),
) -> str:
    cfg = load_config()

    if not os.environ.get("SKIP_TWILIO_SIGNATURE"):
        validator = RequestValidator(cfg.secrets.twilio_auth_token)
        form_data = await request.form()
        signature = request.headers.get("X-Twilio-Signature", "")
        url = str(request.url)
        if not validator.validate(url, dict(form_data), signature):
            log.warning("Invalid Twilio signature for inbound from %s", From)
            raise HTTPException(status_code=403, detail="invalid signature")

    log.info("Inbound from %s: %r", From, Body[:80])
    background_tasks.add_task(_process_inbound_and_reply, From, Body.strip())
    return ""

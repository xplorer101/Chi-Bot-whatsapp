import json
import logging
import secrets

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import PlainTextResponse

from app.config import settings
from app.services.pipeline import process_webhook_payload
from app.whatsapp.signature import verify_signature

logger = logging.getLogger("chibot.webhook")

router = APIRouter(prefix="/api", tags=["whatsapp"])


@router.get("/webhook")
async def verify_webhook(request: Request) -> PlainTextResponse:
    """Meta webhook verification handshake."""
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token", "")
    challenge = params.get("hub.challenge", "")
    if (
        mode == "subscribe"
        and settings.whatsapp_verify_token
        and secrets.compare_digest(token, settings.whatsapp_verify_token)
    ):
        logger.info("webhook verification succeeded")
        return PlainTextResponse(challenge)
    logger.warning("webhook verification failed (mode=%s)", mode)
    raise HTTPException(status_code=403, detail="verification failed")


@router.post("/webhook")
async def receive_webhook(
    request: Request, background_tasks: BackgroundTasks
) -> dict:
    """Receive a delivery, verify its signature, and process it out-of-band."""
    raw_body = await request.body()
    signature = request.headers.get("x-hub-signature-256")
    if not verify_signature(raw_body, signature, settings.meta_app_secret):
        logger.warning("rejected webhook delivery: bad signature")
        raise HTTPException(status_code=403, detail="invalid signature")

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        logger.warning("ignored webhook delivery: invalid JSON")
        return {"status": "ignored"}

    background_tasks.add_task(process_webhook_payload, payload)
    return {"status": "received"}
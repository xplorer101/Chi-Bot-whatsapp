import logging

import httpx

from app.config import settings

logger = logging.getLogger("chibot.whatsapp")


class WhatsAppSendError(Exception):
    pass


async def send_text(phone_number_id: str, to: str, body: str) -> dict:
    """Send a plain text WhatsApp message via the Meta Cloud API.

    In dry-run mode (no access token configured, or WHATSAPP_DRY_RUN=true)
    the message is only logged, so the pipeline can be tested locally.
    """
    if settings.whatsapp_dry_run or not settings.whatsapp_access_token:
        logger.info("[DRY-RUN] -> %s via %s: %s", to, phone_number_id, body)
        return {"dry_run": True}

    url = f"{settings.graph_api_base}/{phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {settings.whatsapp_access_token}"}
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"preview_url": False, "body": body},
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code >= 400:
            logger.error("send failed %s: %s", resp.status_code, resp.text)
            raise WhatsAppSendError(f"{resp.status_code}: {resp.text}")
        return resp.json()
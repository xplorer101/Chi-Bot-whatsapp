"""Send a signed, Meta-shaped webhook delivery to a local ChiBot server.

Usage:
  python scripts/send_test_webhook.py --text "Hello"
  python scripts/send_test_webhook.py --text "Abeg, you dey deliver?" --from 2348011223344

Reads WHATSAPP_VERIFY_TOKEN / META_APP_SECRET only for signing the payload.
"""
import argparse
import hashlib
import hmac
import json
import os
import uuid

import httpx


def build_payload(phone_number_id: str, sender: str, text: str, message_id: str) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA_TEST",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15550001111",
                                "phone_number_id": phone_number_id,
                            },
                            "contacts": [
                                {"profile": {"name": "Test Customer"}, "wa_id": sender}
                            ],
                            "messages": [
                                {
                                    "from": sender,
                                    "id": message_id,
                                    "timestamp": "1700000000",
                                    "type": "text",
                                    "text": {"body": text},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


def sign(raw: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000/api/webhook")
    parser.add_argument("--phone-number-id", default=os.getenv("DEMO_PHONE_NUMBER_ID", "1234567890"))
    parser.add_argument("--from", dest="sender", default="2348011223344")
    parser.add_argument("--text", default="Hello, do you deliver?")
    parser.add_argument("--secret", default=os.getenv("META_APP_SECRET", "dev-app-secret"))
    parser.add_argument("--message-id", default=f"wamid.{uuid.uuid4()}")
    args = parser.parse_args()

    raw = json.dumps(
        build_payload(args.phone_number_id, args.sender, args.text, args.message_id)
    ).encode()
    headers = {
        "Content-Type": "application/json",
        "X-Hub-Signature-256": sign(raw, args.secret),
    }
    resp = httpx.post(args.url, content=raw, headers=headers, timeout=15)
    print(f"message_id: {args.message_id}")
    print(f"HTTP {resp.status_code}: {resp.text}")


if __name__ == "__main__":
    main()
import hashlib
import hmac


def verify_signature(
    raw_body: bytes, signature_header: str | None, app_secret: str
) -> bool:
    """Verify Meta's X-Hub-Signature-256 header against the raw request body."""
    if not signature_header or not app_secret:
        return False
    if not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(
        app_secret.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    provided = signature_header[len("sha256=") :].strip()
    return hmac.compare_digest(expected, provided)
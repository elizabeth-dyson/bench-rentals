"""Cloudflare verification transport, with explicit configuration and injectable I/O."""

import json
from urllib.request import Request, urlopen

from services.public_inquiry import PublicVerificationError, TURNSTILE_ACTION


def verify_turnstile(token: str, verification_id: str, *, secret: str, hostname: str, opener=urlopen) -> None:
    request = Request(
        "https://challenges.cloudflare.com/turnstile/v0/siteverify",
        data=json.dumps({"secret": secret, "response": token, "idempotency_key": verification_id}).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with opener(request, timeout=10) as response:
            result = json.loads(response.read(16384))
    except Exception:
        raise PublicVerificationError("Verification is unavailable. Try verification again; your answers are still here.") from None
    if (not isinstance(result, dict) or result.get("success") is not True
            or result.get("hostname") != hostname or result.get("action") != TURNSTILE_ACTION):
        raise PublicVerificationError("Verification expired or failed. Please verify again; your answers are still here.")

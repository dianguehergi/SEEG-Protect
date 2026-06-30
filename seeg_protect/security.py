import hmac
import hashlib


def build_signature(secret: str, raw_body: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def verify_signature(secret: str, raw_body: bytes, signature: str | None) -> bool:
    if not signature:
        return False
    expected = build_signature(secret, raw_body)
    return hmac.compare_digest(expected, signature.strip())


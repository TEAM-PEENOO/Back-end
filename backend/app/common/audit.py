import json
import logging
from datetime import datetime, timezone

from fastapi import Request


audit_logger = logging.getLogger("audit")
if not audit_logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    audit_logger.addHandler(handler)
audit_logger.setLevel(logging.INFO)
audit_logger.propagate = False


def _mask_email(email: str) -> str:
    if "@" not in email:
        return "***"
    user, domain = email.split("@", 1)
    if len(user) <= 2:
        masked = "*" * len(user)
    else:
        masked = user[:2] + "*" * (len(user) - 2)
    return f"{masked}@{domain}"


def audit_event(
    *,
    request: Request | None,
    event: str,
    outcome: str,
    user_id: str | None = None,
    email: str | None = None,
    detail: str | None = None,
) -> None:
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "outcome": outcome,
        "user_id": user_id,
        "email": _mask_email(email) if email else None,
        "detail": detail,
        "request_id": getattr(request.state, "request_id", None) if request else None,
        "path": str(request.url.path) if request else None,
        "method": request.method if request else None,
    }
    audit_logger.info(json.dumps(payload, ensure_ascii=False))


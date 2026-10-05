"""Domain events: in-app notifications and outgoing ATS webhooks (HMAC-SHA256 signed)."""

import hashlib
import hmac
import json
import logging
import threading

import httpx
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.models import Company, Notification, WebhookDelivery

log = logging.getLogger(__name__)


def notify(db: Session, user_id: int, kind: str, title: str, link: str = "") -> None:
    db.add(Notification(user_id=user_id, kind=kind, title=title, link=link))


def _deliver(company_id: int, url: str, secret: str, event: str, payload: dict) -> None:
    body = json.dumps({"event": event, "data": payload}, ensure_ascii=False, default=str).encode()
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    status_code, error = None, ""
    try:
        resp = httpx.post(url, content=body, timeout=5, headers={
            "Content-Type": "application/json", "X-FSP-Talent-Event": event, "X-FSP-Talent-Signature": signature})
        status_code = resp.status_code
    except httpx.HTTPError as exc:
        error = str(exc)[:500]
    with SessionLocal() as db:
        db.add(WebhookDelivery(company_id=company_id, event=event, payload=payload, status_code=status_code,
                               error=error))
        db.commit()


def emit_webhook(company: Company, event: str, payload: dict) -> None:
    """Fire-and-forget delivery so a slow ATS never blocks the user's request."""
    if not company.webhook_url:
        return
    threading.Thread(target=_deliver, daemon=True,
                     args=(company.id, company.webhook_url, company.webhook_secret or "", event, payload)).start()

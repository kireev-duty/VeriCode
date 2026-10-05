import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings

log = logging.getLogger(__name__)


def send_email(to: str, subject: str, body: str) -> bool:
    """Best-effort delivery: in dev the mail goes to mailpit; a failed send must not break registration."""
    if not settings.smtp_host:  # mail disabled (tests, offline demo): the dev link in the API response is used
        return False
    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=5) as smtp:
            smtp.send_message(msg)
        return True
    except OSError as exc:
        log.warning("email to %s not sent: %s", to, exc)
        return False

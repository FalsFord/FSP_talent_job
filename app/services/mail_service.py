import asyncio
import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings

log = logging.getLogger("mail")


def _send_smtp(to: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = settings.mail_from, to, subject
    msg.set_content(body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as s:
        s.starttls()
        if settings.smtp_user:
            s.login(settings.smtp_user, settings.smtp_password)
        s.send_message(msg)


async def send_mail(to: str, subject: str, body: str) -> None:
    """console — пишет письмо в лог (dev); smtp — отправляет через SMTP в отдельном потоке."""
    if settings.mail_backend == "smtp" and settings.smtp_host:
        try:
            await asyncio.to_thread(_send_smtp, to, subject, body)
            return
        except Exception:  # noqa: BLE001
            log.exception("SMTP send failed to=%s", to[:3] + "***")
            return
    log.info("MAIL (console) to=%s subject=%s\n%s", to, subject, body)

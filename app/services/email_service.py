import logging
import smtplib
from email.mime.text import MIMEText

from app.config import settings

logger = logging.getLogger("smartreco.email")


def send_digest(to_email: str, narrative: str, items: list[dict]) -> None:
    subject = "Your SmartReco picks for today"
    lines = [narrative, "", "Today's recommendations:"]
    for item in items:
        lines.append(f'- {item["title"]} (${item["price"]:.2f}) — {item.get("reason") or ""}')
    body = "\n".join(lines)

    if not settings.smtp_host:
        logger.info("[digest email — SMTP not configured, logging instead] to=%s\n%s", to_email, body)
        return

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from
    msg["To"] = to_email

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls()
            if settings.smtp_username:
                server.login(settings.smtp_username, settings.smtp_password)
            server.sendmail(settings.smtp_from, [to_email], msg.as_string())
        logger.info("Sent digest email to %s", to_email)
    except Exception:
        logger.error("Failed to send digest email to %s", to_email, exc_info=True)

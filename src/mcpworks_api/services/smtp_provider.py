"""SMTP email provider for self-hosted MCPWorks."""

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib
import structlog

logger = structlog.get_logger()


class SmtpProvider:
    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        from_email: str,
        use_tls: bool = True,
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.from_email = from_email
        self.use_tls = use_tls

    async def send(self, to: str, subject: str, html: str) -> str | None:
        msg = MIMEMultipart("alternative")
        msg["From"] = self.from_email
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(html, "html"))
        try:
            await aiosmtplib.send(
                msg,
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                start_tls=self.use_tls,
            )
            logger.info("email_smtp_sent", to=to, subject=subject)
            return f"smtp-{to}"
        except Exception:
            logger.exception("email_smtp_error", to=to)
            return None

"""Email service - provider abstraction and Resend integration."""

import asyncio
from pathlib import Path
from typing import Any, Protocol

import httpx
import structlog
from jinja2 import Environment, FileSystemLoader

from mcpworks_api.config import get_settings
from mcpworks_api.models.email_log import EmailLog

logger = structlog.get_logger(__name__)

TEMPLATES_DIR = Path(__file__).parent.parent / "templates" / "emails"

_jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=True,
)


class EmailProvider(Protocol):
    async def send(
        self,
        to: str,
        subject: str,
        html: str,
    ) -> str | None:
        """Send an email. Returns provider message ID or None on failure."""
        ...


class ResendProvider:
    """Send emails via Resend REST API (direct httpx, no SDK)."""

    def __init__(self, api_key: str, from_email: str) -> None:
        self._api_key = api_key
        self._from_email = from_email

    async def send(self, to: str, subject: str, html: str) -> str | None:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "from": self._from_email,
                    "to": [to],
                    "subject": subject,
                    "html": html,
                },
                timeout=10.0,
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                return data.get("id")
            logger.warning(
                "resend_send_failed",
                status=resp.status_code,
                body=resp.text[:200],
            )
            return None


class ConsoleProvider:
    """Dev/test provider that logs to console instead of sending."""

    async def send(self, to: str, subject: str, html: str) -> str | None:  # noqa: ARG002
        logger.info("email_console", to=to, subject=subject)
        return "console-dev-id"


def _get_provider() -> EmailProvider:
    settings = get_settings()
    if settings.resend_api_key:
        return ResendProvider(settings.resend_api_key, settings.resend_from_email)
    return ConsoleProvider()


def _render_template(template_name: str, **kwargs: Any) -> str:
    template = _jinja_env.get_template(template_name)
    return template.render(**kwargs)


async def send_email(
    to: str,
    email_type: str,
    subject: str,
    template_name: str,
    template_vars: dict[str, Any] | None = None,
) -> None:
    """Send an email with retry logic and audit logging.

    This is the primary entry point. Call via asyncio.create_task()
    for fire-and-forget dispatch.
    """
    provider = _get_provider()
    html = _render_template(template_name, **(template_vars or {}))
    max_retries = 3

    for attempt in range(max_retries):
        message_id = await provider.send(to, subject, html)
        if message_id:
            await _log_email(to, email_type, subject, "sent", message_id)
            return

        if attempt < max_retries - 1:
            delay = 2**attempt
            logger.warning("email_retry", to=to, attempt=attempt + 1, delay=delay)
            await _log_email(
                to, email_type, subject, "retrying", error_message=f"Attempt {attempt + 1} failed"
            )
            await asyncio.sleep(delay)

    await _log_email(
        to, email_type, subject, "failed", error_message=f"All {max_retries} attempts failed"
    )
    logger.error("email_send_failed", to=to, email_type=email_type)


async def _log_email(
    recipient: str,
    email_type: str,
    subject: str,
    status: str,
    provider_message_id: str | None = None,
    error_message: str | None = None,
) -> None:
    """Create an EmailLog audit record."""
    try:
        from mcpworks_api.core.database import get_db_context

        async with get_db_context() as db:
            log = EmailLog(
                recipient=recipient,
                email_type=email_type,
                subject=subject,
                status=status,
                provider_message_id=provider_message_id,
                error_message=error_message,
            )
            db.add(log)
            await db.commit()
    except Exception as e:
        logger.warning("email_log_failed", error=str(e))


async def send_welcome_email(email: str, name: str | None = None) -> None:
    await send_email(
        to=email,
        email_type="welcome",
        subject="Welcome to MCPWorks",
        template_name="welcome.html",
        template_vars={"name": name or email.split("@")[0]},
    )


async def send_registration_pending_email(email: str, name: str | None = None) -> None:
    await send_email(
        to=email,
        email_type="registration_pending",
        subject="MCPWorks - Registration Received",
        template_name="registration_pending.html",
        template_vars={"name": name or email.split("@")[0]},
    )


async def send_admin_new_registration_email(
    admin_email: str, user_email: str, user_name: str | None = None
) -> None:
    await send_email(
        to=admin_email,
        email_type="admin_new_registration",
        subject=f"MCPWorks - New Registration: {user_email}",
        template_name="admin_new_registration.html",
        template_vars={"user_email": user_email, "user_name": user_name},
    )


async def send_account_approved_email(email: str, name: str | None = None) -> None:
    await send_email(
        to=email,
        email_type="account_approved",
        subject="MCPWorks - Account Approved",
        template_name="account_approved.html",
        template_vars={"name": name or email.split("@")[0]},
    )


async def send_account_rejected_email(
    email: str, name: str | None = None, reason: str | None = None
) -> None:
    await send_email(
        to=email,
        email_type="account_rejected",
        subject="MCPWorks - Account Update",
        template_name="account_rejected.html",
        template_vars={"name": name or email.split("@")[0], "reason": reason},
    )

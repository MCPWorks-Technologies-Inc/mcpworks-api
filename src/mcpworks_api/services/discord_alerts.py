"""Discord webhook alerts for security-critical admin events."""

import httpx
import structlog

from mcpworks_api.config import get_settings

logger = structlog.get_logger(__name__)


async def send_alert(title: str, description: str, color: int, fields: list[dict]) -> None:
    url = get_settings().discord_alert_webhook_url
    if not url:
        return

    embed = {
        "title": title,
        "description": description,
        "color": color,
        "fields": fields,
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                json={"embeds": [embed]},
                timeout=5.0,
            )
            if resp.status_code not in (200, 204):
                logger.warning(
                    "discord_alert_failed", status=resp.status_code, body=resp.text[:200]
                )
    except Exception as e:
        logger.warning("discord_alert_error", error=str(e))


async def send_new_account_alert(
    email: str,
    name: str | None,
    ip_address: str | None,
    user_agent: str | None,
) -> None:
    await send_alert(
        title="New Account Registration",
        description=f"**{email}** just signed up",
        color=0x5865F2,
        fields=[
            {"name": "Email", "value": email, "inline": True},
            {"name": "Name", "value": name or "-", "inline": True},
            {"name": "IP Address", "value": f"`{ip_address or 'unknown'}`", "inline": True},
            {
                "name": "User-Agent",
                "value": f"`{(user_agent or 'unknown')[:200]}`",
                "inline": False,
            },
        ],
    )


async def send_execution_alert(
    event: str,
    execution_id: str,
    tier: str,
    namespace: str,
    error_type: str | None = None,
    duration_ms: int | None = None,
    exit_code: int | None = None,
) -> None:
    color_map = {
        "timeout": 0xFEE75C,
        "violation": 0xED4245,
        "error": 0xE67E22,
    }
    fields = [
        {"name": "Execution", "value": f"`{execution_id[:12]}…`", "inline": True},
        {"name": "Tier", "value": tier, "inline": True},
        {"name": "Namespace", "value": namespace, "inline": True},
    ]
    if error_type:
        fields.append({"name": "Error Type", "value": error_type, "inline": True})
    if duration_ms is not None:
        fields.append({"name": "Duration", "value": f"{duration_ms}ms", "inline": True})
    if exit_code is not None:
        fields.append({"name": "Exit Code", "value": str(exit_code), "inline": True})
    await send_alert(
        title=f"Sandbox {event.title()}",
        description=f"Execution {event} in **{namespace}**",
        color=color_map.get(event, 0xE67E22),
        fields=fields,
    )


async def send_impersonation_alert(
    admin_email: str,
    target_email: str,
    ip_address: str,
    user_agent: str,
    timestamp: str,
) -> None:
    await send_alert(
        title="Impersonation Alert",
        description=f"**{admin_email}** is logging in as **{target_email}**",
        color=0xED4245,
        fields=[
            {"name": "Admin", "value": admin_email, "inline": True},
            {"name": "Target User", "value": target_email, "inline": True},
            {"name": "IP Address", "value": f"`{ip_address}`", "inline": True},
            {"name": "User-Agent", "value": f"`{user_agent[:200]}`", "inline": False},
            {"name": "Time (UTC)", "value": timestamp, "inline": True},
        ],
    )

"""Function templates for quick-start onboarding.

ORDER-011: Pre-built templates that demonstrate value in 60 seconds.
Each template provides code, description, input/output schemas, and requirements.
"""

from typing import Any


class FunctionTemplate:
    """A pre-built function template."""

    def __init__(
        self,
        name: str,
        description: str,
        code: str,
        input_schema: dict[str, Any],
        output_schema: dict[str, Any],
        tags: list[str],
        requirements: list[str] | None = None,
    ):
        self.name = name
        self.description = description
        self.code = code
        self.input_schema = input_schema
        self.output_schema = output_schema
        self.tags = tags
        self.requirements = requirements or []

    def to_dict(self) -> dict[str, Any]:
        """Return template as a dict for MCP response."""
        return {
            "name": self.name,
            "description": self.description,
            "tags": self.tags,
            "requirements": self.requirements,
        }

    def to_full_dict(self) -> dict[str, Any]:
        """Return template with code and schemas for cloning."""
        return {
            "name": self.name,
            "description": self.description,
            "code": self.code,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "tags": self.tags,
            "requirements": self.requirements,
        }


TEMPLATES: dict[str, FunctionTemplate] = {
    "hello-world": FunctionTemplate(
        name="hello-world",
        description="Simple input/output function — proves the system works",
        code='''\
def main(input_data):
    name = input_data.get("name", "World")
    return {"greeting": f"Hello, {name}!", "message": "Your sandbox is working."}
''',
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name to greet"},
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "greeting": {"type": "string"},
                "message": {"type": "string"},
            },
        },
        tags=["starter", "example"],
    ),
    "csv-analyzer": FunctionTemplate(
        name="csv-analyzer",
        description="Parse CSV data and return summary statistics",
        code='''\
import csv
import io
import statistics


def main(input_data):
    raw_csv = input_data.get("csv_data", "")
    reader = csv.DictReader(io.StringIO(raw_csv))
    rows = list(reader)

    if not rows:
        return {"error": "No data rows found"}

    columns = list(rows[0].keys())
    summary = {"row_count": len(rows), "columns": columns, "stats": {}}

    for col in columns:
        values = [r[col] for r in rows if r[col]]
        try:
            nums = [float(v) for v in values]
            summary["stats"][col] = {
                "type": "numeric",
                "min": min(nums),
                "max": max(nums),
                "mean": round(statistics.mean(nums), 2),
                "median": round(statistics.median(nums), 2),
            }
        except (ValueError, TypeError):
            unique = set(values)
            summary["stats"][col] = {
                "type": "text",
                "unique_count": len(unique),
                "sample_values": sorted(unique)[:5],
            }

    return summary
''',
        input_schema={
            "type": "object",
            "properties": {
                "csv_data": {
                    "type": "string",
                    "description": "Raw CSV text with header row",
                },
            },
            "required": ["csv_data"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "row_count": {"type": "integer"},
                "columns": {"type": "array", "items": {"type": "string"}},
                "stats": {"type": "object"},
            },
        },
        tags=["data", "analytics"],
    ),
    "api-connector": FunctionTemplate(
        name="api-connector",
        description="Call an external API and transform the response",
        code='''\
import httpx


def main(input_data):
    url = input_data.get("url", "")
    method = input_data.get("method", "GET").upper()
    headers = input_data.get("headers", {})
    body = input_data.get("body")

    if not url:
        return {"error": "url is required"}

    with httpx.Client(timeout=15) as client:
        response = client.request(method, url, headers=headers, json=body)

    return {
        "status_code": response.status_code,
        "headers": dict(response.headers),
        "body": response.text[:10000],
        "ok": response.is_success,
    }
''',
        input_schema={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to call"},
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"],
                    "description": "HTTP method (default: GET)",
                },
                "headers": {"type": "object", "description": "Request headers"},
                "body": {"description": "Request body (sent as JSON)"},
            },
            "required": ["url"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status_code": {"type": "integer"},
                "headers": {"type": "object"},
                "body": {"type": "string"},
                "ok": {"type": "boolean"},
            },
        },
        tags=["http", "integration"],
        requirements=["httpx"],
    ),
    "slack-notifier": FunctionTemplate(
        name="slack-notifier",
        description="Send a formatted message to a Slack webhook",
        code='''\
import httpx


def main(input_data):
    webhook_url = input_data.get("webhook_url", "")
    text = input_data.get("text", "")
    channel = input_data.get("channel")

    if not webhook_url or not text:
        return {"error": "webhook_url and text are required"}

    payload = {"text": text}
    if channel:
        payload["channel"] = channel

    with httpx.Client(timeout=10) as client:
        response = client.post(webhook_url, json=payload)

    return {
        "sent": response.is_success,
        "status_code": response.status_code,
        "response": response.text[:500],
    }
''',
        input_schema={
            "type": "object",
            "properties": {
                "webhook_url": {"type": "string", "description": "Slack incoming webhook URL"},
                "text": {"type": "string", "description": "Message text (supports Slack markdown)"},
                "channel": {"type": "string", "description": "Override channel (optional)"},
            },
            "required": ["webhook_url", "text"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "sent": {"type": "boolean"},
                "status_code": {"type": "integer"},
                "response": {"type": "string"},
            },
        },
        tags=["notification", "slack", "integration"],
        requirements=["httpx"],
    ),
    "scheduled-report": FunctionTemplate(
        name="scheduled-report",
        description="Generate and format a structured report from data",
        code='''\
from datetime import datetime, timezone


def main(input_data):
    title = input_data.get("title", "Report")
    sections = input_data.get("sections", [])
    output_format = input_data.get("format", "markdown")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    if output_format == "markdown":
        lines = [f"# {title}", f"*Generated: {now}*", ""]
        for section in sections:
            lines.append(f"## {section.get('heading', 'Section')}")
            lines.append(section.get("content", ""))
            lines.append("")
        report = "\\n".join(lines)
    else:
        report_data = {
            "title": title,
            "generated_at": now,
            "sections": sections,
        }
        import json
        report = json.dumps(report_data, indent=2)

    return {"report": report, "format": output_format, "generated_at": now}
''',
        input_schema={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Report title"},
                "sections": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "heading": {"type": "string"},
                            "content": {"type": "string"},
                        },
                    },
                    "description": "Report sections with heading and content",
                },
                "format": {
                    "type": "string",
                    "enum": ["markdown", "json"],
                    "description": "Output format (default: markdown)",
                },
            },
            "required": ["title", "sections"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "report": {"type": "string"},
                "format": {"type": "string"},
                "generated_at": {"type": "string"},
            },
        },
        tags=["reporting", "formatting"],
    ),
}


def list_templates() -> list[dict[str, Any]]:
    """Return summary of all available templates."""
    return [t.to_dict() for t in TEMPLATES.values()]


def get_template(name: str) -> FunctionTemplate | None:
    """Get a template by name."""
    return TEMPLATES.get(name)

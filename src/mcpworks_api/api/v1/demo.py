"""Demo request endpoint — receives booking form submissions from www.mcpworks.io/book/."""

import asyncio

from fastapi import APIRouter, status
from pydantic import BaseModel, EmailStr

from mcpworks_api.config import get_settings
from mcpworks_api.services.email import send_email

router = APIRouter(prefix="/demo", tags=["demo"])


class DemoRequest(BaseModel):
    name: str
    email: EmailStr
    company: str = ""
    preferred_date: str
    time_window: str
    message: str = ""


@router.post("/request", status_code=status.HTTP_200_OK)
async def request_demo(body: DemoRequest) -> dict[str, str]:
    settings = get_settings()

    for admin in settings.admin_emails:
        asyncio.create_task(
            send_email(
                to=admin,
                email_type="demo_request",
                subject=f"MCPWorks Demo Request: {body.name} ({body.email})",
                template_name="demo_request.html",
                template_vars={
                    "name": body.name,
                    "email": body.email,
                    "company": body.company,
                    "preferred_date": body.preferred_date,
                    "time_window": body.time_window,
                    "message": body.message,
                },
            )
        )

    asyncio.create_task(
        send_email(
            to=body.email,
            email_type="demo_confirmation",
            subject="MCPWorks — Demo Request Received",
            template_name="demo_confirmation.html",
            template_vars={"name": body.name},
        )
    )

    return {"status": "received"}

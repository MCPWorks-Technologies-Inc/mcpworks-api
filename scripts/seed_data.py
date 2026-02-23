#!/usr/bin/env python3
"""Seed initial data for development and testing.

Seeds:
- Services (math, agent)
- Test user (development only)

Usage:
    python scripts/seed_data.py
"""

import asyncio
from decimal import Decimal

from sqlalchemy import select

from mcpworks_api.config import get_settings
from mcpworks_api.core.database import get_db_context
from mcpworks_api.models import Credit, Service, User


async def seed_services() -> None:
    """Seed initial services for routing."""
    services_data = [
        {
            "name": "math",
            "display_name": "Math MCP",
            "description": "Mathematical verification and tutoring using Qwen2.5-Math models",
            "url": "http://mcpworks-math:8000",
            "health_check_url": "http://mcpworks-math:8000/health",
            "credit_cost": Decimal("1.00"),
            "tier_required": "free",
            "status": "active",
        },
        {
            "name": "agent",
            "display_name": "Agent MCP",
            "description": "Activepieces workflow execution via MCP protocol",
            "url": "http://mcpworks-agent:8000",
            "health_check_url": "http://mcpworks-agent:8000/health",
            "credit_cost": Decimal("5.00"),
            "tier_required": "starter",
            "status": "active",
        },
    ]

    async with get_db_context() as db:
        for service_data in services_data:
            # Check if service already exists
            result = await db.execute(select(Service).where(Service.name == service_data["name"]))
            existing = result.scalar_one_or_none()

            if existing:
                print(f"Service '{service_data['name']}' already exists, skipping")
                continue

            service = Service(**service_data)
            db.add(service)
            print(f"Created service: {service_data['name']}")

        await db.commit()


async def seed_test_user() -> None:
    """Seed a test user for development (only in debug mode)."""
    settings = get_settings()

    if not settings.app_debug:
        print("Skipping test user creation (not in debug mode)")
        return

    async with get_db_context() as db:
        # Check if test user exists
        result = await db.execute(select(User).where(User.email == "test@mcpworks.io"))
        existing = result.scalar_one_or_none()

        if existing:
            print("Test user already exists, skipping")
            return

        # Create test user with hashed password "testpassword"
        from mcpworks_api.core.security import hash_api_key

        user = User(
            email="test@mcpworks.io",
            password_hash=hash_api_key("testpassword"),
            name="Test User",
            tier="pro",
            status="active",
            email_verified=True,
        )
        db.add(user)
        await db.flush()

        # Create credit balance
        credit = Credit(
            user_id=user.id,
            available_balance=Decimal("1000.00"),
            held_balance=Decimal("0.00"),
            lifetime_earned=Decimal("1000.00"),
            lifetime_spent=Decimal("0.00"),
        )
        db.add(credit)

        await db.commit()
        print("Created test user: test@mcpworks.io (password: testpassword)")


async def main() -> None:
    """Run all seed functions."""
    print("Seeding database...")

    await seed_services()
    await seed_test_user()

    print("Done!")


if __name__ == "__main__":
    asyncio.run(main())

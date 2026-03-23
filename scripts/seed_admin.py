#!/usr/bin/env python3
"""Create an initial admin account for self-hosted MCPWorks.

Usage:
    ADMIN_EMAIL=admin@example.com ADMIN_PASSWORD=secret python3 scripts/seed_admin.py

The ADMIN_EMAIL must match the ADMIN_EMAILS config setting for admin access.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


async def main() -> None:
    email = os.environ.get("ADMIN_EMAIL")
    password = os.environ.get("ADMIN_PASSWORD")

    if not email or not password:
        print("Error: ADMIN_EMAIL and ADMIN_PASSWORD environment variables are required.")
        print(
            "Usage: ADMIN_EMAIL=admin@example.com ADMIN_PASSWORD=secret python3 scripts/seed_admin.py"
        )
        sys.exit(1)

    from mcpworks_api.core.security import hash_password
    from mcpworks_api.database import async_session_factory, engine
    from mcpworks_api.models.user import User, UserStatus, UserTier

    async with engine.begin():
        pass

    async with async_session_factory() as session:
        from sqlalchemy import select

        existing = await session.execute(select(User).where(User.email == email))
        if existing.scalar_one_or_none():
            print(f"User {email} already exists. Skipping.")
            return

        user = User(
            email=email,
            password_hash=hash_password(password),
            name="Admin",
            tier=UserTier.DEDICATED_AGENT.value,
            status=UserStatus.ACTIVE.value,
            email_verified=True,
        )
        session.add(user)
        await session.commit()
        print(f"Admin account created: {email}")
        print("Ensure this email is in ADMIN_EMAILS config for admin panel access.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

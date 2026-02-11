#!/usr/bin/env python3
"""Migrate tier names from old (starter/pro) to new (founder/founder_pro).

This script updates existing users and subscriptions to use the new tier names
per A0-SYSTEM-SPECIFICATION.md.

Usage:
    python scripts/migrate_tier_names.py [--dry-run]
"""

import argparse
import asyncio
import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


TIER_MAPPING = {
    "starter": "founder",
    "pro": "founder_pro",
}


async def migrate_tiers(database_url: str, dry_run: bool = False) -> dict:
    """Migrate tier names in users and subscriptions tables.

    Args:
        database_url: PostgreSQL connection URL
        dry_run: If True, only show what would be changed

    Returns:
        Dict with migration results
    """
    engine = create_async_engine(database_url)
    results = {"users": {}, "subscriptions": {}}

    async with engine.begin() as conn:
        # Check and migrate users table
        for old_tier, new_tier in TIER_MAPPING.items():
            # Count affected users
            count_result = await conn.execute(
                text("SELECT COUNT(*) FROM users WHERE tier = :old_tier"),
                {"old_tier": old_tier}
            )
            count = count_result.scalar()
            results["users"][f"{old_tier}_to_{new_tier}"] = count

            if count > 0 and not dry_run:
                await conn.execute(
                    text("UPDATE users SET tier = :new_tier WHERE tier = :old_tier"),
                    {"old_tier": old_tier, "new_tier": new_tier}
                )
                print(f"  Updated {count} users from '{old_tier}' to '{new_tier}'")
            elif count > 0:
                print(f"  [DRY RUN] Would update {count} users from '{old_tier}' to '{new_tier}'")

        # Check and migrate subscriptions table
        for old_tier, new_tier in TIER_MAPPING.items():
            # Count affected subscriptions
            count_result = await conn.execute(
                text("SELECT COUNT(*) FROM subscriptions WHERE tier = :old_tier"),
                {"old_tier": old_tier}
            )
            count = count_result.scalar()
            results["subscriptions"][f"{old_tier}_to_{new_tier}"] = count

            if count > 0 and not dry_run:
                await conn.execute(
                    text("UPDATE subscriptions SET tier = :new_tier WHERE tier = :old_tier"),
                    {"old_tier": old_tier, "new_tier": new_tier}
                )
                print(f"  Updated {count} subscriptions from '{old_tier}' to '{new_tier}'")
            elif count > 0:
                print(f"  [DRY RUN] Would update {count} subscriptions from '{old_tier}' to '{new_tier}'")

    await engine.dispose()
    return results


async def show_current_tiers(database_url: str) -> None:
    """Show current tier distribution."""
    engine = create_async_engine(database_url)

    async with engine.begin() as conn:
        print("\nCurrent tier distribution:")
        print("-" * 40)

        # Users by tier
        result = await conn.execute(
            text("SELECT tier, COUNT(*) as count FROM users GROUP BY tier ORDER BY tier")
        )
        rows = result.fetchall()
        print("\nUsers:")
        for row in rows:
            print(f"  {row[0]}: {row[1]}")

        # Subscriptions by tier
        result = await conn.execute(
            text("SELECT tier, COUNT(*) as count FROM subscriptions GROUP BY tier ORDER BY tier")
        )
        rows = result.fetchall()
        print("\nSubscriptions:")
        for row in rows:
            print(f"  {row[0]}: {row[1]}")

    await engine.dispose()


async def main():
    parser = argparse.ArgumentParser(description="Migrate tier names to new format")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without applying")
    args = parser.parse_args()

    # Get database URL from environment
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL environment variable not set")
        sys.exit(1)

    # Ensure async driver
    if "postgresql://" in database_url and "asyncpg" not in database_url:
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://")

    print("=" * 50)
    print("Tier Migration: starter/pro → founder/founder_pro")
    print("=" * 50)

    if args.dry_run:
        print("\n[DRY RUN MODE - No changes will be made]\n")

    # Show current state
    await show_current_tiers(database_url)

    # Run migration
    print("\nMigrating tiers...")
    results = await migrate_tiers(database_url, dry_run=args.dry_run)

    # Summary
    total_users = sum(results["users"].values())
    total_subs = sum(results["subscriptions"].values())

    print("\n" + "=" * 50)
    print("Migration Summary:")
    print(f"  Users affected: {total_users}")
    print(f"  Subscriptions affected: {total_subs}")

    if args.dry_run and (total_users > 0 or total_subs > 0):
        print("\nRun without --dry-run to apply changes")
    elif total_users == 0 and total_subs == 0:
        print("\nNo migration needed - all tiers already use new names")
    else:
        print("\nMigration complete!")

    # Show final state
    if not args.dry_run:
        await show_current_tiers(database_url)


if __name__ == "__main__":
    asyncio.run(main())

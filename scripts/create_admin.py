#!/usr/bin/env python3
"""
Bootstrap script to create the first admin user.

Usage: uv run -m scripts.create_admin --name admin --email admin@example.com --password mypassword
"""

import argparse

from src.api.core.auth import get_password_hash
from src.db.models import aget_db_session
from src.db.repositories.client_repository import ClientRepository
from src.db.repositories.role_repository import RoleRepository
from src.schemas.db.models import ROLES, ClientSchema
from src.schemas.types import RoleTypeEnum, TierEnum


async def acreate_admin_user(name: str, email: str, password: str) -> None:
    """Create the first admin user."""
    async with aget_db_session() as db:
        client_repo = ClientRepository(db=db)
        role_repo = RoleRepository(db=db)

        # Check if user already exists
        existing_user = await client_repo.aget_client_by_name(name=name)
        if existing_user:
            print(f"❌ User '{name}' already exists.")

            print(f"Name: {name}")
            print(f"Email: {email}")
            print(f"Password: {password}")
            return

        # Check if roles exist, if not create them
        try:
            for role_name, role_schema in ROLES.items():
                await role_repo.acreate_role(role=role_schema)
                print(f"✅ Role '{role_name}' created successfully.")

        except Exception as e:
            print(f"❌ Role creation failed or roles already exist: {e}")

        try:
            # Create admin user
            password_hash = get_password_hash(password)
            user_data = ClientSchema(
                name=name,
                external_id="admin-001",
                email=email,
                tier=TierEnum.PRO,
                credits=10_000.0,
                password_hash=password_hash,
            )

            client_id = await client_repo.acreate_client(client=user_data)
            await client_repo.aassign_role_to_client(
                client_id=client_id, role=RoleTypeEnum.ADMIN
            )
        except Exception as e:
            print(f"❌ Admin user creation failed or already exists: {e}")

            print(f"Name: {name}")
            print(f"Email: {email}")
            print(f"Password: {password}")
            return

        finally:
            print("🎉 Admin user created successfully!")
            print(f"Name: {name}")
            print(f"Email: {email}")
            print(f"Password: {password}")


async def main() -> None:
    """Main function."""
    parser = argparse.ArgumentParser(description="Create the first admin user")
    parser.add_argument("--name", required=True, help="Admin username")
    parser.add_argument("--email", required=True, help="Admin email")
    parser.add_argument("--password", required=True, help="Admin password")

    args = parser.parse_args()

    print("🚀 Creating first admin user...")
    await acreate_admin_user(
        name=args.name,
        email=args.email,
        password=args.password,
    )


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())

"""
Crud operations for the role repository.

(Using SQLAlchemy ORM v2.x)
"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from src import create_logger
from src.db.models import DBRole
from src.schemas.db.models import RoleSchema

logger = create_logger(__name__)


class RoleRepository:
    """CRUD operations for the Role repository."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def aget_role_by_id(self, id: int) -> DBRole | None:
        """Get a role by its ID."""
        try:
            stmt = select(DBRole).where(DBRole.id == id)
            return await self.db.scalar(stmt)
        except Exception as e:
            logger.error(f"Error fetching role by id '{id}': {e}")
            return None

    async def aget_role_by_name(self, name: str) -> DBRole | None:
        """Get a role by its name."""
        try:
            stmt = select(DBRole).where(DBRole.name == name)
            return await self.db.scalar(stmt)
        except Exception as e:
            logger.error(f"Error fetching role by name '{name}': {e}")
            return None

    async def acreate_role(self, role: RoleSchema) -> bool:
        """Create a role in the database."""
        try:
            db_role = DBRole(
                **role.model_dump(exclude={"id", "created_at", "updated_at"})
            )
        except Exception as e:
            logger.error(f"Error preparing role for creation: {e}")
            raise e

        try:
            self.db.add(db_role)
            await self.db.commit()
            logger.info("Successfully created role in the database.")
            return True

        except IntegrityError as e:
            logger.error(f"Integrity error creating role: {e}")
            await self.db.rollback()
            raise e

        except Exception as e:
            logger.error(f"Error creating role: {e}")
            await self.db.rollback()
            raise e

    def convert_DBRole_to_schema(  # noqa: N802
        self, db_role: DBRole
    ) -> RoleSchema | None:
        """Convert a DBRole ORM object directly to a Pydantic response schema."""
        try:
            return RoleSchema.model_validate(db_role)
        except Exception as e:
            logger.error(f"Error converting DBRole to RoleSchema: {e}")
            return None

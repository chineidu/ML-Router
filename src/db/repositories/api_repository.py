"""
Crud operations for the api_keys repository.

(Using SQLAlchemy ORM v2.x)
"""

from datetime import datetime

from dateutil.parser import parse  # Very fast, handles ISO formats well
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)
from sqlalchemy.orm import selectinload

from src import create_logger
from src.db.models import DBApiKey
from src.schemas.db.models import ApiKeySchema

logger = create_logger(__name__)


class ApiKeyRepository:
    """CRUD operations for the api_keys repository."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def aget_api_keys_by_id(self, id: int) -> DBApiKey | None:
        """Get a api_keys by its ID."""
        try:
            stmt = select(DBApiKey).where(DBApiKey.id == id)
            return await self.db.scalar(stmt)
        except Exception as e:
            logger.error(f"Error fetching api_keys by id '{id}': {e}")
            return None

    async def aget_api_keys_by_prefix(self, key_prefix: str) -> DBApiKey | None:
        """Get a api_keys by its key prefix with eager loading of the client relationship."""
        try:
            stmt = (
                select(DBApiKey)
                .where(DBApiKey.key_prefix == key_prefix)
                .options(selectinload(DBApiKey.client))
            )
            return await self.db.scalar(stmt)
        except Exception as e:
            logger.error(f"Error fetching api_keys by key prefix '{key_prefix}': {e}")
            return None

    async def aget_api_keys_by_client_ids(
        self, client_ids: list[int]
    ) -> list[DBApiKey]:
        """Get api_keys by their client IDs with eager loading of the client relationship."""
        try:
            stmt = (
                select(DBApiKey)
                .where(DBApiKey.client_id.in_(client_ids))
                .options(selectinload(DBApiKey.client))
            )
            result = await self.db.scalars(stmt)
            return list(result.all())
        except Exception as e:
            logger.error(f"Error fetching api_keys by ids {client_ids}: {e}")
            return []

    async def aget_api_keys_by_creation_time(
        self, created_after: str, created_before: str
    ) -> list[DBApiKey]:
        """Get api_keys created within a specific time range. Uses database-level comparison.

        Parameters
        ----------
        created_after : str
            The start timestamp (inclusive). e.g. "2023-01-01T00:00:00"
        created_before : str
            The end timestamp (inclusive). e.g. "2023-01-31T23:59:59"

        Returns
        -------
        list[DBApiKey]
            List of api_keys created within the specified time range.
        """
        # Internal check: ensures the strings are at least valid dates
        # before hitting the DB
        try:
            start: datetime = parse(created_after)
            end: datetime = parse(created_before)
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid date format passed to query: {e}")
            raise ValueError("Timestamps must be valid ISO 8601 strings.") from e

        stmt = select(DBApiKey).where(
            DBApiKey.created_at >= start,
            DBApiKey.created_at <= end,
        )
        result = await self.db.scalars(stmt)
        return list(result.all())

    async def aget_api_keys_by_last_used_time(
        self, last_used_after: str, last_used_before: str
    ) -> list[DBApiKey]:
        """Get api_keys last used within a certain time period. Uses database-level comparison.

        Parameters
        ----------
        last_used_after : str
            The start timestamp (inclusive). e.g. "2023-01-01T00:00:00"
        last_used_before : str
            The end timestamp (inclusive). e.g. "2023-01-31T23:59:59"

        Returns
        -------
        list[DBApiKey]
            List of api_keys last_used within the specified time range.
        """
        # Internal check: ensures the strings are at least valid dates
        # before hitting the DB
        try:
            start: datetime = parse(last_used_after)
            end: datetime = parse(last_used_before)
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid date format passed to query: {e}")
            raise ValueError("Timestamps must be valid ISO 8601 strings.") from e

        stmt = select(DBApiKey).where(
            DBApiKey.last_used_at >= start,
            DBApiKey.last_used_at <= end,
        )
        result = await self.db.scalars(stmt)
        return list(result.all())

    async def acreate_api_keys(self, api_keys_obj: ApiKeySchema) -> bool:
        """Create api_keys in the database."""
        try:
            data = api_keys_obj.model_dump(exclude={"id", "created_at", "last_used_at"})
        except Exception as e:
            logger.error(f"Error preparing api_keys for creation: {e}")
            raise

        # Normalize to a list of dicts
        items = (
            [data]
            if isinstance(data, dict)
            else (data if isinstance(data, list) else None)
        )
        if not items:
            raise TypeError("api_keys_obj.model_dump returned unexpected type")

        db_objs = [DBApiKey(**item) for item in items]

        try:
            self.db.add_all(db_objs)
            await self.db.commit()
            logger.info(
                f"Successfully created {len(db_objs)} api_keys in the database."
            )
            return True

        except IntegrityError as e:
            logger.error(f"Integrity error creating api_keys: {e}")
            await self.db.rollback()
            raise
        except Exception as e:
            logger.error(f"Error creating api_keys: {e}")
            await self.db.rollback()
            raise e

    async def aupdate_api_keys(self, api_keys: ApiKeySchema) -> None:
        """Update a api_keys in the database in a single round trip."""

        # Filter out fields that are None/excluded
        update_data = {
            k: v
            for k, v in api_keys.model_dump(
                exclude={"id", "created_at", "last_used_at"}
            ).items()
            if v is not None
        }
        if not update_data:
            logger.info(
                f"No fields to update for api_keys with client_id {api_keys.client_id}. Skipping update."
            )
            return

        try:
            stmt = (
                update(DBApiKey)
                .where(DBApiKey.client_id == api_keys.client_id)
                .values(**update_data)
            )
            result = await self.db.execute(stmt)

            if result.rowcount == 0:  # type: ignore
                raise ValueError(
                    f"api_keys with client_id {api_keys.client_id!r} does not exist."
                )

            await self.db.commit()
            logger.info(
                f"Successfully updated api_keys with client_id {api_keys.client_id!r}."
            )

        except Exception as e:
            logger.error(
                f"Error updating api_keys with client_id {api_keys.client_id!r}: {e}"
            )
            await self.db.rollback()
            raise e

    def convert_DBApiKey_to_schema(self, db_api_key: DBApiKey) -> ApiKeySchema | None:  # noqa: N802
        """Convert a DBApiKey ORM object directly to a Pydantic response schema."""
        try:
            return ApiKeySchema.model_validate(db_api_key)
        except Exception as e:
            logger.error(f"Error converting DBApiKey to ApiKeySchema: {e}")
            return None

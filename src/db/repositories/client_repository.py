"""
Crud operations for the client repository.

(Using SQLAlchemy ORM v2.x)
"""

from datetime import datetime
from typing import Any

from dateutil.parser import parse  # Very fast, handles ISO formats well
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)
from sqlalchemy.orm import selectinload

from src import create_logger
from src.db.models import DBClient
from src.schemas.db.models import BaseClientSchema, ClientSchema
from src.schemas.types import ClientStatusEnum

logger = create_logger(__name__)


class ClientRepository:
    """CRUD operations for the Client repository."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def aget_client_by_id(self, id: int) -> DBClient | None:
        """Get a client by its external ID."""
        try:
            stmt = select(DBClient).where(DBClient.id == id)
            return await self.db.scalar(stmt)
        except Exception as e:
            logger.error(f"Error fetching client by id '{id}': {e}")
            return None

    async def aget_client_by_external_id(self, external_id: str) -> DBClient | None:
        """Get a client by its external ID."""
        try:
            stmt = select(DBClient).where(DBClient.external_id == external_id)
            return await self.db.scalar(stmt)
        except Exception as e:
            logger.error(f"Error fetching client by external_id '{external_id}': {e}")
            return None

    async def aget_client_by_external_ids(
        self, external_ids: list[str]
    ) -> list[DBClient]:
        """Get client by their external IDs."""
        try:
            stmt = select(DBClient).where(DBClient.external_id.in_(external_ids))
            result = await self.db.scalars(stmt)
            return list(result.all())
        except Exception as e:
            logger.error(f"Error fetching client by ids {external_ids}: {e}")
            return []

    async def aget_client_by_name(self, name: str) -> DBClient | None:
        """Get a client by its name."""
        try:
            stmt = select(DBClient).where(DBClient.name == name)
            return await self.db.scalar(stmt)
        except Exception as e:
            logger.error(f"Error fetching client by name '{name}': {e}")
            return None

    async def aget_client_by_email(self, email: str) -> DBClient | None:
        """Get a client by its email."""
        try:
            stmt = select(DBClient).where(DBClient.email == email)
            return await self.db.scalar(stmt)
        except Exception as e:
            logger.error(f"Error fetching client by email '{email}': {e}")
            return None

    async def aget_client_with_keys(self, external_id: str) -> DBClient | None:
        """Get a client along with their associated API keys.

        Note
        ----
        This method uses eager loading to fetch related API keys in a single query.
        (i.e. avoids N+1 query problem)
        """
        try:
            stmt = (
                select(DBClient)
                .where(DBClient.external_id == external_id)
                .options(selectinload(DBClient.api_keys))
            )
            return await self.db.scalar(stmt)

        except Exception as e:
            logger.error(f"Error fetching client with keys by id '{external_id}': {e}")
            return None

    async def aget_clients_by_status(self, status: ClientStatusEnum) -> list[DBClient]:
        """Get clients by their status."""
        try:
            stmt = select(DBClient).where(DBClient.status == status.value)
            result = await self.db.scalars(stmt)
            return list(result.all())
        except Exception as e:
            logger.error(f"Error fetching clients by status {status}: {e}")
            return []

    async def aget_clients_by_creation_time(
        self, created_after: str, created_before: str
    ) -> list[DBClient]:
        """Get clients created within a specific time range. Uses database-level comparison.

        Parameters
        ----------
        created_after : str
            The start timestamp (inclusive). e.g. "2023-01-01T00:00:00"
        created_before : str
            The end timestamp (inclusive). e.g. "2023-01-31T23:59:59"

        Returns
        -------
        list[DBClient]
            List of clients created within the specified time range.
        """
        # Internal check: ensures the strings are at least valid dates
        # before hitting the DB
        try:
            start: datetime = parse(created_after)
            end: datetime = parse(created_before)
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid date format passed to query: {e}")
            raise ValueError("Timestamps must be valid ISO 8601 strings.") from e

        stmt = select(DBClient).where(
            DBClient.created_at >= start,
            DBClient.created_at <= end,
        )
        result = await self.db.scalars(stmt)
        return list(result.all())

    async def aget_clients_by_updated_time(
        self, updated_after: str, updated_before: str
    ) -> list[DBClient]:
        """Get clients updated within a specific time range. Uses database-level comparison.

        Parameters
        ----------
        updated_after : str
            The start timestamp (inclusive). e.g. "2023-01-01T00:00:00"
        updated_before : str
            The end timestamp (inclusive). e.g. "2023-01-31T23:59:59"

        Returns
        -------
        list[DBClient]
            List of clients updated within the specified time range.
        """
        # Internal check: ensures the strings are at least valid dates
        # before hitting the DB
        try:
            start: datetime = parse(updated_after)
            end: datetime = parse(updated_before)
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid date format passed to query: {e}")
            raise ValueError("Timestamps must be valid ISO 8601 strings.") from e

        stmt = select(DBClient).where(
            DBClient.updated_at >= start,
            DBClient.updated_at <= end,
        )
        result = await self.db.scalars(stmt)
        return list(result.all())

    async def acreate_client(self, clients: list[ClientSchema]) -> bool:
        """Batch create client in the database."""
        try:
            db_clients = [
                DBClient(
                    **client.model_dump(
                        exclude={"id", "password", "created_at", "updated_at"}
                    )
                )
                for client in clients
            ]
        except Exception as e:
            logger.error(f"Error preparing clients for creation: {e}")
            raise e

        try:
            self.db.add_all(db_clients)
            await self.db.commit()
            logger.info(
                f"Successfully created {len(db_clients)!r} clients in the database."
            )
            return True

        except IntegrityError as e:
            logger.error(f"Integrity error creating clients: {e}")
            await self.db.rollback()
            raise e

        except Exception as e:
            logger.error(f"Error creating clients: {e}")
            await self.db.rollback()
            raise e

    async def aupdate_client(self, client: ClientSchema) -> None:
        """Update a client in the database in a single round trip."""

        # Filter out fields that are None/excluded
        update_data = {
            k: v
            for k, v in client.model_dump(
                exclude={"id", "created_at", "updated_at"}
            ).items()
            if v is not None
        }
        if not update_data:
            logger.info(
                f"No fields to update for client with external_id {client.external_id}. Skipping update."
            )
            return

        try:
            stmt = (
                update(DBClient)
                .where(DBClient.external_id == client.external_id)
                .values(**update_data)
            )
            result = await self.db.execute(stmt)

            if result.rowcount == 0:  # type: ignore
                raise ValueError(
                    f"Client with external_id {client.external_id!r} does not exist."
                )

            await self.db.commit()
            logger.info(
                f"Successfully updated client with external_id {client.external_id!r}."
            )

        except Exception as e:
            logger.error(
                f"Error updating client with external_id {client.external_id!r}: {e}"
            )
            await self.db.rollback()
            raise e

    async def abatch_update_clients(self, clients: list[ClientSchema]) -> None:
        """Batch update clients in the database."""
        external_ids = [client.external_id for client in clients]
        existing_clients = await self.aget_client_by_external_ids(external_ids)
        existing_clients_dict = {
            client.external_id: client for client in existing_clients
        }

        for client in clients:
            existing_client = existing_clients_dict.get(client.external_id)
            if not existing_client:
                logger.warning(
                    f"Client with external_id {client.external_id!r} does not exist. Skipping update."
                )
                continue

            # Filter out fields that are None/excluded
            updated_values = {
                k: v
                for k, v in client.model_dump(
                    exclude={"id", "created_at", "updated_at"}
                ).items()
                if v is not None
            }
            # Update only the fields that are provided
            for field, value in updated_values.items():
                setattr(existing_client, field, value)

        try:
            self.db.add_all(existing_clients)
            await self.db.commit()
            logger.info(
                f"Successfully completed batch update of {len(existing_clients)} clients in the database."
            )

        except Exception as e:
            logger.error(f"Error batch updating clients: {e}")
            await self.db.rollback()
            raise e

    async def aupdate_client_status(
        self, external_id: str, status: ClientStatusEnum
    ) -> None:
        """Update the status of a client.

        Parameters
        ----------
        external_id : str
            The unique client identifier.
        status : ClientStatusEnum
            The new status to set for the client.

        Raises
        ------
        Exception
            If the update fails.
        """
        try:
            update_values: dict[str, Any] = {"status": status.value}

            stmt = (
                update(DBClient)
                .where(DBClient.external_id == external_id)
                .values(**update_values)
            )
            await self.db.execute(stmt)
            await self.db.commit()
            logger.info(f"Marked external_id='{external_id}' as {status.name}.")

        except Exception as e:
            logger.error(
                f"Error marking external_id='{external_id}' as {status.name}: {e}"
            )
            await self.db.rollback()
            raise e

    def convert_DBClient_to_schema(
        self, db_client: DBClient
    ) -> BaseClientSchema | None:  # noqa: N802
        """Convert a DBClient ORM object directly to a Pydantic response schema."""
        try:
            return BaseClientSchema.model_validate(db_client)
        except Exception as e:
            logger.error(f"Error converting DBClient to BaseClientSchema: {e}")
            return None

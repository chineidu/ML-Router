"""Database models and utilities."""

from contextlib import asynccontextmanager
from datetime import datetime
from decimal import Decimal
from typing import AsyncGenerator

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from src.config import app_settings
from src.db import AsyncDatabasePool
from src.schemas.types import ClientStatusEnum, TierEnum


class Base(DeclarativeBase):
    """Base class for all database models."""

    pass


# =========================================================
# ==================== Database Models ====================
# =========================================================
class DBClient(Base):
    """Data model for storing client information."""

    __tablename__: str = "clients"

    id: Mapped[int] = mapped_column("id", primary_key=True)
    external_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Enums
    tier: Mapped[str] = mapped_column(SAEnum(TierEnum), nullable=False)
    status: Mapped[str] = mapped_column(SAEnum(ClientStatusEnum), nullable=False)

    # Decimal is used for precise financial calculations
    credits: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), nullable=False, default=0.0
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now(), onupdate=func.now()
    )

    # Relationship: Enables Python-side navigation (e.g. my_client_instance.api_keys)
    # Note: This does not create a column in the 'clients' database table.
    # When retrieving, use selectinload(DBClient.api_keys) to eager load api_keys
    api_keys: Mapped[list["DBApiKey"]] = relationship(
        back_populates="client", cascade="all, delete-orphan"
    )

    # Composite index for optimized queries
    __table_args__ = (Index("ix_clients_status_created_at", "status", "created_at"),)

    def __repr__(self) -> str:
        """
        Returns a string representation of the Client object.

        Returns
        -------
        str
        """
        return (
            f"{self.__class__.__name__}(id={self.id!r}, external_id={self.external_id!r}, "
            f"status={self.status!r})"
        )


class DBApiKey(Base):
    """Data model for storing api_keys information."""

    __tablename__: str = "api_keys"

    id: Mapped[int] = mapped_column("id", primary_key=True)
    # Foreign key to DBClient.id, unique=False to allow multiple keys per client
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(10), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    requests_per_minute: Mapped[int] = mapped_column(
        Integer, nullable=False, default=60
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now()
    )
    last_used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationship: Enables Python-side navigation (e.g. my_api_key_instance.client)
    # Note: This does not create a column in the 'api_keys' database table.
    client: Mapped["DBClient"] = relationship(back_populates="api_keys")

    # Composite index for optimized queries
    __table_args__ = (Index("ix_api_keys_name_created_at", "name", "created_at"),)

    def __repr__(self) -> str:
        """
        Returns a string representation of the ApiKey object.

        Returns
        -------
        str
        """
        return (
            f"{self.__class__.__name__}(id={self.id!r}, name={self.name!r}, "
            f"requests_per_minute={self.requests_per_minute!r})"
        )


# =========================================================
# ==================== Utilities ==========================
# =========================================================
# Global pool instance
_db_pool: AsyncDatabasePool | None = None


async def aget_db_pool() -> AsyncDatabasePool:
    """Get or create the global async database pool."""
    global _db_pool
    if _db_pool is None:
        _db_pool = AsyncDatabasePool(app_settings.database_url)
    return _db_pool


@asynccontextmanager
async def aget_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Get a database session context manager.

    Use this for manual session management with 'with' statements.

    Yields
    ------
    Session
        A database session

    Example
    -------
        with aget_db_session() as session:
            # use session here
    """
    db_pool = await aget_db_pool()
    async with db_pool.aget_session() as session:
        yield session


async def aget_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for async database sessions.

    This is a generator function that FastAPI will handle automatically.
    Use this with Depends() in your route handlers.

    Yields
    ------
    Session
        An async database session that will be automatically closed after the request
    """
    db_pool = await aget_db_pool()
    async with db_pool.aget_session() as session:
        try:
            yield session
        finally:
            # Session cleanup is handled by the context manager
            pass

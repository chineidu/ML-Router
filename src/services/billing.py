from sqlalchemy import func, update

from src import create_logger
from src.db.models import DBAPIKey, DBClient, aget_db

logger = create_logger(name=__name__)


async def adeduct_credits_background(client_id: int, key_id: int, cost: float) -> None:
    """
    Deduct credits from a client's account and update API key usage.
    Intended to be run as a background task.
    """
    async for session in aget_db():
        try:
            # Task 1: Update Timestamp
            stmt_key = (
                update(DBAPIKey)
                .where(DBAPIKey.id == key_id)
                .values(last_used_at=func.now())
            )
            await session.execute(stmt_key)

            # Task 2: Deduct Credits (if cost > 0)
            if cost > 0:
                stmt_bill = (
                    update(DBClient)
                    .where(DBClient.id == client_id)
                    .values(credits=DBClient.credits - cost)
                )
                await session.execute(stmt_bill)

            # Commit both changes in a single transaction
            # This ensures atomicity - either both succeed or both fail
            await session.commit()
            logger.debug(f"Billing Success: Client {client_id} | Cost {cost:.2f}")

        except Exception as e:
            logger.error(f"Billing Failed for Client {client_id}: {e}")

        # Break generator to close session
        break

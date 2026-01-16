import asyncio
import time
import warnings
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, AsyncGenerator

from fastapi import FastAPI

from src import create_logger
from src.config import app_settings

if TYPE_CHECKING:
    pass

warnings.filterwarnings("ignore")
logger = create_logger(name="api_lifespan")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:  # noqa: ARG001
    """Initialize and cleanup FastAPI application lifecycle.

    This context manager handles the initialization of required resources
    during startup and cleanup during shutdown.
    """
    try:
        start_time: float = time.perf_counter()
        logger.info(f"ENVIRONMENT: {app_settings.ENV} | DEBUG: {app_settings.DEBUG} ")
        logger.info("Starting up application and loading model...")

        # ====================================================
        # ================= Load Dependencies ================
        # ====================================================

        # ---------- Setup database ----------

        logger.info(
            f"Application startup completed in {time.perf_counter() - start_time:.2f} seconds"
        )

        # Yield control to the application
        yield

    # ====================================================
    # =============== Cleanup Dependencies ===============
    # ====================================================
    except Exception as e:
        logger.error("❌ Application startup failed")
        logger.error(f"   Reason: {e}")
        raise

    finally:
        logger.info("Shutting down application...")

        # ---------- Cleanup log cleanup task ----------
        if hasattr(app.state, "cleanup_task"):
            try:
                cleanup_task = app.state.cleanup_task
                cleanup_task.cancel()
                try:
                    await cleanup_task
                except asyncio.CancelledError:
                    logger.info("🚨 Log cleanup task cancelled")
            except Exception as e:
                logger.error(f"❌ Error shutting down log cleanup task: {e}")

        # ---------- Cleanup rate limiter ----------
        if hasattr(app.state, "limiter"):
            try:
                app.state.limiter = None
                logger.info("🚨 Rate limiter shutdown.")

            except Exception as e:
                logger.error(f"❌ Error shutting down the rate limiter: {e}")

        # ---------- Cleanup cache ----------
        if hasattr(app.state, "cache"):
            try:
                app.state.cache = None
                logger.info("🚨 Cache shutdown.")

            except Exception as e:
                logger.error(f"❌ Error shutting down the cache: {e}")

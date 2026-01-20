import asyncio
import time
import warnings
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, AsyncGenerator

import httpx
from fastapi import FastAPI

from src import create_logger
from src.api.core.cache import setup_cache
from src.api.core.ratelimit import limiter
from src.config import app_config, app_settings
from src.services.service_discovery import BackendRegistry, ServiceRegistry

if TYPE_CHECKING:
    pass

warnings.filterwarnings("ignore")
logger = create_logger(name=__name__)
BASE_URL: str = (
    f"{app_settings.PROTOCOL.value}://{app_settings.HOST}:{app_settings.PORT}"
)


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

        # ---------- Init shared client ----------
        timeout = httpx.Timeout(
            timeout=app_config.connection_config.timeout_seconds,
            connect=app_config.connection_config.connect_timeout_seconds,
            read=app_config.connection_config.read_timeout_seconds,
        )
        client: httpx.AsyncClient = httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=timeout,
            limits=httpx.Limits(
                max_connections=app_config.connection_config.max_connections,
                max_keepalive_connections=app_config.connection_config.max_keepalive_connections,
            ),
        )
        app.state.client = client

        # ---------- Setup Backend Registry ----------
        service_registry = ServiceRegistry(
            registry_file=app_config.registry_config.registry_file,
            load_registry_from_file=app_config.registry_config.load_registry_from_file,
            health_check_interval=app_config.registry_config.health_check_interval,
        )
        backend_registry: BackendRegistry = BackendRegistry(
            service_registry=service_registry
        )
        await service_registry.ainitialize()
        app.state.backend_registry = backend_registry
        app.state.service_registry = service_registry

        # Start background health check loop
        app.state.health_check_task = asyncio.create_task(
            service_registry.ahealth_check_loop()
        )

        logger.info("✅ Shared HTTP client initialized.")

        # ---------- Setup cache ----------
        app.state.cache = setup_cache()
        logger.info("✅ Cache initialized")

        # ---------- Setup rate limiter ----------
        app.state.limiter = limiter
        logger.info("✅ Rate limiter initialized")

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

        # ---------- Cleanup rate limiter ----------
        if hasattr(app.state, "limiter"):
            try:
                app.state.limiter = None
                logger.info("🚨 Rate limiter shutdown.")

            except Exception as e:
                logger.error(f"❌ Error shutting down the rate limiter: {e}")

        # ---------- Cleanup client ----------
        if hasattr(app.state, "client") and app.state.client:
            try:
                await app.state.client.aclose()
                logger.info("🚨 Client shutdown.")

            except Exception as e:
                logger.error(f"❌ Error shutting down the client: {e}")

        # ---------- Cleanup health check task ----------
        if hasattr(app.state, "health_check_task") and app.state.health_check_task:
            try:
                app.state.health_check_task.cancel()
                logger.info("🚨 Health check task cancelled.")
            except Exception as e:
                logger.error(f"❌ Error cancelling health check task: {e}")

        # ---------- Cleanup backend registry ----------
        if hasattr(app.state, "backend_registry") and app.state.backend_registry:
            try:
                app.state.backend_registry = None
                logger.info("🚨 Backend registry saved and shutdown.")

            except Exception as e:
                logger.error(f"❌ Error shutting down the backend registry: {e}")

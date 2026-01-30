from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from omegaconf import DictConfig, OmegaConf
from pydantic import BaseModel, Field

from src import ROOT
from src.schemas.types import LoadBalancerStrategyEnum


@dataclass(slots=True, kw_only=True)
class RegistryConfig:
    """Service registry configuration class."""

    registry_file: str = field(
        metadata={"description": "Path to the service registry file."}
    )
    load_registry_from_file: bool = field(
        default=True,
        metadata={"description": "Whether to load the registry from file on startup."},
    )
    health_check_interval: int = field(
        default=10,
        metadata={
            "description": "Interval in seconds for performing health checks on services."
        },
    )

    def __post_init__(self) -> None:
        """Resolve registry_file path relative to project root if it's relative."""

        registry_path = Path(self.registry_file)
        if not registry_path.is_absolute():
            # Resolve relative to ROOT
            self.registry_file = str(ROOT / self.registry_file)


@dataclass(slots=True, kw_only=True)
class CircuitBreakerConfig:
    failure_threshold: int = field(
        default=5,
        metadata={
            "description": "Number of consecutive failures to trip the circuit breaker"
        },
    )
    recovery_timeout: int = field(
        default=60,
        metadata={
            "description": "Time in seconds before attempting to reset the circuit breaker"
        },
    )


@dataclass(slots=True, kw_only=True)
class BulkheadConfig:
    """Bulkhead configuration class."""

    queue_timeout_seconds: float = field(
        metadata={"description": "Timeout duration for queueing in seconds."}
    )
    prediction_semaphore_config: dict[str, int] = field(
        metadata={
            "description": "Configuration for prediction semaphores per model type"
        }
    )


@dataclass(slots=True, kw_only=True)
class ConnectionConfig:
    """Connection configuration class."""

    timeout_seconds: int = field(
        metadata={"description": "Timeout duration for connections in seconds."}
    )
    connect_timeout_seconds: int = field(
        metadata={"description": "Connection timeout duration in seconds."}
    )
    read_timeout_seconds: int = field(
        metadata={"description": "Read timeout duration in seconds."}
    )
    max_connections: int = field(
        metadata={"description": "Maximum number of connections."}
    )
    max_keepalive_connections: int = field(
        metadata={"description": "Maximum number of keep-alive connections."}
    )


@dataclass(slots=True, kw_only=True)
class LoadBalancerConfig:
    """Load balancer configuration class."""

    strategy: LoadBalancerStrategyEnum = field(
        default=LoadBalancerStrategyEnum.ROUND_ROBIN,
        metadata={
            "description": "Load balancing strategy (e.g., round_robin, weighted_round_robin)."
        },
    )


@dataclass(slots=True, kw_only=True)
class CORS:
    """CORS configuration class."""

    allow_origins: list[str] = field(
        default_factory=list, metadata={"description": "Allowed origins for CORS."}
    )
    allow_credentials: bool = field(
        metadata={"description": "Allow credentials for CORS."}
    )
    allow_methods: list[str] = field(
        default_factory=list, metadata={"description": "Allowed methods for CORS."}
    )
    allow_headers: list[str] = field(
        default_factory=list, metadata={"description": "Allowed headers for CORS."}
    )


@dataclass(slots=True, kw_only=True)
class Middleware:
    """Middleware configuration class."""

    cors: CORS = field(metadata={"description": "CORS configuration."})


@dataclass(slots=True, kw_only=True)
class APIConfig:
    """API-level configuration."""

    title: str = field(metadata={"description": "The title of the API."})
    name: str = field(metadata={"description": "The name of the API."})
    description: str = field(metadata={"description": "The description of the API."})
    version: str = field(metadata={"description": "The version of the API."})
    status: str = field(metadata={"description": "The current status of the API."})
    prefix: str = field(metadata={"description": "The prefix for the API routes."})
    auth_prefix: str = field(
        metadata={"description": "The prefix for the authentication routes."}
    )
    middleware: Middleware = field(
        metadata={"description": "Middleware configuration."}
    )
    ratelimit: dict[str, dict[str, Any]] = field(
        metadata={"description": "Ratelimit configuration."}
    )
    credit_costs: dict[str, float] = field(
        default_factory=dict,
        metadata={"description": "Per-endpoint credit cost overrides."},
    )


@dataclass(slots=True, kw_only=True)
class DatabaseConfig:
    """Database configuration class."""

    pool_size: int = field(
        default=30, metadata={"description": "Number of connections to keep in pool"}
    )
    max_overflow: int = field(
        default=10, metadata={"description": "Number of extra connections allowed"}
    )
    pool_timeout: int = field(
        default=20, metadata={"description": "Seconds to wait for a connection"}
    )
    pool_recycle: int = field(
        default=1800,
        metadata={"description": "Seconds after which to recycle connections"},
    )
    pool_pre_ping: bool = field(
        default=True, metadata={"description": "Whether to test connections before use"}
    )
    expire_on_commit: bool = field(
        default=False, metadata={"description": "Whether to expire objects on commit"}
    )


class AppConfig(BaseModel):
    """Application configuration with validation."""

    connection_config: ConnectionConfig = Field(
        description="Configuration settings for connections"
    )
    registry_config: RegistryConfig = Field(
        description="Configuration settings for the service registry"
    )
    circuit_breaker_config: CircuitBreakerConfig = Field(
        description="Configuration settings for the circuit breaker"
    )
    load_balancer_config: LoadBalancerConfig = Field(
        description="Configuration settings for the load balancer"
    )
    bulkhead_config: BulkheadConfig = Field(
        description="Configuration for bulkhead pattern and queue timeout"
    )
    api_config: APIConfig = Field(description="Configuration settings for the API")
    database_config: DatabaseConfig = Field(
        description="Configuration settings for the database"
    )


config_path: Path = ROOT / "src/config/config.yaml"
config: DictConfig = OmegaConf.load(config_path).config
resolved_cfg = OmegaConf.to_container(config, resolve=True)
app_config: AppConfig = AppConfig(**dict(resolved_cfg))  # type: ignore

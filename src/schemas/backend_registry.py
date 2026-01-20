import time
from dataclasses import asdict, dataclass, field
from typing import Any

from src.schemas.types import ProtocolEnum, StatusEnum


@dataclass(slots=True, kw_only=True)
class ServiceInstance:
    """Represents a backend service instance."""

    service_id: str = field(
        metadata={"description": "Unique identifier for the service instance."}
    )
    service_name: str = field(metadata={"description": "Name of the service."})
    host: str = field(metadata={"description": "Host address of the service instance."})
    port: int = field(metadata={"description": "Port number of the service instance."})
    protocol: ProtocolEnum = field(
        metadata={
            "description": "Protocol used by the service instance (e.g., http, https)."
        }
    )
    ttl_seconds: int = field(
        default=10,
        metadata={"description": "Time-to-live in seconds for the service instance."},
    )
    health_check_url: str = field(
        metadata={"description": "URL for health checking the service instance."}
    )
    metadata: dict[str, Any] = field(
        default_factory=dict,
        metadata={"description": "Additional metadata for the service instance."},
    )
    last_heartbeat: float | None = field(
        default=None,
        metadata={
            "description": "Timestamp of the last heartbeat received from the service instance."
        },
    )
    status: StatusEnum = field(
        default=StatusEnum.UNKNOWN,
        metadata={
            "description": "Current status of the service instance (e.g., healthy, unhealthy)."
        },
    )
    weight: int = field(
        default=1,
        metadata={
            "description": "Weight for load balancing among service instances. "
            "Higher weight means more traffic."
        },
    )
    # Runtime state (not part of initialization)
    active_connections: int = field(
        default=0,
        init=False,
        metadata={"description": "Number of in-flight requests."},
    )

    def __post_init__(self) -> None:
        """Post-initialization to ensure enums are correctly set."""
        if isinstance(self.protocol, str):
            self.protocol = ProtocolEnum(self.protocol)
        if isinstance(self.status, str):
            self.status = StatusEnum(self.status)

    def model_dump(self) -> dict[str, Any]:
        """Converts the ServiceInstance to a dictionary."""
        return asdict(self)

    @property
    def endpoint_url(self) -> str:
        """Constructs the endpoint URL for the service instance."""
        return f"{self.protocol.value}://{self.host}:{self.port}"

    @property
    def is_stale(self) -> bool:
        """Determines if the service instance is stale (no heartbeat in the last N seconds)."""
        if self.last_heartbeat:
            return (time.time() - self.last_heartbeat) > self.ttl_seconds
        return False

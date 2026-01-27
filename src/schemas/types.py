from enum import StrEnum


class EnvironmentEnum(StrEnum):
    DEVELOPMENT = "development"
    PRODUCTION = "production"
    SANDBOX = "sandbox"
    STAGING = "staging"
    TESTING = "testing"


class ModelTypeEnum(StrEnum):
    ANOMALY_DETECTION = "anomaly_detection"
    CLASSIFICATION = "classification"
    CLUSTERING = "clustering"
    NER = "ner"
    RECOMMENDATION = "recommendation"
    REGRESSION = "regression"
    SENTIMENT = "sentiment"


class ErrorCodeEnum(StrEnum):
    CIRCUIT_OPEN_ERROR = "circuit_open_error"
    HTTP_ERROR = "http_error"
    INTERNAL_SERVER_ERROR = "internal_server_error"
    INVALID_INPUT = "invalid_input"
    MAX_RETRIES_EXCEEDED = "max_retries_exceeded"
    RESOURCES_NOT_FOUND = "resources_not_found"
    SERVICE_UNAVAILABLE = "service_unavailable"
    TIMEOUT_ERROR = "timeout_error"
    UNAUTHORIZED = "unauthorized"
    UNEXPECTED_ERROR = "unexpected_error"


class ResourceEnum(StrEnum):
    """The type of resource to use."""

    BACKEND_REGISTRY = "backend_registry"
    CACHE = "cache"
    DATABASE = "database"
    RATE_LIMITER = "rate_limiter"
    SERVICE_REGISTRY = "service_registry"


class StatusEnum(StrEnum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class LoadBalancerStrategyEnum(StrEnum):
    LEAST_CONNECTIONS = "least_connections"
    ROUND_ROBIN = "round_robin"
    WEIGHTED = "weighted"


class CircuitBreakerStateEnum(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class ProtocolEnum(StrEnum):
    HTTP = "http"
    HTTPS = "https"


class TierEnum(StrEnum):
    """Client subscription tier."""

    FREE = "free"  # low limits, short TTLs and basic support
    PLUS = "plus"  # moderate limits, medium TTLs and standard support
    PRO = "pro"  # high limits, long TTLs and premium support


class ClientStatusEnum(StrEnum):
    # Onboarding
    PENDING_VERIFICATION = "pending_verification"  # Awaiting email/admin approval

    # Normal Operation
    ACTIVE = "active"  # Fully functional

    # User-Initiated (The user wants to stop)
    PAUSED = "paused"  # Temporarily stopped by the client
    ARCHIVED = "archived"  # Soft-deleted

    # Admin/System-Initiated (You stopped them)
    SUSPENDED = "suspended"  # Temporarily blocked (e.g. unpaid bill, rate limit abuse)
    BANNED = "banned"  # Permanently blocked

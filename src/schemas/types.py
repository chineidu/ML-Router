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
    BLOB_STORAGE_ERROR = "blob_storage_error"
    BUSINESS_LOGIC_ERROR = "business_logic_error"
    DATABASE_ERROR = "database_error"
    HTTP_ERROR = "http_error"
    INTERNAL_SERVER_ERROR = "internal_server_error"
    INVALID_INPUT = "invalid_input"
    MAX_RETRIES_EXCEEDED = "max_retries_exceeded"
    POISON_MESSAGE = "poison_message"
    RABBITMQ_ERROR = "rabbitmq_error"
    RESOURCES_NOT_FOUND = "resources_not_found"
    UNAUTHORIZED = "unauthorized"
    TIMEOUT_ERROR = "timeout_error"
    UNEXPECTED_ERROR = "unexpected_error"


class ResourceEnum(StrEnum):
    """The type of resource to use."""

    BACKEND_REGISTRY = "backend_registry"
    CACHE = "cache"
    DATABASE = "database"
    RATE_LIMITER = "rate_limiter"


class StatusEnum(StrEnum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class TaskEventTypeEnum(StrEnum):
    TASK_CREATED = "task.created"
    TASK_STARTED = "task.started"
    TASK_PROGRESS = "task.progress"
    TASK_ROUTED_TO_DELAY_QUEUE = "task.routed_to_delay_queue"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"


class PriorityEnum(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CircuitBreakerStateEnum(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class ProtocolEnum(StrEnum):
    HTTP = "http"
    HTTPS = "https"

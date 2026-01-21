# Architecture Decision Record (ADR)

- For documenting architectural decisions.

## ADR 001: Service Registry Loading Behavior

### Context

- In order to manage the lifecycle of services effectively, it is essential to ensure that the Service Registry is properly initialized and available for use in API endpoints.
- It performs the following functions:
  - Maintains a list of available services.
  - Provides service discovery capabilities.
  - Monitors the health status of services.
- The Service Registry should be loaded during the application startup phase to ensure that it is ready for use when API endpoints are accessed.
- Similar to the Backend Registry, the Service Registry will be injected into API endpoints using a dedicated dependency function.

### Decision

- The Service Registry will be loaded during the application startup phase, similar to the Backend Registry. A dedicated dependency function `get_service_registry` will be created to inject the Service Registry into API endpoints.
- This function will check for the existence of the Service Registry in the application state and raise a `ResourcesNotFoundError` if it is not found.

## ADR 002: Backend Registry

### Context

- The Backend Registry is a critical component that maintains a list of available backend services for the application.
- It provides service discovery capabilities and monitors the health status of backend services via the service discovery mechanism.
- Load balancing is implemented to distribute requests across multiple backend instances effectively.

### Decision

- The Backend Registry will be loaded during the application startup phase to ensure that it is ready for use when API endpoints are accessed.
- A dedicated dependency function `get_backend_registry` will be created to inject the Backend Registry into API endpoints.
- This function will check for the existence of the Backend Registry in the application state and raise a `ResourcesNotFoundError` if it is not found.

## ADR 003: Advanced Load Balancing Strategies

### Context

- The current load balancing strategy implemented in the Backend Registry is a simple round-robin approach.
- As the application scales and the number of backend services increases, it may be necessary to implement more advanced load balancing strategies to optimize performance and resource utilization.

### Decision

- The Backend Registry will be designed to support multiple load balancing strategies, including:
  - Least Connections: Directs traffic to the backend with the fewest active connections.
  - Weighted Round Robin: Distributes requests based on predefined weights assigned to each backend.
- The load balancing strategy can be configured via application settings, allowing for flexibility and adaptability to different deployment scenarios.

## ADR 004: Framework Selection - FastAPI

### Context

- Need a modern, high-performance web framework for building the ML Router API.
- Must support async/await for concurrent request handling.
- Require built-in data validation and serialization (Pydantic).
- Need automatic API documentation generation.
- Must support middleware composition and extensibility.

### Decision

- **Selected Framework**: FastAPI
  - Performance benefits: Uses Starlette under the hood with Uvicorn ASGI server
  - Async/await support enables non-blocking I/O for better concurrency
  - Pydantic integration provides automatic request/response validation and serialization
  - Built-in OpenAPI/Swagger and ReDoc documentation
  - Dependency injection system enables clean separation of concerns
  - Extensible middleware support allows custom request/response processing

**Rationale**: FastAPI's performance (3x faster than Flask, 2x faster than Node.js/Express) makes it ideal for handling high-throughput ML inference requests. The async architecture enables efficient connection pooling and concurrent processing of multiple ML model predictions.

## ADR 005: Service Discovery Strategy

### Context

- Need a mechanism to discover and register ML model backend services.
- Services may be deployed as standalone instances or in containerized environments (Docker).
- Must support dynamic service registration and health monitoring.
- Need to handle service failures and maintain service availability.

### Decision

- **Service Discovery Implementation**: Dual-mode approach
  1. **File-based Registry** (`data/service_registry.json`): Used for development and testing purposes. Allows manual service configuration and persistence.
  2. **Docker Discovery** (`DockerServiceDiscovery`): Used for production environments with Docker. Automatically discovers services running in the same Docker Compose network.

- **Health Monitoring**: Background health check loop (configurable interval, default 10 seconds) that:
  - Performs HTTP health checks on all registered services
  - Updates service status (HEALTHY/UNHEALTHY)
  - Automatically deregisters stale services (services that haven't reported a heartbeat)
  - Saves health status to the registry file

- **Persistence**: Registry state is persisted to disk on every registration, deregistration, or health status update.

**Rationale**: Dual-mode approach provides flexibility for different deployment scenarios. File-based registry simplifies development and testing, while Docker discovery enables seamless integration with containerized deployments. Background health checks ensure services are automatically marked as unhealthy when they become unavailable, improving system reliability.

## ADR 006: Load Balancing Strategies

### Context

- Need to distribute incoming prediction requests across multiple backend ML model services.
- Different strategies may be optimal for different workloads:
  - Round-robin provides even distribution for balanced workloads
  - Least connections optimizes for services with varying processing times
  - Weighted distribution allows prioritizing specific models or backends with more resources

### Decision

- Implemented three load balancing strategies in the BackendRegistry:
  1. **Round-Robin** (`ROUND_ROBIN`): Cyclic distribution across healthy instances. Simple and predictable.
  2. **Least Connections** (`LEAST_CONNECTIONS`): Selects backend with fewest active connections. Optimized for varying request processing times.
  3. **Weighted** (`WEIGHTED`): Random selection based on instance weights. Allows controlled distribution based on capacity or importance.

- Strategy configuration via `load_balancer_config.strategy` in config.yaml (default: `weighted`).
- Strategy selection is stateful (maintains index for round-robin, active connection counts for least connections).

**Rationale**: Providing multiple strategies allows flexibility to optimize request distribution based on specific requirements. Least connections is particularly valuable for ML inference where some models may have variable processing times based on input complexity. Weighted strategy enables capacity-based distribution without changing round-robin behavior.

## ADR 007: Async HTTP Client and Connection Management

### Context

- Need to forward prediction requests to backend ML services.
- Must handle concurrent connections efficiently.
- Need connection pooling to reduce overhead.
- Must support timeout configuration for various operations.

### Decision

- **HTTP Client**: httpx.AsyncClient with connection pooling
  - Supports async HTTP/1.1 and HTTP/2
  - Built-in connection pooling (configurable via config.yaml)
  - Automatic keep-alive for improved performance
  - Context manager pattern for proper resource cleanup

- **Configuration**:
  - Connection timeout: 10 seconds
  - Connect timeout: 5 seconds
  - Read timeout: 3 seconds
  - Maximum connections: 100
  - Maximum keepalive connections: 20

- **Implementation**: Dependency injection of httpx.AsyncClient via `get_client` dependency function in `dependencies.py`.

**Rationale**: httpx provides an excellent async interface compatible with httpx standard library patterns. Connection pooling significantly reduces connection overhead for high-throughput workloads. Separate timeouts for connect, read, and total operations allow fine-tuned control based on backend service capabilities.

## ADR 008: Middleware Stack Order and Composition

### Context

- Need to implement multiple concerns in request/response processing:
  - Custom application middleware
  - CORS (Cross-Origin Resource Sharing) handling
  - Response compression (GZip)
  - Request/Response logging and monitoring
  - Rate limiting

- Middleware execution order affects functionality and error handling.

### Decision

- **Middleware Stack Order** (LIFO - Last In, First Out for requests):
  1. **Custom Middleware** (innermost): Request/response transformation, request ID tracking
  2. **CORS**: Must be applied before error handlers to ensure CORS headers are present on all responses
  3. **GZip**: Outermost layer for response compression

- **Middleware Components**:
  - Custom request logging with request IDs
  - Prometheus metrics instrumentation
  - CORS configuration
  - GZip compression
  - Rate limiting (via dependency)

- **Exception Handling**: Custom exception handlers registered last to catch errors from all middleware.

**Rationale**: Ordering ensures CORS headers are present on all responses (including error responses), proper compression happens after all processing, and metrics are collected for all requests. Custom middleware placement enables per-request transformations before routing.

## ADR 009: Circuit Breaker Pattern for Fault Tolerance

### Context

- Backend ML services may fail temporarily due to:
  - Network issues
  - Resource exhaustion
  - Model inference errors
  - Dependency failures

- Repeated calls to failing backends can exhaust router resources.

### Decision

- **Circuit Breaker Configuration** in `config.yaml`:
  - Failure threshold: 5 consecutive failures
  - Recovery timeout: 30 seconds
  - Expected exception types: ConnectionError, TimeoutError

- **Implementation**: Configuration-based circuit breaker that tracks consecutive failures. When threshold is reached, circuit opens and subsequent requests fail immediately without reaching backend.

- **Integration**: Circuit breaker behavior is configured but may need explicit implementation in backend registry.

**Rationale**: Circuit breaker prevents cascading failures by isolating failing services. It allows services to recover (when circuit resets) and avoids overwhelming already-stressed systems with additional requests. The 30-second recovery timeout balances between allowing failed services to recover and preventing rapid re-probing.

## ADR 010: Rate Limiting Strategy

### Context

- Need to protect the API from abuse and excessive load.
- Different endpoints may require different rate limits.
- Must support both global and per-endpoint rate limiting.

### Decision

- **Rate Limiting Library**: slowapi for request throttling
  - In-memory token bucket algorithm
  - Configurable default rate limits
  - Per-endpoint rate limit support

- **Configuration**:
  - Default rate limit: 50 requests per minute
  - Burst rate: 100 requests
  - Login rate: 10 requests per minute

- **Implementation**: Rate limiter as a dependency decorator on the `/predict` endpoint, with request injection via `limiter.limit()`.

**Rationale**: slowapi provides a simple yet effective rate limiting solution with minimal overhead. The token bucket algorithm allows burst requests while maintaining overall rate limits. Different limits for login vs. API endpoints enables fine-grained access control. In-memory implementation is sufficient for single-instance deployments.

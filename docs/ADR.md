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

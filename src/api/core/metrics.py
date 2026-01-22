from prometheus_client import Counter
from prometheus_fastapi_instrumentator.metrics import Info

# 1. Define the metric globally so it persists across requests
# We use a distinct name to avoid conflicts with default metrics
MODEL_REQUEST_COUNT = Counter(
    "http_requests_by_model_total",
    "Total HTTP requests grouped by model type",
    labelnames=["model_type", "method", "status"],
)


def model_label(info: Info) -> None:
    """Add model_type label to Prometheus metrics if available in the request path."""
    # 2. Extract the path param (e.g., from /v1/{model_type}/predict)
    # Note: path_params is only populated if the router matched the request
    model_type = info.request.path_params.get("model_type")

    # 3. Only record if model_type is present
    if model_type:
        status_code = info.response.status_code if info.response else 500
        MODEL_REQUEST_COUNT.labels(
            model_type=model_type,
            method=info.method,
            status=str(status_code),
        ).inc()

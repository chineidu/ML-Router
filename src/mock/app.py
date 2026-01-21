import argparse

import uvicorn

from src import create_logger
from src.mock.mock_backends import create_backend_app

# ---------------------------------------------------------
# LOGGING INITIALIZATION (runs once per worker process)
# ---------------------------------------------------------
logger = create_logger(
    "src.mock.app",
    structured=False,
    log_file=None,
)
logger.info("Initializing FastAPI application")


# ---------------------------------------------------------
# PARSE CLI ARGS AT MODULE LEVEL (Required for workers)
# ---------------------------------------------------------
parser = argparse.ArgumentParser(description="Run a mock ML backend")
parser.add_argument(
    "--model",
    type=str,
    required=True,
    choices=["sentiment", "classification", "regression", "ner"],
    help="Type of model to simulate",
)
parser.add_argument("--port", type=int, default=8001, help="Port to run the backend on")
parser.add_argument(
    "--latency", type=int, default=100, help="Simulated latency in milliseconds"
)

# Parse args at module level for app creation before workers spawn
args, _ = parser.parse_known_args()

# Create app at module level for uvicorn workers
app = create_backend_app(args.model, args.latency)


def main() -> None:
    """Entry point for running the mock backend server."""
    logger.info(f"Creating {args.model} backend with {args.latency}ms latency")

    uvicorn.run(
        "src.mock.app:app",
        host="0.0.0.0",
        port=args.port,
        loop="uvloop",
        workers=2,
    )


if __name__ == "__main__":
    main()

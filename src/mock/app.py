import argparse

import uvicorn

from src.mock.mock_backends import create_backend_app

# Module-level app for ASGI servers (Required)
app = None


def main() -> None:
    """Entry point for running the mock backend server."""
    global app

    parser = argparse.ArgumentParser(description="Run a mock ML backend")
    parser.add_argument(
        "--model",
        type=str,
        required=True,
        choices=["sentiment", "classification", "regression", "ner"],
        help="Type of model to simulate",
    )
    parser.add_argument(
        "--port", type=int, default=8001, help="Port to run the backend on"
    )
    parser.add_argument(
        "--latency", type=int, default=100, help="Simulated latency in milliseconds"
    )

    args = parser.parse_args()

    app = create_backend_app(args.model, args.latency)

    print(f"Starting {args.model} backend on port {args.port}")
    print(f"Simulated latency: {args.latency}ms")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=args.port,
        log_level="info",
        loop="uvloop",
    )


if __name__ == "__main__":
    main()

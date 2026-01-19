"""
Mock ML Model Backends
Simulates different ML models with varying latencies and behaviors
Run multiple instances on different ports to test load balancing
"""

import asyncio
import random
from typing import Any

from fastapi import FastAPI, HTTPException, status
from pydantic import Field

from src.schemas.base import BaseSchema, Float


class PredictionRequestSchema(BaseSchema):
    model_version: str | None = Field(
        None, description="Optional version of the model to use for inference."
    )
    input_data: dict[str, Any] = Field(
        description="The input data for the model inference."
    )


class PredictionResponseSchema(BaseSchema):
    prediction: dict[str, Any] = Field(
        description="The prediction result from the model inference."
    )
    confidence: Float = Field(
        description="Confidence score of the prediction rounded to 2 decimal places."
    )
    model_version: str = Field(description="Version of the model used for inference.")
    model_name: str = Field(description="Name of the model used for inference.")


# ============================================================================
# MOCK MODEL IMPLEMENTATIONS
# ============================================================================


class MockSentimentModel:
    """Simulates a sentiment analysis model"""

    def __init__(self, latency_ms: int = 100) -> None:
        self.latency_ms = latency_ms
        self.model_name = "sentiment-analyzer"
        self.version = "v1.0.0"

    async def apredict(self, text: str) -> dict[str, Any]:
        """Simulate sentiment prediction"""
        # Simulate processing time
        await asyncio.sleep(self.latency_ms / 1000)

        # Simple mock logic
        sentiment = random.choice(["positive", "negative", "neutral"])
        confidence = random.uniform(0.7, 0.99)

        return {
            "prediction": {
                "sentiment": sentiment,
                "text": text[:50] + "..." if len(text) > 50 else text,
            },
            "confidence": round(confidence, 4),
            "model_version": self.version,
            "model_name": self.model_name,
        }


class MockClassificationModel:
    """Simulates a classification model"""

    def __init__(self, latency_ms: int = 150) -> None:
        self.latency_ms = latency_ms
        self.model_name = "multi-class-classifier"
        self.version = "v2.1.0"
        self.classes = ["category_a", "category_b", "category_c", "category_d"]

    async def apredict(self, features: list[str]) -> dict[str, Any]:  # noqa: ARG002
        """Simulate classification prediction"""
        await asyncio.sleep(self.latency_ms / 1000)

        predicted_class = random.choice(self.classes)
        confidence = random.uniform(0.6, 0.95)

        return {
            "prediction": {
                "class": predicted_class,
                "probabilities": {
                    cls: round(random.uniform(0.1, 0.9), 4) for cls in self.classes
                },
            },
            "confidence": round(confidence, 4),
            "model_version": self.version,
            "model_name": self.model_name,
        }


class MockRegressionModel:
    """Simulates a regression model"""

    def __init__(self, latency_ms: int = 80) -> None:
        self.latency_ms = latency_ms
        self.model_name = "regression-predictor"
        self.version = "v1.2.0"

    async def apredict(self, features: list) -> dict[str, Any]:
        """Simulate regression prediction"""
        await asyncio.sleep(self.latency_ms / 1000)

        # Mock prediction
        predicted_value = sum(features) * random.uniform(0.8, 1.2)
        confidence = random.uniform(0.75, 0.95)

        return {
            "prediction": {
                "value": round(predicted_value, 4),
                "range": [
                    round(predicted_value * 0.9, 4),
                    round(predicted_value * 1.1, 4),
                ],
            },
            "confidence": round(confidence, 4),
            "model_version": self.version,
            "model_name": self.model_name,
        }


class MockNERModel:
    """Simulates a Named Entity Recognition model"""

    def __init__(self, latency_ms: int = 200) -> None:
        self.latency_ms = latency_ms
        self.model_name = "ner-extractor"
        self.version = "v1.2.0"

    async def apredict(self, text: str) -> dict[str, Any]:
        """Simulate NER prediction"""
        await asyncio.sleep(self.latency_ms / 1000)

        # Mock entity extraction
        entities = [
            {"text": "mock_person", "type": "PERSON", "start": 0, "end": 11},
            {"text": "mock_org", "type": "ORGANIZATION", "start": 20, "end": 28},
        ]

        return {
            "prediction": {"entities": entities, "text": text},
            "confidence": round(random.uniform(0.8, 0.95), 4),
            "model_version": self.version,
            "model_name": self.model_name,
        }


MODEL_CLASSES = {
    "sentiment": MockSentimentModel,
    "classification": MockClassificationModel,
    "regression": MockRegressionModel,
    "ner": MockNERModel,
}

# ============================================================================
# CREATE BACKEND APP
# ============================================================================


def create_backend_app(model_type: str, latency_ms: int) -> FastAPI:
    """Factory function to create backend apps"""

    app = FastAPI(title=f"Mock {model_type} Backend")

    # Initialize appropriate model
    if model_type == "sentiment":
        model = MODEL_CLASSES["sentiment"](latency_ms)
    elif model_type == "classification":
        model = MODEL_CLASSES["classification"](latency_ms)
    elif model_type == "regression":
        model = MODEL_CLASSES["regression"](latency_ms)
    elif model_type == "ner":
        model = MODEL_CLASSES["ner"](latency_ms)
    else:
        raise ValueError(f"Unknown model type: {model_type}")

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Health check endpoint"""
        return {"status": "healthy", "model": model.model_name}

    @app.post("/predict", response_model=PredictionResponseSchema)
    async def predict(input_data: PredictionRequestSchema) -> PredictionResponseSchema:
        """Prediction endpoint"""

        data = input_data.input_data

        # Route to appropriate prediction method
        if model_type == "sentiment":
            result = await model.apredict(data.get("text", ""))
        elif model_type == "classification":
            result = await model.apredict(data.get("features", []))
        elif model_type == "regression":
            result = await model.apredict(data.get("features", []))
        elif model_type == "ner":
            result = await model.apredict(data.get("text", ""))
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported model type: {model_type}",
            )

        return PredictionResponseSchema(**result)

    return app

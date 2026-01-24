import logging
import random
import time

from locust import HttpUser, between, task


class MLRouterUser(HttpUser):
    wait_time = between(0, 0)  # No wait between requests

    @task
    def predict_sentiment(self) -> None:
        max_retries = 3

        for attempt in range(max_retries):
            with self.client.post(
                "/api/v1/predict/sentiment",
                json={
                    "input_data": {"text": f"Random text {random.randint(1, 1000000)}"},
                    "model_version": "v1.0.0",
                    "timeout": 10,
                },
                headers={"accept": "application/json"},
                catch_response=True,
            ) as response:
                if response.status_code == 429:
                    response.failure(
                        f"Rate limited (attempt {attempt + 1}/{max_retries})"
                    )
                    # Exponential backoff
                    wait_time = (2**attempt) * 0.1
                    time.sleep(wait_time)
                    continue
                if response.status_code == 200:
                    response.success()
                    break
                response.failure(f"Got {response.status_code}")
                logging.error(f"Failed: {response.status_code} - {response.text}")
                break

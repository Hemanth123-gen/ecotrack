"""Gemini calls with retries and a model fallback, so one overloaded model doesn't break the app."""

import time
from typing import Any

from google.genai import errors

# Overloaded / rate-limited / transient server errors are worth retrying or rerouting
RETRYABLE_CODES = {429, 500, 503, 504}


def model_chain(primary: str, fallbacks: list[str]) -> list[str]:
    return list(dict.fromkeys([primary, *fallbacks]))  # de-duplicated, order kept


def generate(
    client: Any,
    models: list[str],
    *,
    contents: Any,
    config: Any,
    retries: int = 1,
    backoff_seconds: float = 1.0,
    sleep=time.sleep,
):
    """Try each model in turn, retrying transient errors briefly; re-raise anything else immediately."""
    last_error: Exception | None = None
    for model in models:
        for attempt in range(retries + 1):
            try:
                return client.models.generate_content(model=model, contents=contents, config=config)
            except errors.APIError as e:
                if getattr(e, "code", None) not in RETRYABLE_CODES:
                    raise
                last_error = e
                if attempt < retries:
                    sleep(backoff_seconds * 2**attempt)
    assert last_error is not None
    raise last_error

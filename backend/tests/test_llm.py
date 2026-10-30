import pytest
from google.genai import errors

from app.agent import CarbonAgent
from app.llm import generate, model_chain

from .conftest import text


def busy():
    return errors.ServerError(503, {"error": {"code": 503, "message": "high demand", "status": "UNAVAILABLE"}})


class Scripted:
    """Raises or returns per call, recording which model was asked."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.models_called = []
        self.models = self

    def generate_content(self, model, contents, config):
        self.models_called.append(model)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def test_model_chain_dedupes():
    assert model_chain("a", ["b", "a", "c"]) == ["a", "b", "c"]


def test_retries_then_falls_back_to_next_model():
    client = Scripted(busy(), busy(), text("ok"))
    resp = generate(client, ["primary", "backup"], contents=[], config=None, sleep=lambda s: None)
    assert resp.text == "ok"
    assert client.models_called == ["primary", "primary", "backup"]


def test_non_retryable_error_is_raised_immediately():
    bad = errors.ClientError(400, {"error": {"code": 400, "message": "bad request", "status": "INVALID_ARGUMENT"}})
    client = Scripted(bad)
    with pytest.raises(errors.ClientError):
        generate(client, ["primary", "backup"], contents=[], config=None, sleep=lambda s: None)
    assert client.models_called == ["primary"]


def test_raises_last_error_when_every_model_is_busy():
    client = Scripted(busy(), busy(), busy(), busy())
    with pytest.raises(errors.ServerError):
        generate(client, ["a", "b"], contents=[], config=None, sleep=lambda s: None)


def test_agent_uses_fallback_model(store, user, monkeypatch):
    monkeypatch.setattr("app.llm.time.sleep", lambda s: None)
    client = Scripted(busy(), busy(), text("Hello from the backup model"))
    reply = CarbonAgent(client, store, "primary", fallback_models=["backup"]).chat(user.id, "hi")
    assert reply.reply == "Hello from the backup model"
    assert client.models_called[-1] == "backup"

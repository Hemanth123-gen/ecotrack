import os

# Keep tests off the real database and the real Gemini API (set before app.main is imported).
os.environ["DATABASE_PATH"] = ":memory:"
os.environ["GEMINI_API_KEY"] = ""

import pytest  # noqa: E402
from google.genai import types  # noqa: E402

from app.store import Store


@pytest.fixture
def store():
    return Store(":memory:")


@pytest.fixture
def user(store):
    return store.create_user("Asha")


def fn_call(name: str, **args) -> types.GenerateContentResponse:
    part = types.Part(function_call=types.FunctionCall(id=f"call-{name}", name=name, args=args))
    return types.GenerateContentResponse(candidates=[types.Candidate(content=types.Content(role="model", parts=[part]))])


def text(t: str) -> types.GenerateContentResponse:
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=[types.Part(text=t)]))]
    )


class FakeClient:
    """Stands in for google.genai.Client, replaying scripted responses."""

    def __init__(self, *script: types.GenerateContentResponse):
        self.script = list(script)
        self.requests: list[dict] = []
        self.models = self

    def generate_content(self, model, contents, config):
        self.requests.append({"model": model, "contents": list(contents), "config": config})
        return self.script.pop(0)

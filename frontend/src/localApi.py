# Runs inside Pyodide (the browser) for the static demo build: serves the real FastAPI app over a fetch shim.
import asyncio
import json
import os
import sys
import types as _types

sys.path.insert(0, "/srv")
os.environ.update(DATABASE_PATH="/data/carbon.db", AUTH_MODE="dev", CORS_ORIGINS="")


# --- Stubs for server-only dependencies. The demo has no Gemini key and no Firebase auth, so these code
# paths are never called; the stubs only let the modules import.
def _module(name, **attrs):
    mod = _types.ModuleType(name)
    mod.__dict__.update(attrs)
    sys.modules[name] = mod
    return mod


class _Unavailable:
    def __init__(self, *args, **kwargs):
        raise RuntimeError("Not available in the in-browser demo")


class _APIError(Exception):
    message = None


_google = _module("google")
_genai = _module("google.genai", Client=_Unavailable)
_genai.errors = _module("google.genai.errors", APIError=_APIError)
_genai.types = _module("google.genai.types")
_genai.types.__getattr__ = lambda name: _Unavailable
_google.genai = _genai
_auth = _module("google.auth")
_auth.exceptions = _module("google.auth.exceptions", GoogleAuthError=type("GoogleAuthError", (Exception,), {}))
_auth.jwt = _module("google.auth.jwt", decode=_Unavailable)
_google.auth = _auth
_module("requests", get=_Unavailable)

# --- Pyodide has no threads: run FastAPI's sync endpoints inline instead of in a thread pool.
import fastapi.concurrency  # noqa: E402
import fastapi.dependencies.utils  # noqa: E402
import fastapi.routing  # noqa: E402
import starlette.concurrency  # noqa: E402


async def _run_inline(func, *args, **kwargs):
    return func(*args, **kwargs)


for _mod in (starlette.concurrency, fastapi.concurrency, fastapi.routing, fastapi.dependencies.utils):
    if hasattr(_mod, "run_in_threadpool"):
        _mod.run_in_threadpool = _run_inline

from app.main import create_app  # noqa: E402

app = create_app()


async def handle(method, path, query, headers_json, body):
    """One HTTP request through the ASGI app. Returns [status, headers, body bytes] for JS."""
    from js import Object
    from pyodide.ffi import to_js

    data = body.to_bytes() if body is not None else b""
    headers = [(k.lower().encode(), str(v).encode()) for k, v in json.loads(headers_json).items()]
    headers.append((b"content-length", str(len(data)).encode()))
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method,
        "scheme": "https", "path": path, "raw_path": path.encode(), "query_string": query.encode(),
        "root_path": "", "headers": headers, "client": ("browser", 0), "server": ("localhost", 443),
    }
    request_sent = False
    response_done = asyncio.Event()
    status, resp_headers, chunks = 500, {}, []

    async def receive():
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {"type": "http.request", "body": data, "more_body": False}
        await response_done.wait()  # like a real client: only "disconnect" once the response is finished
        return {"type": "http.disconnect"}

    async def send(message):
        nonlocal status
        if message["type"] == "http.response.start":
            status = message["status"]
            resp_headers.update({k.decode(): v.decode() for k, v in message.get("headers", [])})
        elif message["type"] == "http.response.body":
            chunks.append(message.get("body", b""))
            if not message.get("more_body"):
                response_done.set()

    await app(scope, receive, send)
    return to_js([status, resp_headers, b"".join(chunks)], dict_converter=Object.fromEntries)

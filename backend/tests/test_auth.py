"""Firebase auth: real RS256 tokens signed by a throwaway key, verified by the production verifier."""

import time

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from google.auth import crypt, jwt

from app.agent import CarbonAgent
from app.auth import AuthError, FirebaseVerifier, RateLimiter, bearer_token
from app.config import Settings
from app.main import create_app

from .conftest import FakeClient, text

PROJECT = "ecotrack-test"


@pytest.fixture(scope="module")
def keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test")])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(1).not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    pem_key = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption())
    return pem_key, cert.public_bytes(serialization.Encoding.PEM).decode()


@pytest.fixture
def verifier(keypair):
    calls = []

    def fetch():
        calls.append(1)
        return {"kid1": keypair[1]}, 3600

    v = FirebaseVerifier(PROJECT, fetch_certs=fetch)
    v.fetch_calls = calls
    return v


def make_token(keypair, uid="alice", **overrides):
    now = int(time.time())
    claims = {
        "iss": f"https://securetoken.google.com/{PROJECT}", "aud": PROJECT, "sub": uid,
        "iat": now, "exp": now + 3600, "email": f"{uid}@example.com", "name": uid.title(),
    }
    claims.update(overrides)
    signer = crypt.RSASigner.from_string(keypair[0], key_id="kid1")
    return jwt.encode(signer, claims).decode()


# --- verifier ------------------------------------------------------------------

def test_verifier_accepts_valid_token_and_caches_certs(verifier, keypair):
    p = verifier.verify(make_token(keypair))
    assert (p.uid, p.email, p.name) == ("alice", "alice@example.com", "Alice")
    verifier.verify(make_token(keypair, uid="bob"))
    assert len(verifier.fetch_calls) == 1


@pytest.mark.parametrize("overrides", [
    {"aud": "other-project"},
    {"iss": "https://securetoken.google.com/other-project"},
    {"exp": int(time.time()) - 60, "iat": int(time.time()) - 3700},
    {"sub": ""},
])
def test_verifier_rejects_bad_tokens(verifier, keypair, overrides):
    with pytest.raises(AuthError):
        verifier.verify(make_token(keypair, **overrides))


def test_verifier_rejects_wrong_signature(verifier):
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    with pytest.raises(AuthError):
        verifier.verify(make_token((other, None)))
    with pytest.raises(AuthError):
        verifier.verify("not.a.jwt")


def test_bearer_token_parsing():
    assert bearer_token("Bearer abc") == "abc"
    assert bearer_token("bearer  abc ") == "abc"
    assert bearer_token("Basic abc") is None and bearer_token(None) is None and bearer_token("Bearer ") is None


def test_rate_limiter_window():
    rl = RateLimiter(2, window_seconds=0.2)
    assert rl.check("a") is None and rl.check("a") is None
    assert rl.check("a") > 0
    assert rl.check("b") is None  # per key
    time.sleep(0.25)
    assert rl.check("a") is None


# --- API in firebase mode ------------------------------------------------------------

def settings(**overrides):
    base = dict(gemini_api_key=None, gemini_model="m", gemini_fallback_models=[], database_url=":memory:", cors_origins=[],
                auth_mode="firebase", firebase_project_id=PROJECT, chat_requests_per_hour=2,
                document_requests_per_hour=2)
    base.update(overrides)
    return Settings(**base)


@pytest.fixture
def api(store, verifier):
    agent = CarbonAgent(FakeClient(*[text("ok")] * 10), store, "m")
    return TestClient(create_app(store=store, agent=agent, verifier=verifier, settings=settings()))


def auth(keypair, uid="alice"):
    return {"Authorization": f"Bearer {make_token(keypair, uid=uid)}"}


def test_public_endpoints_need_no_token(api):
    assert api.get("/api/health").json()["auth_mode"] == "firebase"
    assert api.get("/api/factors").status_code == 200
    assert api.get("/api/import/csv-template").status_code == 200


def test_user_endpoints_require_valid_token(api, keypair):
    assert api.post("/api/users", json={"name": "A"}).status_code == 401
    assert api.get("/api/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_profile_is_bound_to_account_and_isolated(api, keypair):
    alice, bob = auth(keypair, "alice"), auth(keypair, "bob")
    assert api.get("/api/me", headers=alice).status_code == 404

    a = api.post("/api/users", json={"name": "Alice"}, headers=alice).json()
    again = api.post("/api/users", json={"name": "Alice 2"}, headers=alice).json()
    assert again["id"] == a["id"]  # one profile per account
    assert api.get("/api/me", headers=alice).json()["id"] == a["id"]

    r = api.post(f"/api/users/{a['id']}/activities", json={"key": "rice", "quantity": 1, "unit": "kg"}, headers=alice)
    assert r.status_code == 201

    # Bob can't read, write, delete or chat as Alice
    assert api.get(f"/api/users/{a['id']}/activities", headers=bob).status_code == 403
    assert api.get(f"/api/users/{a['id']}/summary", headers=bob).status_code == 403
    assert api.delete(f"/api/users/{a['id']}/activities/{r.json()['id']}", headers=bob).status_code == 403
    assert api.post("/api/chat", json={"user_id": a["id"], "message": "hi"}, headers=bob).status_code == 403
    assert api.get("/api/users/nope/summary", headers=bob).status_code == 404

    # ...while Alice still can
    assert api.get(f"/api/users/{a['id']}/goal", headers=alice).status_code == 200


def test_unowned_legacy_user_is_forbidden(api, store, keypair):
    legacy = store.create_user("Legacy")  # created without auth, e.g. before auth was enabled
    assert api.get(f"/api/users/{legacy.id}/summary", headers=auth(keypair)).status_code == 403


def test_chat_rate_limited_per_account(api, keypair):
    alice = auth(keypair)
    uid = api.post("/api/users", json={"name": "Alice"}, headers=alice).json()["id"]
    codes = [api.post("/api/chat", json={"user_id": uid, "message": "hi"}, headers=alice).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_api_responses_are_not_cacheable(api, keypair):
    alice = auth(keypair)
    uid = api.post("/api/users", json={"name": "Alice"}, headers=alice).json()["id"]
    assert api.get(f"/api/users/{uid}/summary", headers=alice).headers["cache-control"] == "no-store"
    assert "no-store" not in api.get("/api/factors").headers.get("cache-control", "")


def test_refuses_dev_auth_on_cloud_run(monkeypatch, store):
    monkeypatch.setenv("K_SERVICE", "ecotrack-api")
    with pytest.raises(RuntimeError, match="AUTH_MODE"):
        create_app(store=store, settings=settings(auth_mode="dev", firebase_project_id=None))


def test_serves_frontend_publicly_with_spa_fallback(monkeypatch, tmp_path, store, verifier, keypair):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html>app</html>")
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path.parent / "secret.txt").write_text("nope")
    monkeypatch.setenv("STATIC_DIR", str(tmp_path))
    api = TestClient(create_app(store=store, verifier=verifier, settings=settings()))

    assert api.get("/").text == "<html>app</html>"
    assert api.get("/goals/some/client/route").text == "<html>app</html>"  # SPA fallback, no token needed
    js = api.get("/assets/app.js")
    assert js.text == "console.log(1)" and "immutable" in js.headers["cache-control"]
    assert "nope" not in api.get("/..%2Fsecret.txt").text and "nope" not in api.get("/assets/../../secret.txt").text
    assert api.get("/api/unknown").status_code in (401, 404)  # API paths never fall back to the app
    assert api.get("/api/me").status_code == 401  # and stay protected
    assert api.get("/api/health").json()["status"] == "ok"


def test_refuses_dev_auth_on_render(monkeypatch, store):
    monkeypatch.setenv("RENDER", "true")
    with pytest.raises(RuntimeError, match="AUTH_MODE"):
        create_app(store=store, settings=settings(auth_mode="dev", firebase_project_id=None))

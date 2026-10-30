"""Authentication.

- dev: no sign-in; any caller can use any user id (local development only).
- firebase: every user-scoped request needs `Authorization: Bearer <Firebase ID token>`; the token is
  verified against Google's public keys and the user record must belong to the token's uid.
"""

import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable

import requests
from google.auth import exceptions as google_auth_exceptions
from google.auth import jwt
from pydantic import BaseModel

FIREBASE_CERTS_URL = "https://www.googleapis.com/robot/v1/metadata/x509/securetoken@system.gserviceaccount.com"


class AuthError(Exception):
    pass


class Principal(BaseModel):
    uid: str
    email: str | None = None
    name: str | None = None


def _fetch_certs() -> tuple[dict[str, str], float]:
    """Google's signing certs and how long they may be cached (from Cache-Control max-age)."""
    resp = requests.get(FIREBASE_CERTS_URL, timeout=10)
    resp.raise_for_status()
    max_age = 3600.0
    for part in resp.headers.get("Cache-Control", "").split(","):
        if part.strip().startswith("max-age="):
            max_age = float(part.strip()[len("max-age="):])
    return resp.json(), max_age


class FirebaseVerifier:
    def __init__(self, project_id: str, fetch_certs: Callable[[], tuple[dict[str, str], float]] = _fetch_certs):
        self.project_id = project_id
        self._fetch = fetch_certs
        self._certs: dict[str, str] = {}
        self._expires = 0.0
        self._lock = threading.Lock()

    def _get_certs(self) -> dict[str, str]:
        with self._lock:
            if time.monotonic() >= self._expires:
                self._certs, max_age = self._fetch()
                self._expires = time.monotonic() + max_age
            return self._certs

    def verify(self, token: str) -> Principal:
        try:
            claims = jwt.decode(token, certs=self._get_certs(), audience=self.project_id, clock_skew_in_seconds=10)
        except (ValueError, google_auth_exceptions.GoogleAuthError) as e:
            raise AuthError(f"Invalid token: {e}") from e
        if claims.get("iss") != f"https://securetoken.google.com/{self.project_id}":
            raise AuthError("Invalid token issuer")
        if not claims.get("sub"):
            raise AuthError("Token has no subject")
        return Principal(uid=claims["sub"], email=claims.get("email"), name=claims.get("name"))


def bearer_token(header: str | None) -> str | None:
    if header and header.lower().startswith("bearer "):
        return header[7:].strip() or None
    return None


class RateLimiter:
    """Sliding-window limit per key, in memory.

    Protects the Gemini bill from a runaway client. Per-instance only: with N Cloud Run instances the
    effective limit is up to N times higher, which is acceptable for cost protection at small scale.
    """

    def __init__(self, max_requests: int, window_seconds: float = 3600):
        self.max = max_requests
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> float | None:
        """Record a hit. Returns None if allowed, else seconds until the next request is allowed."""
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] >= self.window:
                hits.popleft()
            if len(hits) >= self.max:
                return self.window - (now - hits[0])
            hits.append(now)
            return None

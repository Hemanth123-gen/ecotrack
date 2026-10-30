"""Persistence for users, logged activities, goals and chat history.

SQLAlchemy Core keeps one code path for SQLite (local dev, tests) and Postgres (production).
"""

import contextlib
import functools
import threading
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

import sqlalchemy as sa
from pydantic import BaseModel
from sqlalchemy.pool import StaticPool

from .engine import Activity, EmissionResult, FactorDB, Goal, calculate, default_db

UserKind = Literal["individual", "organization"]

metadata = sa.MetaData()

users = sa.Table(
    "users", metadata,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("auth_uid", sa.String(128), unique=True),  # Firebase uid; NULL in dev mode
    sa.Column("name", sa.String(100), nullable=False),
    sa.Column("kind", sa.String(20), nullable=False, server_default="individual"),
    sa.Column("region", sa.String(10), nullable=False, server_default="IN"),
    sa.Column("created_at", sa.String(40), nullable=False),
)

activities = sa.Table(
    "activities", metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    sa.Column("key", sa.String(64), nullable=False),
    sa.Column("quantity", sa.Float, nullable=False),
    sa.Column("unit", sa.String(32), nullable=False),
    sa.Column("region", sa.String(10), nullable=False),
    sa.Column("occurred_on", sa.Date, nullable=False),
    sa.Column("description", sa.Text),
    sa.Column("kg_co2e", sa.Float, nullable=False),
    sa.Column("created_at", sa.String(40), nullable=False),
    sa.Index("ix_activities_user_date", "user_id", "occurred_on"),
)

conversations = sa.Table(
    "conversations", metadata,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    sa.Column("created_at", sa.String(40), nullable=False),
)

goals = sa.Table(
    "goals", metadata,
    sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    sa.Column("baseline_t_per_year", sa.Float, nullable=False),
    sa.Column("target_t_per_year", sa.Float, nullable=False),
    sa.Column("start_date", sa.Date, nullable=False),
    sa.Column("target_date", sa.Date, nullable=False),
    sa.Column("created_at", sa.String(40), nullable=False),
)

messages = sa.Table(
    "messages", metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("conversation_id", sa.String(32), sa.ForeignKey("conversations.id", ondelete="CASCADE"),
              nullable=False, index=True),
    sa.Column("content_json", sa.Text, nullable=False),
    sa.Column("created_at", sa.String(40), nullable=False),
)


class NotFound(LookupError):
    pass


class User(BaseModel):
    id: str
    name: str
    kind: UserKind
    region: str


class StoredActivity(BaseModel):
    id: int
    key: str
    quantity: float
    unit: str
    region: str
    occurred_on: date
    description: str | None
    kg_co2e: float


_ACTIVITY_COLS = [activities.c[n] for n in StoredActivity.model_fields]
_USER_COLS = [users.c[n] for n in User.model_fields]
_GOAL_COLS = [goals.c[n] for n in Goal.model_fields]


def _locked(method):
    """SQLite allows one writer at a time; serialise access there. Postgres handles concurrency itself."""

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def database_url(target: str | Path) -> str:
    """Accept a SQLAlchemy URL, a SQLite file path, or ':memory:'."""
    target = str(target)
    if target == ":memory:":
        return "sqlite://"
    if "://" in target:
        # Hosted Postgres URLs usually say postgres:// or postgresql://; pick the psycopg 3 driver
        for prefix in ("postgres://", "postgresql://"):
            if target.startswith(prefix):
                return "postgresql+psycopg://" + target[len(prefix):]
        return target
    return f"sqlite:///{target}"


class Store:
    def __init__(self, target: str | Path = ":memory:", db: FactorDB | None = None):
        self.factors = db or default_db()
        url = database_url(target)
        self.is_sqlite = url.startswith("sqlite")
        if self.is_sqlite:
            kwargs: dict = {"connect_args": {"check_same_thread": False, "timeout": 30}}
            if url == "sqlite://":
                kwargs["poolclass"] = StaticPool  # one shared in-memory database
            self.engine = sa.create_engine(url, **kwargs)
            sa.event.listen(self.engine, "connect", lambda conn, _: conn.execute("PRAGMA foreign_keys = ON"))
            self._lock: contextlib.AbstractContextManager = threading.RLock()
        else:
            self.engine = sa.create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5)
            self._lock = contextlib.nullcontext()
        metadata.create_all(self.engine)
        self._migrate()

    def _migrate(self) -> None:
        """Bring databases created by earlier versions up to date (add-only, safe to re-run)."""
        cols = {c["name"] for c in sa.inspect(self.engine).get_columns("users")}
        if "auth_uid" not in cols:
            with self.engine.begin() as conn:
                conn.execute(sa.text("ALTER TABLE users ADD COLUMN auth_uid VARCHAR(128)"))
                conn.execute(sa.text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_auth_uid ON users (auth_uid)"))

    # users

    @_locked
    def create_user(
        self, name: str, kind: UserKind = "individual", region: str = "IN", auth_uid: str | None = None
    ) -> User:
        user = User(id=uuid.uuid4().hex, name=name, kind=kind, region=region.upper())
        with self.engine.begin() as conn:
            conn.execute(sa.insert(users).values(**user.model_dump(), auth_uid=auth_uid, created_at=_now()))
        return user

    @_locked
    def get_user(self, user_id: str) -> User:
        with self.engine.connect() as conn:
            row = conn.execute(sa.select(*_USER_COLS).where(users.c.id == user_id)).first()
        if not row:
            raise NotFound(f"User {user_id} not found")
        return User(**row._mapping)

    @_locked
    def get_user_by_auth_uid(self, auth_uid: str) -> User | None:
        with self.engine.connect() as conn:
            row = conn.execute(sa.select(*_USER_COLS).where(users.c.auth_uid == auth_uid)).first()
        return User(**row._mapping) if row else None

    @_locked
    def owner_of(self, user_id: str) -> str | None:
        """The auth uid that owns a user record (None for dev-mode users)."""
        with self.engine.connect() as conn:
            row = conn.execute(sa.select(users.c.auth_uid).where(users.c.id == user_id)).first()
        if not row:
            raise NotFound(f"User {user_id} not found")
        return row.auth_uid

    # activities

    @_locked
    def add_activity(self, user_id: str, activity: Activity) -> StoredActivity:
        """Calculate and persist an activity. Defaults to today and the user's region."""
        user = self.get_user(user_id)
        activity = activity.model_copy(update={
            "region": activity.region if "region" in activity.model_fields_set else user.region,
            "occurred_on": activity.occurred_on or date.today(),
        })
        result = calculate(activity, self.factors)
        with self.engine.begin() as conn:
            res = conn.execute(sa.insert(activities).values(
                user_id=user_id, key=activity.key, quantity=activity.quantity, unit=activity.unit,
                region=activity.region, occurred_on=activity.occurred_on, description=activity.description,
                kg_co2e=round(result.kg_co2e, 4), created_at=_now(),
            ))
            row = conn.execute(
                sa.select(*_ACTIVITY_COLS).where(activities.c.id == res.inserted_primary_key[0])
            ).one()
        return StoredActivity(**row._mapping)

    @_locked
    def list_activities(self, user_id: str, days: int | None = None, limit: int | None = None) -> list[StoredActivity]:
        """Newest first. `days` keeps activities from the last N days including today."""
        q = sa.select(*_ACTIVITY_COLS).where(activities.c.user_id == user_id)
        if days is not None:
            q = q.where(activities.c.occurred_on >= date.today() - timedelta(days=days - 1))
        q = q.order_by(activities.c.occurred_on.desc(), activities.c.id.desc())
        if limit is not None:
            q = q.limit(limit)
        with self.engine.connect() as conn:
            return [StoredActivity(**r._mapping) for r in conn.execute(q)]

    @_locked
    def delete_activity(self, user_id: str, activity_id: int) -> None:
        with self.engine.begin() as conn:
            res = conn.execute(
                sa.delete(activities).where(activities.c.id == activity_id, activities.c.user_id == user_id)
            )
        if res.rowcount == 0:
            raise NotFound(f"Activity {activity_id} not found")

    @_locked
    def emission_results(self, user_id: str, days: int) -> list[EmissionResult]:
        """Re-derive results with current factors so analysis always uses one consistent factor set."""
        return [
            calculate(Activity(**a.model_dump(exclude={"id", "kg_co2e"})), self.factors)
            for a in self.list_activities(user_id, days)
        ]

    # goals (one active goal per user)

    @_locked
    def set_goal(self, user_id: str, goal: Goal) -> Goal:
        self.get_user(user_id)
        with self.engine.begin() as conn:
            conn.execute(sa.delete(goals).where(goals.c.user_id == user_id))
            conn.execute(sa.insert(goals).values(user_id=user_id, **goal.model_dump(), created_at=_now()))
        return goal

    @_locked
    def get_goal(self, user_id: str) -> Goal | None:
        with self.engine.connect() as conn:
            row = conn.execute(sa.select(*_GOAL_COLS).where(goals.c.user_id == user_id)).first()
        return Goal(**row._mapping) if row else None

    @_locked
    def delete_goal(self, user_id: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(sa.delete(goals).where(goals.c.user_id == user_id))

    # conversations

    @_locked
    def create_conversation(self, user_id: str) -> str:
        self.get_user(user_id)
        conv_id = uuid.uuid4().hex
        with self.engine.begin() as conn:
            conn.execute(sa.insert(conversations).values(id=conv_id, user_id=user_id, created_at=_now()))
        return conv_id

    @_locked
    def check_conversation(self, user_id: str, conversation_id: str) -> None:
        with self.engine.connect() as conn:
            row = conn.execute(sa.select(conversations.c.id).where(
                conversations.c.id == conversation_id, conversations.c.user_id == user_id,
            )).first()
        if not row:
            raise NotFound(f"Conversation {conversation_id} not found")

    @_locked
    def load_messages(self, conversation_id: str) -> list[str]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                sa.select(messages.c.content_json)
                .where(messages.c.conversation_id == conversation_id)
                .order_by(messages.c.id)
            )
            return [r.content_json for r in rows]

    @_locked
    def append_messages(self, conversation_id: str, contents_json: list[str]) -> None:
        now = _now()
        with self.engine.begin() as conn:
            conn.execute(sa.insert(messages), [
                {"conversation_id": conversation_id, "content_json": c, "created_at": now} for c in contents_json
            ])

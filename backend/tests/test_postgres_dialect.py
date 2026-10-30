"""Postgres compatibility without a server: compile the schema and the store's queries for Postgres."""

from datetime import date

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app import store as store_module
from app.store import activities, database_url, goals, metadata, users


def test_schema_compiles_for_postgres():
    ddl = []
    engine = sa.create_mock_engine("postgresql+psycopg://", lambda sql, *a, **kw: ddl.append(str(sql.compile(dialect=engine.dialect))))
    metadata.create_all(engine, checkfirst=False)
    text = "\n".join(ddl)
    assert "CREATE TABLE activities" in text and "id SERIAL NOT NULL" in text
    assert "occurred_on DATE NOT NULL" in text
    assert "ON DELETE CASCADE" in text
    assert "CREATE INDEX ix_activities_user_date ON activities (user_id, occurred_on)" in text
    assert "auth_uid VARCHAR(128)" in text and "UNIQUE (auth_uid)" in text


def test_queries_compile_for_postgres():
    dialect = postgresql.psycopg.dialect()
    stmts = [
        sa.insert(activities).values(user_id="u", key="rice", quantity=1.0, unit="kg", region="IN",
                                     occurred_on=date(2026, 10, 1), description=None, kg_co2e=4.0, created_at="t"),
        sa.select(*store_module._ACTIVITY_COLS).where(activities.c.user_id == "u")
        .where(activities.c.occurred_on >= date(2026, 10, 1))
        .order_by(activities.c.occurred_on.desc(), activities.c.id.desc()).limit(5),
        sa.delete(goals).where(goals.c.user_id == "u"),
        sa.select(users.c.auth_uid).where(users.c.id == "u"),
    ]
    compiled = [str(s.compile(dialect=dialect)) for s in stmts]
    assert "%(user_id)s" in compiled[0]  # psycopg paramstyle, not SQLite's '?'
    assert "LIMIT %(param_1)s" in compiled[1]


def test_database_url_normalisation():
    assert database_url(":memory:") == "sqlite://"
    assert database_url("carbon.db") == "sqlite:///carbon.db"
    assert database_url("postgres://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert database_url("postgresql://u:p@/db?host=/cloudsql/p:r:i") == "postgresql+psycopg://u:p@/db?host=/cloudsql/p:r:i"
    assert database_url("postgresql+psycopg://u@h/db") == "postgresql+psycopg://u@h/db"


def test_migration_adds_auth_uid_to_old_sqlite_db(tmp_path):
    import sqlite3

    path = tmp_path / "old.db"
    with sqlite3.connect(path) as conn:  # schema from before auth existed
        conn.execute("CREATE TABLE users (id TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'individual',"
                     " region TEXT NOT NULL DEFAULT 'IN', created_at TEXT NOT NULL)")
        conn.execute("INSERT INTO users VALUES ('abc', 'Old', 'individual', 'IN', 'then')")
    s = store_module.Store(path)
    assert s.get_user("abc").name == "Old" and s.owner_of("abc") is None
    s.create_user("New", auth_uid="firebase-uid")
    assert s.get_user_by_auth_uid("firebase-uid").name == "New"
    store_module.Store(path)  # re-running the migration is a no-op

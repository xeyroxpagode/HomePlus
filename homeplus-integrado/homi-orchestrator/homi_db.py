"""HOMI V1 — PostgreSQL access layer for HOMI-D durable state.

HOMI-D keeps its orchestration state (proposal lifecycle, compound
execution trace, attachment metadata) in the EXISTING HomePlus
PostgreSQL database, inside the dedicated ``homi`` schema.  This module
is the only place where HOMI-D opens a database connection.

Boundaries
----------
* One engine, one database: PostgreSQL only.  No SQLite, no second
  database, no local file store for durable state.
* Minimum privileges: the connection uses the ``homi_runtime`` role,
  which has grants only on the ``homi`` schema.  It cannot read or
  write ``public.planner_tasks`` nor ``public.planner_idempotency_keys``:
  HomePlus/T07 remains the only authority of Planner writes.
* Configuration is read from the process environment first and from a
  local, non-committed environment file second.  Secrets are never
  logged, printed or returned.
"""

from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence


ORCHESTRATOR_ROOT = Path(__file__).resolve().parent

ENV_FILE_ENV = "HOMI_ENV_FILE"

DEFAULT_ENV_FILE = ORCHESTRATOR_ROOT / ".env.homi"

HOST_ENV = "HOMI_DB_HOST"
PORT_ENV = "HOMI_DB_PORT"
NAME_ENV = "HOMI_DB_NAME"
USER_ENV = "HOMI_DB_USER"
PASSWORD_ENV = "HOMI_DB_PASSWORD"
SCHEMA_ENV = "HOMI_DB_SCHEMA"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 56222
DEFAULT_NAME = "postgres"
DEFAULT_USER = "homi_runtime"
DEFAULT_SCHEMA = "homi"

DEFAULT_CONNECT_TIMEOUT = 5.0

DEFAULT_STATEMENT_TIMEOUT_MS = 8000

DEFAULT_LOCK_TIMEOUT_MS = 4000


class DatabaseError(RuntimeError):
    """Fail-closed error of the HOMI-D PostgreSQL access layer."""


@dataclass(frozen=True)
class DatabaseConfig:
    """The resolved, secret-free description of the connection."""

    host: str
    port: int
    dbname: str
    user: str
    password: str
    schema: str
    connect_timeout: float = DEFAULT_CONNECT_TIMEOUT

    def describe(self) -> dict[str, Any]:
        """A description that never exposes the password."""

        return {
            "host": self.host,
            "port": self.port,
            "dbname": self.dbname,
            "user": self.user,
            "schema": self.schema,
            "password_present": bool(self.password),
        }


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}

    try:
        raw = path.read_text(encoding="utf-8")

    except OSError:
        return values

    for line in raw.splitlines():
        entry = line.strip()

        if not entry or entry.startswith("#") or "=" not in entry:
            continue

        key, value = entry.split("=", 1)
        values[key.strip()] = value.strip()

    return values


def load_environment(
    environ: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Merge the local environment file with the process environment."""

    env = dict(os.environ if environ is None else environ)
    file_path = Path(
        env.get(ENV_FILE_ENV) or DEFAULT_ENV_FILE
    )
    file_values = _read_env_file(file_path)

    for key, value in file_values.items():
        env.setdefault(key, value)

    return env


def db_config(environ: Mapping[str, str] | None = None) -> DatabaseConfig:
    """Resolve the connection configuration."""

    env = load_environment(environ)

    raw_port = (env.get(PORT_ENV) or "").strip()

    try:
        port = int(raw_port) if raw_port else DEFAULT_PORT

    except (TypeError, ValueError) as error:
        raise DatabaseError(
            f"{PORT_ENV} must be an integer port"
        ) from error

    return DatabaseConfig(
        host=(env.get(HOST_ENV) or DEFAULT_HOST).strip(),
        port=port,
        dbname=(env.get(NAME_ENV) or DEFAULT_NAME).strip(),
        user=(env.get(USER_ENV) or DEFAULT_USER).strip(),
        password=(env.get(PASSWORD_ENV) or "").strip(),
        schema=(env.get(SCHEMA_ENV) or DEFAULT_SCHEMA).strip(),
    )


class Database:
    """A small, thread-safe PostgreSQL client for HOMI-D.

    The connection is shared and serialized: HOMI-D performs a handful of
    short writes per turn and never a long transaction, so a single
    guarded connection keeps the state machine simple and predictable.
    """

    def __init__(self, config: DatabaseConfig | None = None) -> None:
        self.config = config or db_config()
        self._connection: Any = None
        self._lock = threading.RLock()

    # -- connection ------------------------------------------------------

    def _connect(self) -> Any:
        import psycopg  # noqa: PLC0415
        from psycopg.rows import dict_row  # noqa: PLC0415

        return psycopg.connect(
            host=self.config.host,
            port=self.config.port,
            dbname=self.config.dbname,
            user=self.config.user,
            password=self.config.password,
            connect_timeout=int(self.config.connect_timeout),
            options=(
                f"-c statement_timeout={DEFAULT_STATEMENT_TIMEOUT_MS} "
                f"-c lock_timeout={DEFAULT_LOCK_TIMEOUT_MS}"
            ),
            autocommit=True,
            row_factory=dict_row,
        )

    def _connection_or_open(self) -> Any:
        if self._connection is None or self._connection.closed:
            try:
                self._connection = self._connect()

            except Exception as error:
                raise DatabaseError(
                    "the HOMI-D database connection failed"
                ) from error

        return self._connection

    def close(self) -> None:
        """Close the connection, if any."""

        with self._lock:
            if self._connection is not None:
                try:
                    self._connection.close()

                except Exception:
                    pass

                self._connection = None

    # -- queries ---------------------------------------------------------

    @contextmanager
    def cursor(self) -> Iterator[Any]:
        """Yield a cursor on the shared connection."""

        with self._lock:
            connection = self._connection_or_open()
            cursor = connection.cursor()

            try:
                yield cursor

            finally:
                try:
                    cursor.close()

                except Exception:
                    pass

    def query(
        self,
        sql: str,
        params: Sequence[Any] | Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Run one read query and return the rows."""

        with self.cursor() as cursor:
            cursor.execute(sql, params)

            return [dict(row) for row in cursor.fetchall()]

    def query_one(
        self,
        sql: str,
        params: Sequence[Any] | Mapping[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Run one read query and return the first row, if any."""

        rows = self.query(sql, params)

        return rows[0] if rows else None

    def execute(
        self,
        sql: str,
        params: Sequence[Any] | Mapping[str, Any] | None = None,
    ) -> None:
        """Run one write statement."""

        with self.cursor() as cursor:
            cursor.execute(sql, params)

    def execute_many(
        self,
        sql: str,
        params: Sequence[Sequence[Any]],
    ) -> None:
        """Run one write statement for every parameter row."""

        if not params:
            return

        with self.cursor() as cursor:
            cursor.executemany(sql, params)

    def table_exists(self, table: str) -> bool:
        """Whether one table of the configured schema exists."""

        row = self.query_one(
            "select exists ("
            "  select 1 from information_schema.tables"
            "  where table_schema = %s and table_name = %s"
            ") as present",
            (self.config.schema, table),
        )

        return bool(row and row.get("present"))


_DATABASE: Database | None = None
_DATABASE_LOCK = threading.RLock()


def get_database() -> Database:
    """Return the process database client."""

    global _DATABASE

    with _DATABASE_LOCK:
        if _DATABASE is None:
            _DATABASE = Database()

        return _DATABASE


def configure_database(config: DatabaseConfig) -> Database:
    """Configure an explicit database client, primarily for tests."""

    global _DATABASE

    with _DATABASE_LOCK:
        if _DATABASE is not None:
            _DATABASE.close()

        _DATABASE = Database(config)

        return _DATABASE


def reset_database() -> None:
    """Close and forget the process database client."""

    global _DATABASE

    with _DATABASE_LOCK:
        if _DATABASE is not None:
            _DATABASE.close()

        _DATABASE = None

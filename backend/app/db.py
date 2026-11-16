"""Thin DB layer. SQLite (dev/tests) and PostgreSQL (production) behind one API.
SQL is written once with `?` placeholders; the PG driver gets them rewritten to %s."""
import sqlite3, threading, uuid, json
from contextlib import contextmanager
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def uid():
    return uuid.uuid4().hex


def jd(v):
    return json.dumps(v, ensure_ascii=False)


def jl(v, default=None):
    if v is None or v == "":
        return default
    return json.loads(v) if isinstance(v, str) else v


class DB:
    def __init__(self, url):
        self.url = url
        self.pg = url.startswith("postgres")
        self.local = threading.local()
        if not self.pg:
            self.path = url.replace("sqlite:///", "", 1)

    # -- connection -------------------------------------------------------
    def conn(self):
        c = getattr(self.local, "c", None)
        if c is None:
            if self.pg:
                import psycopg  # pip install "psycopg[binary]"
                from psycopg.rows import dict_row
                c = psycopg.connect(self.url, row_factory=dict_row, autocommit=True)
            else:
                c = sqlite3.connect(self.path, timeout=15, isolation_level=None)
                c.row_factory = sqlite3.Row
                c.execute("PRAGMA foreign_keys=ON")
                c.execute("PRAGMA journal_mode=WAL")
            self.local.c = c
        return c

    def _sql(self, sql):
        if self.pg:
            return sql.replace("?", "%s").replace("{SKIP}", "FOR UPDATE SKIP LOCKED")
        return sql.replace("{SKIP}", "")

    @staticmethod
    def _row(r):
        if r is None:
            return None
        d = dict(r)
        for k, v in d.items():
            if isinstance(v, datetime):
                d[k] = v.isoformat()
        return d

    # -- API ----------------------------------------------------------------
    def execute(self, sql, params=()):
        cur = self.conn().execute(self._sql(sql), params)
        return cur

    def all(self, sql, params=()):
        return [self._row(r) for r in self.execute(sql, params).fetchall()]

    def one(self, sql, params=()):
        return self._row(self.execute(sql, params).fetchone())

    def scalar(self, sql, params=()):
        r = self.one(sql, params)
        return next(iter(r.values())) if r else None

    @contextmanager
    def tx(self):
        c = self.conn()
        c.execute("BEGIN IMMEDIATE" if not self.pg else "BEGIN")
        try:
            yield
            c.execute("COMMIT")
        except Exception:
            c.execute("ROLLBACK")
            raise

    def init_schema(self):
        from .schema import ddl, MIGRATIONS, migration_statements
        for stmt in ddl(self.pg):
            self.conn().execute(stmt)
        self.migrate(MIGRATIONS, migration_statements)

    def migrate(self, migrations, expand):
        """Apply each pending migration once, in order, inside a transaction; record it in schema_migrations."""
        ts = "TIMESTAMPTZ" if self.pg else "TEXT"
        self.conn().execute(f"CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, description TEXT NOT NULL, applied_at {ts} NOT NULL)")
        done = {r["version"] for r in self.all("SELECT version FROM schema_migrations")}
        for version, desc, sql in sorted(migrations):
            if version in done:
                continue
            with self.tx():
                if self.pg:  # one process migrates at a time
                    self.execute("SELECT pg_advisory_xact_lock(727274)")
                    if self.scalar("SELECT 1 FROM schema_migrations WHERE version=?", (version,)):
                        continue
                for stmt in expand(sql, self.pg):
                    self.execute(stmt)
                self.execute("INSERT INTO schema_migrations (version, description, applied_at) VALUES (?,?,?)", (version, desc, now()))

    def close(self):
        c = getattr(self.local, "c", None)
        if c:
            c.close()
            self.local.c = None

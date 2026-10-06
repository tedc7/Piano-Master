"""SQLite access and numbered migrations (arch §5 "Schema changes").

Migrations are app/migrations/NNN_name.sql, applied in order; PRAGMA user_version records the
last one applied. A migration that must also change the library's files is NNN_name.py instead, with
`run(con, data)`: its database changes are in the same transaction, and its file changes are safe
to make again. The database is the file named by PIANO_DB (/data/piano.db on the server).
"""
from __future__ import annotations

import importlib.util
import os
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parent / "migrations"


def db_path() -> str:
    return os.environ.get("PIANO_DB", "piano.db")


def data_dir() -> Path:
    """Where the song library's files live (library/, and staging/ for every song not in it):
    PIANO_DATA, else beside the database (/data on the server)."""
    d = os.environ.get("PIANO_DATA")
    return Path(d) if d else Path(db_path()).resolve().parent


def connect(path: str | None = None) -> sqlite3.Connection:
    con = sqlite3.connect(path or db_path(), timeout=10, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA busy_timeout = 10000")
    return con


def migrations() -> list[tuple[int, Path]]:
    out = []
    for p in sorted([*MIGRATIONS.glob("*.sql"), *MIGRATIONS.glob("*.py")]):
        m = re.match(r"(\d+)_", p.name)
        if m:
            out.append((int(m.group(1)), p))
    return out


def migrate(path: str | None = None) -> int:
    """Apply any new migrations; returns the schema version."""
    con = connect(path)
    try:
        con.execute("PRAGMA journal_mode = WAL")      # the backup job copies it with the online backup API
        version = con.execute("PRAGMA user_version").fetchone()[0]
        for n, p in migrations():
            if n <= version:
                continue
            con.execute("BEGIN IMMEDIATE")      # each migration file runs in one transaction
            try:
                if p.suffix == ".py":
                    spec = importlib.util.spec_from_file_location(f"migration_{n}", p)
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    mod.run(con, data_dir())
                else:
                    for stmt in split_sql(p.read_text()):
                        con.execute(stmt)
                con.execute(f"PRAGMA user_version = {n}")
                con.execute("COMMIT")
            except Exception:
                con.execute("ROLLBACK")
                raise
            version = n
        return version
    finally:
        con.close()


def split_sql(text: str) -> list[str]:
    """Statements of a migration file, comments removed (our migrations use no strings or
    triggers that contain `--` or `;`)."""
    body = "\n".join(re.sub(r"--.*$", "", line) for line in text.splitlines())
    return [s.strip() for s in body.split(";") if s.strip()]


@contextmanager
def transaction(con: sqlite3.Connection):
    con.execute("BEGIN IMMEDIATE")
    try:
        yield con
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise

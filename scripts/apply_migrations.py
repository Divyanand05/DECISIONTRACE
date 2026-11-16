"""
Apply all SQL migration files in order to the configured database.

Usage:
    python scripts/apply_migrations.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text
from decision_trace.utils.db import get_engine, get_session
from decision_trace.utils.logger import get_logger

log = get_logger("apply_migrations")

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "db" / "migrations"

# Statements that require autocommit (cannot run inside a transaction block)
_AUTOCOMMIT_PREFIXES = ("CREATE DATABASE", "DROP DATABASE", "CREATE TABLESPACE")


def _needs_autocommit(stmt: str) -> bool:
    upper = stmt.strip().upper()
    return any(upper.startswith(p) for p in _AUTOCOMMIT_PREFIXES)


def apply_migrations() -> None:
    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not migration_files:
        log.warning("No migration files found in %s", MIGRATIONS_DIR)
        return

    engine = get_engine()

    for mf in migration_files:
        log.info("Applying migration: %s", mf.name)
        sql_text = mf.read_text(encoding="utf-8")
        # Split on semicolons; skip comment-only and blank chunks
        statements = []
        for chunk in sql_text.split(";"):
            cleaned = chunk.strip()
            # Skip empty or pure-comment chunks
            non_comment = "\n".join(
                line for line in cleaned.splitlines()
                if not line.strip().startswith("--")
            ).strip()
            if non_comment:
                statements.append(cleaned)

        for stmt in statements:
            try:
                if _needs_autocommit(stmt):
                    with engine.connect() as conn:
                        conn.execute(text("COMMIT"))   # end any open txn
                        conn.connection.set_isolation_level(0)  # autocommit
                        conn.execute(text(stmt))
                else:
                    with get_session() as session:
                        session.execute(text(stmt))
            except Exception as exc:
                # IF NOT EXISTS guards handle most re-runs; log and continue
                msg = str(exc).splitlines()[0]
                if "already exists" in msg.lower():
                    log.debug("Skipping (already exists): %s", msg)
                else:
                    log.error("Failed in %s: %s", mf.name, msg)
                    raise

        log.info("Migration %s applied.", mf.name)

    log.info("All migrations complete.")


if __name__ == "__main__":
    apply_migrations()

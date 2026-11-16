"""
One-time database setup script.

Creates the 'dtuser' role and 'decisiontrace' database on your local
PostgreSQL 18 installation, then applies all migrations.

Usage:
    python scripts/setup_db.py --pg-password YOUR_POSTGRES_PASSWORD

Example:
    python scripts/setup_db.py --pg-password secret123
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT


APP_USER     = "dtuser"
APP_PASSWORD = "dtpassword"
APP_DB       = "decisiontrace"


def setup(pg_password: str, pg_host: str = "localhost", pg_port: int = 5432) -> None:
    print(f"Connecting to PostgreSQL at {pg_host}:{pg_port} as postgres …")

    # Connect to the default 'postgres' maintenance database
    conn = psycopg2.connect(
        host=pg_host,
        port=pg_port,
        dbname="postgres",
        user="postgres",
        password=pg_password,
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()

    # 1. Create role
    cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (APP_USER,))
    if cur.fetchone():
        print(f"Role '{APP_USER}' already exists — updating password.")
        cur.execute(
            sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD %s").format(sql.Identifier(APP_USER)),
            (APP_PASSWORD,),
        )
    else:
        print(f"Creating role '{APP_USER}' …")
        cur.execute(
            sql.SQL("CREATE ROLE {} WITH LOGIN PASSWORD %s").format(sql.Identifier(APP_USER)),
            (APP_PASSWORD,),
        )
    print(f"  ✓ Role '{APP_USER}' ready.")

    # 2. Create database
    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (APP_DB,))
    if cur.fetchone():
        print(f"Database '{APP_DB}' already exists.")
    else:
        print(f"Creating database '{APP_DB}' …")
        cur.execute(
            sql.SQL("CREATE DATABASE {} OWNER {}").format(
                sql.Identifier(APP_DB), sql.Identifier(APP_USER)
            )
        )
        print(f"  ✓ Database '{APP_DB}' created.")

    # 3. Grant privileges
    cur.execute(
        sql.SQL("GRANT ALL PRIVILEGES ON DATABASE {} TO {}").format(
            sql.Identifier(APP_DB), sql.Identifier(APP_USER)
        )
    )
    print(f"  ✓ Privileges granted.")

    cur.close()
    conn.close()

    # 4. Apply migrations
    print("\nApplying migrations …")
    from scripts.apply_migrations import apply_migrations
    apply_migrations()

    print("\n✅  Database setup complete!")
    print(f"   Host:     {pg_host}:{pg_port}")
    print(f"   Database: {APP_DB}")
    print(f"   User:     {APP_USER}")
    print(f"   Password: {APP_PASSWORD}")
    print("\nCreate your .env file:")
    print(f'   DATABASE_URL=postgresql://{APP_USER}:{APP_PASSWORD}@{pg_host}:{pg_port}/{APP_DB}')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Set up the DecisionTrace database.")
    parser.add_argument(
        "--pg-password", required=True,
        help="Password for the local 'postgres' superuser account"
    )
    parser.add_argument("--pg-host", default="localhost")
    parser.add_argument("--pg-port", type=int, default=5432)
    args = parser.parse_args()

    try:
        setup(args.pg_password, args.pg_host, args.pg_port)
    except psycopg2.OperationalError as e:
        print(f"\n❌  Connection failed: {e}")
        print("    Check that PostgreSQL is running and the password is correct.")
        sys.exit(1)

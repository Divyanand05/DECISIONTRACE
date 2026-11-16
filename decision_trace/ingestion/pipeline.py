"""
ETL ingestion pipeline.

Responsibilities:
  1. Load raw CSVs from the configured data directory.
  2. Validate field completeness and business rules.
  3. Mark duplicates.
  4. Write clean rows to the database.
  5. Write rejected rows to data/validated/<source>_rejected.csv.
  6. Record an IngestionRun audit row for every file processed.
"""
from __future__ import annotations

import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from config.settings import settings
from decision_trace.ingestion.deduplicator import mark_duplicates
from decision_trace.ingestion.loader import load_csv
from decision_trace.ingestion.validators import (
    validate_orders,
    validate_payments,
    validate_refunds,
)
from decision_trace.utils.db import get_engine, get_session
from decision_trace.utils.logger import get_logger

log = get_logger(__name__)

# Map source name → (csv filename, validator fn, DB table, primary key col)
SOURCE_CONFIG: dict[str, tuple[str, object | None, str, str]] = {
    "customers":   ("customers.csv",   None,              "customers",   "customer_id"),
    "orders":      ("orders.csv",       validate_orders,   "orders",      "order_id"),
    "order_items": ("order_items.csv",  None,              "order_items", "item_id"),
    "payments":    ("payments.csv",     validate_payments, "payments",    "payment_id"),
    "refunds":     ("refunds.csv",      validate_refunds,  "refunds",     "refund_id"),
    "settlements": ("settlements.csv",  None,              "settlements", "settlement_id"),
}


def _upsert_dataframe(df: pd.DataFrame, table: str, pk_col: str) -> None:
    """Write *df* to *table* using INSERT … ON CONFLICT DO NOTHING."""
    if df.empty:
        return
    engine = get_engine()
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy import Table, MetaData

    meta = MetaData()
    meta.reflect(bind=engine, only=[table])
    tbl = meta.tables[table]

    rows = df.where(pd.notna(df), other=None).to_dict(orient="records")
    with engine.begin() as conn:
        for chunk_start in range(0, len(rows), 500):
            chunk = rows[chunk_start : chunk_start + 500]
            stmt = pg_insert(tbl).values(chunk).on_conflict_do_nothing()
            conn.execute(stmt)


def _record_run(
    source_name: str,
    source_file: str,
    total: int,
    accepted: int,
    rejected: int,
    duplicates: int,
    status: str,
    error: str | None = None,
) -> None:
    with get_session() as session:
        session.execute(
            text(
                """
                INSERT INTO ingestion_runs
                    (source_name, source_file, total_records, accepted_records,
                     rejected_records, duplicate_records, status, error_message)
                VALUES
                    (:source_name, :source_file, :total, :accepted,
                     :rejected, :duplicates, :status, :error)
                """
            ),
            {
                "source_name": source_name,
                "source_file": source_file,
                "total": total,
                "accepted": accepted,
                "rejected": rejected,
                "duplicates": duplicates,
                "status": status,
                "error": error,
            },
        )


def ingest_source(source_name: str, raw_dir: Path | None = None) -> dict:
    """
    Ingest a single source CSV.

    Returns a summary dict with counts and status.
    """
    raw_dir = raw_dir or settings.raw_data_dir
    csv_name, validator, table, pk_col = SOURCE_CONFIG[source_name]
    csv_path = Path(raw_dir) / csv_name

    if not csv_path.exists():
        log.warning("CSV not found, skipping: %s", csv_path)
        return {"source": source_name, "status": "skipped", "total": 0}

    try:
        df = load_csv(csv_path, source_name)
        total = len(df)

        # Validate
        if validator is not None:
            result = validator(df)
            valid_df = result.valid
            invalid_df = result.invalid
        else:
            valid_df = df.copy()
            invalid_df = pd.DataFrame()

        # Mark duplicates (only for sources that support it)
        if pk_col in valid_df.columns and source_name in ("orders", "payments"):
            valid_df = mark_duplicates(valid_df, source_name, pk_col)
            dupe_count = int(valid_df["is_duplicate"].sum())
        else:
            # Drop is_duplicate if deduplicator didn't add it (e.g. refunds, settlements)
            valid_df = valid_df.drop(columns=["is_duplicate"], errors="ignore")
            dupe_count = 0

        # Persist valid rows
        # Drop rows that would violate PK constraint (already in DB)
        _upsert_dataframe(valid_df, table, pk_col)

        # Save rejected rows for audit
        if not invalid_df.empty:
            rejected_path = Path(settings.validated_data_dir) / f"{source_name}_rejected.csv"
            rejected_path.parent.mkdir(parents=True, exist_ok=True)
            invalid_df.to_csv(rejected_path, index=False)
            log.warning(
                "%s: %d rows rejected → %s", source_name, len(invalid_df), rejected_path
            )

        accepted = len(valid_df)
        rejected = len(invalid_df)
        _record_run(source_name, str(csv_path), total, accepted, rejected, dupe_count, "success")
        log.info(
            "%s ingested: total=%d accepted=%d rejected=%d duplicates=%d",
            source_name, total, accepted, rejected, dupe_count,
        )
        return {
            "source": source_name,
            "status": "success",
            "total": total,
            "accepted": accepted,
            "rejected": rejected,
            "duplicates": dupe_count,
        }

    except Exception as exc:
        log.exception("Ingestion failed for %s: %s", source_name, exc)
        _record_run(source_name, str(csv_path), 0, 0, 0, 0, "failed", str(exc))
        return {"source": source_name, "status": "failed", "error": str(exc)}


def run_ingestion(raw_dir: Path | None = None) -> list[dict]:
    """Ingest all configured sources in dependency order."""
    order = ["customers", "orders", "order_items", "payments", "refunds", "settlements"]
    summaries = []
    for source in order:
        summary = ingest_source(source, raw_dir)
        summaries.append(summary)
    return summaries

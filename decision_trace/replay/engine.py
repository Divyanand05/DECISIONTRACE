"""
Decision Replay Engine.

Responsibilities:
  1. Compute current KPI values from verified data.
  2. Store each computation as a versioned KpiSnapshot.
  3. Compare any two versions of the same KPI to explain the difference.
  4. Identify the correction events that account for the change.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import text

from decision_trace.utils.db import get_session
from decision_trace.utils.logger import get_logger

log = get_logger(__name__)


# --------------------------------------------------------------------------- #
# KPI computations
# --------------------------------------------------------------------------- #

_KPI_QUERIES: dict[str, str] = {
    "gross_revenue": """
        SELECT COALESCE(SUM(total_amount), 0)
        FROM orders
        WHERE is_duplicate = FALSE
          AND status IN ('confirmed', 'delivered', 'shipped')
          AND order_date BETWEEN :start AND :end
    """,
    "net_revenue": """
        SELECT
            COALESCE(SUM(o.total_amount), 0)
            - COALESCE(SUM(r.amount) FILTER (WHERE r.status = 'processed'), 0)
        FROM orders o
        LEFT JOIN refunds r ON r.order_id = o.order_id
        WHERE o.is_duplicate = FALSE
          AND o.status IN ('confirmed', 'delivered', 'shipped')
          AND o.order_date BETWEEN :start AND :end
    """,
    "total_orders": """
        SELECT COUNT(*)
        FROM orders
        WHERE is_duplicate = FALSE
          AND order_date BETWEEN :start AND :end
    """,
    "payment_success_rate": """
        SELECT
            ROUND(
                100.0 * SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END)
                / NULLIF(COUNT(*), 0),
                2
            )
        FROM payments
        WHERE is_duplicate = FALSE
          AND payment_date BETWEEN :start AND :end
    """,
    "total_refunds": """
        SELECT COALESCE(SUM(amount), 0)
        FROM refunds
        WHERE status = 'processed'
          AND refund_date BETWEEN :start AND :end
    """,
    "unreconciled_difference": """
        SELECT COALESCE(SUM(ABS(difference)), 0)
        FROM reconciliation_results
        WHERE status IN ('unmatched', 'partial')
          AND reconciled_at BETWEEN :start AND :end
    """,
}


def compute_kpi(
    kpi_name: str,
    period_start: datetime,
    period_end: datetime,
    pipeline_run_id: int | None = None,
) -> Decimal:
    """Compute a single KPI for the given period and return its value."""
    sql = _KPI_QUERIES.get(kpi_name)
    if sql is None:
        raise ValueError(f"Unknown KPI: {kpi_name!r}. Available: {list(_KPI_QUERIES)}")

    with get_session() as session:
        row = session.execute(
            text(sql), {"start": period_start, "end": period_end}
        ).fetchone()
    value = Decimal(str(row[0] if row and row[0] is not None else 0))
    return value


def snapshot_kpis(
    period_start: datetime,
    period_end: datetime,
    pipeline_run_id: int | None = None,
    is_corrected: bool = False,
    correction_reason: str | None = None,
) -> list[dict]:
    """
    Compute all KPIs for a period, determine the next version number,
    persist KpiSnapshot rows, and return a list of snapshot dicts.
    """
    snapshots = []
    snapshot_at = datetime.now(tz=timezone.utc)

    for kpi_name in _KPI_QUERIES:
        try:
            value = compute_kpi(kpi_name, period_start, period_end, pipeline_run_id)
        except Exception as exc:
            log.warning("KPI '%s' computation failed: %s", kpi_name, exc)
            continue

        # Determine next version
        with get_session() as session:
            row = session.execute(
                text(
                    """
                    SELECT COALESCE(MAX(version), 0)
                    FROM kpi_snapshots
                    WHERE kpi_name = :name
                      AND period_start = :ps
                      AND period_end   = :pe
                    """
                ),
                {"name": kpi_name, "ps": period_start, "pe": period_end},
            ).fetchone()
        next_version = int(row[0]) + 1

        with get_session() as session:
            session.execute(
                text(
                    """
                    INSERT INTO kpi_snapshots
                        (snapshot_at, kpi_name, kpi_value, period_start, period_end,
                         version, is_corrected, correction_reason, pipeline_run_id)
                    VALUES
                        (:ts, :name, :val, :ps, :pe,
                         :ver, :corrected, :reason, :run_id)
                    """
                ),
                {
                    "ts":        snapshot_at,
                    "name":      kpi_name,
                    "val":       float(value),
                    "ps":        period_start,
                    "pe":        period_end,
                    "ver":       next_version,
                    "corrected": is_corrected,
                    "reason":    correction_reason,
                    "run_id":    pipeline_run_id,
                },
            )

        snapshots.append({
            "kpi_name":     kpi_name,
            "value":        value,
            "version":      next_version,
            "is_corrected": is_corrected,
        })
        log.info("KPI '%s' v%d = %s", kpi_name, next_version, value)

    return snapshots


# --------------------------------------------------------------------------- #
# Decision Replay comparison
# --------------------------------------------------------------------------- #

@dataclass
class ReplayDiff:
    kpi_name: str
    period_start: datetime
    period_end: datetime
    original_version: int
    original_value: Decimal
    corrected_version: int
    corrected_value: Decimal
    difference: Decimal
    pct_change: float
    correction_events: list[dict]


def replay_kpi(
    kpi_name: str,
    period_start: datetime,
    period_end: datetime,
    version_a: int = 1,
    version_b: int | None = None,
) -> ReplayDiff:
    """
    Compare version_a with version_b (default: latest) of a KPI snapshot
    and return a ReplayDiff explaining what changed.
    """
    with get_session() as session:
        def _fetch(version):
            return session.execute(
                text(
                    """
                    SELECT kpi_value, version
                    FROM kpi_snapshots
                    WHERE kpi_name    = :name
                      AND period_start = :ps
                      AND period_end   = :pe
                      AND version      = :ver
                    LIMIT 1
                    """
                ),
                {"name": kpi_name, "ps": period_start, "pe": period_end, "ver": version},
            ).fetchone()

        row_a = _fetch(version_a)
        if row_a is None:
            raise ValueError(f"Snapshot v{version_a} for {kpi_name} not found.")

        if version_b is None:
            row_b = session.execute(
                text(
                    """
                    SELECT kpi_value, version
                    FROM kpi_snapshots
                    WHERE kpi_name    = :name
                      AND period_start = :ps
                      AND period_end   = :pe
                    ORDER BY version DESC
                    LIMIT 1
                    """
                ),
                {"name": kpi_name, "ps": period_start, "pe": period_end},
            ).fetchone()
        else:
            row_b = _fetch(version_b)

        if row_b is None:
            raise ValueError("No corrected snapshot found for comparison.")

        # Fetch correction events that fall in the period
        events = session.execute(
            text(
                """
                SELECT event_at, affected_table, affected_record_id,
                       correction_type, description
                FROM correction_events
                WHERE event_at BETWEEN :ps AND :pe
                ORDER BY event_at
                """
            ),
            {"ps": period_start, "pe": period_end},
        ).fetchall()

    val_a = Decimal(str(row_a.kpi_value))
    val_b = Decimal(str(row_b.kpi_value))
    diff  = val_b - val_a
    pct   = float(diff / val_a * 100) if val_a != 0 else 0.0

    correction_events = [
        {
            "event_at":          e.event_at,
            "affected_table":    e.affected_table,
            "affected_record_id": e.affected_record_id,
            "correction_type":   e.correction_type,
            "description":       e.description,
        }
        for e in events
    ]

    return ReplayDiff(
        kpi_name=kpi_name,
        period_start=period_start,
        period_end=period_end,
        original_version=int(row_a.version),
        original_value=val_a,
        corrected_version=int(row_b.version),
        corrected_value=val_b,
        difference=diff,
        pct_change=round(pct, 4),
        correction_events=correction_events,
    )

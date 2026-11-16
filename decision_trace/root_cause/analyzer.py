"""
Root-Cause Analyzer.

For each category of discrepancy found in reconciliation_results and
data_quality_issues, this module diagnoses the likely cause, collects
supporting evidence (transaction IDs, source systems, amounts), and
produces a structured RootCauseReport.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from decision_trace.utils.db import get_session
from decision_trace.utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class RootCauseItem:
    category: str            # duplicate_records | late_refund | amount_mismatch | missing_payment | ...
    severity: str            # critical | warning | info
    affected_count: int
    total_exposure: float    # financial exposure in base currency
    description: str
    evidence: list[dict[str, Any]] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class RootCauseReport:
    generated_at: datetime
    items: list[RootCauseItem]

    @property
    def total_exposure(self) -> float:
        return sum(i.total_exposure for i in self.items)

    @property
    def critical_count(self) -> int:
        return sum(1 for i in self.items if i.severity == "critical")


def _investigate_duplicates() -> RootCauseItem | None:
    sql = """
        SELECT
            source_system,
            COUNT(*) AS dup_count,
            SUM(total_amount) AS exposure
        FROM orders
        WHERE is_duplicate = TRUE
        GROUP BY source_system
        UNION ALL
        SELECT
            source_system,
            COUNT(*) AS dup_count,
            SUM(amount) AS exposure
        FROM payments
        WHERE is_duplicate = TRUE
        GROUP BY source_system
    """
    try:
        with get_session() as session:
            rows = session.execute(text(sql)).fetchall()
    except Exception as exc:
        log.warning("duplicate investigation query failed: %s", exc)
        return None

    if not rows:
        return None

    total_count = sum(r.dup_count for r in rows)
    total_exposure = sum(float(r.exposure or 0) for r in rows)
    evidence = [
        {"source_system": r.source_system, "duplicate_count": r.dup_count,
         "financial_exposure": float(r.exposure or 0)}
        for r in rows
    ]
    return RootCauseItem(
        category="duplicate_records",
        severity="critical",
        affected_count=total_count,
        total_exposure=total_exposure,
        description=(
            f"{total_count} duplicate transactions detected across order and payment systems. "
            f"Total financial exposure: {total_exposure:,.2f}."
        ),
        evidence=evidence,
        recommendations=[
            "Implement idempotency keys at the payment gateway integration layer.",
            "Add unique constraints on gateway_reference in the payments table.",
            "Audit the ingestion pipeline for the identified source systems.",
        ],
    )


def _investigate_unmatched_payments() -> RootCauseItem | None:
    sql = """
        SELECT
            rr.reference_id  AS order_id,
            o.source_system,
            rr.expected_amount,
            rr.actual_amount,
            rr.difference
        FROM reconciliation_results rr
        JOIN orders o ON o.order_id = rr.reference_id
        WHERE rr.reconciliation_type = 'order_payment'
          AND rr.status = 'unmatched'
        LIMIT 50
    """
    try:
        with get_session() as session:
            rows = session.execute(text(sql)).fetchall()
    except Exception as exc:
        log.warning("unmatched_payment investigation failed: %s", exc)
        return None

    if not rows:
        return None

    total_exposure = sum(float(r.expected_amount or 0) for r in rows)
    evidence = [
        {"order_id": r.order_id, "source_system": r.source_system,
         "expected": float(r.expected_amount or 0)}
        for r in rows
    ]
    return RootCauseItem(
        category="missing_payment",
        severity="critical",
        affected_count=len(rows),
        total_exposure=total_exposure,
        description=(
            f"{len(rows)} confirmed orders have no matching successful payment. "
            f"Revenue at risk: {total_exposure:,.2f}."
        ),
        evidence=evidence,
        recommendations=[
            "Trigger payment status requery for orders older than 1 hour with no payment.",
            "Alert the finance team for manual review of orders above threshold.",
            "Check gateway webhook configuration for missed payment confirmations.",
        ],
    )


def _investigate_late_refunds() -> RootCauseItem | None:
    sql = """
        SELECT
            rr.reference_id  AS payment_id,
            rr.expected_amount,
            rr.actual_amount,
            ABS(rr.difference) AS over_refunded
        FROM reconciliation_results rr
        WHERE rr.reconciliation_type = 'refund_check'
          AND rr.status = 'unmatched'
        LIMIT 50
    """
    try:
        with get_session() as session:
            rows = session.execute(text(sql)).fetchall()
    except Exception as exc:
        log.warning("late_refund investigation failed: %s", exc)
        return None

    if not rows:
        return None

    total_exposure = sum(float(r.over_refunded or 0) for r in rows)
    evidence = [
        {"payment_id": r.payment_id,
         "over_refunded_by": float(r.over_refunded or 0)}
        for r in rows
    ]
    return RootCauseItem(
        category="over_refund",
        severity="critical",
        affected_count=len(rows),
        total_exposure=total_exposure,
        description=(
            f"{len(rows)} payments have been over-refunded. "
            f"Total over-refunded amount: {total_exposure:,.2f}."
        ),
        evidence=evidence,
        recommendations=[
            "Block refund requests exceeding the original payment amount at the API layer.",
            "Raise an alert to the reconciliation team for each over-refund event.",
            "Review the refund workflow in the source refund system.",
        ],
    )


def _investigate_data_quality_critical() -> RootCauseItem | None:
    sql = """
        SELECT
            source_table,
            rule_name,
            COUNT(*) AS violation_count
        FROM data_quality_issues
        WHERE severity = 'critical'
          AND is_resolved = FALSE
        GROUP BY source_table, rule_name
        ORDER BY violation_count DESC
        LIMIT 20
    """
    try:
        with get_session() as session:
            rows = session.execute(text(sql)).fetchall()
    except Exception as exc:
        log.warning("quality investigation failed: %s", exc)
        return None

    if not rows:
        return None

    total = sum(r.violation_count for r in rows)
    evidence = [
        {"table": r.source_table, "rule": r.rule_name, "count": r.violation_count}
        for r in rows
    ]
    return RootCauseItem(
        category="data_quality_critical",
        severity="critical",
        affected_count=total,
        total_exposure=0.0,
        description=(
            f"{total} critical data quality violations remain open across "
            f"{len(set(r.source_table for r in rows))} tables."
        ),
        evidence=evidence,
        recommendations=[
            "Resolve null required-field violations before the next reporting cycle.",
            "Investigate upstream source systems producing invalid records.",
            "Implement schema validation at the ingestion boundary.",
        ],
    )


def run_root_cause_analysis() -> RootCauseReport:
    """Run all root-cause investigations and produce a combined report."""
    investigators = [
        _investigate_duplicates,
        _investigate_unmatched_payments,
        _investigate_late_refunds,
        _investigate_data_quality_critical,
    ]

    items: list[RootCauseItem] = []
    for fn in investigators:
        result = fn()
        if result is not None:
            items.append(result)
            log.info(
                "Root cause [%s] — %d affected, exposure=%.2f",
                result.category, result.affected_count, result.total_exposure,
            )

    report = RootCauseReport(generated_at=datetime.now(tz=timezone.utc), items=items)
    log.info(
        "Root-cause analysis complete: %d issues found, total exposure=%.2f",
        len(items), report.total_exposure,
    )
    return report

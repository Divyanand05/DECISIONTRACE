"""
Business Insights Generator.

Queries verified data to surface actionable findings. Each insight
includes the supporting calculation, affected record counts, and
a recommended next action.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import text

from decision_trace.utils.db import get_session
from decision_trace.utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class Insight:
    title: str
    category: str           # revenue | payment_method | data_quality | operational
    severity: str           # high | medium | low
    metric_value: float
    metric_label: str
    description: str
    supporting_sql: str
    evidence: list[dict] = field(default_factory=list)
    recommendation: str = ""


@dataclass
class InsightsReport:
    generated_at: datetime
    insights: list[Insight]

    def high_priority(self) -> list[Insight]:
        return [i for i in self.insights if i.severity == "high"]


def _insight_payment_method_failure_rate() -> Insight | None:
    sql = """
        SELECT
            method,
            COUNT(*)                                                AS total,
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END)     AS failed,
            ROUND(
                100.0 * SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END)
                / NULLIF(COUNT(*), 0),
            2) AS failure_rate
        FROM payments
        WHERE is_duplicate = FALSE
        GROUP BY method
        HAVING ROUND(
            100.0 * SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END)
            / NULLIF(COUNT(*), 0), 2) > 10
        ORDER BY failure_rate DESC
    """
    try:
        with get_session() as session:
            rows = session.execute(text(sql)).fetchall()
    except Exception as exc:
        log.warning("payment_method_failure insight failed: %s", exc)
        return None

    if not rows:
        return None

    worst = rows[0]
    evidence = [
        {"method": r.method, "total": r.total, "failed": r.failed, "failure_rate_pct": float(r.failure_rate)}
        for r in rows
    ]
    return Insight(
        title="High Payment Failure Rate by Method",
        category="payment_method",
        severity="high",
        metric_value=float(worst.failure_rate),
        metric_label=f"failure rate % for {worst.method}",
        description=(
            f"Payment method '{worst.method}' has a {worst.failure_rate}% failure rate "
            f"({worst.failed} of {worst.total} transactions). "
            f"{len(rows)} method(s) exceed the 10% threshold."
        ),
        supporting_sql=sql,
        evidence=evidence,
        recommendation=(
            f"Investigate '{worst.method}' gateway configuration. "
            "Consider routing high-value transactions through a secondary gateway."
        ),
    )


def _insight_revenue_discrepancy_by_method() -> Insight | None:
    sql = """
        SELECT method, order_total, payment_total, discrepancy
        FROM (
            SELECT
                p.method,
                SUM(o.total_amount) AS order_total,
                SUM(p.amount)       AS payment_total,
                SUM(o.total_amount) - SUM(p.amount) AS discrepancy
            FROM orders o
            JOIN payments p ON p.order_id = o.order_id
            WHERE o.is_duplicate = FALSE
              AND p.is_duplicate = FALSE
              AND p.status = 'success'
            GROUP BY p.method
        ) sub
        WHERE ABS(discrepancy) > 100
        ORDER BY ABS(discrepancy) DESC
    """
    try:
        with get_session() as session:
            rows = session.execute(text(sql)).fetchall()
    except Exception as exc:
        log.warning("revenue_discrepancy_by_method insight failed: %s", exc)
        return None

    if not rows:
        return None

    total_discrepancy = sum(abs(float(r.discrepancy)) for r in rows)
    evidence = [
        {"method": r.method, "order_total": float(r.order_total),
         "payment_total": float(r.payment_total), "discrepancy": float(r.discrepancy)}
        for r in rows
    ]
    return Insight(
        title="Revenue Discrepancy Concentrated in Specific Payment Methods",
        category="revenue",
        severity="high",
        metric_value=total_discrepancy,
        metric_label="total discrepancy (₹)",
        description=(
            f"Revenue discrepancies totalling ₹{total_discrepancy:,.2f} are concentrated in "
            f"{len(rows)} payment method(s). This may indicate partial captures, "
            "failed settlement reconciliation, or booking errors."
        ),
        supporting_sql=sql,
        evidence=evidence,
        recommendation=(
            "Review each payment method's settlement report. "
            "Verify gateway fee deductions are accounted for in reconciliation rules."
        ),
    )


def _insight_repeated_dq_failures_by_source() -> Insight | None:
    sql = """
        SELECT
            source_table,
            COUNT(*) AS total_issues,
            SUM(CASE WHEN severity = 'critical' THEN 1 ELSE 0 END) AS critical_issues
        FROM data_quality_issues
        WHERE is_resolved = FALSE
        GROUP BY source_table
        ORDER BY critical_issues DESC, total_issues DESC
        LIMIT 5
    """
    try:
        with get_session() as session:
            rows = session.execute(text(sql)).fetchall()
    except Exception as exc:
        log.warning("dq_failures_by_source insight failed: %s", exc)
        return None

    if not rows:
        return None

    top = rows[0]
    evidence = [
        {"source_table": r.source_table, "total": r.total_issues, "critical": r.critical_issues}
        for r in rows
    ]
    return Insight(
        title="Repeated Data Quality Failures from Source Systems",
        category="data_quality",
        severity="high" if top.critical_issues > 0 else "medium",
        metric_value=float(top.critical_issues),
        metric_label=f"critical open issues in {top.source_table}",
        description=(
            f"Table '{top.source_table}' has {top.critical_issues} open critical "
            f"and {top.total_issues} total unresolved quality issues. "
            "This may reflect a systemic problem in the upstream source system."
        ),
        supporting_sql=sql,
        evidence=evidence,
        recommendation=(
            "Engage the team responsible for the upstream source to fix root data issues. "
            "Consider adding a data contract (schema + value expectations) at the ingestion boundary."
        ),
    )


def _insight_kpi_shift_after_corrections() -> Insight | None:
    sql = """
        SELECT kpi_name, original_value, corrected_value, shift
        FROM (
            SELECT
                kpi_name,
                MIN(kpi_value) FILTER (WHERE version = 1)        AS original_value,
                MAX(kpi_value) FILTER (WHERE is_corrected = TRUE) AS corrected_value,
                MAX(kpi_value) FILTER (WHERE is_corrected = TRUE)
                    - MIN(kpi_value) FILTER (WHERE version = 1)   AS shift
            FROM kpi_snapshots
            GROUP BY kpi_name
        ) sub
        WHERE shift IS NOT NULL
          AND ABS(shift) > 0
        ORDER BY ABS(shift) DESC
        LIMIT 5
    """
    try:
        with get_session() as session:
            rows = session.execute(text(sql)).fetchall()
    except Exception as exc:
        log.warning("kpi_shift insight failed: %s", exc)
        return None

    if not rows:
        return None

    evidence = [
        {"kpi": r.kpi_name, "original": float(r.original_value or 0),
         "corrected": float(r.corrected_value or 0), "shift": float(r.shift or 0)}
        for r in rows
    ]
    top_shift = max(abs(float(r.shift or 0)) for r in rows)
    return Insight(
        title="KPI Values Changed After Late-Arriving Data Corrections",
        category="operational",
        severity="medium",
        metric_value=top_shift,
        metric_label="largest KPI shift after correction",
        description=(
            f"{len(rows)} KPI(s) changed after corrections were applied. "
            f"The largest shift was {top_shift:,.2f}. "
            "This indicates business decisions may have been made on stale or incorrect data."
        ),
        supporting_sql=sql,
        evidence=evidence,
        recommendation=(
            "Publish KPI correction notifications to dashboard consumers. "
            "Establish a maximum reporting lag SLA to minimise future correction magnitude."
        ),
    )


def generate_insights() -> InsightsReport:
    """Run all insight generators and return a combined InsightsReport."""
    generators = [
        _insight_payment_method_failure_rate,
        _insight_revenue_discrepancy_by_method,
        _insight_repeated_dq_failures_by_source,
        _insight_kpi_shift_after_corrections,
    ]

    insights: list[Insight] = []
    for fn in generators:
        result = fn()
        if result is not None:
            insights.append(result)
            log.info("Insight [%s] — severity=%s value=%.2f", result.title, result.severity, result.metric_value)

    report = InsightsReport(
        generated_at=datetime.now(tz=timezone.utc),
        insights=insights,
    )
    log.info("Insights complete: %d findings (%d high priority)", len(insights), len(report.high_priority()))
    return report

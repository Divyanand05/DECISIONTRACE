"""
Data Quality Engine — orchestrates rule execution and stores issues.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text

from decision_trace.quality.rules import RULES, QualityRule
from decision_trace.quality.scorer import ReliabilityReport, compute_reliability_score
from decision_trace.utils.db import get_session
from decision_trace.utils.logger import get_logger

log = get_logger(__name__)


def _run_rule(rule: QualityRule) -> list[str]:
    """
    Execute a rule's check SQL and return the list of failing record IDs.
    Returns an empty list if the table doesn't exist yet.
    """
    failing_ids: list[str] = []
    try:
        with get_session() as session:
            rows = session.execute(text(rule.check_sql)).fetchall()
            failing_ids = [str(r[0]) for r in rows]
    except Exception as exc:
        log.warning("Rule %s could not execute: %s", rule.rule_name, exc)
    return failing_ids


def _persist_issues(rule: QualityRule, failing_ids: list[str]) -> None:
    """Write one DataQualityIssue row per failing record."""
    if not failing_ids:
        return
    now = datetime.now(tz=timezone.utc)
    with get_session() as session:
        for record_id in failing_ids:
            session.execute(
                text(
                    """
                    INSERT INTO data_quality_issues
                        (detected_at, source_table, record_id, dimension,
                         rule_name, severity, description)
                    VALUES
                        (:ts, :table, :rid, :dim, :rule, :sev, :desc)
                    """
                ),
                {
                    "ts":    now,
                    "table": rule.table,
                    "rid":   record_id,
                    "dim":   rule.dimension,
                    "rule":  rule.rule_name,
                    "sev":   rule.severity,
                    "desc":  rule.description,
                },
            )


def run_quality_checks(rules: list[QualityRule] | None = None) -> ReliabilityReport:
    """
    Execute all (or selected) quality rules, persist issues, and return a ReliabilityReport.
    """
    rules = rules or RULES
    failed_rule_names: list[str] = []
    total_violations = 0

    for rule in rules:
        failing_ids = _run_rule(rule)
        if failing_ids:
            log.warning(
                "[%s] Rule '%s' failed: %d record(s) in violation",
                rule.severity.upper(), rule.rule_name, len(failing_ids),
            )
            failed_rule_names.append(rule.rule_name)
            total_violations += len(failing_ids)
            _persist_issues(rule, failing_ids)
        else:
            log.info("Rule '%s' passed.", rule.rule_name)

    report = compute_reliability_score(failed_rule_names)
    log.info(
        "Quality check complete — overall score: %.1f%s | violations: %d",
        report.overall_score,
        " (capped due to critical failures)" if report.capped else "",
        total_violations,
    )
    return report

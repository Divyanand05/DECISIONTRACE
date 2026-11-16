"""
Integration tests for the full pipeline.

These tests require a running PostgreSQL instance.  They are skipped
automatically when the database is not reachable.

Run with:
    pytest tests/integration/ -v
"""
from __future__ import annotations

import os
import pytest

# Skip all integration tests if DB is unavailable
def _db_available() -> bool:
    try:
        from decision_trace.utils.db import test_connection
        return test_connection()
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _db_available(),
    reason="PostgreSQL database not reachable — skipping integration tests",
)


def test_db_connection():
    from decision_trace.utils.db import test_connection
    assert test_connection() is True


def test_quality_checks_return_report():
    from decision_trace.quality.engine import run_quality_checks
    report = run_quality_checks()
    assert 0.0 <= report.overall_score <= 100.0
    assert isinstance(report.failed_rule_names, list)


def test_reconciliation_returns_summaries():
    from decision_trace.reconciliation.engine import run_reconciliation
    summaries = run_reconciliation()
    assert len(summaries) == 3
    types = {s.reconciliation_type for s in summaries}
    assert "order_payment" in types
    assert "payment_settlement" in types
    assert "refund_check" in types


def test_root_cause_returns_report():
    from decision_trace.root_cause.analyzer import run_root_cause_analysis
    report = run_root_cause_analysis()
    assert report.generated_at is not None
    assert isinstance(report.items, list)


def test_insights_returns_report():
    from decision_trace.insights.generator import generate_insights
    report = generate_insights()
    assert report.generated_at is not None
    assert isinstance(report.insights, list)

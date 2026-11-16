"""
Unit tests for the Decision Replay engine — logic only, no DB required.
"""
from decimal import Decimal
from datetime import datetime, timezone

import pytest

from decision_trace.replay.engine import _KPI_QUERIES


def test_all_kpis_have_queries():
    expected = {"gross_revenue", "net_revenue", "total_orders",
                "payment_success_rate", "total_refunds", "unreconciled_difference"}
    assert expected == set(_KPI_QUERIES.keys())


def test_kpi_queries_contain_period_params():
    for name, sql in _KPI_QUERIES.items():
        assert ":start" in sql, f"KPI '{name}' query missing :start parameter"
        assert ":end"   in sql, f"KPI '{name}' query missing :end parameter"

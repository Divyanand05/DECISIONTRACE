"""
Unit tests for the duplicate detection logic.
"""
import pandas as pd
import pytest

from decision_trace.ingestion.deduplicator import mark_duplicates


def _orders(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_no_duplicates():
    df = _orders([
        {"order_id": "O1", "customer_id": "C1", "order_date": "2026-01-01", "total_amount": 100.0},
        {"order_id": "O2", "customer_id": "C2", "order_date": "2026-01-02", "total_amount": 200.0},
    ])
    result = mark_duplicates(df, "orders", "order_id")
    assert result["is_duplicate"].sum() == 0


def test_exact_pk_duplicate():
    df = _orders([
        {"order_id": "O1", "customer_id": "C1", "order_date": "2026-01-01", "total_amount": 100.0},
        {"order_id": "O1", "customer_id": "C1", "order_date": "2026-01-01", "total_amount": 100.0},
    ])
    result = mark_duplicates(df, "orders", "order_id")
    assert result["is_duplicate"].sum() == 1
    # First occurrence should be canonical
    assert result.iloc[0]["is_duplicate"] is False or result.iloc[0]["is_duplicate"] == False


def test_business_key_near_duplicate():
    """Same customer + amount + date but different order_id = near-duplicate."""
    df = _orders([
        {"order_id": "O1", "customer_id": "C1", "order_date": "2026-01-01", "total_amount": 100.0},
        {"order_id": "O2", "customer_id": "C1", "order_date": "2026-01-01", "total_amount": 100.0},
    ])
    result = mark_duplicates(df, "orders", "order_id")
    assert result["is_duplicate"].sum() == 1


def test_different_amounts_not_duplicate():
    df = _orders([
        {"order_id": "O1", "customer_id": "C1", "order_date": "2026-01-01", "total_amount": 100.0},
        {"order_id": "O2", "customer_id": "C1", "order_date": "2026-01-01", "total_amount": 200.0},
    ])
    result = mark_duplicates(df, "orders", "order_id")
    assert result["is_duplicate"].sum() == 0

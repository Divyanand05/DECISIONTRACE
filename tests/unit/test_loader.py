"""
Unit tests for the CSV loader.
"""
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from decision_trace.ingestion.loader import load_csv


def _write_csv(content: str) -> Path:
    tmp = tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w", encoding="utf-8")
    tmp.write(content)
    tmp.close()
    return Path(tmp.name)


def test_load_orders_coerces_dates():
    csv_content = "order_id,customer_id,order_date,total_amount,status\nORD001,C1,2026-01-15,1000,confirmed\n"
    path = _write_csv(csv_content)
    df = load_csv(path, "orders")
    assert pd.api.types.is_datetime64_any_dtype(df["order_date"])


def test_load_orders_coerces_amounts():
    csv_content = "order_id,customer_id,order_date,total_amount,status\nORD001,C1,2026-01-15,1000,confirmed\n"
    path = _write_csv(csv_content)
    df = load_csv(path, "orders")
    assert pd.api.types.is_float_dtype(df["total_amount"]) or pd.api.types.is_integer_dtype(df["total_amount"])


def test_column_names_lowercased():
    csv_content = "Order_ID,Customer_ID,Order_Date,Total_Amount,Status\nORD001,C1,2026-01-15,1000,confirmed\n"
    path = _write_csv(csv_content)
    df = load_csv(path, "orders")
    assert all(c == c.lower() for c in df.columns)


def test_invalid_date_becomes_nat():
    csv_content = "order_id,customer_id,order_date,total_amount,status\nORD001,C1,NOT_A_DATE,1000,confirmed\n"
    path = _write_csv(csv_content)
    df = load_csv(path, "orders")
    assert df["order_date"].isna().all()

"""
Unit tests for field-level validators.
"""
import pytest
import pandas as pd

from decision_trace.ingestion.validators import validate_orders, validate_payments, validate_refunds


# --------------------------------------------------------------------------- #
# Orders
# --------------------------------------------------------------------------- #

def _make_orders(**overrides) -> pd.DataFrame:
    base = {
        "order_id":     ["ORD001", "ORD002"],
        "customer_id":  ["CUST001", "CUST002"],
        "order_date":   ["2026-01-01", "2026-01-02"],
        "total_amount": [1000.0, 2500.0],
        "status":       ["confirmed", "delivered"],
        "source_system":["web", "mobile"],
    }
    base.update(overrides)
    return pd.DataFrame(base)


def test_valid_orders_pass():
    df = _make_orders()
    result = validate_orders(df)
    assert len(result.valid) == 2
    assert len(result.invalid) == 0


def test_null_customer_id_rejected():
    df = _make_orders(customer_id=["CUST001", None])
    result = validate_orders(df)
    assert len(result.invalid) == 1
    assert "null_required_field" in result.invalid.iloc[0]["rejection_reason"]


def test_negative_amount_rejected():
    df = _make_orders(total_amount=[1000.0, -500.0])
    result = validate_orders(df)
    assert len(result.invalid) == 1
    assert "negative_total_amount" in result.invalid.iloc[0]["rejection_reason"]


def test_invalid_status_rejected():
    df = _make_orders(status=["confirmed", "MYSTERY"])
    result = validate_orders(df)
    assert len(result.invalid) == 1
    assert "invalid_order_status" in result.invalid.iloc[0]["rejection_reason"]


def test_missing_required_column_raises():
    df = pd.DataFrame({"order_id": ["ORD001"], "total_amount": [100]})
    with pytest.raises(ValueError, match="missing required columns"):
        validate_orders(df)


# --------------------------------------------------------------------------- #
# Payments
# --------------------------------------------------------------------------- #

def _make_payments(**overrides) -> pd.DataFrame:
    base = {
        "payment_id":   ["PAY001", "PAY002"],
        "order_id":     ["ORD001", "ORD002"],
        "payment_date": ["2026-01-01", "2026-01-02"],
        "amount":       [1000.0, 2500.0],
        "method":       ["card", "upi"],
        "status":       ["success", "success"],
    }
    base.update(overrides)
    return pd.DataFrame(base)


def test_valid_payments_pass():
    result = validate_payments(_make_payments())
    assert len(result.valid) == 2
    assert len(result.invalid) == 0


def test_invalid_payment_method_rejected():
    result = validate_payments(_make_payments(method=["card", "CRYPTO"]))
    assert len(result.invalid) == 1


def test_negative_payment_amount_rejected():
    result = validate_payments(_make_payments(amount=[1000.0, -50.0]))
    assert len(result.invalid) == 1


# --------------------------------------------------------------------------- #
# Refunds
# --------------------------------------------------------------------------- #

def _make_refunds(**overrides) -> pd.DataFrame:
    base = {
        "refund_id":   ["REF001"],
        "payment_id":  ["PAY001"],
        "order_id":    ["ORD001"],
        "refund_date": ["2026-01-05"],
        "amount":      [500.0],
        "status":      ["processed"],
    }
    base.update(overrides)
    return pd.DataFrame(base)


def test_valid_refund_passes():
    result = validate_refunds(_make_refunds())
    assert len(result.valid) == 1


def test_zero_refund_amount_rejected():
    result = validate_refunds(_make_refunds(amount=[0.0]))
    assert len(result.invalid) == 1

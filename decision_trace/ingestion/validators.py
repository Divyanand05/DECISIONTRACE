"""
Field-level validation rules applied during ingestion.

Each validator receives a pandas DataFrame and returns two DataFrames:
  - valid rows
  - invalid rows (with an added `rejection_reason` column)
"""
from __future__ import annotations

from typing import NamedTuple

import pandas as pd


class ValidationResult(NamedTuple):
    valid: pd.DataFrame
    invalid: pd.DataFrame


def _reject(df: pd.DataFrame, mask: pd.Series, reason: str) -> pd.DataFrame:
    """Tag rows matching *mask* with a rejection reason."""
    rejected = df[mask].copy()
    if "rejection_reason" not in rejected.columns:
        rejected["rejection_reason"] = reason
    else:
        rejected["rejection_reason"] = rejected["rejection_reason"] + "; " + reason
    return rejected


def validate_orders(df: pd.DataFrame) -> ValidationResult:
    required = ["order_id", "customer_id", "order_date", "total_amount", "status"]
    missing_cols = [c for c in required if c not in df.columns]
    if missing_cols:
        raise ValueError(f"Orders CSV missing required columns: {missing_cols}")

    invalid_parts: list[pd.DataFrame] = []
    mask_all_bad = pd.Series(False, index=df.index)

    # Null required fields
    null_mask = df[required].isnull().any(axis=1)
    if null_mask.any():
        invalid_parts.append(_reject(df, null_mask, "null_required_field"))
        mask_all_bad |= null_mask

    # Negative amounts
    if "total_amount" in df.columns:
        neg_mask = pd.to_numeric(df["total_amount"], errors="coerce") < 0
        neg_mask = neg_mask.fillna(False) & ~mask_all_bad
        if neg_mask.any():
            invalid_parts.append(_reject(df, neg_mask, "negative_total_amount"))
            mask_all_bad |= neg_mask

    # Invalid status values
    valid_statuses = {"pending", "confirmed", "shipped", "delivered", "cancelled"}
    if "status" in df.columns:
        bad_status = ~df["status"].str.lower().isin(valid_statuses) & ~mask_all_bad
        if bad_status.any():
            invalid_parts.append(_reject(df, bad_status, "invalid_order_status"))
            mask_all_bad |= bad_status

    invalid = pd.concat(invalid_parts) if invalid_parts else pd.DataFrame(columns=df.columns)
    valid = df[~mask_all_bad].copy()
    return ValidationResult(valid=valid, invalid=invalid)


def validate_payments(df: pd.DataFrame) -> ValidationResult:
    required = ["payment_id", "order_id", "payment_date", "amount", "method", "status"]
    missing_cols = [c for c in required if c not in df.columns]
    if missing_cols:
        raise ValueError(f"Payments CSV missing required columns: {missing_cols}")

    invalid_parts: list[pd.DataFrame] = []
    mask_all_bad = pd.Series(False, index=df.index)

    null_mask = df[required].isnull().any(axis=1)
    if null_mask.any():
        invalid_parts.append(_reject(df, null_mask, "null_required_field"))
        mask_all_bad |= null_mask

    if "amount" in df.columns:
        neg_mask = pd.to_numeric(df["amount"], errors="coerce") < 0
        neg_mask = neg_mask.fillna(False) & ~mask_all_bad
        if neg_mask.any():
            invalid_parts.append(_reject(df, neg_mask, "negative_payment_amount"))
            mask_all_bad |= neg_mask

    valid_methods = {"card", "upi", "netbanking", "wallet", "cod"}
    if "method" in df.columns:
        bad_method = ~df["method"].str.lower().isin(valid_methods) & ~mask_all_bad
        if bad_method.any():
            invalid_parts.append(_reject(df, bad_method, "invalid_payment_method"))
            mask_all_bad |= bad_method

    valid_statuses = {"success", "failed", "pending", "refunded"}
    if "status" in df.columns:
        bad_status = ~df["status"].str.lower().isin(valid_statuses) & ~mask_all_bad
        if bad_status.any():
            invalid_parts.append(_reject(df, bad_status, "invalid_payment_status"))
            mask_all_bad |= bad_status

    invalid = pd.concat(invalid_parts) if invalid_parts else pd.DataFrame(columns=df.columns)
    valid = df[~mask_all_bad].copy()
    return ValidationResult(valid=valid, invalid=invalid)


def validate_refunds(df: pd.DataFrame) -> ValidationResult:
    required = ["refund_id", "payment_id", "order_id", "refund_date", "amount", "status"]
    missing_cols = [c for c in required if c not in df.columns]
    if missing_cols:
        raise ValueError(f"Refunds CSV missing required columns: {missing_cols}")

    invalid_parts: list[pd.DataFrame] = []
    mask_all_bad = pd.Series(False, index=df.index)

    null_mask = df[required].isnull().any(axis=1)
    if null_mask.any():
        invalid_parts.append(_reject(df, null_mask, "null_required_field"))
        mask_all_bad |= null_mask

    if "amount" in df.columns:
        neg_mask = pd.to_numeric(df["amount"], errors="coerce") <= 0
        neg_mask = neg_mask.fillna(False) & ~mask_all_bad
        if neg_mask.any():
            invalid_parts.append(_reject(df, neg_mask, "non_positive_refund_amount"))
            mask_all_bad |= neg_mask

    invalid = pd.concat(invalid_parts) if invalid_parts else pd.DataFrame(columns=df.columns)
    valid = df[~mask_all_bad].copy()
    return ValidationResult(valid=valid, invalid=invalid)

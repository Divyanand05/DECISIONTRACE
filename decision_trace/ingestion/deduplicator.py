"""
Duplicate detection logic.

Business logic:
  - Exact duplicates: identical primary key.
  - Near-duplicates: same business key (order_id + amount + date within tolerance)
    but different surrogate IDs — common with double-submit or gateway retries.
"""
from __future__ import annotations

import pandas as pd

from decision_trace.utils.logger import get_logger

log = get_logger(__name__)

# Columns that together uniquely identify a business event
_BUSINESS_KEYS: dict[str, list[str]] = {
    "orders":   ["customer_id", "order_date", "total_amount"],
    "payments": ["order_id", "amount", "payment_date", "method"],
    "refunds":  ["payment_id", "amount", "refund_date"],
}


def mark_duplicates(df: pd.DataFrame, source_name: str, id_col: str) -> pd.DataFrame:
    """
    Add an `is_duplicate` boolean column to *df*.

    The first occurrence of each primary key AND each business key combination
    is kept as the canonical record (is_duplicate=False). Subsequent
    occurrences are flagged True.

    Parameters
    ----------
    df:
        DataFrame for a single source.
    source_name:
        Logical source (orders | payments | refunds).
    id_col:
        Primary key column name.
    """
    df = df.copy()
    df["is_duplicate"] = False

    # 1. Exact primary-key duplicates
    pk_dup = df.duplicated(subset=[id_col], keep="first")
    df.loc[pk_dup, "is_duplicate"] = True
    pk_count = pk_dup.sum()
    if pk_count:
        log.warning("%s: %d exact primary-key duplicates found", source_name, pk_count)

    # 2. Business-key near-duplicates (only for already-canonical rows)
    biz_keys = _BUSINESS_KEYS.get(source_name)
    available_keys = [k for k in (biz_keys or []) if k in df.columns]
    if available_keys:
        # Only look at rows not already flagged
        canonical = df[~df["is_duplicate"]].copy()
        # Normalise datetime to date for fuzzy matching
        for col in available_keys:
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                canonical[col] = canonical[col].dt.normalize()

        biz_dup = canonical.duplicated(subset=available_keys, keep="first")
        biz_dup_ids = canonical.loc[biz_dup, id_col]
        biz_count = len(biz_dup_ids)
        if biz_count:
            log.warning(
                "%s: %d near-duplicate business events (same keys, different IDs)",
                source_name, biz_count,
            )
            df.loc[df[id_col].isin(biz_dup_ids), "is_duplicate"] = True

    total_dupes = df["is_duplicate"].sum()
    log.info("%s: %d / %d rows flagged as duplicates", source_name, total_dupes, len(df))
    return df

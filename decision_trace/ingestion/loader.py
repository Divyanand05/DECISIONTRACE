"""
CSV loader: reads raw CSVs, standardises column names and dtypes.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from decision_trace.utils.logger import get_logger

log = get_logger(__name__)

_DATE_COLS: dict[str, list[str]] = {
    "orders":      ["order_date"],
    "payments":    ["payment_date"],
    "refunds":     ["refund_date"],
    "settlements": ["settlement_date"],
    "customers":   ["created_at", "updated_at"],
}

_AMOUNT_COLS: dict[str, list[str]] = {
    "orders":      ["total_amount"],
    "payments":    ["amount"],
    "refunds":     ["amount"],
    "settlements": ["settled_amount", "fee"],
    "order_items": ["unit_price", "line_total"],
}


def load_csv(path: Path | str, source_name: str) -> pd.DataFrame:
    """
    Load a CSV file and apply standard type coercions for *source_name*.

    Parameters
    ----------
    path:
        Absolute or relative path to the CSV file.
    source_name:
        Logical source name (orders | payments | refunds | settlements | customers | order_items).
    """
    path = Path(path)
    log.info("Loading %s from %s", source_name, path)
    df = pd.read_csv(path, dtype=str)                     # read everything as str first
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    # Coerce dates
    for col in _DATE_COLS.get(source_name, []):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)

    # Coerce amounts
    for col in _AMOUNT_COLS.get(source_name, []):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    log.info("Loaded %d rows from %s", len(df), path.name)
    return df

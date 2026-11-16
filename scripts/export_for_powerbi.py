"""
Export analytical views to CSV for Power BI import.

Exports:
  - v_daily_revenue
  - v_payment_method_summary
  - v_reconciliation_overview
  - v_quality_summary
  - v_latest_kpi
  - kpi_snapshots (full, for Decision Replay page)
  - data_quality_issues (open only)
  - reconciliation_results

Run:
    python scripts/export_for_powerbi.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from decision_trace.utils.db import get_engine
from decision_trace.utils.logger import get_logger

log = get_logger("export_for_powerbi")

EXPORT_DIR = Path("reports") / "powerbi_export"
EXPORT_DIR.mkdir(parents=True, exist_ok=True)


EXPORTS = {
    "daily_revenue":           "SELECT * FROM v_daily_revenue ORDER BY order_day",
    "payment_method_summary":  "SELECT * FROM v_payment_method_summary",
    "reconciliation_overview": "SELECT * FROM v_reconciliation_overview",
    "quality_summary":         "SELECT * FROM v_quality_summary",
    "latest_kpi":              "SELECT * FROM v_latest_kpi ORDER BY kpi_name, period_start",
    "kpi_snapshots":           "SELECT * FROM kpi_snapshots ORDER BY kpi_name, period_start, version",
    "open_quality_issues":     "SELECT * FROM data_quality_issues WHERE is_resolved = FALSE ORDER BY severity, source_table",
    "reconciliation_results":  "SELECT * FROM reconciliation_results ORDER BY reconciled_at DESC",
    "correction_events":       "SELECT * FROM correction_events ORDER BY event_at DESC",
}


def export() -> None:
    engine = get_engine()
    for name, sql in EXPORTS.items():
        try:
            df = pd.read_sql(sql, engine)
            path = EXPORT_DIR / f"{name}.csv"
            df.to_csv(path, index=False)
            log.info("Exported %s → %d rows → %s", name, len(df), path)
        except Exception as exc:
            log.warning("Export '%s' failed: %s", name, exc)

    log.info("Power BI export complete. Files in %s", EXPORT_DIR.resolve())


if __name__ == "__main__":
    export()

# Power BI Connection Guide

## Connecting Power BI to PostgreSQL

1. **Install** the PostgreSQL ODBC driver if prompted.
2. In Power BI Desktop: **Get Data → PostgreSQL database**.
3. Enter:
   - **Server:** `localhost` (or Docker host IP)
   - **Database:** `decisiontrace`
4. Use credentials from your `.env` file.

---

## Recommended Dataset Import Order

Import each view/table as a separate query:

| Query Name | Source |
|---|---|
| DailyRevenue | `v_daily_revenue` |
| PaymentMethodSummary | `v_payment_method_summary` |
| ReconciliationOverview | `v_reconciliation_overview` |
| QualitySummary | `v_quality_summary` |
| LatestKPI | `v_latest_kpi` |
| KpiSnapshots | `kpi_snapshots` |
| OpenQualityIssues | `data_quality_issues WHERE is_resolved = FALSE` |
| ReconciliationResults | `reconciliation_results` |
| CorrectionEvents | `correction_events` |

Alternatively, run `python scripts/export_for_powerbi.py` and import the CSV files
from `reports/powerbi_export/`.

---

## Suggested Dashboard Pages

### Page 1 — Executive Overview
- Card: Total orders (DailyRevenue[total_orders])
- Card: Reconciled net revenue (DailyRevenue[net_revenue])
- Card: Payment success rate (PaymentMethodSummary)
- Card: Total refunds (DailyRevenue[total_refunds])
- Bar chart: Revenue by day (DailyRevenue)

### Page 2 — Data Reliability
- Gauge: Overall reliability score (from pipeline run report)
- Table: Open quality issues by dimension and severity (OpenQualityIssues)
- Donut: Issues by dimension
- Bar: Duplicate count by source table

### Page 3 — Financial Reconciliation
- Stacked bar: Matched / Partial / Unmatched by reconciliation type (ReconciliationOverview)
- Table: Unmatched transactions with differences (ReconciliationResults WHERE status ≠ 'matched')
- Line: Discrepancy trend over time

### Page 4 — Root-Cause Explorer
- Matrix: Issues by category and severity
- Table: Affected transactions with financial exposure
- Bar: Violations by source table

### Page 5 — Decision Replay
- Slicer: KPI name, period
- Two KPI cards: Original value vs corrected value
- Calculated measure: Difference = [Corrected] − [Original]
- Table: Correction events timeline (CorrectionEvents)
- Line chart: KPI version history (KpiSnapshots filtered by selected KPI)

---

## Decision Replay Measure Example (DAX)

```dax
KPI Difference =
VAR OriginalValue =
    CALCULATE(
        MAX(KpiSnapshots[kpi_value]),
        KpiSnapshots[version] = 1
    )
VAR LatestValue =
    CALCULATE(
        MAX(KpiSnapshots[kpi_value]),
        KpiSnapshots[is_corrected] = TRUE
    )
RETURN LatestValue - OriginalValue
```

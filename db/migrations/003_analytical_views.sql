-- =============================================================================
-- Migration 003 — Analytical views
-- =============================================================================

-- -------------------------------------------------------------------------
-- Revenue summary per day (excluding duplicates)
-- -------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_daily_revenue AS
SELECT
    DATE_TRUNC('day', o.order_date)::DATE AS order_day,
    COUNT(DISTINCT o.order_id)             AS total_orders,
    SUM(o.total_amount)                    AS gross_revenue,
    COALESCE(SUM(r.amount), 0)             AS total_refunds,
    SUM(o.total_amount) - COALESCE(SUM(r.amount), 0) AS net_revenue
FROM orders o
LEFT JOIN payments  p ON p.order_id    = o.order_id  AND p.is_duplicate = FALSE
LEFT JOIN refunds   r ON r.order_id    = o.order_id  AND r.status       = 'processed'
WHERE o.is_duplicate = FALSE
GROUP BY DATE_TRUNC('day', o.order_date);


-- -------------------------------------------------------------------------
-- Payment method breakdown
-- -------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_payment_method_summary AS
SELECT
    p.method,
    COUNT(*)                              AS payment_count,
    SUM(p.amount)                         AS total_amount,
    SUM(CASE WHEN p.status = 'success' THEN 1 ELSE 0 END)  AS success_count,
    SUM(CASE WHEN p.status = 'failed'  THEN 1 ELSE 0 END)  AS failure_count,
    ROUND(
        100.0 * SUM(CASE WHEN p.status = 'success' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0),
        2
    ) AS success_rate_pct
FROM payments p
WHERE p.is_duplicate = FALSE
GROUP BY p.method;


-- -------------------------------------------------------------------------
-- Reconciliation status overview
-- -------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_reconciliation_overview AS
SELECT
    reconciliation_type,
    status,
    COUNT(*)                   AS record_count,
    SUM(ABS(difference))       AS total_difference,
    AVG(ABS(difference))       AS avg_difference
FROM reconciliation_results
GROUP BY reconciliation_type, status;


-- -------------------------------------------------------------------------
-- Data quality issue summary
-- -------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_quality_summary AS
SELECT
    source_table,
    dimension,
    severity,
    COUNT(*)                                              AS issue_count,
    SUM(CASE WHEN is_resolved THEN 1 ELSE 0 END)         AS resolved_count,
    SUM(CASE WHEN NOT is_resolved THEN 1 ELSE 0 END)     AS open_count
FROM data_quality_issues
GROUP BY source_table, dimension, severity;


-- -------------------------------------------------------------------------
-- Latest KPI snapshot per name (for Decision Replay base)
-- -------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_latest_kpi AS
SELECT DISTINCT ON (kpi_name, period_start, period_end)
    kpi_name,
    period_start,
    period_end,
    kpi_value,
    snapshot_at,
    version,
    is_corrected,
    correction_reason
FROM kpi_snapshots
ORDER BY kpi_name, period_start, period_end, version DESC;

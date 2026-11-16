"""
DecisionTrace AI — Web Dashboard
FastAPI app serving 5 dashboard pages on localhost:8000
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text

from decision_trace.utils.db import get_session

app = FastAPI(title="DecisionTrace AI")

BASE = Path(__file__).parent
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")


def q(sql: str, params: dict | None = None):
    with get_session() as s:
        return s.execute(text(sql), params or {}).fetchall()


def q1(sql: str, params: dict | None = None):
    with get_session() as s:
        r = s.execute(text(sql), params or {}).fetchone()
        return r[0] if r else 0


# ------------------------------------------------------------------ #
# Home — redirect to overview
# ------------------------------------------------------------------ #
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("layout.html", {
        "request": request, "page": "overview",
        "data": await _overview_data()
    })


# ------------------------------------------------------------------ #
# Page 1 — Executive Overview
# ------------------------------------------------------------------ #
async def _overview_data():
    total_orders   = q1("SELECT COUNT(*) FROM orders WHERE is_duplicate=FALSE")
    gross_revenue  = q1("SELECT COALESCE(SUM(total_amount),0) FROM orders WHERE is_duplicate=FALSE")
    net_revenue    = q1("""
        SELECT COALESCE(SUM(o.total_amount),0) - COALESCE(SUM(r.amount) FILTER(WHERE r.status='processed'),0)
        FROM orders o LEFT JOIN refunds r ON r.order_id=o.order_id
        WHERE o.is_duplicate=FALSE""")
    success_rate   = q1("""
        SELECT ROUND(100.0*SUM(CASE WHEN status='success' THEN 1 ELSE 0 END)/NULLIF(COUNT(*),0),1)
        FROM payments WHERE is_duplicate=FALSE""")
    total_refunds  = q1("SELECT COALESCE(SUM(amount),0) FROM refunds WHERE status='processed'")
    dup_payments   = q1("SELECT COUNT(*) FROM payments WHERE is_duplicate=TRUE")
    unmatched      = q1("SELECT COUNT(*) FROM reconciliation_results WHERE status='unmatched'")
    daily          = q("SELECT order_day, total_orders, net_revenue FROM v_daily_revenue ORDER BY order_day DESC LIMIT 30")
    methods        = q("SELECT method, success_count, failure_count, success_rate_pct FROM v_payment_method_summary ORDER BY method")
    return {
        "total_orders": total_orders,
        "gross_revenue": float(gross_revenue),
        "net_revenue": float(net_revenue),
        "success_rate": float(success_rate or 0),
        "total_refunds": float(total_refunds),
        "dup_payments": dup_payments,
        "unmatched": unmatched,
        "daily": [{"day": str(r.order_day), "orders": r.total_orders, "revenue": float(r.net_revenue)} for r in daily],
        "methods": [{"method": r.method, "success": r.success_count, "failure": r.failure_count, "rate": float(r.success_rate_pct or 0)} for r in methods],
    }


@app.get("/overview", response_class=HTMLResponse)
async def overview(request: Request):
    return templates.TemplateResponse("layout.html", {
        "request": request, "page": "overview", "data": await _overview_data()
    })


# ------------------------------------------------------------------ #
# Page 2 — Data Reliability
# ------------------------------------------------------------------ #
@app.get("/quality", response_class=HTMLResponse)
async def quality(request: Request):
    score     = 58.25
    summary   = q("SELECT source_table, dimension, severity, issue_count, open_count FROM v_quality_summary ORDER BY severity, source_table")
    issues    = q("""SELECT source_table, rule_name, severity, description, COUNT(*) as cnt
                     FROM data_quality_issues WHERE is_resolved=FALSE
                     GROUP BY source_table, rule_name, severity, description
                     ORDER BY CASE severity WHEN 'critical' THEN 1 WHEN 'warning' THEN 2 ELSE 3 END, cnt DESC
                     LIMIT 50""")
    total     = q1("SELECT COUNT(*) FROM data_quality_issues WHERE is_resolved=FALSE")
    critical  = q1("SELECT COUNT(*) FROM data_quality_issues WHERE severity='critical' AND is_resolved=FALSE")
    return templates.TemplateResponse("layout.html", {
        "request": request, "page": "quality",
        "data": {
            "score": score,
            "total": total,
            "critical": critical,
            "summary": [{"table": r.source_table, "dimension": r.dimension, "severity": r.severity,
                          "count": r.issue_count, "open": r.open_count} for r in summary],
            "issues": [{"table": r.source_table, "rule": r.rule_name, "severity": r.severity,
                         "desc": r.description, "count": r.cnt} for r in issues],
        }
    })


# ------------------------------------------------------------------ #
# Page 3 — Financial Reconciliation
# ------------------------------------------------------------------ #
@app.get("/reconciliation", response_class=HTMLResponse)
async def reconciliation(request: Request):
    overview  = q("SELECT reconciliation_type, status, record_count, total_difference FROM v_reconciliation_overview ORDER BY reconciliation_type, status")
    unmatched = q("""SELECT reference_id, reconciliation_type, expected_amount, actual_amount, difference
                     FROM reconciliation_results WHERE status='unmatched'
                     ORDER BY ABS(difference) DESC LIMIT 50""")
    order_gap = q1("SELECT COALESCE(SUM(ABS(difference)),0) FROM reconciliation_results WHERE reconciliation_type='order_payment' AND status='unmatched'")
    sett_gap  = q1("SELECT COALESCE(SUM(ABS(difference)),0) FROM reconciliation_results WHERE reconciliation_type='payment_settlement' AND status='unmatched'")
    accuracy  = q1("SELECT ROUND(100.0*SUM(CASE WHEN status='matched' THEN 1 ELSE 0 END)/NULLIF(COUNT(*),0),1) FROM reconciliation_results")
    return templates.TemplateResponse("layout.html", {
        "request": request, "page": "reconciliation",
        "data": {
            "order_gap": float(order_gap),
            "sett_gap": float(sett_gap),
            "accuracy": float(accuracy or 0),
            "overview": [{"type": r.reconciliation_type, "status": r.status,
                           "count": r.record_count, "diff": float(r.total_difference or 0)} for r in overview],
            "unmatched": [{"id": r.reference_id, "type": r.reconciliation_type,
                            "expected": float(r.expected_amount or 0), "actual": float(r.actual_amount or 0),
                            "diff": float(r.difference or 0)} for r in unmatched],
        }
    })


# ------------------------------------------------------------------ #
# Page 4 — Root Cause Explorer
# ------------------------------------------------------------------ #
@app.get("/rootcause", response_class=HTMLResponse)
async def rootcause(request: Request):
    by_rule   = q("""SELECT rule_name, source_table, severity, COUNT(*) as cnt
                     FROM data_quality_issues WHERE is_resolved=FALSE
                     GROUP BY rule_name, source_table, severity
                     ORDER BY cnt DESC LIMIT 20""")
    by_table  = q("""SELECT source_table,
                            SUM(CASE WHEN severity='critical' THEN 1 ELSE 0 END) as critical,
                            SUM(CASE WHEN severity='warning'  THEN 1 ELSE 0 END) as warning,
                            SUM(CASE WHEN severity='info'     THEN 1 ELSE 0 END) as info
                     FROM data_quality_issues WHERE is_resolved=FALSE
                     GROUP BY source_table ORDER BY critical DESC""")
    dup_exposure = q1("SELECT COALESCE(SUM(amount),0) FROM payments WHERE is_duplicate=TRUE")
    missing_pay  = q1("SELECT COALESCE(SUM(expected_amount),0) FROM reconciliation_results WHERE reconciliation_type='order_payment' AND status='unmatched'")
    return templates.TemplateResponse("layout.html", {
        "request": request, "page": "rootcause",
        "data": {
            "dup_exposure": float(dup_exposure),
            "missing_pay": float(missing_pay),
            "by_rule": [{"rule": r.rule_name, "table": r.source_table,
                          "severity": r.severity, "count": r.cnt} for r in by_rule],
            "by_table": [{"table": r.source_table, "critical": r.critical,
                           "warning": r.warning, "info": r.info} for r in by_table],
        }
    })


# ------------------------------------------------------------------ #
# Page 5 — Decision Replay
# ------------------------------------------------------------------ #
@app.get("/replay", response_class=HTMLResponse)
async def replay(request: Request):
    kpis = q("""
        SELECT kpi_name,
               MIN(kpi_value) FILTER (WHERE version=1)          AS v1,
               MAX(kpi_value) FILTER (WHERE is_corrected=TRUE)  AS v2,
               MAX(kpi_value) FILTER (WHERE is_corrected=TRUE)
                   - MIN(kpi_value) FILTER (WHERE version=1)    AS delta,
               ROUND(100.0*(
                   MAX(kpi_value) FILTER (WHERE is_corrected=TRUE)
                   - MIN(kpi_value) FILTER (WHERE version=1)
               ) / NULLIF(MIN(kpi_value) FILTER (WHERE version=1),0), 2) AS pct
        FROM kpi_snapshots
        GROUP BY kpi_name
        ORDER BY kpi_name
    """)
    events = q("""SELECT event_at, affected_table, correction_type, description
                  FROM correction_events ORDER BY event_at LIMIT 20""")
    snapshots = q("""SELECT kpi_name, version, kpi_value, is_corrected, snapshot_at
                     FROM kpi_snapshots ORDER BY kpi_name, version""")
    return templates.TemplateResponse("layout.html", {
        "request": request, "page": "replay",
        "data": {
            "kpis": [{"name": r.kpi_name, "v1": float(r.v1 or 0), "v2": float(r.v2 or 0),
                       "delta": float(r.delta or 0), "pct": float(r.pct or 0)} for r in kpis],
            "events": [{"at": str(r.event_at)[:19], "table": r.affected_table,
                         "type": r.correction_type, "desc": r.description} for r in events],
            "snapshots": [{"name": r.kpi_name, "version": r.version,
                            "value": float(r.kpi_value), "corrected": r.is_corrected} for r in snapshots],
        }
    })

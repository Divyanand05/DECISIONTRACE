"""
Full DecisionTrace AI pipeline.

Runs as a plain Python script by default.
If Prefect is installed, decorators are applied for orchestration.
If not, they are no-ops so the pipeline runs without Prefect.

Usage:
    python pipelines/full_pipeline.py
    python pipelines/full_pipeline.py --start 2026-10-01 --end 2026-10-31
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

# ------------------------------------------------------------------ #
# Optional Prefect integration — degrade gracefully if not installed
# ------------------------------------------------------------------ #
try:
    from prefect import flow, task
    from prefect import get_run_logger as _prefect_logger

    def get_run_logger():
        try:
            return _prefect_logger()
        except Exception:
            import logging
            return logging.getLogger("pipeline")

    PREFECT_AVAILABLE = True
except ModuleNotFoundError:
    import logging
    import functools

    PREFECT_AVAILABLE = False

    def get_run_logger():
        return logging.getLogger("pipeline")

    # No-op decorators when Prefect is absent
    def task(**kwargs):
        def decorator(fn):
            @functools.wraps(fn)
            def wrapper(*a, **kw):
                return fn(*a, **kw)
            return wrapper
        return decorator

    def flow(**kwargs):
        def decorator(fn):
            @functools.wraps(fn)
            def wrapper(*a, **kw):
                return fn(*a, **kw)
            return wrapper
        return decorator


# ------------------------------------------------------------------ #
# Project imports
# ------------------------------------------------------------------ #
from decision_trace.ingestion.pipeline import run_ingestion
from decision_trace.quality.engine import run_quality_checks
from decision_trace.reconciliation.engine import run_reconciliation
from decision_trace.root_cause.analyzer import run_root_cause_analysis
from decision_trace.replay.engine import snapshot_kpis
from decision_trace.insights.generator import generate_insights
from decision_trace.utils.db import test_connection, get_session
from decision_trace.utils.logger import get_logger
from sqlalchemy import text

log = get_logger(__name__)


# ------------------------------------------------------------------ #
# Tasks
# ------------------------------------------------------------------ #

@task(name="check-db-connection")
def check_db() -> bool:
    ok = test_connection()
    if not ok:
        raise RuntimeError("Cannot reach PostgreSQL database.")
    log.info("Database connection verified.")
    return True


@task(name="ingest-raw-data")
def ingest_data(raw_dir: Optional[str] = None) -> list[dict]:
    from pathlib import Path
    summaries = run_ingestion(raw_dir=Path(raw_dir) if raw_dir else None)
    for s in summaries:
        log.info("Ingestion %s: %s", s.get("source"), s.get("status"))
    return summaries


@task(name="run-quality-checks")
def quality_checks() -> dict:
    report = run_quality_checks()
    return {
        "overall_score": report.overall_score,
        "capped": report.capped,
        "failed_rules": report.failed_rule_names,
    }


@task(name="run-reconciliation")
def reconciliation() -> list[dict]:
    summaries = run_reconciliation()
    return [
        {
            "type":             s.reconciliation_type,
            "matched":          s.matched,
            "unmatched":        s.unmatched,
            "partial":          s.partial,
            "total_difference": float(s.total_difference),
        }
        for s in summaries
    ]


@task(name="run-root-cause-analysis")
def root_cause() -> dict:
    report = run_root_cause_analysis()
    return {
        "total_exposure": report.total_exposure,
        "critical_issues": report.critical_count,
        "categories": [i.category for i in report.items],
    }


@task(name="snapshot-kpis")
def kpi_snapshot(
    period_start: datetime,
    period_end: datetime,
    is_corrected: bool = False,
    correction_reason: Optional[str] = None,
) -> list[dict]:
    snaps = snapshot_kpis(
        period_start, period_end,
        is_corrected=is_corrected,
        correction_reason=correction_reason,
    )
    return [
        {"kpi": s["kpi_name"], "value": float(s["value"]), "version": s["version"]}
        for s in snaps
    ]


@task(name="generate-insights")
def insights() -> dict:
    report = generate_insights()
    return {
        "total":          len(report.insights),
        "high_priority":  len(report.high_priority()),
        "titles":         [i.title for i in report.insights],
    }


@task(name="record-correction-events")
def record_corrections(simulated: bool) -> int:
    """Write correction_events rows from the fault manifest (simulated run only)."""
    if not simulated:
        return 0
    from pathlib import Path
    from config.settings import settings
    manifest = Path(settings.simulated_data_dir) / "fault_manifest.txt"
    if not manifest.exists():
        return 0

    lines = [l.strip() for l in manifest.read_text().splitlines() if l.strip()]
    now = datetime.now(tz=timezone.utc)
    count = 0
    with get_session() as session:
        for line in lines:
            session.execute(
                text("""
                    INSERT INTO correction_events
                        (event_at, affected_table, affected_record_id,
                         correction_type, description, detected_by)
                    VALUES
                        (:ts, 'simulated', :fault_id, 'fault_injection', :desc, 'inject_faults.py')
                """),
                {
                    "ts":       now,
                    "fault_id": line.split(":")[0].strip(),
                    "desc":     line,
                },
            )
            count += 1
    log.info("Recorded %d correction events from fault manifest", count)
    return count


@task(name="write-summary-report")
def write_report(payload: dict) -> str:
    reports_dir = Path("reports")
    reports_dir.mkdir(exist_ok=True)
    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = reports_dir / f"pipeline_run_{ts}.json"
    path.write_text(json.dumps(payload, indent=2, default=str))
    return str(path)


# ------------------------------------------------------------------ #
# Flow / main entry point
# ------------------------------------------------------------------ #

@flow(name="DecisionTrace-Full-Pipeline")
def full_pipeline(
    period_start: Optional[datetime] = None,
    period_end:   Optional[datetime] = None,
    simulated:    bool = False,
) -> dict:
    """
    End-to-end DecisionTrace pipeline.

    Parameters
    ----------
    period_start / period_end:
        Reporting period for KPI snapshots. Defaults to last 30 days.
    simulated:
        If True, ingests from data/simulated/ (fault-injected dataset)
        and marks KPI snapshots as corrected (is_corrected=True, version++)
    """
    now = datetime.now(tz=timezone.utc)
    if period_end is None:
        period_end = now
    if period_start is None:
        period_start = now - timedelta(days=30)

    raw_dir = str(settings.simulated_data_dir) if simulated else None
    correction_reason = (
        "Re-run on fault-injected simulated dataset to demonstrate Decision Replay"
        if simulated else None
    )

    log.info("=" * 60)
    log.info("DecisionTrace pipeline starting")
    log.info("Mode    : %s", "SIMULATED (fault-injected)" if simulated else "NORMAL")
    log.info("Period  : %s → %s", period_start.date(), period_end.date())
    if not PREFECT_AVAILABLE:
        log.info("(running without Prefect — install prefect for orchestration UI)")
    log.info("=" * 60)

    # Stage 1
    check_db()

    # Stage 2
    ingestion_summary = ingest_data(raw_dir=raw_dir)

    # Stage 3 & 4
    quality_result = quality_checks()
    recon_result   = reconciliation()

    # Stage 5
    rca_result = root_cause()

    # Stage 6 — record corrections before snapshotting so they appear in replay
    corrections_count = record_corrections(simulated=simulated)

    # Stage 7 — KPI snapshots (corrected version for simulated run)
    kpi_result = kpi_snapshot(
        period_start, period_end,
        is_corrected=simulated,
        correction_reason=correction_reason,
    )

    # Stage 8
    insights_result = insights()

    # Stage 9
    payload = {
        "run_at":             now.isoformat(),
        "period_start":       period_start.isoformat(),
        "period_end":         period_end.isoformat(),
        "mode":               "simulated" if simulated else "normal",
        "prefect":            PREFECT_AVAILABLE,
        "ingestion":          ingestion_summary,
        "quality":            quality_result,
        "reconciliation":     recon_result,
        "root_cause":         rca_result,
        "correction_events":  corrections_count,
        "kpi_snapshots":      kpi_result,
        "insights":           insights_result,
    }
    report_path = write_report(payload)
    log.info("Pipeline complete. Report written to: %s", report_path)
    return payload


# ------------------------------------------------------------------ #
# CLI
# ------------------------------------------------------------------ #

if __name__ == "__main__":
    import argparse
    from config.settings import settings

    parser = argparse.ArgumentParser(description="Run the DecisionTrace full pipeline.")
    parser.add_argument("--start",     help="Period start date YYYY-MM-DD (default: 30 days ago)")
    parser.add_argument("--end",       help="Period end date   YYYY-MM-DD (default: today)")
    parser.add_argument("--simulated", action="store_true",
                        help="Ingest from data/simulated/ and mark KPIs as corrected (Decision Replay)")
    args = parser.parse_args()

    def _parse(s: str) -> datetime:
        return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)

    p_start = _parse(args.start) if args.start else None
    p_end   = _parse(args.end)   if args.end   else None

    result = full_pipeline(period_start=p_start, period_end=p_end, simulated=args.simulated)
    print("\nPipeline result summary:")
    print(f"  Mode          : {result['mode']}")
    print(f"  Quality score : {result['quality']['overall_score']}")
    print(f"  Insights found: {result['insights']['total']}")
    for r in result["reconciliation"]:
        print(f"  Recon [{r['type']}]: matched={r['matched']} unmatched={r['unmatched']}")
    print("\nKPI Snapshots:")
    for k in result["kpi_snapshots"]:
        print(f"  {k['kpi']:<30} = {k['value']:>15,.2f}  (v{k['version']})")

"""
Show the Decision Replay diff for all KPIs — v1 (original) vs v2 (corrected).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text
from decision_trace.utils.db import get_session

with get_session() as s:
    rows = s.execute(text("""
        SELECT
            kpi_name,
            MAX(kpi_value) FILTER (WHERE version = 1)        AS v1_original,
            MAX(kpi_value) FILTER (WHERE version = 2)        AS v2_corrected,
            MAX(kpi_value) FILTER (WHERE version = 2)
                - MAX(kpi_value) FILTER (WHERE version = 1)  AS difference,
            ROUND(
                100.0 * (
                    MAX(kpi_value) FILTER (WHERE version = 2)
                    - MAX(kpi_value) FILTER (WHERE version = 1)
                ) / NULLIF(MAX(kpi_value) FILTER (WHERE version = 1), 0),
            2) AS pct_change
        FROM kpi_snapshots
        GROUP BY kpi_name
        HAVING MAX(kpi_value) FILTER (WHERE version = 2) IS NOT NULL
        ORDER BY ABS(
            MAX(kpi_value) FILTER (WHERE version = 2)
            - MAX(kpi_value) FILTER (WHERE version = 1)
        ) DESC
    """)).fetchall()

    events = s.execute(text("""
        SELECT fault_id, description
        FROM (
            SELECT affected_record_id AS fault_id, description
            FROM correction_events
            ORDER BY event_at
        ) sub
    """)).fetchall()

print("\n" + "=" * 70)
print("  DECISION REPLAY — KPI v1 (original) vs v2 (corrected/simulated)")
print("=" * 70)
print(f"  {'KPI':<30} {'v1 Original':>18} {'v2 Corrected':>18} {'Difference':>14} {'Change':>8}")
print("  " + "-" * 68)
for r in rows:
    v1  = float(r.v1_original  or 0)
    v2  = float(r.v2_corrected or 0)
    diff = float(r.difference  or 0)
    pct  = float(r.pct_change  or 0)
    arrow = "▲" if diff > 0 else ("▼" if diff < 0 else "─")
    print(f"  {r.kpi_name:<30} {v1:>18,.2f} {v2:>18,.2f} {diff:>14,.2f}  {arrow}{abs(pct):>6.2f}%")

print("\n" + "=" * 70)
print("  CORRECTION EVENTS (fault manifest)")
print("=" * 70)
for e in events:
    print(f"  {e.fault_id:<6}  {e.description}")
print()

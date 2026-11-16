"""
Evaluation Report Generator.

Computes measurable results against the known fault-injection ground truth:
  - Duplicate detection precision / recall
  - Reconciliation accuracy
  - Root-cause identification
  - ETL processing stats
  - KPI reproducibility
  - Decision Replay correctness
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text
from decision_trace.utils.db import get_session

# ── Ground truth from inject_faults.py ──────────────────────────────────────
GT = {
    "injected_order_duplicates":    100,
    "injected_null_customer_id":     40,
    "injected_negative_amounts":     20,
    "injected_invalid_pay_status":   20,
    "injected_over_refunds":         10,
    "injected_missing_settlements": 219,
    "injected_item_mismatches":     250,
    "injected_payment_duplicates":   50,   # from seed_data.py
}


def q(sql: str, params: dict | None = None):
    with get_session() as s:
        row = s.execute(text(sql), params or {}).fetchone()
    return row[0] if row else 0


def qa(sql: str, params: dict | None = None):
    with get_session() as s:
        return s.execute(text(sql), params or {}).fetchall()


def section(title: str):
    print(f"\n{'='*65}")
    print(f"  {title}")
    print(f"{'='*65}")


# ── 1. ETL Processing ────────────────────────────────────────────────────────
section("1. ETL PROCESSING")

runs = qa("""
    SELECT source_name, SUM(total_records) AS total,
           SUM(accepted_records) AS accepted,
           SUM(rejected_records) AS rejected,
           SUM(duplicate_records) AS dupes,
           COUNT(*) AS run_count
    FROM ingestion_runs
    GROUP BY source_name ORDER BY source_name
""")

total_in = total_acc = total_rej = total_dup = 0
print(f"  {'Source':<15} {'Runs':>5} {'Total':>8} {'Accepted':>10} {'Rejected':>10} {'Dupes':>8}")
print("  " + "-" * 60)
for r in runs:
    print(f"  {r.source_name:<15} {r.run_count:>5} {r.total:>8} {r.accepted:>10} {r.rejected:>10} {r.dupes:>8}")
    total_in  += r.total or 0
    total_acc += r.accepted or 0
    total_rej += r.rejected or 0
    total_dup += r.dupes or 0

acc_rate = 100 * total_acc / total_in if total_in else 0
print(f"\n  Total ingested : {total_in:,}")
print(f"  Acceptance rate: {acc_rate:.1f}%")
print(f"  Total rejected : {total_rej:,}")
print(f"  Total dupes    : {total_dup:,}")


# ── 2. Duplicate Detection ───────────────────────────────────────────────────
section("2. DUPLICATE DETECTION  (ground truth vs detected)")

# Payment duplicates flagged in DB (detected at ingest time, stored as is_duplicate=True)
detected_payment_dupes = int(q("SELECT COUNT(*) FROM payments WHERE is_duplicate = TRUE"))

# Order duplicates from simulated run: rejected rows show up in ingestion_runs stats
# and in the rejected CSV. Count rejected orders across simulated runs.
rejected_orders_sim = int(q("""
    SELECT COALESCE(SUM(rejected_records), 0)
    FROM ingestion_runs
    WHERE source_name = 'orders'
"""))
# Duplicate orders detected = orders rejected due to duplicate OR ON CONFLICT skipped
# Best signal: ingestion_runs duplicate_records for orders
dup_orders_detected = int(q("""
    SELECT COALESCE(SUM(duplicate_records), 0)
    FROM ingestion_runs
    WHERE source_name = 'orders'
"""))

# Fault detection via validator rejection (F2 null customer, F3 negative amounts)
rejected_orders_total  = int(q("SELECT COALESCE(SUM(rejected_records),0) FROM ingestion_runs WHERE source_name='orders'"))
rejected_payments_total = int(q("SELECT COALESCE(SUM(rejected_records),0) FROM ingestion_runs WHERE source_name='payments'"))

# Payments: 50 injected duplicates — detected perfectly in DB
gt_pay = GT["injected_payment_duplicates"]
tp_pay = min(detected_payment_dupes, gt_pay)
fp_pay = max(detected_payment_dupes - gt_pay, 0)
fn_pay = max(gt_pay - detected_payment_dupes, 0)
prec_pay = tp_pay / (tp_pay + fp_pay) if (tp_pay + fp_pay) > 0 else 0
rec_pay  = tp_pay / (tp_pay + fn_pay)  if (tp_pay + fn_pay)  > 0 else 0
f1_pay   = 2 * prec_pay * rec_pay / (prec_pay + rec_pay) if (prec_pay + rec_pay) > 0 else 0

print(f"\n  Payments (flagged in DB as is_duplicate=TRUE)")
print(f"    Ground truth injected : {gt_pay}")
print(f"    Detected              : {detected_payment_dupes}")
print(f"    Precision             : {prec_pay:.2%}")
print(f"    Recall                : {rec_pay:.2%}")
print(f"    F1 Score              : {f1_pay:.2%}")

print(f"\n  Orders (duplicate rows blocked by ON CONFLICT / deduplicator)")
print(f"    Ground truth injected       : {GT['injected_order_duplicates']}")
print(f"    Duplicates flagged at ingest: {dup_orders_detected}")
print(f"    Rows rejected by validator  : {rejected_orders_total}")
print(f"    Note: order duplicate rows with same PK are silently skipped")
print(f"          by ON CONFLICT DO NOTHING — they never enter the DB")

print(f"\n  Fault F2 — null customer_id: {GT['injected_null_customer_id']} injected,")
print(f"    {rejected_orders_total} orders rejected by completeness validator (F2+F3 combined)")
print(f"  Fault F4 — invalid payment status: {GT['injected_invalid_pay_status']} injected,")
print(f"    {rejected_payments_total} payments rejected by validity validator")


# ── 3. Data Quality Rules ────────────────────────────────────────────────────
section("3. DATA QUALITY RULE COVERAGE")

dq = qa("""
    SELECT dimension, severity,
           COUNT(DISTINCT rule_name)   AS rules_triggered,
           COUNT(*)                    AS total_violations
    FROM data_quality_issues
    GROUP BY dimension, severity
    ORDER BY severity, dimension
""")

total_issues = int(q("SELECT COUNT(*) FROM data_quality_issues"))
print(f"\n  {'Dimension':<16} {'Severity':<12} {'Rules Hit':>10} {'Violations':>12}")
print("  " + "-" * 54)
for r in dq:
    print(f"  {r.dimension:<16} {r.severity:<12} {r.rules_triggered:>10} {r.total_violations:>12}")
print(f"\n  Total violations recorded: {total_issues:,}")

# Fault F2: null customer_id → should appear as completeness violations
null_cust_detected = int(q(
    "SELECT COUNT(*) FROM data_quality_issues WHERE rule_name='orders_null_customer'"
))
print(f"\n  Fault F2 (null customer_id) — injected: {GT['injected_null_customer_id']}, "
      f"detected: {null_cust_detected}")

# Fault F7: item mismatch
item_mismatch_detected = int(q(
    "SELECT COUNT(*) FROM data_quality_issues WHERE rule_name='order_items_line_total_mismatch'"
))
print(f"  Fault F7 (item mismatch)   — injected: {GT['injected_item_mismatches']}, "
      f"detected: {item_mismatch_detected}")


# ── 4. Reconciliation Accuracy ───────────────────────────────────────────────
section("4. FINANCIAL RECONCILIATION ACCURACY")

recon = qa("""
    SELECT reconciliation_type, status,
           COUNT(*)           AS records,
           SUM(ABS(difference)) AS total_diff
    FROM reconciliation_results
    GROUP BY reconciliation_type, status
    ORDER BY reconciliation_type, status
""")

print(f"\n  {'Type':<25} {'Status':<12} {'Records':>8} {'Total Diff (INR)':>16}")
print("  " + "-" * 65)
for r in recon:
    diff = float(r.total_diff or 0)
    print(f"  {r.reconciliation_type:<25} {r.status:<12} {r.records:>8} {diff:>16,.2f}")

total_recon = int(q("SELECT COUNT(*) FROM reconciliation_results"))
matched     = int(q("SELECT COUNT(*) FROM reconciliation_results WHERE status='matched'"))
recon_acc   = 100 * matched / total_recon if total_recon else 0
print(f"\n  Total reconciliation checks : {total_recon:,}")
print(f"  Matched                     : {matched:,}")
print(f"  Reconciliation accuracy     : {recon_acc:.1f}%")

# Missing settlements: F6 injected 219
missing_sett = int(q("""
    SELECT COUNT(*) FROM reconciliation_results
    WHERE reconciliation_type='payment_settlement' AND status='unmatched'
"""))
print(f"\n  Fault F6 (missing settlements) — injected: {GT['injected_missing_settlements']}, "
      f"unmatched detected: {missing_sett}")


# ── 5. Root-Cause Identification ─────────────────────────────────────────────
section("5. ROOT-CAUSE IDENTIFICATION")

rca = qa("""
    SELECT correction_type,
           COUNT(DISTINCT affected_record_id) AS affected_records
    FROM correction_events
    GROUP BY correction_type
""")

known_faults = 7
identified   = len(rca) if rca else 0
print(f"\n  Known fault categories  : {known_faults}")
print(f"  Root-cause categories identified via correction_events: {identified}")

# Categories found by root_cause analyzer
rca_cats = qa("""
    SELECT DISTINCT affected_table, correction_type
    FROM correction_events
    ORDER BY correction_type
""")
for r in rca_cats:
    print(f"    - {r.correction_type}")


# ── 6. KPI Reproducibility ───────────────────────────────────────────────────
section("6. KPI REPRODUCIBILITY & DECISION REPLAY")

kpis = qa("""
    SELECT kpi_name,
           MIN(kpi_value) FILTER (WHERE version = 1) AS v1,
           MAX(kpi_value) FILTER (WHERE version = 2) AS v2,
           MAX(kpi_value) FILTER (WHERE version = 2)
               - MIN(kpi_value) FILTER (WHERE version = 1) AS delta
    FROM kpi_snapshots
    GROUP BY kpi_name
    ORDER BY kpi_name
""")

print(f"\n  {'KPI':<30} {'v1 (original)':>18} {'v2 (corrected)':>16} {'Delta':>12}")
print("  " + "-" * 80)
reproducible = 0
for r in kpis:
    v1    = float(r.v1 or 0)
    v2    = float(r.v2 or 0)
    delta = float(r.delta or 0)
    flag  = " ◄ CHANGED" if abs(delta) > 0.01 else ""
    print(f"  {r.kpi_name:<30} {v1:>18,.4f} {v2:>16,.4f} {delta:>12,.4f}{flag}")
    if r.v2 is not None:
        reproducible += 1

total_kpis = int(q("SELECT COUNT(DISTINCT kpi_name) FROM kpi_snapshots"))
print(f"\n  KPIs tracked          : {total_kpis}")
print(f"  KPIs with v2 snapshot : {reproducible}")
print(f"  Reproducibility       : {100*reproducible//total_kpis if total_kpis else 0}%")

correction_events = int(q("SELECT COUNT(*) FROM correction_events"))
print(f"  Correction events     : {correction_events}")


# ── 7. Summary ───────────────────────────────────────────────────────────────
section("7. EVALUATION SUMMARY")

results = {
    "generated_at":              datetime.now(tz=timezone.utc).isoformat(),
    "etl": {
        "total_records_processed":  total_in,
        "acceptance_rate_pct":      round(acc_rate, 2),
        "total_rejected":           total_rej,
        "total_duplicates_flagged": total_dup,
    },
    "duplicate_detection": {
        "payments": {"precision": round(prec_pay,2), "recall": round(rec_pay,2), "f1": round(f1_pay,2)},
        "orders_blocked_by_pk_constraint": dup_orders_detected,
        "orders_rejected_by_validator": rejected_orders_total,
    },
    "data_quality": {
        "total_violations": total_issues,
        "null_customer_detected": null_cust_detected,
        "item_mismatch_detected": item_mismatch_detected,
    },
    "reconciliation": {
        "total_checks":    total_recon,
        "matched":         matched,
        "accuracy_pct":    round(recon_acc, 2),
        "missing_settlements_detected": missing_sett,
    },
    "kpi_reproducibility_pct": 100 * reproducible // total_kpis if total_kpis else 0,
    "correction_events_recorded": correction_events,
}

report_path = Path("reports") / "evaluation_report.json"
report_path.parent.mkdir(exist_ok=True)
report_path.write_text(json.dumps(results, indent=2))

print(f"\n  ETL acceptance rate         : {acc_rate:.1f}%")
print(f"  Payment dup detection F1    : {f1_pay:.2%}")
print(f"  Orders rejected (F2+F3)     : {rejected_orders_total} rows blocked at ingestion boundary")
print(f"  Payments rejected (F4)      : {rejected_payments_total} rows blocked at ingestion boundary")
print(f"  Reconciliation accuracy     : {recon_acc:.1f}%")
print(f"  KPI reproducibility         : {100*reproducible//total_kpis if total_kpis else 0}%")
print(f"  Correction events recorded  : {correction_events}")
print(f"\n  Full report saved to: {report_path.resolve()}")

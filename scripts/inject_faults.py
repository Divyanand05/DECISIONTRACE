"""
Fault injector — creates a controlled test copy of each CSV with known errors
written to data/simulated/.

Injected faults (documented for evaluation):
  F1  Duplicate orders (5% of orders injected twice with same order_id)
  F2  Null customer_id on 2% of orders
  F3  Negative total_amount on 1% of orders
  F4  Invalid payment status on 1% of payments
  F5  Refund amount > payment amount on 10 records
  F6  Missing settlements (drop 15% of success payments from settlements)
  F7  Order total ≠ sum of items (5% of orders get a random item price change)

Run:
    python scripts/inject_faults.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import settings

RAW_DIR  = Path(settings.raw_data_dir)
SIM_DIR  = Path(settings.simulated_data_dir)
SIM_DIR.mkdir(parents=True, exist_ok=True)


def inject(seed: int = 99) -> None:
    rng = np.random.default_rng(seed)
    print("Injecting faults into simulated dataset …\n")

    # ------------------------------------------------------------------ #
    # Orders
    # ------------------------------------------------------------------ #
    orders = pd.read_csv(RAW_DIR / "orders.csv")
    n = len(orders)
    fault_log = []

    # F1: Duplicate order_id rows (5%)
    dup_idx = rng.choice(n, size=int(n * 0.05), replace=False)
    dup_rows = orders.iloc[dup_idx].copy()
    orders_faulty = pd.concat([orders, dup_rows], ignore_index=True)
    fault_log.append(f"F1: {len(dup_idx)} duplicate order rows injected")

    # F2: Null customer_id (2%)
    null_idx = rng.choice(len(orders_faulty), size=int(n * 0.02), replace=False)
    orders_faulty.loc[null_idx, "customer_id"] = None
    fault_log.append(f"F2: {len(null_idx)} null customer_id injected")

    # F3: Negative total_amount (1%)
    neg_idx = rng.choice(len(orders_faulty), size=int(n * 0.01), replace=False)
    orders_faulty.loc[neg_idx, "total_amount"] = -orders_faulty.loc[neg_idx, "total_amount"]
    fault_log.append(f"F3: {len(neg_idx)} negative total_amount injected")

    orders_faulty.to_csv(SIM_DIR / "orders.csv", index=False)

    # ------------------------------------------------------------------ #
    # Payments
    # ------------------------------------------------------------------ #
    payments = pd.read_csv(RAW_DIR / "payments.csv")
    np2 = len(payments)

    # F4: Invalid payment status (1%)
    bad_idx = rng.choice(np2, size=int(np2 * 0.01), replace=False)
    payments.loc[bad_idx, "status"] = "INVALID_STATUS"
    fault_log.append(f"F4: {len(bad_idx)} invalid payment status injected")

    payments.to_csv(SIM_DIR / "payments.csv", index=False)

    # ------------------------------------------------------------------ #
    # Refunds
    # ------------------------------------------------------------------ #
    refunds    = pd.read_csv(RAW_DIR / "refunds.csv")
    payments_r = pd.read_csv(RAW_DIR / "payments.csv")

    # F5: Refund amount > payment amount (10 records)
    pmap = payments_r.set_index("payment_id")["amount"].to_dict()
    targets = refunds.sample(n=min(10, len(refunds)), random_state=seed)
    for idx in targets.index:
        pid = refunds.at[idx, "payment_id"]
        if pid in pmap:
            refunds.at[idx, "amount"] = float(pmap[pid]) * 1.5   # 150% of payment
    fault_log.append("F5: 10 over-refund records injected")

    refunds.to_csv(SIM_DIR / "refunds.csv", index=False)

    # ------------------------------------------------------------------ #
    # Settlements
    # ------------------------------------------------------------------ #
    settlements = pd.read_csv(RAW_DIR / "settlements.csv")

    # F6: Drop 15% of settlements
    drop_n = int(len(settlements) * 0.15)
    drop_idx = rng.choice(len(settlements), size=drop_n, replace=False)
    settlements_faulty = settlements.drop(index=drop_idx).reset_index(drop=True)
    fault_log.append(f"F6: {drop_n} settlement rows removed (missing settlements)")

    settlements_faulty.to_csv(SIM_DIR / "settlements.csv", index=False)

    # ------------------------------------------------------------------ #
    # Order items
    # ------------------------------------------------------------------ #
    items = pd.read_csv(RAW_DIR / "order_items.csv")

    # F7: Modify unit_price on 5% of items so line_total ≠ qty × price
    fi_idx = rng.choice(len(items), size=int(len(items) * 0.05), replace=False)
    items.loc[fi_idx, "unit_price"] = items.loc[fi_idx, "unit_price"] * 1.20
    fault_log.append(f"F7: {len(fi_idx)} item unit_price/line_total mismatches injected")

    items.to_csv(SIM_DIR / "order_items.csv", index=False)

    # Pass-through for customers (no faults)
    pd.read_csv(RAW_DIR / "customers.csv").to_csv(SIM_DIR / "customers.csv", index=False)

    # ------------------------------------------------------------------ #
    # Fault manifest
    # ------------------------------------------------------------------ #
    manifest_path = SIM_DIR / "fault_manifest.txt"
    manifest_path.write_text("\n".join(fault_log) + "\n")
    print("\n".join(fault_log))
    print(f"\nFault manifest: {manifest_path.resolve()}")
    print(f"Simulated CSVs written to {SIM_DIR.resolve()}")


if __name__ == "__main__":
    inject()

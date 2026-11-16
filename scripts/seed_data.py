"""
Generate realistic synthetic transaction data and write CSV files
to data/raw/ for ingestion.

Produces:
  - customers.csv        (500 customers)
  - orders.csv           (2 000 orders)
  - order_items.csv      (4 000–8 000 items)
  - payments.csv         (2 000 payments + ~100 duplicate candidates)
  - refunds.csv          (~200 refunds)
  - settlements.csv      (~1 800 settlements)

Run:
    python scripts/seed_data.py
"""
from __future__ import annotations

import random
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pandas as pd
from faker import Faker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import settings

fake = Faker("en_IN")
Faker.seed(42)
random.seed(42)

RAW_DIR = Path(settings.raw_data_dir)
RAW_DIR.mkdir(parents=True, exist_ok=True)

NOW = datetime.now(tz=timezone.utc)


def _rdt(days_ago_max: int = 90) -> datetime:
    return NOW - timedelta(
        days=random.randint(0, days_ago_max),
        hours=random.randint(0, 23),
        minutes=random.randint(0, 59),
    )


# --------------------------------------------------------------------------- #
# Customers
# --------------------------------------------------------------------------- #
def gen_customers(n: int = 500) -> pd.DataFrame:
    rows = []
    for i in range(n):
        rows.append({
            "customer_id": f"CUST{i+1:05d}",
            "name":        fake.name(),
            "email":       fake.email() if random.random() > 0.05 else None,
            "phone":       fake.phone_number()[:20],
            "country":     random.choice(["India", "India", "India", "UAE", "US"]),
            "created_at":  _rdt(365).isoformat(),
            "updated_at":  _rdt(30).isoformat(),
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Orders
# --------------------------------------------------------------------------- #
def gen_orders(customers: pd.DataFrame, n: int = 2000) -> pd.DataFrame:
    cust_ids = customers["customer_id"].tolist()
    statuses = ["confirmed", "delivered", "shipped", "cancelled", "pending"]
    weights  = [0.40, 0.35, 0.10, 0.10, 0.05]
    rows = []
    for i in range(n):
        amt = round(random.uniform(100, 50000), 2)
        rows.append({
            "order_id":     f"ORD{i+1:06d}",
            "customer_id":  random.choice(cust_ids),
            "order_date":   _rdt(90).isoformat(),
            "status":       random.choices(statuses, weights)[0],
            "total_amount": amt,
            "currency":     "INR",
            "source_system": random.choice(["web", "mobile", "pos"]),
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Order items
# --------------------------------------------------------------------------- #
def gen_order_items(orders: pd.DataFrame) -> pd.DataFrame:
    products = [
        ("Wireless Headphones", 1200), ("Smart Watch", 8500), ("USB Hub", 650),
        ("Laptop Stand", 1100), ("Mechanical Keyboard", 3200), ("Webcam", 2200),
        ("Mouse Pad XL", 450), ("Power Bank", 1800), ("Desk Lamp", 900),
        ("Portable Speaker", 2600),
    ]
    rows = []
    item_counter = 1
    for _, order in orders.iterrows():
        n_items = random.randint(1, 4)
        total = 0.0
        for j in range(n_items):
            product, base_price = random.choice(products)
            qty = random.randint(1, 3)
            price = round(base_price * random.uniform(0.9, 1.1), 2)
            line_total = round(qty * price, 2)
            total += line_total
            rows.append({
                "item_id":      f"ITEM{item_counter:07d}",
                "order_id":     order["order_id"],
                "product_name": product,
                "quantity":     qty,
                "unit_price":   price,
                "line_total":   line_total,
            })
            item_counter += 1
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Payments
# --------------------------------------------------------------------------- #
def gen_payments(orders: pd.DataFrame) -> pd.DataFrame:
    methods  = ["card", "upi", "netbanking", "wallet", "cod"]
    mweights = [0.35, 0.30, 0.15, 0.15, 0.05]
    rows = []
    pay_counter = 1
    for _, order in orders.iterrows():
        status = "success"
        if order["status"] == "cancelled":
            status = "failed"
        elif random.random() < 0.08:
            status = "failed"
        elif random.random() < 0.03:
            status = "pending"

        rows.append({
            "payment_id":        f"PAY{pay_counter:06d}",
            "order_id":          order["order_id"],
            "payment_date":      (pd.Timestamp(order["order_date"]) + timedelta(minutes=random.randint(1, 30))).isoformat(),
            "amount":            order["total_amount"],
            "method":            random.choices(methods, mweights)[0],
            "status":            status,
            "gateway_reference": fake.uuid4(),
            "source_system":     "payment_gateway",
        })
        pay_counter += 1

    # Inject ~50 duplicate payments (same order, same amount, different payment_id)
    base_rows = rows.copy()
    for _ in range(50):
        original = random.choice(base_rows)
        dup = original.copy()
        dup["payment_id"] = f"PAY{pay_counter:06d}"
        dup["gateway_reference"] = fake.uuid4()
        rows.append(dup)
        pay_counter += 1

    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Refunds
# --------------------------------------------------------------------------- #
def gen_refunds(payments: pd.DataFrame) -> pd.DataFrame:
    success_pays = payments[payments["status"] == "success"].sample(frac=0.10, random_state=42)
    rows = []
    ref_counter = 1
    for _, pay in success_pays.iterrows():
        reason = random.choice(["customer_request", "defective_product", "wrong_item", "late_delivery"])
        refund_amt = round(float(pay["amount"]) * random.uniform(0.3, 1.0), 2)
        rows.append({
            "refund_id":    f"REF{ref_counter:06d}",
            "payment_id":   pay["payment_id"],
            "order_id":     pay["order_id"],
            "refund_date":  (pd.Timestamp(pay["payment_date"]) + timedelta(days=random.randint(1, 14))).isoformat(),
            "amount":       refund_amt,
            "reason":       reason,
            "status":       random.choice(["processed", "processed", "pending", "rejected"]),
            "source_system": "refund_service",
        })
        ref_counter += 1
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Settlements
# --------------------------------------------------------------------------- #
def gen_settlements(payments: pd.DataFrame) -> pd.DataFrame:
    success_pays = payments[payments["status"] == "success"]
    # ~90% get settled; ~10% are pending/missing (freshness issue)
    settle_pays = success_pays.sample(frac=0.90, random_state=42)
    rows = []
    s_counter = 1
    for _, pay in settle_pays.iterrows():
        fee = round(float(pay["amount"]) * random.uniform(0.005, 0.025), 2)
        rows.append({
            "settlement_id":   f"SET{s_counter:06d}",
            "payment_id":      pay["payment_id"],
            "settled_amount":  round(float(pay["amount"]) - fee, 2),
            "fee":             fee,
            "settlement_date": (pd.Timestamp(pay["payment_date"]) + timedelta(days=random.randint(1, 3))).isoformat(),
            "gateway":         random.choice(["Razorpay", "Stripe", "PayU", "Cashfree"]),
            "status":          random.choice(["settled", "settled", "settled", "pending"]),
            "source_system":   "settlement_system",
        })
        s_counter += 1
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def seed() -> None:
    print("Generating synthetic data …")

    customers  = gen_customers(500)
    orders     = gen_orders(customers, 2000)
    items      = gen_order_items(orders)
    payments   = gen_payments(orders)
    refunds    = gen_refunds(payments)
    settlements = gen_settlements(payments)

    customers.to_csv(RAW_DIR / "customers.csv",   index=False)
    orders.to_csv(RAW_DIR / "orders.csv",         index=False)
    items.to_csv(RAW_DIR / "order_items.csv",     index=False)
    payments.to_csv(RAW_DIR / "payments.csv",     index=False)
    refunds.to_csv(RAW_DIR / "refunds.csv",       index=False)
    settlements.to_csv(RAW_DIR / "settlements.csv", index=False)

    print(f"Customers:    {len(customers):>6}")
    print(f"Orders:       {len(orders):>6}")
    print(f"Order items:  {len(items):>6}")
    print(f"Payments:     {len(payments):>6}  (includes ~50 duplicates)")
    print(f"Refunds:      {len(refunds):>6}")
    print(f"Settlements:  {len(settlements):>6}")
    print(f"CSVs written to {RAW_DIR.resolve()}")


if __name__ == "__main__":
    seed()

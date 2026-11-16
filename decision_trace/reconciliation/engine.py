"""
Financial Reconciliation Engine.

Three reconciliation passes:
  1. Order → Payment  — every confirmed order should have a matching payment.
  2. Payment → Settlement — every successful payment should have a settlement.
  3. Payment → Refund  — refund amounts should not exceed original payments.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

import pandas as pd
from sqlalchemy import text

from decision_trace.utils.db import get_session
from decision_trace.utils.logger import get_logger

log = get_logger(__name__)

TOLERANCE = Decimal("1.00")   # ₹1 rounding tolerance


@dataclass
class ReconciliationSummary:
    reconciliation_type: str
    matched: int
    unmatched: int
    partial: int
    duplicate: int
    total_difference: Decimal


def _persist_result(
    recon_type: str,
    reference_id: str,
    expected: Decimal | None,
    actual: Decimal | None,
    status: str,
    notes: str | None = None,
) -> None:
    diff = None
    if expected is not None and actual is not None:
        diff = actual - expected
    with get_session() as session:
        session.execute(
            text(
                """
                INSERT INTO reconciliation_results
                    (reconciliation_type, reference_id, expected_amount,
                     actual_amount, difference, status, notes)
                VALUES
                    (:rtype, :rid, :exp, :act, :diff, :status, :notes)
                """
            ),
            {
                "rtype":  recon_type,
                "rid":    reference_id,
                "exp":    float(expected) if expected is not None else None,
                "act":    float(actual)   if actual   is not None else None,
                "diff":   float(diff)     if diff     is not None else None,
                "status": status,
                "notes":  notes,
            },
        )


# --------------------------------------------------------------------------- #
# Pass 1: Order → Payment
# --------------------------------------------------------------------------- #

def reconcile_orders_to_payments() -> ReconciliationSummary:
    """
    For each non-duplicate, confirmed/delivered order, check whether total
    successful payments (net of refunds) match the order total.
    """
    sql = """
        SELECT
            o.order_id,
            o.total_amount                                          AS order_total,
            COALESCE(SUM(p.amount) FILTER (
                WHERE p.status = 'success' AND p.is_duplicate = FALSE
            ), 0)                                                   AS paid_amount,
            COALESCE(SUM(r.amount) FILTER (
                WHERE r.status = 'processed'
            ), 0)                                                   AS refunded_amount
        FROM orders o
        LEFT JOIN payments p ON p.order_id = o.order_id
        LEFT JOIN refunds  r ON r.order_id = o.order_id
        WHERE o.is_duplicate = FALSE
          AND o.status IN ('confirmed', 'delivered', 'shipped')
        GROUP BY o.order_id, o.total_amount
    """
    counts = dict(matched=0, unmatched=0, partial=0, duplicate=0)
    total_diff = Decimal("0")

    with get_session() as session:
        rows = session.execute(text(sql)).fetchall()

    for row in rows:
        order_id    = row.order_id
        expected    = Decimal(str(row.order_total))
        paid        = Decimal(str(row.paid_amount))
        refunded    = Decimal(str(row.refunded_amount))
        net_paid    = paid - refunded

        diff = net_paid - expected

        if abs(diff) <= TOLERANCE:
            status = "matched"
            counts["matched"] += 1
        elif net_paid == 0:
            status = "unmatched"
            counts["unmatched"] += 1
        else:
            status = "partial"
            counts["partial"] += 1

        total_diff += abs(diff)
        _persist_result(
            "order_payment",
            order_id,
            expected,
            net_paid,
            status,
            notes=f"paid={paid} refunded={refunded} diff={diff}",
        )

    log.info(
        "order_payment recon: matched=%d unmatched=%d partial=%d",
        counts["matched"], counts["unmatched"], counts["partial"],
    )
    return ReconciliationSummary(
        reconciliation_type="order_payment",
        total_difference=total_diff,
        **counts,
    )


# --------------------------------------------------------------------------- #
# Pass 2: Payment → Settlement
# --------------------------------------------------------------------------- #

def reconcile_payments_to_settlements() -> ReconciliationSummary:
    sql = """
        SELECT
            p.payment_id,
            p.amount                                      AS payment_amount,
            COALESCE(SUM(s.settled_amount), 0)            AS settled_amount,
            COALESCE(SUM(s.fee), 0)                       AS total_fee
        FROM payments p
        LEFT JOIN settlements s ON s.payment_id = p.payment_id
        WHERE p.status = 'success'
          AND p.is_duplicate = FALSE
        GROUP BY p.payment_id, p.amount
    """
    counts = dict(matched=0, unmatched=0, partial=0, duplicate=0)
    total_diff = Decimal("0")

    with get_session() as session:
        rows = session.execute(text(sql)).fetchall()

    for row in rows:
        payment_id = row.payment_id
        expected   = Decimal(str(row.payment_amount))
        settled    = Decimal(str(row.settled_amount))
        fee        = Decimal(str(row.total_fee))
        gross      = settled + fee   # gateway disburses net; gross ≈ original amount

        diff = gross - expected

        if settled == 0:
            status = "unmatched"
            counts["unmatched"] += 1
        elif abs(diff) <= TOLERANCE:
            status = "matched"
            counts["matched"] += 1
        else:
            status = "partial"
            counts["partial"] += 1

        total_diff += abs(diff)
        _persist_result(
            "payment_settlement",
            payment_id,
            expected,
            settled,
            status,
            notes=f"fee={fee} gross={gross} diff={diff}",
        )

    log.info(
        "payment_settlement recon: matched=%d unmatched=%d partial=%d",
        counts["matched"], counts["unmatched"], counts["partial"],
    )
    return ReconciliationSummary(
        reconciliation_type="payment_settlement",
        total_difference=total_diff,
        **counts,
    )


# --------------------------------------------------------------------------- #
# Pass 3: Refund integrity
# --------------------------------------------------------------------------- #

def reconcile_refunds() -> ReconciliationSummary:
    sql = """
        SELECT
            r.payment_id,
            p.amount                                       AS payment_amount,
            SUM(r.amount) FILTER (WHERE r.status = 'processed') AS total_refunded
        FROM refunds r
        JOIN payments p ON p.payment_id = r.payment_id
        GROUP BY r.payment_id, p.amount
    """
    counts = dict(matched=0, unmatched=0, partial=0, duplicate=0)
    total_diff = Decimal("0")

    with get_session() as session:
        rows = session.execute(text(sql)).fetchall()

    for row in rows:
        payment_id    = row.payment_id
        payment_amt   = Decimal(str(row.payment_amount))
        total_refunded = Decimal(str(row.total_refunded or 0))
        diff = total_refunded - payment_amt

        if total_refunded <= payment_amt + TOLERANCE:
            status = "matched"
            counts["matched"] += 1
        else:
            status = "unmatched"   # over-refunded
            counts["unmatched"] += 1

        total_diff += max(diff, Decimal("0"))
        _persist_result(
            "refund_check",
            payment_id,
            payment_amt,
            total_refunded,
            status,
            notes=f"over_refund_by={max(diff, Decimal('0'))}",
        )

    log.info(
        "refund_check recon: matched=%d unmatched=%d",
        counts["matched"], counts["unmatched"],
    )
    return ReconciliationSummary(
        reconciliation_type="refund_check",
        total_difference=total_diff,
        **counts,
    )


def run_reconciliation() -> list[ReconciliationSummary]:
    """Run all three reconciliation passes."""
    return [
        reconcile_orders_to_payments(),
        reconcile_payments_to_settlements(),
        reconcile_refunds(),
    ]

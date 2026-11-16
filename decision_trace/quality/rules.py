"""
Data quality rule definitions.

Each rule is a dataclass describing a check to run against a table.
Actual check execution is in engine.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


Dimension = Literal["completeness", "uniqueness", "freshness", "validity"]
Severity  = Literal["critical", "warning", "info"]


@dataclass
class QualityRule:
    rule_name:   str
    table:       str
    dimension:   Dimension
    severity:    Severity
    description: str
    # SQL fragment returning rows that FAIL the rule (uses {table} placeholder)
    check_sql:   str


RULES: list[QualityRule] = [
    # ------------------------------------------------------------------ #
    # Completeness
    # ------------------------------------------------------------------ #
    QualityRule(
        rule_name="orders_null_customer",
        table="orders",
        dimension="completeness",
        severity="critical",
        description="Orders with no customer_id",
        check_sql="SELECT order_id AS record_id FROM orders WHERE customer_id IS NULL",
    ),
    QualityRule(
        rule_name="orders_null_amount",
        table="orders",
        dimension="completeness",
        severity="critical",
        description="Orders with null total_amount",
        check_sql="SELECT order_id AS record_id FROM orders WHERE total_amount IS NULL",
    ),
    QualityRule(
        rule_name="payments_null_order",
        table="payments",
        dimension="completeness",
        severity="critical",
        description="Payments not linked to any order",
        check_sql="SELECT payment_id AS record_id FROM payments WHERE order_id IS NULL",
    ),
    QualityRule(
        rule_name="customers_null_email",
        table="customers",
        dimension="completeness",
        severity="warning",
        description="Customer records missing email address",
        check_sql="SELECT customer_id AS record_id FROM customers WHERE email IS NULL OR TRIM(email) = ''",
    ),

    # ------------------------------------------------------------------ #
    # Uniqueness
    # ------------------------------------------------------------------ #
    QualityRule(
        rule_name="orders_exact_duplicates",
        table="orders",
        dimension="uniqueness",
        severity="critical",
        description="Orders flagged as exact or near-duplicate records",
        check_sql="SELECT order_id AS record_id FROM orders WHERE is_duplicate = TRUE",
    ),
    QualityRule(
        rule_name="payments_exact_duplicates",
        table="payments",
        dimension="uniqueness",
        severity="critical",
        description="Payments flagged as exact or near-duplicate records",
        check_sql="SELECT payment_id AS record_id FROM payments WHERE is_duplicate = TRUE",
    ),
    QualityRule(
        rule_name="orders_multiple_success_payments",
        table="payments",
        dimension="uniqueness",
        severity="warning",
        description="Orders with more than one successful payment (possible double-capture)",
        check_sql="""
            SELECT order_id AS record_id
            FROM payments
            WHERE status = 'success' AND is_duplicate = FALSE
            GROUP BY order_id
            HAVING COUNT(*) > 1
        """,
    ),

    # ------------------------------------------------------------------ #
    # Freshness
    # ------------------------------------------------------------------ #
    QualityRule(
        rule_name="orders_stale_pending",
        table="orders",
        dimension="freshness",
        severity="warning",
        description="Orders stuck in 'pending' status for more than 48 hours",
        check_sql="""
            SELECT order_id AS record_id
            FROM orders
            WHERE status = 'pending'
              AND order_date < NOW() - INTERVAL '48 hours'
        """,
    ),
    QualityRule(
        rule_name="payments_stale_pending",
        table="payments",
        dimension="freshness",
        severity="warning",
        description="Payments stuck in 'pending' status for more than 24 hours",
        check_sql="""
            SELECT payment_id AS record_id
            FROM payments
            WHERE status = 'pending'
              AND payment_date < NOW() - INTERVAL '24 hours'
        """,
    ),
    QualityRule(
        rule_name="settlements_missing_recent",
        table="settlements",
        dimension="freshness",
        severity="info",
        description="Success payments with no settlement record within 72 hours",
        check_sql="""
            SELECT p.payment_id AS record_id
            FROM payments p
            LEFT JOIN settlements s ON s.payment_id = p.payment_id
            WHERE p.status = 'success'
              AND p.is_duplicate = FALSE
              AND s.settlement_id IS NULL
              AND p.payment_date < NOW() - INTERVAL '72 hours'
        """,
    ),

    # ------------------------------------------------------------------ #
    # Validity
    # ------------------------------------------------------------------ #
    QualityRule(
        rule_name="orders_negative_amount",
        table="orders",
        dimension="validity",
        severity="critical",
        description="Orders with a negative total_amount",
        check_sql="SELECT order_id AS record_id FROM orders WHERE total_amount < 0",
    ),
    QualityRule(
        rule_name="payments_amount_exceeds_order",
        table="payments",
        dimension="validity",
        severity="critical",
        description="Payments whose amount exceeds the linked order total (before refunds)",
        check_sql="""
            SELECT p.payment_id AS record_id
            FROM payments p
            JOIN orders o ON o.order_id = p.order_id
            WHERE p.is_duplicate = FALSE
              AND p.amount > o.total_amount * 1.01   -- 1% tolerance for rounding
        """,
    ),
    QualityRule(
        rule_name="refunds_exceed_payment",
        table="refunds",
        dimension="validity",
        severity="critical",
        description="Refunds whose total amount exceeds the original payment",
        check_sql="""
            SELECT r.refund_id AS record_id
            FROM refunds r
            JOIN (
                SELECT payment_id, SUM(amount) AS total_refunded
                FROM refunds
                WHERE status = 'processed'
                GROUP BY payment_id
            ) agg ON agg.payment_id = r.payment_id
            JOIN payments p ON p.payment_id = r.payment_id
            WHERE agg.total_refunded > p.amount
        """,
    ),
    QualityRule(
        rule_name="order_items_line_total_mismatch",
        table="order_items",
        dimension="validity",
        severity="warning",
        description="Line items where line_total ≠ quantity × unit_price",
        check_sql="""
            SELECT item_id AS record_id
            FROM order_items
            WHERE ABS(line_total - (quantity * unit_price)) > 0.01
        """,
    ),
    QualityRule(
        rule_name="order_total_vs_items_sum",
        table="orders",
        dimension="validity",
        severity="warning",
        description="Orders where total_amount doesn't match the sum of line items",
        check_sql="""
            SELECT o.order_id AS record_id
            FROM orders o
            JOIN (
                SELECT order_id, SUM(line_total) AS items_total
                FROM order_items
                GROUP BY order_id
            ) agg ON agg.order_id = o.order_id
            WHERE ABS(o.total_amount - agg.items_total) > 1.00
        """,
    ),
]

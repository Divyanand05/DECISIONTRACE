"""
Core ORM models mirroring the PostgreSQL schema.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from decision_trace.models.base import Base


# --------------------------------------------------------------------------- #
# Dimension tables
# --------------------------------------------------------------------------- #

class Customer(Base):
    __tablename__ = "customers"

    customer_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(50))
    country: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    orders: Mapped[list["Order"]] = relationship(back_populates="customer")


# --------------------------------------------------------------------------- #
# Fact tables
# --------------------------------------------------------------------------- #

class Order(Base):
    __tablename__ = "orders"

    order_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    customer_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("customers.customer_id"), index=True
    )
    order_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(50))          # pending | confirmed | shipped | delivered | cancelled
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    source_system: Mapped[str | None] = mapped_column(String(100))
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False)

    customer: Mapped["Customer"] = relationship(back_populates="orders")
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order")
    payments: Mapped[list["Payment"]] = relationship(back_populates="order")


class OrderItem(Base):
    __tablename__ = "order_items"

    item_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    order_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("orders.order_id"), index=True
    )
    product_name: Mapped[str] = mapped_column(String(255))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    line_total: Mapped[Decimal] = mapped_column(Numeric(18, 2))

    order: Mapped["Order"] = relationship(back_populates="items")


class Payment(Base):
    __tablename__ = "payments"

    payment_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    order_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("orders.order_id"), index=True
    )
    payment_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    method: Mapped[str] = mapped_column(String(50))          # card | upi | netbanking | wallet | cod
    status: Mapped[str] = mapped_column(String(50))          # success | failed | pending | refunded
    gateway_reference: Mapped[str | None] = mapped_column(String(255))
    source_system: Mapped[str | None] = mapped_column(String(100))
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False)

    order: Mapped["Order"] = relationship(back_populates="payments")
    refunds: Mapped[list["Refund"]] = relationship(back_populates="payment")


class Refund(Base):
    __tablename__ = "refunds"

    refund_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    payment_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("payments.payment_id"), index=True
    )
    order_id: Mapped[str] = mapped_column(String(50), index=True)
    refund_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50))          # pending | processed | rejected
    source_system: Mapped[str | None] = mapped_column(String(100))
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    payment: Mapped["Payment"] = relationship(back_populates="refunds")


class Settlement(Base):
    __tablename__ = "settlements"

    settlement_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    payment_id: Mapped[str] = mapped_column(String(50), index=True)
    settled_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    fee: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    settlement_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    gateway: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(50))          # settled | pending | failed
    source_system: Mapped[str | None] = mapped_column(String(100))
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# --------------------------------------------------------------------------- #
# Operational / audit tables
# --------------------------------------------------------------------------- #

class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    run_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    source_name: Mapped[str] = mapped_column(String(100))
    source_file: Mapped[str | None] = mapped_column(Text)
    total_records: Mapped[int] = mapped_column(Integer, default=0)
    accepted_records: Mapped[int] = mapped_column(Integer, default=0)
    rejected_records: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_records: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(50))          # success | partial | failed
    error_message: Mapped[str | None] = mapped_column(Text)


class DataQualityIssue(Base):
    __tablename__ = "data_quality_issues"

    issue_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    source_table: Mapped[str] = mapped_column(String(100))
    record_id: Mapped[str | None] = mapped_column(String(255))
    dimension: Mapped[str] = mapped_column(String(50))       # completeness | uniqueness | freshness | validity
    rule_name: Mapped[str] = mapped_column(String(255))
    severity: Mapped[str] = mapped_column(String(20))        # critical | warning | info
    description: Mapped[str] = mapped_column(Text)
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReconciliationResult(Base):
    __tablename__ = "reconciliation_results"

    result_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    reconciled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    reconciliation_type: Mapped[str] = mapped_column(String(100))  # order_payment | payment_settlement | refund_check
    reference_id: Mapped[str] = mapped_column(String(255))
    expected_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    actual_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    difference: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    status: Mapped[str] = mapped_column(String(50))          # matched | unmatched | partial | duplicate
    notes: Mapped[str | None] = mapped_column(Text)


class KpiSnapshot(Base):
    __tablename__ = "kpi_snapshots"

    snapshot_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    kpi_name: Mapped[str] = mapped_column(String(255))
    kpi_value: Mapped[Decimal] = mapped_column(Numeric(28, 4))
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_corrected: Mapped[bool] = mapped_column(Boolean, default=False)
    correction_reason: Mapped[str | None] = mapped_column(Text)
    pipeline_run_id: Mapped[int | None] = mapped_column(BigInteger)


class CorrectionEvent(Base):
    __tablename__ = "correction_events"

    event_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    affected_table: Mapped[str] = mapped_column(String(100))
    affected_record_id: Mapped[str] = mapped_column(String(255))
    correction_type: Mapped[str] = mapped_column(String(100))  # late_arrival | duplicate_removal | amount_fix | status_fix
    before_value: Mapped[str | None] = mapped_column(Text)
    after_value: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    detected_by: Mapped[str | None] = mapped_column(String(100))

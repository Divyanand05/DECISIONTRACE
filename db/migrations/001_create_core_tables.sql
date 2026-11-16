-- =============================================================================
-- Migration 001 — Core tables
-- =============================================================================

-- -------------------------------------------------------------------------
-- Customers
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS customers (
    customer_id  VARCHAR(50)  PRIMARY KEY,
    name         VARCHAR(255) NOT NULL,
    email        VARCHAR(255),
    phone        VARCHAR(50),
    country      VARCHAR(100),
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_customers_email ON customers (email);

-- -------------------------------------------------------------------------
-- Orders
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS orders (
    order_id      VARCHAR(50)    PRIMARY KEY,
    customer_id   VARCHAR(50)    NOT NULL REFERENCES customers (customer_id),
    order_date    TIMESTAMPTZ    NOT NULL,
    status        VARCHAR(50)    NOT NULL,
    total_amount  NUMERIC(18, 2) NOT NULL,
    currency      VARCHAR(10)    NOT NULL DEFAULT 'INR',
    source_system VARCHAR(100),
    ingested_at   TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    is_duplicate  BOOLEAN        NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_orders_customer    ON orders (customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_date        ON orders (order_date);
CREATE INDEX IF NOT EXISTS idx_orders_status      ON orders (status);
CREATE INDEX IF NOT EXISTS idx_orders_duplicate   ON orders (is_duplicate) WHERE is_duplicate = TRUE;

-- -------------------------------------------------------------------------
-- Order items
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS order_items (
    item_id      VARCHAR(50)    PRIMARY KEY,
    order_id     VARCHAR(50)    NOT NULL REFERENCES orders (order_id),
    product_name VARCHAR(255)   NOT NULL,
    quantity     INTEGER        NOT NULL CHECK (quantity > 0),
    unit_price   NUMERIC(18, 2) NOT NULL CHECK (unit_price >= 0),
    line_total   NUMERIC(18, 2) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items (order_id);

-- -------------------------------------------------------------------------
-- Payments
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS payments (
    payment_id        VARCHAR(50)    PRIMARY KEY,
    order_id          VARCHAR(50)    NOT NULL REFERENCES orders (order_id),
    payment_date      TIMESTAMPTZ    NOT NULL,
    amount            NUMERIC(18, 2) NOT NULL,
    method            VARCHAR(50)    NOT NULL,
    status            VARCHAR(50)    NOT NULL,
    gateway_reference VARCHAR(255),
    source_system     VARCHAR(100),
    ingested_at       TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    is_duplicate      BOOLEAN        NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_payments_order     ON payments (order_id);
CREATE INDEX IF NOT EXISTS idx_payments_date      ON payments (payment_date);
CREATE INDEX IF NOT EXISTS idx_payments_status    ON payments (status);
CREATE INDEX IF NOT EXISTS idx_payments_method    ON payments (method);
CREATE INDEX IF NOT EXISTS idx_payments_duplicate ON payments (is_duplicate) WHERE is_duplicate = TRUE;

-- -------------------------------------------------------------------------
-- Refunds
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS refunds (
    refund_id     VARCHAR(50)    PRIMARY KEY,
    payment_id    VARCHAR(50)    NOT NULL REFERENCES payments (payment_id),
    order_id      VARCHAR(50)    NOT NULL,
    refund_date   TIMESTAMPTZ    NOT NULL,
    amount        NUMERIC(18, 2) NOT NULL,
    reason        TEXT,
    status        VARCHAR(50)    NOT NULL,
    source_system VARCHAR(100),
    ingested_at   TIMESTAMPTZ    NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_refunds_payment ON refunds (payment_id);
CREATE INDEX IF NOT EXISTS idx_refunds_order   ON refunds (order_id);
CREATE INDEX IF NOT EXISTS idx_refunds_date    ON refunds (refund_date);

-- -------------------------------------------------------------------------
-- Settlements
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS settlements (
    settlement_id   VARCHAR(50)    PRIMARY KEY,
    payment_id      VARCHAR(50)    NOT NULL,
    settled_amount  NUMERIC(18, 2) NOT NULL,
    fee             NUMERIC(18, 2) NOT NULL DEFAULT 0,
    settlement_date TIMESTAMPTZ    NOT NULL,
    gateway         VARCHAR(100),
    status          VARCHAR(50)    NOT NULL,
    source_system   VARCHAR(100),
    ingested_at     TIMESTAMPTZ    NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_settlements_payment ON settlements (payment_id);
CREATE INDEX IF NOT EXISTS idx_settlements_date    ON settlements (settlement_date);

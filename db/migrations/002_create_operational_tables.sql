-- =============================================================================
-- Migration 002 — Operational / audit tables
-- =============================================================================

-- -------------------------------------------------------------------------
-- ETL execution history
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ingestion_runs (
    run_id           BIGSERIAL    PRIMARY KEY,
    run_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    source_name      VARCHAR(100) NOT NULL,
    source_file      TEXT,
    total_records    INTEGER      NOT NULL DEFAULT 0,
    accepted_records INTEGER      NOT NULL DEFAULT 0,
    rejected_records INTEGER      NOT NULL DEFAULT 0,
    duplicate_records INTEGER     NOT NULL DEFAULT 0,
    status           VARCHAR(50)  NOT NULL,
    error_message    TEXT
);

-- -------------------------------------------------------------------------
-- Data quality issues
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS data_quality_issues (
    issue_id      BIGSERIAL   PRIMARY KEY,
    detected_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_table  VARCHAR(100) NOT NULL,
    record_id     VARCHAR(255),
    dimension     VARCHAR(50)  NOT NULL,   -- completeness | uniqueness | freshness | validity
    rule_name     VARCHAR(255) NOT NULL,
    severity      VARCHAR(20)  NOT NULL,   -- critical | warning | info
    description   TEXT         NOT NULL,
    is_resolved   BOOLEAN      NOT NULL DEFAULT FALSE,
    resolved_at   TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_dqi_source    ON data_quality_issues (source_table);
CREATE INDEX IF NOT EXISTS idx_dqi_dimension ON data_quality_issues (dimension);
CREATE INDEX IF NOT EXISTS idx_dqi_severity  ON data_quality_issues (severity);
CREATE INDEX IF NOT EXISTS idx_dqi_resolved  ON data_quality_issues (is_resolved);

-- -------------------------------------------------------------------------
-- Financial reconciliation results
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reconciliation_results (
    result_id            BIGSERIAL      PRIMARY KEY,
    reconciled_at        TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    reconciliation_type  VARCHAR(100)   NOT NULL,
    reference_id         VARCHAR(255)   NOT NULL,
    expected_amount      NUMERIC(18, 2),
    actual_amount        NUMERIC(18, 2),
    difference           NUMERIC(18, 2),
    status               VARCHAR(50)    NOT NULL,  -- matched | unmatched | partial | duplicate
    notes                TEXT
);

CREATE INDEX IF NOT EXISTS idx_recon_type      ON reconciliation_results (reconciliation_type);
CREATE INDEX IF NOT EXISTS idx_recon_status    ON reconciliation_results (status);
CREATE INDEX IF NOT EXISTS idx_recon_reference ON reconciliation_results (reference_id);

-- -------------------------------------------------------------------------
-- KPI historical snapshots (Decision Replay)
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS kpi_snapshots (
    snapshot_id       BIGSERIAL      PRIMARY KEY,
    snapshot_at       TIMESTAMPTZ    NOT NULL,
    kpi_name          VARCHAR(255)   NOT NULL,
    kpi_value         NUMERIC(28, 4) NOT NULL,
    period_start      TIMESTAMPTZ    NOT NULL,
    period_end        TIMESTAMPTZ    NOT NULL,
    version           INTEGER        NOT NULL DEFAULT 1,
    is_corrected      BOOLEAN        NOT NULL DEFAULT FALSE,
    correction_reason TEXT,
    pipeline_run_id   BIGINT
);

CREATE INDEX IF NOT EXISTS idx_kpi_name       ON kpi_snapshots (kpi_name);
CREATE INDEX IF NOT EXISTS idx_kpi_period     ON kpi_snapshots (period_start, period_end);
CREATE INDEX IF NOT EXISTS idx_kpi_corrected  ON kpi_snapshots (is_corrected);

-- -------------------------------------------------------------------------
-- Correction events
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS correction_events (
    event_id           BIGSERIAL    PRIMARY KEY,
    event_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    affected_table     VARCHAR(100) NOT NULL,
    affected_record_id VARCHAR(255) NOT NULL,
    correction_type    VARCHAR(100) NOT NULL,
    before_value       TEXT,
    after_value        TEXT,
    description        TEXT,
    detected_by        VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS idx_correction_table  ON correction_events (affected_table);
CREATE INDEX IF NOT EXISTS idx_correction_type   ON correction_events (correction_type);
CREATE INDEX IF NOT EXISTS idx_correction_record ON correction_events (affected_record_id);

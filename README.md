# DecisionTrace AI

**An Explainable Business Decision & Data Reliability Intelligence Platform**

DecisionTrace AI detects inconsistencies in business transaction data, reconciles financial records, identifies root causes, and generates explainable business insights. Its flagship **Decision Replay** feature lets you compare historical KPI snapshots with corrected values after late-arriving data or errors are discovered.

---

## Stack

| Layer | Technology |
|---|---|
| Data Processing | Python 3.11, Pandas, SQLAlchemy |
| Database | PostgreSQL 15 |
| Orchestration | Prefect 2 |
| Containerization | Docker / Docker Compose |
| Visualization | Power BI |
| Testing | Pytest |

---

## Project Structure

```
decision/
├── config/                  # Environment and pipeline configuration
├── data/
│   ├── raw/                 # Source CSV files
│   ├── validated/           # Post-validation exports
│   └── simulated/           # Fault-injected test datasets
├── db/
│   ├── migrations/          # Ordered SQL DDL scripts
│   └── seeds/               # Reference and test seed data
├── decision_trace/
│   ├── ingestion/           # ETL — load, clean, validate
│   ├── quality/             # Data quality & reliability scoring
│   ├── reconciliation/      # Financial reconciliation engine
│   ├── root_cause/          # Root-cause investigation
│   ├── replay/              # Decision Replay (KPI versioning)
│   ├── insights/            # Business insights generator
│   ├── models/              # SQLAlchemy ORM models
│   └── utils/               # Shared helpers (DB, logging, config)
├── pipelines/               # Prefect flows
├── scripts/                 # CLI utilities (seed, inject faults, export)
├── tests/
│   ├── unit/
│   └── integration/
├── reports/                 # Generated text / JSON reports
├── powerbi/                 # Power BI dataset connection notes
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

---

## Quick Start

### 1. Prerequisites

- Docker Desktop
- Python 3.11+

### 2. Start the database

```bash
docker-compose up -d postgres
```

### 3. Apply schema

```bash
python scripts/apply_migrations.py
```

### 4. Seed reference data and generate simulated transactions

```bash
python scripts/seed_data.py
python scripts/inject_faults.py
```

### 5. Run the full pipeline

```bash
python pipelines/full_pipeline.py
```

### 6. Run tests

```bash
pytest tests/ -v
```

---

## Modules

| Module | Entry Point |
|---|---|
| ETL Ingestion | `decision_trace/ingestion/pipeline.py` |
| Data Quality | `decision_trace/quality/engine.py` |
| Reconciliation | `decision_trace/reconciliation/engine.py` |
| Root-Cause Analysis | `decision_trace/root_cause/analyzer.py` |
| Decision Replay | `decision_trace/replay/engine.py` |
| Insights | `decision_trace/insights/generator.py` |

---

## Power BI

Connection details and dataset export instructions are in `powerbi/README.md`.

---

## Evaluation Metrics

- Duplicate detection precision / recall
- Reconciliation accuracy
- Root-cause identification accuracy
- ETL processing time
- KPI reproducibility and replay correctness

Actual results are recorded after each pipeline run in `reports/`.

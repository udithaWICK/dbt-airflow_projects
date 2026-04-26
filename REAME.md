# lh-d01 — Analytics Pipeline

A self-contained Airflow + dbt project that moves data from raw sources through
staging to a published mart, with quality gates enforced before any downstream
publish step runs.

---

## DAG purpose

`analytics_pipeline_v1` orchestrates a daily analytics pipeline that:

1. Extracts raw data from source systems
2. Stages and prepares it for transformation
3. Runs dbt models to build the mart layer
4. Validates data quality via dbt tests
5. Publishes the mart only if all tests pass
6. Notifies on success

The DAG runs at **07:00 UTC daily** (`schedule="0 7 * * *"`).

---

## Task flow

```
extract_raw_data
      │
      ▼
  stage_data
      │
      ▼
dbt_run_models          ← builds staging + mart models
      │
      ▼
dbt_test_models         ← quality gate (blocks publish on failure)
      │
      ▼
 publish_mart
      │
      ▼
notify_status
```

---

## Why dbt_test is separate and blocks publish

`dbt_run_models` and `dbt_test_models` are intentionally split into two tasks
rather than using `dbt build` (which combines both).

**Reason:** Airflow task dependencies are the quality gate. If `dbt_test_models`
returns a non-zero exit code (any test failure), Airflow marks it as failed and
`publish_mart` is never triggered. This means:

- Bad data never reaches downstream consumers
- The failure is visible at the task level in the UI — you can see immediately
  that tests failed, not just that the pipeline failed
- You can rerun `dbt_test_models` in isolation after fixing data without
  re-running the full pipeline
- Retries apply only to the test task, not to the model build

If you used `dbt build`, a single test failure would fail the entire build step
and you'd lose visibility into whether models ran successfully before the failure.

---

## Retry and timeout choices

| Task | Retries | Timeout | Reason |
|---|---|---|---|
| extract_raw_data | 2 | 20 min | Source systems can be flaky — retry before alerting |
| stage_data | 2 | 20 min | Idempotent operation, safe to retry |
| dbt_run_models | 2 | 20 min | Network/warehouse timeouts are transient |
| dbt_test_models | 2 | 20 min | Retry handles transient DB connection issues |
| publish_mart | 2 | 20 min | Publish is idempotent — safe to retry |
| notify_status | 2 | — | Notification retried if endpoint is temporarily down |

`retry_delay` is set to 5 minutes across all tasks to allow transient issues
to resolve before retrying.

`catchup=False` — the DAG will not backfill missed runs if Airflow was down.
`max_active_runs=1` — only one pipeline run at a time, preventing data collisions.

---

## How to trigger a run

**Manual trigger via CLI:**
```bash
airflow dags trigger analytics_pipeline_v1
```

**Check run status:**
```bash
airflow dags list-runs --dag-id analytics_pipeline_v1
```

**Trigger with a specific logical date:**
```bash
airflow dags trigger analytics_pipeline_v1 --logical-date 2026-04-25T07:00:00
```

**Via Airflow UI:**
Navigate to `http://localhost:8080` → DAGs → `analytics_pipeline_v1` → click the
trigger (▶) button.

---

## Project structure

```
lh-d01/
├── dags/
│   └── analytics_pipeline_v1.py
├── dbt/
│   └── lh_analytics/
│       ├── models/
│       │   └── example/
│       ├── tests/
│       ├── macros/
│       ├── seeds/
│       ├── snapshots/
│       └── dbt_project.yml
├── .gitignore
├── README.md
└── RUNBOOK.md
```

---

## Requirements

- Python 3.12+
- Apache Airflow 3.0 (`apache-airflow`)
- dbt-postgres 1.10+ (`dbt-bigquery` for BigQuery target)
- PostgreSQL running locally on port 5432
- venv at `/root/.venv/dbt-airflow`

**Start Airflow:**
```bash
source /root/.venv/dbt-airflow/bin/activate
airflow standalone
```
# RUNBOOK — analytics_pipeline_v1

Operational reference for diagnosing and recovering from pipeline failures.

---

## First 5 checks on failure

When a task turns red, run through these in order before changing anything.

### 1. Read the task logs

The log tells you the exact failure reason — always start here.

```bash
# list recent runs to get the run_id
airflow dags list-runs --dag-id analytics_pipeline_v1

# view logs for the failed task
airflow tasks logs analytics_pipeline_v1 <task_id> <logical_date>
```

In the UI: click the red task → **Log** tab. Look for the last `ERROR` or
`FAIL` line — that is the actual cause, everything above it is context.

---

### 2. Check the database connection

If `dbt_run_models` or `dbt_test_models` failed, verify Postgres is up:

```bash
sudo service postgresql status
```

If stopped:
```bash
sudo service postgresql start
```

Test the dbt connection directly:
```bash
source /root/.venv/dbt-airflow/bin/activate
cd /root/lh-d01/dbt/lh_analytics
dbt debug
```

All checks should pass. If `Connection test` fails, Postgres is the issue.

---

### 3. Check the dbt target and profiles

If dbt commands fail with `profile not found` or `dataset not found`:

```bash
cat ~/.dbt/profiles.yml
```

Verify `lh_analytics` profile exists and points to the correct:
- `host: localhost`
- `dbname: dbt_practice`
- `schema: lh_dev`
- `user: dbt_user`

Run dbt manually to isolate the issue from Airflow:
```bash
cd /root/lh-d01/dbt/lh_analytics
dbt run --profiles-dir /root/.dbt
dbt test --profiles-dir /root/.dbt
```

If this passes but Airflow fails, the issue is the bash_command path or venv
activation in the DAG, not dbt itself.

---

### 4. Check upstream data freshness

If `dbt_test_models` fails with test failures (not connection errors):

```bash
cd /root/lh-d01/dbt/lh_analytics

# see exactly which tests failed and why
dbt test --profiles-dir /root/.dbt

# inspect the compiled SQL of a failing test
cat target/compiled/lh_analytics/models/example/schema.yml/<test_name>.sql
```

Run the compiled SQL directly in psql to see the failing rows:
```bash
sudo -u postgres psql -d dbt_practice
```

Common causes:
- Null values arriving in a not_null column → source data issue
- Unexpected values in an accepted_values test → new status introduced upstream
- Duplicate keys → source system sent duplicate records

---

### 5. Check retry behaviour

Airflow retries failed tasks automatically (up to 2 retries, 5 min apart).
Before manually intervening, confirm the task has exhausted its retries:

```bash
airflow dags list-runs --dag-id analytics_pipeline_v1
```

Look at the `state` column:
- `running` — still retrying, wait
- `failed` — retries exhausted, manual action needed
- `success` — recovered on retry, no action needed

In the UI the retry count is visible in the task instance tooltip.

---

## Safe rerun guidance

### Rerun a single failed task (preferred)

Use this when the root cause is fixed and you want to resume without
re-running tasks that already succeeded.

```bash
airflow tasks run analytics_pipeline_v1 <task_id> <logical_date> --force
```

Example — rerun only dbt_test_models after fixing a data issue:
```bash
airflow tasks run analytics_pipeline_v1 dbt_test_models 2026-04-26T07:00:00 --force
```

In the UI: click the failed task → **Clear** → confirm. Airflow reruns from
that task and continues downstream if it passes.

**Safe for:** `dbt_run_models`, `dbt_test_models`, `publish_mart`, `notify_status`

---

### Full DAG rerun

Use this only when multiple upstream tasks need to be re-executed, or when
the source data itself was re-loaded.

```bash
airflow dags trigger analytics_pipeline_v1 --logical-date <date>
```

Or in the UI: **Trigger DAG** button with a specific logical date.

**Caution:** A full rerun will re-extract, re-stage, re-run dbt, and
re-publish. If publish is not idempotent in your environment, this can
cause duplicates. Verify before triggering.

**Safe for:** situations where source data was fully replaced or the pipeline
never completed a previous run.

---

### When NOT to rerun

- Do not rerun `publish_mart` if downstream consumers have already read the
  data and the issue is cosmetic (e.g. a column rename) — coordinate with
  consumers first.
- Do not rerun while a previous run is still in `running` state —
  `max_active_runs=1` will queue it but this can cause confusion.
- Do not clear and rerun `dbt_test_models` without first fixing the
  underlying data issue — it will fail again immediately.

---

## Quick reference

| Situation | Action |
|---|---|
| Postgres down | `sudo service postgresql start` |
| dbt profile missing | check `~/.dbt/profiles.yml` |
| Test failure — data issue | fix source data → rerun `dbt_test_models` |
| Test failure — model bug | fix SQL → rerun `dbt_run_models` → `dbt_test_models` |
| Airflow not picking up DAG | `airflow dags list-import-errors` |
| DAG not showing in list | check `AIRFLOW__CORE__DAGS_FOLDER` in `airflow.cfg` |
| Stuck in retrying state | wait for retry_delay (5 min) to elapse |
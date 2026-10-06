# Phase 9 — Data Quality Framework

## Phase Goal
Create a practical data quality framework to validate correctness, completeness, and reliability across the data pipeline.

## Step 1: Define quality checks
- Identify data quality dimensions such as nulls, duplicates, and completeness.
- Map checks to raw and transformed data.
- Decide what level of validation is required at each pipeline stage.

## Step 2: Implement monitoring
- Add checks for anomalies and schema drift.
- Monitor pipeline execution quality.
- Review validation results and identify recurring issues.

## Step 3: Improve trust in data products
- Use quality metrics to confirm pipeline health.
- Address issues before data reaches downstream consumers.
- Define a feedback loop for continuous improvement.

## Issues faced
- Data quality requirements were not yet defined.
- There was no formal framework for validation.
- Pipeline outputs could become hard to trust without checks.

## Root cause
- The architecture was being built without a consistent quality validation layer.
- Data quality tools and checks were not yet standardized.

## Fix
- Define quality checks and record what is expected at each stage.
- Standardize validation logic across the pipeline.
- Use monitorable rules to confirm that output is fit for use.

## What I learned
- Data quality is a design requirement, not an afterthought.
- Trust in data depends on observability and validation.
- Quality checks should exist at multiple pipeline stages.

## Interview questions
1. What is data quality in a data engineering context?
2. Why is schema validation important?
3. How do you detect nulls or duplicates at scale?
4. What are some common data quality failures in pipelines?
5. How can data quality checks prevent downstream business issues?

## Already in place (built in Phase 5)

- **Silver expectations.** `workspace.silver.coinbase_ticker` enforces four rules with `expect_all_or_drop`: `event_time` not null, `product_id` not null, `price > 0`, and `best_bid <= best_ask`. Dropped-row counts show on the pipeline's Data quality tab.
- **Deduplication.** Silver removes repeats on `product_id`, `event_time` and `sequence_num`.
- **Safe casts.** `try_cast` turns bad numbers into `NULL`, which a rule then catches.
- **Freshness monitoring.** `coinbase-consumer-health-check` fails and emails when no new S3 file has arrived for 10 minutes.
- **Pipeline failure alerts.** `coinbase-bronze-job` retries 3 times and emails on failure.

## Still to build

- Rules for Bronze and for the Gold tables from Phase 8.
- Schema-drift detection.
- A single place that reports quality results over time.
- Reconciliation checks between layers.

## Phase status ⏳

Pending. Quality rules and freshness alerting exist for Silver and the consumer (Phase 5), but the full framework described above is not built.

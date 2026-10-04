# Phase 7 — Gold Transformations

## Phase Goal

Build the Gold layer: business-ready, aggregated tables on top of the clean Silver data. Bronze and Silver are not part of this phase; they were built and documented in Phase 5 (`05-databricks-asset-bundle.md`, sub-phases 5.4 and 5.6).

## Starting Point (From Phase 5)

```text
Coinbase WebSocket -> EC2 consumer -> S3 raw -> Auto Loader -> workspace.bronze.coinbase_bronze
                                                          -> workspace.silver.coinbase_ticker   <- Phase 7 starts here
                                                          -> Gold (this phase)
```

`workspace.silver.coinbase_ticker` has one row per BTC-USD price update, with typed columns: `product_id`, `event_time`, `sequence_num`, `event_type`, `price`, `best_bid`, `best_ask`, `best_bid_quantity`, `best_ask_quantity`, `volume_24h`, `high_24h`, `low_24h`, `high_52w`, `low_52w`, `price_pct_chg_24h`, `ingestion_timestamp`, `source_file`.

Bronze and Silver already run every 15 minutes in `coinbase-bronze-job`, with a failure email and the consumer health check. Gold is added to the same pipeline, so it refreshes on the same schedule.

## Step 1: Define the Gold use cases and grain

Decide each Gold table's consumer and grain before writing code.

| Candidate table | Grain | What it answers |
| --- | --- | --- |
| `workspace.gold.coinbase_ohlc_1m` | one row per product per minute | Open, high, low, close price and tick count for candle charts |
| `workspace.gold.coinbase_price_summary_hourly` | one row per product per hour | Average price, volatility, average bid-ask spread |
| `workspace.gold.coinbase_market_latest` | one row per product | Latest price, 24-hour change and volume for a current-state view |

These are candidates. Final tables depend on the business questions chosen.

## Step 2: Build the Gold transformations

- Read from `workspace.silver.coinbase_ticker`, not from Bronze.
- Aggregate by the chosen grain with windowed or grouped logic.
- Decide how late data is handled, since Silver can be up to 15 minutes behind S3.
- Publish to a new `workspace.gold` schema, created before the first run.
- Add the Gold file to `resources/pipeline.yml` so Gold runs after Silver in one pipeline update.

## Step 3: Add quality rules and verify

- Add expectations to Gold tables (for example `high >= low`, `tick_count > 0`).
- Reconcile Gold against Silver: counts and totals must match for a sample window.
- Confirm a business question can be answered from Gold alone.

## Completion check

Each Gold table has a named consumer, a documented grain, quality rules, and a repeatable transformation from Silver that runs on the existing job schedule.

## Issues faced

Not started. This section will record real issues when the phase is built.

## What I learned

Not started.

## Interview questions

1. What is the Gold layer, and how does it differ from Silver?
2. What is the grain of a table, and why define it first?
3. Why build Gold from Silver and not from Bronze?
4. How would you handle late-arriving data in an aggregate?
5. How do you keep Gold consistent with Silver?

## Phase status ⏳

Pending. Bronze and Silver are complete in Phase 5; only Gold transformations remain for this phase.

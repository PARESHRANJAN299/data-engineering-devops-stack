# Phase 5 Extension — Coinbase WebSocket → EC2 → S3 → Databricks Bronze

This file covers only the Phase 5 extension work. It is separate from `05-databricks-asset-bundle.md` so the earlier documentation is not overwritten.

Completed in this extension:

- Coinbase WebSocket connection from EC2
- Real-time BTC-USD ticker ingestion
- Event buffering on EC2
- Batch JSON writes to Amazon S3
- Incremental Databricks Auto Loader ingestion
- Verification of real records in `workspace.bronze.coinbase_bronze`

## 1. Goal

Already completed earlier:

```
EC2 → S3                     ✅
Databricks → S3              ✅
External Location            ✅
Auto Loader                  ✅
Bronze Delta ingestion       ✅
```

Added in this extension:

```
Coinbase WebSocket → EC2     ✅
EC2 buffered events → S3     ✅
S3 real events → Bronze      ✅
```

## 2. Architecture Completed

```
Coinbase WebSocket
      |  live BTC-USD ticker events
      v
AWS EC2  (Python WebSocket consumer)
      |
In-memory event buffer
      |  flush approximately every 15 seconds
      v
Amazon S3  coinbase/raw/YYYY/MM/DD/HH/
      |  Databricks Auto Loader
      v
Lakeflow / ETL Pipeline
      |
      v
workspace.bronze.coinbase_bronze
```

In plain words: Coinbase sends events → EC2 receives them → EC2 groups many events → EC2 writes one JSON batch file to S3 → Databricks reads new S3 files → rows are appended into Bronze.

## 3. Coinbase WebSocket Consumer

Source file: `src/ingestion/coinbase_websocket_consumer.py`

The Coinbase source is a WebSocket stream, so events arrive continuously. A long-running Python consumer on EC2 receives them.

## 4. WebSocket Connection

- Endpoint: `wss://advanced-trade-ws.coinbase.com`
- Product: `BTC-USD`
- Channel: `ticker`

Successful output:

```
Connected to Coinbase WebSocket
Subscribed to BTC-USD
```

followed by live ticker messages.

## 5. Python Dependencies

```bash
uv add websocket-client
```

S3 upload logic uses `boto3`.

```
Python consumer
   ├─ websocket-client → Coinbase WebSocket
   └─ boto3            → Amazon S3 API
```

## 6. Why We Buffer Events

Coinbase can send many events per second. One event per S3 file would create many tiny files. Instead:

```
many Coinbase events → EC2 memory buffer → wait ~15 s → one JSON batch file
```

Example: a 15-second window with 28 events becomes one S3 file; the next window with 32 events becomes another.

## 7. S3 Raw File Layout

Raw location: `s3://paresh-data-engineering-coinbase-dev/coinbase/raw/`

```
coinbase/
└── raw/
    └── YYYY/MM/DD/HH/
        └── events_YYYYMMDD_HHMMSS.json
```

Example: `coinbase/raw/2026/10/04/05/events_20261004_054913.json`

Benefits: debugging, replay, operational investigation, time-based organization.

## 8. EC2 → S3 Real Streaming Write

The consumer wrote live Coinbase batches into S3. Observed batch sizes: 28, 32, 35, 38, 45, 37, 35 events.

```
Coinbase → EC2 WebSocket consumer → 15-second buffer → boto3 put_object() → S3 raw
```

This proves the EC2 IAM role works for a real Python application, not only AWS CLI test commands.

## 9. IAM Authentication Used by the Consumer

No permanent AWS access keys are in the Python code.

```
boto3 → EC2 IAM Role → temporary AWS credentials → S3 PutObject
```

The code contains no `AWS_ACCESS_KEY_ID` or `AWS_SECRET_ACCESS_KEY`.

Interview explanation: *The Python ingestion process uses boto3 on EC2. boto3 automatically obtains temporary credentials from the EC2 instance IAM role, so no long-lived AWS credentials are stored in source code.*

## 10. Graceful Buffer Flush

Stopping the consumer with `Ctrl + C` wrote the remaining buffered events before the connection closed:

```
Wrote 6 events to S3
WebSocket connection closed
```

Without a final flush, events still in memory would be lost when the process stops. With it: `flush_buffer()` → S3 → process closes.

## 11. Databricks Incremental Bronze Ingestion

After the real Coinbase files landed in S3, the existing Databricks pipeline was run.

```
S3 raw files → Auto Loader → Lakeflow pipeline → workspace.bronze.coinbase_bronze
```

## 12. Incremental Ingestion Concept

Auto Loader processes new files incrementally: files already processed are not reprocessed, new files are, and new rows are appended into Bronze.

```
S3 files 1–3 → Bronze table
later: S3 files 4–5 → same Bronze table
```

## 13. Bronze Ingestion Verification

The pipeline completed successfully with **Output records: 256** into `workspace.bronze.coinbase_bronze`.

```
Coinbase → EC2 → S3 → Auto Loader → Databricks pipeline → 256 records → Bronze Delta
```

## 14. Bronze Table Columns Observed

`source`, `test`, `_rescued_data`, `ingestion_timestamp`, `source_file`, `channel`, `events`, `sequence_num`, `timestamp`

The earlier test row is still present; the new Coinbase records were appended afterward.

## 15. Current End-to-End Architecture

```
                    Coinbase WebSocket (BTC-USD ticker)
                            |
                            v
+------------------------------------------------+
| AWS EC2                                        |
| src/ingestion/coinbase_websocket_consumer.py   |
|   websocket-client → live events               |
|   → memory buffer → ~15 s flush → boto3        |
+-------------------------+----------------------+
                          | EC2 IAM Role
                          v
+------------------------------------------------+
| Amazon S3                                      |
| coinbase/raw/YYYY/MM/DD/HH/events_*.json       |
+-------------------------+----------------------+
                          | Unity Catalog access
                          v
+------------------------------------------------+
| Databricks                                     |
| Storage Credential → External Location         |
| → Auto Loader → data-engineering-pipeline      |
| → workspace.bronze.coinbase_bronze             |
+------------------------------------------------+
```

## 16. Connection-by-Connection Understanding

| # | Connection | Mechanism | Purpose |
|---|------------|-----------|---------|
| 1 | Coinbase → EC2 | websocket-client → Python consumer | Receive live BTC-USD events |
| 2 | EC2 → S3 | boto3 → EC2 IAM Role → S3 | Persist events into durable raw storage |
| 3 | S3 → Databricks | Storage Credential → External Location | Securely read the raw S3 files |
| 4 | External Location → Bronze | Auto Loader → Lakeflow pipeline → Delta | Incrementally ingest new raw files |

## 17. Issues Observed

**Issue 1 — `python` command not found.** `python src/ingestion/coinbase_websocket_consumer.py` failed; the EC2 environment uses `python3 src/ingestion/coinbase_websocket_consumer.py`. (`cat file.py` displays a file; `python3 file.py` executes it.)

**Issue 2 — `git push -m`.** Incorrect. A commit message belongs to `git commit -m "message"`, then push with `git push`.

**Issue 3 — typing file names as commands.** Typing `pyproject.toml` or `uv.lock` in Bash tries to execute them. Use `cat pyproject.toml` to view or `nano pyproject.toml` to edit.

## 18. Completed

- ✅ Coinbase ingestion source folder and WebSocket consumer
- ✅ `websocket-client` dependency
- ✅ EC2 connected to Coinbase WebSocket, subscribed to BTC-USD ticker, live events received
- ✅ boto3-based S3 writing with in-memory buffering, batched ~every 15 seconds
- ✅ Time-partitioned raw S3 files
- ✅ EC2 IAM role used instead of access keys
- ✅ Remaining events flushed on shutdown
- ✅ Databricks Bronze pipeline run; Auto Loader discovered new raw files
- ✅ 256 real records loaded and verified in `workspace.bronze.coinbase_bronze`

## 19. Current Phase 5 Status

```
EC2 → S3 connectivity                  ✅
Databricks → S3 connectivity           ✅
Unity Catalog Storage Credential       ✅
External Location                      ✅
Databricks Asset Bundle                ✅
Serverless pipeline                    ✅
Auto Loader                            ✅
Bronze Delta table                     ✅
Coinbase WebSocket → EC2               ✅
Real Coinbase events → S3              ✅
Real S3 batches → Bronze               ✅

Databricks Job orchestration           ⏳ NEXT
Scheduled pipeline execution           ⏳ NEXT
Silver transformations                 ⏳ Later phase
Gold transformations                   ⏳ Later phase
CI/CD automation                       ⏳ Later phase
```

## 20. Interview Explanation

I built a real-time Coinbase ingestion flow where an EC2-hosted Python consumer connects to the Coinbase WebSocket ticker feed for BTC-USD. The consumer buffers events for a short time window and writes each batch as JSON into a time-partitioned S3 raw location using boto3 and an EC2 IAM role. Databricks accesses the S3 raw location through Unity Catalog using a storage credential and external location. Auto Loader incrementally discovers the new JSON files and a serverless Lakeflow pipeline appends the records into a Bronze Delta table. The end-to-end flow was validated with real Coinbase events, and one pipeline execution ingested 256 records.

## 21. Architecture to Remember

```
Coinbase → WebSocket → EC2 Python Consumer → Buffer → boto3 → EC2 IAM Role
→ S3 Raw → Unity Catalog → External Location → Auto Loader
→ Databricks Pipeline → Bronze Delta
```

This is the completed source-to-Bronze architecture before adding Databricks Job orchestration.

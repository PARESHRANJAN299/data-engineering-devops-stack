# Phase 5 — Databricks Asset Bundle, AWS S3 Integration, and Bronze Ingestion

## Phase Goal

Build and verify the deployment and ingestion foundation in small architectural slices. The implementation first proved EC2-to-S3 and S3-to-Bronze with a test JSON file (5.1–5.4), then replaced the test file with a live Coinbase WebSocket consumer on EC2 (5.5), added Silver (5.6) and a scheduled, monitored job (5.8). Gold (5.7) moves to Phase 7 (Bronze, Silver, Gold pipeline).

## Target Architecture

```text
Coinbase WebSocket
	|
	v
EC2 Python consumer + event buffer
	|  boto3 + EC2 IAM role
	v
S3 raw landing
	|
	v
Unity Catalog External Location
	|
	v
Auto Loader / Lakeflow pipeline
	|
	v
workspace.bronze.coinbase_bronze
	|
	v
workspace.silver.coinbase_ticker
	|
	v
Gold Delta (future)
```

## Phase 5 Sub-Phases

| Sub-phase | Architecture slice | Status |
| --- | --- | --- |
| 5.1 | Asset Bundle, `dev` target, resource discovery | ✅ Complete |
| 5.2 | EC2 IAM role, AWS CLI, and S3 raw landing | ✅ Complete |
| 5.3 | Unity Catalog Storage Credential and External Location | ✅ Complete |
| 5.4 | Auto Loader, serverless pipeline, and Bronze test ingestion | ✅ Complete |
| 5.5 | Coinbase WebSocket consumer writing real events to S3, then to Bronze | ✅ Complete |
| 5.6 | Silver cleansing and standardization | ✅ Complete |
| 5.7 | Gold business-ready transformations | ➡️ Moved to Phase 7 |
| 5.8 | Job orchestration, retries, and failure/consumer alerts | ✅ Complete |
| 5.9 | Consumer reliability: systemd, reconnect, upload retry, spool | ✅ Complete |

The completed slices establish `Coinbase -> EC2 -> S3 -> Databricks -> Auto Loader -> Bronze Delta`. Each new S3 file contributes rows to the same Bronze table; files do not get separate Bronze tables. Silver (5.6) and the scheduled job with alerting (5.8) are complete. Gold (5.7) is not part of Phase 5; it is built in Phase 7.

## Current Connectivity Status

```text
EC2 -> S3                         ✅
Databricks -> S3                  ✅
Storage Credential               ✅
External Location                 ✅
Asset Bundle -> Pipeline          ✅
Serverless pipeline deployment    ✅
Auto Loader -> Bronze Delta       ✅
Test JSON ingestion               ✅
Coinbase WebSocket -> EC2         ✅
Real Coinbase events -> S3        ✅
Real S3 batches -> Bronze         ✅

Silver Delta                      ✅
Job (every 15 min) + retries      ✅
Failure + consumer alerts         ✅

Gold                              ⏳
```

## Sub-Phase 5.1 — Databricks Asset Bundle Foundation

### Step 1 — Create a Phase 5 Git Branch

Phase 5 work is isolated from the trusted `main` branch:

```bash
git switch main
git pull origin main
git switch -c phase-5-databricks-s3-integration
```

Verify the current branch:

```bash
git branch
```

The active branch is `phase-5-databricks-s3-integration`.

### Step 2 — Create `databricks.yml`

The root bundle configuration identifies the Databricks project:

```yaml
bundle:
  name: data-engineering-devops-stack

include:
  - resources/*.yml
```

### Step 3 — Configure the Development Target

Add a `dev` target that uses the Databricks workspace and OAuth profile configured in Phase 4. The full minimal configuration is:

```yaml
bundle:
  name: data-engineering-devops-stack

include:
  - resources/*.yml

targets:
  dev:
    default: true
    workspace:
      host: https://<databricks-workspace-host>
```

The repository's `databricks.yml` contains the actual workspace host. This guide uses a placeholder so the workspace-specific value is not duplicated in documentation. The `include` pattern makes resource YAMLs explicit and reviewable.

```text
bundle       = Databricks project definition
target: dev  = development deployment environment
default      = use dev when no target is explicitly selected
```

No Databricks token or password is stored in `databricks.yml`. Authentication continues to use the Phase 4 OAuth CLI profile.

### Step 4 — Validate the Bundle

Validate the development target:

```bash
databricks bundle validate --target dev
```

Successful validation reports:

```text
Validation OK!
```

This confirms the CLI can resolve the bundle name, target, workspace configuration, authenticated user, bundle workspace path, and resource configuration. Validation checks configuration; it does not deploy the bundle.

Summarize the resources recognized by the bundle:

```bash
databricks bundle summary --target dev
```

Deploy only after validation and review:

```bash
databricks bundle deploy --target dev
```

```text
EC2
	|
	v
Databricks CLI
	|
	v
Phase 4 OAuth profile
	|
	v
databricks.yml
	|
	v
Databricks workspace
```

### Step 5 — Create the Bundle Folder Structure

The project separates transformation code from Databricks resource definitions:

```text
resources/                         Databricks resource definitions
src/                               application and ETL code
├── bronze/                        raw-source ingestion logic
├── silver/                         cleaning and standardization
├── gold/                           business-ready transformations
└── data_engineering_devops_stack/  shared Python package
```

`src/` holds application and transformation code. `resources/` holds bundle-managed resource definitions such as pipelines and jobs. `resources/job.yml` is planned but has no job definition yet.

### Step 6 — Add the Initial Pipeline Resource

The deployed serverless pipeline resource is defined in `resources/pipeline.yml`:

```yaml
resources:
  pipelines:
    data_engineering_pipeline:
      name: data-engineering-pipeline
      serverless: true
      catalog: workspace
      schema: bronze
      libraries:
        - file:
            path: ../src/bronze/bronze_pipeline.py
```

The serverless pipeline publishes tables to `workspace.bronze`; the pipeline source remains in `src/bronze/bronze_pipeline.py`.

## Source Architecture Decision

An EC2-hosted Python process maintains the Coinbase WebSocket connection, buffers events for short intervals, and writes batched JSON files to S3. This avoids creating one S3 object for every event. It was built after the test-file connectivity proof in 5.1–5.4; see Sub-Phase 5.5.

```text
Coinbase WebSocket -> EC2 consumer -> batches of JSON -> S3 raw/
```

Batch filenames carry a UTC timestamp: `events_<UTC timestamp>.json`.

## Sub-Phase 5.2 — EC2 to S3 Raw Landing

### S3 Raw Landing Zone

The development bucket and raw prefix are:

```text
Bucket: paresh-data-engineering-coinbase-dev
Prefix: s3://paresh-data-engineering-coinbase-dev/coinbase/raw/
```

```text
s3://paresh-data-engineering-coinbase-dev/
└── coinbase/
		└── raw/
```

The `raw/` prefix stores source events with minimal or no transformation. Downstream Bronze, Silver, and Gold tables are managed as Delta tables by Databricks.

### EC2-to-S3 IAM Security

### Why Use an IAM Role Instead of Access Keys?

The EC2 instance should receive temporary credentials through its attached IAM role rather than storing permanent AWS access keys:

```text
EC2 instance -> IAM role -> temporary STS credentials -> S3
```

Do not place AWS access keys in source code, `.env` files, GitHub, or EC2 configuration files. The application and AWS CLI use the instance role credentials supplied by AWS.

### Step 1 — Create the IAM Policy

The least-privilege policy is named `PareshCoinbaseRawS3Access`. Its permissions cover the required bucket and raw prefix operations:

```text
s3:ListBucket
s3:GetBucketLocation
s3:PutObject
s3:GetObject
s3:AbortMultipartUpload
```

Object-level access is restricted to:

```text
arn:aws:s3:::paresh-data-engineering-coinbase-dev/coinbase/raw/*
```

Bucket-level actions should be scoped to the required bucket, with listing constrained to the `coinbase/raw/` prefix where supported by the policy condition.

### Step 2 — Create the EC2 IAM Role

The role `PareshCoinbaseEC2S3Role` trusts the EC2 service and has the `PareshCoinbaseRawS3Access` policy attached:

```text
EC2 instance
			|
			v
PareshCoinbaseEC2S3Role
			|
			v
PareshCoinbaseRawS3Access
			|
			v
Coinbase raw S3 prefix
```

### Step 3 — Attach the Role to EC2

Attach the role to the existing development instance. Applications on the instance can then obtain temporary role credentials without static AWS keys.

### Install and Validate the AWS CLI

Initially, `aws --version` returned:

```text
aws: command not found
```

The Ubuntu package manager did not provide an installable `awscli` package in this environment, so AWS CLI v2 was installed using the official AWS x86_64 installer:

```bash
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o awscliv2.zip
unzip awscliv2.zip
sudo ./aws/install
```

The installer is distributed as a ZIP archive. It must be extracted before running `./aws/install`; after installation, the downloaded archive and extracted installer directory are not project source.

Verify the CLI installation:

```bash
aws --version
```

Verified on the EC2 development instance:

```text
aws-cli/2.37.6 ... exe/x86_64.ubuntu.24
```

Verify the AWS identity used by the CLI:

```bash
aws sts get-caller-identity
```

The returned ARN contained `assumed-role/PareshCoinbaseEC2S3Role/`, confirming that the EC2 instance assumed the intended role. The full ARN also contains account and session identifiers, so do not paste it into public documentation or commit it.

Check read access to the raw landing prefix without printing object names:

```bash
aws s3api list-objects-v2 \
	--bucket paresh-data-engineering-coinbase-dev \
	--prefix coinbase/raw/ \
	--max-keys 1 \
	--query KeyCount \
	--output text
```

A successful request, including a result of `0` for an empty prefix, confirms that the caller can list the raw prefix. An `AccessDenied` response requires checking the attached instance role and the bucket/object policy scopes.

The read-only request succeeded and returned `KeyCount` `1`. The object key is intentionally not included here. The equivalent human-readable check is:

```bash
aws s3 ls s3://paresh-data-engineering-coinbase-dev/coinbase/raw/
```

### Verify S3 Write Access

A temporary JSON test object was created and uploaded to the raw prefix:

```bash
echo '{"source":"coinbase","test":true}' > test.json
aws s3 cp test.json s3://paresh-data-engineering-coinbase-dev/coinbase/raw/test.json
aws s3 ls s3://paresh-data-engineering-coinbase-dev/coinbase/raw/
```

The upload succeeded and `test.json` appeared in the listing. This verified the EC2 caller's S3 `PutObject` access. The local `test.json` is temporary validation data, not project source; do not commit it.

## EC2-to-S3 Authentication Model

```text
EC2 instance
	|
	v
Attached IAM role
	|
	v
AWS STS temporary credentials
	|
	v
AWS CLI or Python application
	|
	v
S3 API -> Coinbase raw prefix
```

AWS rotates the temporary role credentials. This avoids permanently storing `AWS_ACCESS_KEY_ID` or `AWS_SECRET_ACCESS_KEY` on the server and makes access easier to revoke and restrict.

## Sub-Phase 5.3 — Databricks to S3 with Unity Catalog

### Architecture

Unity Catalog governs Databricks access to cloud storage. The Storage Credential answers how Databricks authenticates; the External Location defines which storage path it may access.

```text
Databricks
	|
	v
Storage Credential: coinbase_raw_s3_credential
	|
	v
AWS role: PareshDatabricksCoinbaseS3ReadAccess
	|
	v
External Location: coinbase_raw_external_location
	|
	v
s3://paresh-data-engineering-coinbase-dev/coinbase/raw/
```

The Databricks role is separate from the EC2 ingestion role:

```text
EC2 -> S3          PareshCoinbaseEC2S3Role
Databricks -> S3   PareshDatabricksCoinbaseS3ReadAccess
```

### Configure and Validate the Storage Credential

1. In Unity Catalog, start creating the AWS Storage Credential and use the Databricks-generated role configuration.
2. Create the dedicated AWS role `PareshDatabricksCoinbaseS3ReadAccess`; apply the exact trust principal and external ID generated by Databricks.
3. Attach a least-privilege policy that permits the required read/list access to the Coinbase raw bucket path.
4. Create the Storage Credential named `coinbase_raw_s3_credential` using that role. Do not reuse the EC2 role.

Validation succeeded for assume-role, self-assume-role, external-ID condition, and the required data permissions. Do not paste role ARNs, external IDs, or account IDs into public docs.

### Create the External Location

1. Create `coinbase_raw_external_location` with the following configuration:

```text
URL:                  s3://paresh-data-engineering-coinbase-dev/coinbase/raw/
Storage Credential:   coinbase_raw_s3_credential
Read-only:            enabled
Encryption:           SSE-S3
```

2. Validate read, list, path-exists, assume-role, and external-ID access. These checks succeeded.
3. Automatic file-event provisioning and teardown failed because setup attempted `s3:GetBucketNotification`, which the read-only data role intentionally does not have. The location was still created for core read access; file events are not relied upon.

### Verify Databricks-to-S3

Confirm the External Location can list and read the raw prefix using its validation controls. Do not broaden the role to add notification infrastructure permissions unless file events become an explicit requirement.

## Sub-Phase 5.4 — Auto Loader to Bronze Delta

### Goal and Data Model

Auto Loader incrementally discovers new JSON files in S3. It appends records from multiple files into one Bronze table and preserves source fields while adding ingestion metadata.

```text
S3 raw JSON -> Auto Loader -> streaming DataFrame
			-> Lakeflow pipeline -> workspace.bronze.coinbase_bronze
```

The Bronze function in `src/bronze/bronze_pipeline.py` uses the pipeline-native `@dp.table` pattern:

```python
from pyspark import pipelines as dp
from pyspark.sql.functions import col, current_timestamp

raw_path = "s3://paresh-data-engineering-coinbase-dev/coinbase/raw/"

@dp.table(
    name="coinbase_bronze",
    table_properties={"quality": "bronze"}
)
def coinbase_bronze():
    return (
        spark.readStream
        .format("cloudFiles")
        .option("cloudFiles.format", "json")
        .load(raw_path)
        .withColumn("ingestion_timestamp", current_timestamp())
        .withColumn("source_file", col("_metadata.file_path"))
    )
```

Pipeline-managed state/checkpointing is left to Lakeflow. The source-file column uses `_metadata.file_path`, which is supported in this Unity Catalog context.

### Configure the Serverless Pipeline

`resources/pipeline.yml` configures the deployed pipeline:

```yaml
resources:
  pipelines:
		data_engineering_pipeline:
			name: data-engineering-pipeline
			serverless: true
			catalog: workspace
			schema: bronze
			libraries:
				- file:
						path: ../src/bronze/bronze_pipeline.py
```

The table's fully qualified name is `workspace.bronze.coinbase_bronze`.

### Validate, Summarize, and Deploy

Run these commands from the repository root:

```bash
databricks bundle validate --target dev
databricks bundle summary --target dev
databricks bundle deploy --target dev
```

The successful deployment created `data_engineering_pipeline`; the pipeline run then completed with one output record. Trigger and inspect the pipeline run in the Databricks workspace after deployment.

### Bronze Ingestion Proof

The test object was uploaded from EC2 to `s3://paresh-data-engineering-coinbase-dev/coinbase/raw/test.json`. The completed pipeline run reported Auto Loader as the source, `coinbase_bronze` as the target, and one output record. The resulting row included `source = coinbase`, `test = true`, an `ingestion_timestamp`, and the S3 path in `source_file`.

This proves test-file connectivity across EC2, S3, Unity Catalog, Auto Loader, the Lakeflow pipeline, and the Bronze Delta table. It does not prove live Coinbase WebSocket ingestion.

## Sub-Phase 5.5 — Coinbase WebSocket to S3 to Bronze

Sub-phases 5.1–5.4 proved the pipeline with a hand-made `test.json`. Sub-phase 5.5 replaces that test file with real data. The pieces below are built one at a time, in the order the data flows. The EC2 role, S3 raw prefix, Storage Credential, External Location, and Bronze pipeline are reused unchanged from 5.2–5.4.

```text
Coinbase WebSocket -> EC2 consumer -> event buffer -> boto3 -> EC2 IAM role
  -> S3 raw -> External Location -> Auto Loader -> Databricks pipeline -> Bronze Delta
```

| Step | Component | Status |
| --- | --- | --- |
| 5.5.1 | Coinbase WebSocket source | ✅ |
| 5.5.2 | EC2 Python consumer | ✅ |
| 5.5.3 | Event buffer (about 15 seconds) | ✅ |
| 5.5.4 | One JSON batch file per flush | ✅ |
| 5.5.5 | boto3 with the EC2 IAM role | ✅ |
| 5.5.6 | Time-based S3 folder layout | ✅ |
| 5.5.7 | Graceful flush on shutdown | ✅ |
| 5.5.8 | Auto Loader detects the new files | ✅ |
| 5.5.9 | Incremental append into Bronze | ✅ |

All code for 5.5.1–5.5.7 is in `src/ingestion/coinbase_websocket_consumer.py`.

### 5.5.1 — Coinbase WebSocket Source

```text
Coinbase WebSocket (BTC-USD ticker)
        |
        v
(next: EC2 consumer)
```

**What it is.** A push-based feed. The client opens one long-lived connection and Coinbase sends a message every time the BTC-USD ticker changes. There is no polling and no request per event.

**Why we need it.** It is the real data source for the project. A REST API would need constant polling and would miss changes between calls.

**How it connects.** It is the start of the chain. It only needs outbound internet access from EC2, so no inbound ports or security group changes were needed.

**Configuration.**

```python
WS_URL = "wss://advanced-trade-ws.coinbase.com"
PRODUCT_ID = "BTC-USD"

subscribe_message = {
    "type": "subscribe",
    "channel": "ticker",
    "product_ids": [PRODUCT_ID],
}
```

Connecting alone does nothing; the subscribe message is what starts the ticker events. Successful output:

```text
Connected to Coinbase WebSocket
Subscribed to BTC-USD
```

**Issue and fix.** None on the connection itself. Note that the code keeps only messages whose `channel` is `ticker` (`event.get("channel") == "ticker"`), so subscription acknowledgements and other control messages are not written to S3.

**Interview concept.** WebSocket (persistent, server-push, low overhead) versus REST polling. A WebSocket needs a long-running process, which is why the consumer runs on EC2 and not in a short-lived job.

### 5.5.2 — EC2 Python Consumer

```text
Coinbase WebSocket
        |  websocket-client
        v
EC2 Python consumer   <- you are here
```

**What it is.** A long-running Python process, `src/ingestion/coinbase_websocket_consumer.py`, that holds the WebSocket open and reacts to callbacks.

**Why we need it.** Something has to stay connected 24/7 and receive events as they arrive. Databricks pipelines are batch/triggered jobs and are the wrong place for a permanent socket. The consumer is a thin ingestion service that lands data and does no transformation.

**How it connects.** It sits on the same EC2 instance, `uv` environment, and IAM role set up in 5.2, so it needs no new AWS access.

**Configuration and code.**

```bash
uv add websocket-client      # WebSocket client library
python3 src/ingestion/coinbase_websocket_consumer.py
```

```python
ws = websocket.WebSocketApp(
    WS_URL,
    on_open=on_open,        # send the subscribe message
    on_message=on_message,  # buffer ticker events, flush when due
    on_error=on_error,      # log the error
    on_close=on_close,      # final flush
)
ws.run_forever()
```

`boto3` is also used by the script (see 5.5.5).

**Issue and fix.**

| Issue | Root cause | Fix |
| --- | --- | --- |
| `python: command not found` | Ubuntu on EC2 provides `python3` and has no `python` alias. | Run `python3 src/ingestion/coinbase_websocket_consumer.py`. |
| Typing `pyproject.toml` or `uv.lock` in Bash tried to run them | A file name typed alone is treated as a command. | Use `cat pyproject.toml` to view, `nano pyproject.toml` to edit. |

**Interview concept.** Callback (event-driven) programming: the library calls `on_message` for each event. Also, separate the ingestion service (land raw data reliably) from the processing platform (transform it).

### 5.5.3 — Event Buffer

```text
EC2 Python consumer
        |
        v
In-memory event buffer   <- you are here
```

**What it is.** A Python list, `event_buffer`, that collects ticker events in memory, plus `last_flush_time` to track the window.

**Why we need it.** Coinbase can send many events per second. Writing each event to S3 would create a large number of tiny files, which is slow, costly in S3 requests, and hard for Auto Loader to list and process efficiently.

**How it connects.** `on_message` from 5.5.2 appends each ticker event here; the buffer feeds the batch writer in 5.5.4.

**Configuration and code.**

```python
BUFFER_SECONDS = 15
event_buffer = []
last_flush_time = time.time()

def on_message(ws, message):
    event = json.loads(message)
    if event.get("channel") == "ticker":
        event_buffer.append(event)
    if time.time() - last_flush_time >= BUFFER_SECONDS:
        flush_buffer()
```

Observed batch sizes were 28, 32, 35, 38, 45, 37, and 35 events per window.

**Issue and fix.** No issue observed in the run. Known limitations of this simple design, to state honestly in an interview:

- The buffer is in memory, so a crash or `kill -9` loses up to about 15 seconds of events.
- The flush check runs only when a message arrives. If the feed goes silent, the buffer waits until the next message.

Mitigations if needed later: a timer thread, a size-based flush, or a local spool file.

**Interview concept.** Micro-batching trades a little latency (about 15 seconds) for far fewer, larger files. This is the small-files problem.

### 5.5.4 — One JSON Batch File per Flush

```text
Event buffer
        |  flush_buffer()
        v
One JSON batch file   <- you are here
```

**What it is.** When the window expires, all buffered events are serialized into a single file body and the buffer is cleared.

**Why we need it.** Auto Loader reads files. This turns a stream into file-sized units without changing the event content, keeping the raw layer minimally transformed.

**How it connects.** It consumes the buffer from 5.5.3 and hands the body and key to boto3 in 5.5.5.

**Code.**

```python
body = "\n".join(json.dumps(event) for event in event_buffer)
...
event_buffer = []
last_flush_time = time.time()
```

The file contains one JSON object per line (newline-delimited JSON), not a single JSON array. Each line is the full Coinbase message, which is why Bronze shows `channel`, `sequence_num`, `timestamp`, and a nested `events` column. Spark's JSON reader, which Auto Loader uses, reads this format natively, one row per line.

**Issue and fix.** None observed. `flush_buffer()` returns early when the buffer is empty, so no empty files are written.

**Interview concept.** Newline-delimited JSON (JSON Lines) is the standard raw format for streaming into a lake: it is splittable, append-friendly, and needs no outer array. Keep raw data as it arrived and defer parsing to Silver.

### 5.5.5 — boto3 with the EC2 IAM Role

```text
One JSON batch file
        |  boto3 put_object()
        v
EC2 IAM Role (temporary credentials)   <- you are here
        |
        v
(next: S3 raw)
```

**What it is.** boto3 is the AWS SDK for Python. `s3.put_object()` uploads the batch to S3. The credentials come from the EC2 instance role, not from keys in code.

**Why we need it.** The consumer needs permission to write to S3 without storing long-lived secrets in source code or on disk.

**How it connects.** It uses the role and `PutObject` policy from 5.2. Before this step, only AWS CLI commands had used that role. Now a real application does.

**Configuration and code.**

```python
S3_BUCKET = "paresh-data-engineering-coinbase-dev"
S3_PREFIX = "coinbase/raw"

s3 = boto3.client("s3")          # no keys passed anywhere

s3.put_object(
    Bucket=S3_BUCKET,
    Key=key,
    Body=body.encode("utf-8"),
    ContentType="application/json",
)
```

```text
boto3 -> credential provider chain -> EC2 instance metadata
      -> temporary credentials from the role -> S3 PutObject
```

The code contains no `AWS_ACCESS_KEY_ID` or `AWS_SECRET_ACCESS_KEY`. Each successful flush logged `Wrote N events to s3://.../<key>`.

**Issue and fix.** None observed, because the role and policy were already validated in 5.2. A failed upload would raise an exception. There is no retry yet, so buffered events from that window would be lost.

**Interview concept.** The default credential provider chain: boto3 checks environment variables, shared config, then the instance role. On EC2 it finds the role automatically, and credentials rotate on their own. Say: *"boto3 on EC2 obtains temporary credentials from the instance role, so no long-lived keys are stored in source code."*

### 5.5.6 — Time-Based S3 Folder Layout

```text
boto3 put_object()
        |
        v
S3 raw   <- you are here
coinbase/raw/YYYY/MM/DD/HH/events_YYYYMMDD_HHMMSS_ffffff.json
```

**What it is.** The object key is built from the UTC time of the flush.

**Why we need it.** It gives unique file names, makes it easy to find the data for a given hour when debugging or replaying, and lets you list or delete by time range.

**How it connects.** The prefix `coinbase/raw/` is the path the External Location and the Bronze pipeline already read (5.3, 5.4). The date folders sit underneath it, so no Databricks configuration changed.

**Code.**

```python
now = datetime.now(timezone.utc)
key = (
    f"{S3_PREFIX}/"
    f"{now:%Y/%m/%d/%H}/"
    f"events_{now:%Y%m%d_%H%M%S}.json"
)
```

Example: `s3://paresh-data-engineering-coinbase-dev/coinbase/raw/2026/10/04/05/events_20261004_054913_123456.json`

**Issue and fix.** None observed. Auto Loader lists the prefix recursively, so nested date folders were found without any pipeline change. Using UTC avoids daylight-saving ambiguity. Two flushes in the same second would share a key, but a 15-second window makes that unlikely.

**Interview concept.** Time-partitioned raw layout (`year/month/day/hour`). These are folders only, not Hive-style `key=value` partitions, and Bronze does not partition by them. Raw storage is organized for operations; query partitioning is decided later.

### 5.5.7 — Graceful Flush on Shutdown

```text
Ctrl + C  ->  on_close  ->  flush_buffer()  ->  S3  ->  process exits
```

**What it is.** `on_close` calls `flush_buffer()` before the process ends.

**Why we need it.** Events still in memory when the process stops would otherwise be lost. Stopping with `Ctrl + C` is the normal way to end the consumer during development.

**How it connects.** It reuses the same `flush_buffer()` as the regular 15-second flush, so the write path is the same in both cases.

**Code.**

```python
def on_close(ws, close_status_code, close_msg):
    flush_buffer()
    print("WebSocket connection closed")
```

Observed on `Ctrl + C`:

```text
Wrote 6 events to s3://.../...
WebSocket connection closed
```

**Issue and fix.** None observed with `Ctrl + C`. A hard kill (`kill -9`), power loss, or instance failure skips `on_close`, so the final window can still be lost. Only graceful termination is covered.

**Interview concept.** Graceful shutdown and at-least-once thinking: flush buffered state on exit so planned stops lose no data. Know that this does not protect against crashes, and name the options (durable queue, local spool file, smaller windows).

### 5.5.8 — Auto Loader Detects the New Files

```text
S3 raw (new files)
        |  Storage Credential + External Location
        v
Auto Loader (cloudFiles)   <- you are here
```

**What it is.** The `cloudFiles` source in `src/bronze/bronze_pipeline.py` (unchanged from 5.4). It keeps track of which files it has processed and picks up only new ones.

**Why we need it.** Without it, you would need custom code to track which S3 files are new. Auto Loader handles file discovery and state.

**How it connects.** The consumer writes under `coinbase/raw/`. The External Location covers that path, so Databricks can read the new files with no change to permissions. The pipeline uses directory listing and not S3 file notifications, which were not enabled in 5.4 because of the `s3:GetBucketNotification` permission.

**Configuration.** No change to the pipeline code:

```python
spark.readStream.format("cloudFiles")
     .option("cloudFiles.format", "json")
     .load("s3://paresh-data-engineering-coinbase-dev/coinbase/raw/")
```

**Issue and fix.** None new. The issues from 5.4 (`LOCATION_OVERLAP`, file-event permissions) were already resolved and the pipeline ran unchanged on real data.

**Interview concept.** Incremental ingestion with file-discovery state: processed files are not read again. Know the difference between directory-listing mode and file-notification mode, and that listing a growing prefix gets slower at large scale.

### 5.5.9 — Incremental Append into Bronze

```text
Auto Loader
        |
        v
Databricks pipeline (data-engineering-pipeline)
        |
        v
workspace.bronze.coinbase_bronze   <- you are here
```

**What it is.** The existing Bronze streaming table. New rows are appended to it on each pipeline run.

**Why we need it.** Bronze is the first queryable, governed copy of the raw data, with ingestion metadata added.

**How it connects.** It is the end of the ingestion chain. The pipeline from 5.4 is reused, so each S3 file adds rows to the same table and does not create a new table.

**Verification.** After real files landed in S3, the pipeline was run. It completed successfully and reported **256 output records** to `workspace.bronze.coinbase_bronze`.

Observed columns: `source`, `test`, `_rescued_data`, `ingestion_timestamp`, `source_file`, `channel`, `events`, `sequence_num`, `timestamp`. The `source` and `test` columns come from the earlier test row, which is still in the table. The real Coinbase records were appended after it and have `source_file` pointing to the date-partitioned S3 paths.

**Issue and fix.** None. The table now holds both the test-row columns and the Coinbase columns; `_rescued_data` captures values that do not fit the inferred schema.

**Interview concept.** Bronze keeps the raw shape (nested `events` array stays nested) and adds only lineage metadata (`ingestion_timestamp`, `source_file`). Cleaning, flattening, typing, and deduplication belong in Silver.

### 5.5.10 — Completion Check and Limits

The completion check for 5.5 is met: live Coinbase events, not a hand-made file, reached S3 and appeared in Bronze.

Not yet implemented in the consumer (from the original plan):

- Automatic reconnect when the WebSocket drops.
- Retry on failed S3 uploads.
- Size-based or timer-based flush.

Job orchestration and scheduling were added afterward in 5.8, and the consumer's stopped-state is now monitored. The auto-restart and hardening items were added afterward in 5.9.

## Sub-Phase 5.6 — Silver Delta

Silver turns the raw, nested Bronze rows into one clean, typed row per BTC-USD price update. It lives in the same `data-engineering-pipeline` as Bronze, so one pipeline update runs Bronze first and then Silver. The pieces below follow the order of the code in `src/silver/silver_pipeline.py`.

Progressive Silver architecture:

```text
Bronze table
   -> 5.6.1 read as a stream
   -> 5.6.2 parse the JSON text
   -> 5.6.3 explode events and tickers
   -> 5.6.4 cast types and timestamps
   -> 5.6.5 quality rules
   -> 5.6.6 deduplicate
   -> 5.6.7 write workspace.silver.coinbase_ticker
```

Real data read from S3 (257 raw lines): 255 `update` messages, 1 `snapshot` (`sequence_num` 0), 1 test row. Every message had exactly 1 event with exactly 1 ticker, and `sequence_num` was unique within the session (0 to 256). One raw message looks like this:

```json
{"channel": "ticker", "timestamp": "2026-10-04T05:50:33.553456409Z", "sequence_num": 216,
 "events": [{"type": "update", "tickers": [{"product_id": "BTC-USD", "price": "84895.29",
   "best_bid": "84895.29", "best_ask": "84895.3", "volume_24_h": "1806.10224538", "...": "..."}]}]}
```

### 5.6.1 — Read Bronze as a Stream

```text
workspace.bronze.coinbase_bronze
        | dp.read_stream("coinbase_bronze")
        v
Silver flow (new Bronze rows only)   <- you are here
```

1. **What it is.** A streaming read of the Bronze table inside the pipeline. Each update reads only the Bronze rows added since the previous update.
2. **Why we need it.** Silver must grow with Bronze without reprocessing history. A batch read of the whole table would redo every row on every run and risk duplicates.
3. **How it connects.** Bronze (5.4) is the upstream table. Because both live in the same pipeline, Lakeflow knows Silver depends on Bronze and runs Bronze first.
4. **Code.**
   ```python
   dp.read_stream("coinbase_bronze")
   ```
   `resources/pipeline.yml` registers the Silver file as a second library:
   ```yaml
   libraries:
     - file:
         path: ../src/bronze/bronze_pipeline.py
     - file:
         path: ../src/silver/silver_pipeline.py
   ```
5. **Issue.** None in this step.
6. **Fix.** Not needed.
7. **Interview concept.** Streaming table reading another table incrementally; dependency ordering inside one declarative pipeline.

### 5.6.2 — Parse the JSON Text in `events`

```text
Bronze row: events = '[{"type":"update","tickers":[...]}]'   (a STRING)
        | from_json(events, EVENTS_SCHEMA)
        v
events as a real array of structs   <- you are here
```

1. **What it is.** `from_json` with an explicit schema (`TICKER_SCHEMA`, `EVENTS_SCHEMA`) that converts the text in `events` into an array of structs.
2. **Why we need it.** Auto Loader reads JSON fields as text by default, so Bronze stores `events` as a string. A string cannot be exploded or queried by field.
3. **How it connects.** It takes the `events` column from the Bronze stream in 5.6.1 and hands a typed array to the explode steps in 5.6.3.
4. **Code.**
   ```python
   TICKER_SCHEMA = StructType([StructField(name, StringType()) for name in
       ["type", "product_id", "price", "volume_24_h", "low_24_h", "high_24_h",
        "low_52_w", "high_52_w", "price_percent_chg_24_h",
        "best_bid", "best_ask", "best_bid_quantity", "best_ask_quantity"]])
   EVENTS_SCHEMA = ArrayType(StructType([
       StructField("type", StringType()),
       StructField("tickers", ArrayType(TICKER_SCHEMA)),
   ]))
   from_json(col("events"), EVENTS_SCHEMA)
   ```
   All ticker fields are read as strings first and cast in 5.6.4.
5. **Issue.** The first Silver update failed: `Cannot resolve "explode(events)" ... "events" has the type "STRING"`. A failed update then sat in `RETRY_ON_FAILURE`.
6. **Fix.** Parse in Silver with an explicit schema and leave Bronze unchanged. Stop the retrying update (`databricks pipelines stop <pipeline-id>`), deploy the fix, and run again.
7. **Interview concept.** Auto Loader infers JSON columns as strings unless `cloudFiles.inferColumnTypes` is enabled. Keeping Bronze raw and parsing in Silver is a deliberate design choice.

### 5.6.3 — Explode `events` and `tickers`

```text
one message (events[ tickers[ ... ] ])
        | explode(events) -> explode(tickers)
        v
one row per ticker update   <- you are here
```

1. **What it is.** `explode` turns each array element into its own row, first for `events` and then for the nested `tickers`.
2. **Why we need it.** The price is nested two levels deep (`events[].tickers[]`). Analysts need one flat row per price update.
3. **How it connects.** It consumes the parsed array from 5.6.2 and produces the flat `ticker` struct that 5.6.4 casts.
4. **Code.**
   ```python
   explode(from_json(col("events"), EVENTS_SCHEMA)).alias("event")
   ...
   explode(col("event.tickers")).alias("ticker")
   ```
   It also filters `col("channel") == "ticker"`, which removes the old `test.json` row (it has no `channel`). The `snapshot` message is kept and tagged in the `event_type` column.
5. **Issue.** None.
6. **Fix.** Not needed.
7. **Interview concept.** `explode` changes the grain of the data: one message with N tickers becomes N rows. Always state the grain of a table.

### 5.6.4 — Cast Types and Fix the Timestamp

```text
price = "84895.29"  (string)       timestamp = "...33.553456409Z" (nanoseconds)
        | try_cast -> DECIMAL              | trim to microseconds -> TIMESTAMP
        v
price = 84895.29000000             event_time = 2026-10-04 05:50:33.553456   <- you are here
```

1. **What it is.** Converts strings to proper types: prices and volumes to `DECIMAL`, the timestamp to `TIMESTAMP`, `sequence_num` to `BIGINT`.
2. **Why we need it.** You cannot average, compare, or sort text prices. Spark timestamps hold microseconds, but Coinbase sends nanoseconds, so the extra digits must be trimmed.
3. **How it connects.** It reads the flat `ticker` fields from 5.6.3 and feeds typed columns to the quality rules in 5.6.5.
4. **Code.**
   ```python
   def to_decimal(name, precision=18, scale=8):
       return expr(f"try_cast({name} as decimal({precision},{scale}))")

   to_timestamp(regexp_replace(col("timestamp"), r"(\.\d{6})\d*Z$", "$1Z")).alias("event_time")
   col("sequence_num").cast("bigint")
   ```
   `try_cast` returns `NULL` for a bad value instead of crashing the whole pipeline.
5. **Issue.** None observed. `DECIMAL` (not `DOUBLE`) was chosen to avoid floating-point error on money values.
6. **Fix.** Not needed.
7. **Interview concept.** Use `DECIMAL` for prices. `try_cast` plus a quality rule means one bad record is dropped and counted instead of failing the pipeline.

### 5.6.5 — Quality Rules (Expectations)

```text
typed rows
        | expect_all_or_drop(4 rules)
        v
only valid rows continue   <- you are here
        (failing rows dropped and counted on the Data quality tab)
```

1. **What it is.** Declarative data-quality rules attached to the Silver table.
2. **Why we need it.** Silver is the trusted layer. Rows with no time, no product, a zero or negative price, or a bid above the ask would corrupt Gold analysis.
3. **How it connects.** It runs after the casts in 5.6.4, because a failed `try_cast` produces `NULL` and is caught here.
4. **Code.**
   ```python
   @dp.expect_all_or_drop({
       "event_time_not_null": "event_time IS NOT NULL",
       "product_id_not_null": "product_id IS NOT NULL",
       "price_positive": "price > 0",
       "bid_not_above_ask": "best_bid <= best_ask",
   })
   ```
5. **Issue.** None. The 256 real rows passed all four rules.
6. **Fix.** Not needed. Dropped-row counts per rule appear on the pipeline's Data quality tab, so a rule that suddenly drops many rows is a signal to investigate.
7. **Interview concept.** Expectations: `expect` (log only), `expect_or_drop` (drop), `expect_or_fail` (stop the pipeline). Choose the action by how bad the failure is.

### 5.6.6 — Deduplicate

```text
rows (possibly repeated)
        | withWatermark(event_time, 1 hour) + dropDuplicatesWithinWatermark
        v
unique (product_id, event_time, sequence_num)   <- you are here
```

1. **What it is.** Removes repeated rows using a business key.
2. **Why we need it.** The same message could appear twice, for example if a raw file is re-ingested after a rebuild.
3. **How it connects.** It is the last transformation before the table write. The watermark on `event_time` lets Spark forget old keys, so state does not grow forever.
4. **Code.**
   ```python
   .withWatermark("event_time", "1 hour")
   .dropDuplicatesWithinWatermark(["product_id", "event_time", "sequence_num"])
   ```
   The key includes `event_time` and not only `sequence_num`, because `sequence_num` is tied to a WebSocket connection and can be expected to restart after a reconnect. That was reasoned from how the feed works; it has not yet been observed across a reconnect.
5. **Issue.** None observed. The 256 Silver rows had 256 distinct `sequence_num` values.
6. **Fix.** Not needed.
7. **Interview concept.** Streaming deduplication needs a watermark to bound state. Choose a key that is unique in the business sense. Silver is also protected upstream because Auto Loader never re-reads a processed file.

### 5.6.7 — Write `workspace.silver.coinbase_ticker`

```text
valid, unique rows
        | @dp.table(name="workspace.silver.coinbase_ticker")
        v
workspace.silver.coinbase_ticker   <- you are here
```

1. **What it is.** The Silver streaming table, published to its own schema (`workspace.silver`) even though the pipeline default schema is `bronze`.
2. **Why we need it.** It is the clean, queryable, analysis-ready layer that Gold will read.
3. **How it connects.** It is the end of the Silver flow and the input to Gold (5.7, later).
4. **Code.**
   ```python
   @dp.table(name="workspace.silver.coinbase_ticker", table_properties={"quality": "silver"})
   ```
   Output columns: `product_id, event_time, sequence_num, event_type, price, best_bid, best_ask, best_bid_quantity, best_ask_quantity, volume_24h, high_24h, low_24h, high_52w, low_52w, price_pct_chg_24h, ingestion_timestamp, source_file`.
5. **Issue.** `Schema 'workspace.silver' does not exist`.
6. **Fix.**
   ```bash
   databricks schemas create silver workspace
   databricks bundle deploy --target dev
   databricks bundle run data_engineering_pipeline --target dev
   ```
7. **Interview concept.** Unity Catalog naming (`catalog.schema.table`); one pipeline can publish to several schemas by fully qualifying the table name. Keep `source_file` and `ingestion_timestamp` for lineage.

**Verification.**

| Check | Result |
| --- | --- |
| Bronze rows | 257 |
| Silver rows | 256 (the test row is excluded) |
| Distinct `sequence_num` in Silver | 256, no duplicates |
| `price` range | 84,889.97 to 84,897.99 |
| Snapshot rows | 1 |

Example Silver row: `BTC-USD | 2026-10-04T05:50:52.053Z | price 84895.29 | best_bid 84895.29 | best_ask 84895.30 | sequence_num 256`.

## Sub-Phase 5.8 — Job Orchestration and Alerting

Two Databricks jobs, both defined in the bundle, run independently. They are built piece by piece below.

Progressive architecture for 5.8:

```text
5.8.1 Job + schedule        -> triggers the pipeline every 15 minutes
5.8.2 Task retries          -> 3 attempts before the run is called failed
5.8.3 Failure email         -> pipeline problems
5.8.4 Catch-up behavior     -> why gaps and re-runs are safe
5.8.5 Consumer health check -> separate job watching S3 freshness
5.8.6 Two different alerts  -> pipeline failure vs consumer failure
```

```text
Consumer (EC2) --> S3 --> coinbase-bronze-job (every 15 min) --> Bronze --> Silver
                    |
                    +--> coinbase-consumer-health-check (every 15 min) --> alert if S3 is stale
```

### 5.8.1 — Job and Schedule

```text
Schedule (every 15 min, UTC)
        |
        v
coinbase-bronze-job   <- you are here
        | pipeline_task
        v
data-engineering-pipeline (Bronze -> Silver)
```

1. **What it is.** A Databricks Job defined in `resources/job.yml` with one task that starts the pipeline.
2. **Why we need it.** A pipeline does not run by itself. The job decides when new S3 files are appended to Bronze and Silver.
3. **How it connects.** The task points at the pipeline resource from 5.4 using a bundle reference, so the bundle deploys both in the right order.
4. **Code.**
   ```yaml
   resources:
     jobs:
       coinbase_bronze_job:
         name: coinbase-bronze-job
         schedule:
           quartz_cron_expression: "0 0/15 * * * ?"   # :00, :15, :30, :45 UTC
           timezone_id: UTC
           pause_status: UNPAUSED
         max_concurrent_runs: 1
         tasks:
           - task_key: run_bronze_pipeline
             pipeline_task:
               pipeline_id: ${resources.pipelines.data_engineering_pipeline.id}
   ```
   - **Interval.** Every 15 minutes, so data reaches Silver up to 15 minutes after it lands in S3. Each run uses serverless compute, so the interval is also a cost choice.
   - **No overlap.** `max_concurrent_runs: 1`.
   - **Safe rollout.** The schedule was first deployed `PAUSED`, tested with a manual run (it succeeded), then unpaused.
5. **Issue.** A cron edit made with `sed` did not match, so the job was unpaused while still on its old schedule.
6. **Fix.** Edit the YAML directly, check the file contents, then redeploy.
7. **Interview concept.** Job vs pipeline (the job schedules, the pipeline transforms). Bundle-managed jobs should be changed in YAML and redeployed, because edits in the UI are overwritten by the next deploy.

### 5.8.2 — Task Retries

```text
run_bronze_pipeline fails
        | wait 60 s -> retry (up to 3 times)
        v
success, or the run is marked failed   <- you are here
```

1. **What it is.** A retry policy on the pipeline task.
2. **Why we need it.** Most pipeline failures are brief (a cloud blip, a cluster start problem). Retrying avoids an email for something that fixes itself.
3. **How it connects.** It sits on the task from 5.8.1; the failure email in 5.8.3 is sent only after the retries are used up.
4. **Code.**
   ```yaml
   max_retries: 3
   min_retry_interval_millis: 60000
   retry_on_timeout: true
   ```
5. **Issue.** None.
6. **Fix.** Not needed.
7. **Interview concept.** Retry policies handle transient errors; they do not fix bad code. A permanent error (like the Silver `STRING` error) fails every attempt.

### 5.8.3 — Failure Email

```text
run fails after all retries
        | email_notifications.on_failure
        v
pareshranjan7327@gmail.com   <- you are here
```

1. **What it is.** An email sent when the job run fails.
2. **Why we need it.** The job runs unattended, including overnight.
3. **How it connects.** It is attached to the job in 5.8.1 and fires after the retries in 5.8.2.
4. **Code.**
   ```yaml
   email_notifications:
     on_failure:
       - pareshranjan7327@gmail.com
   ```
   Only failures are configured. A success email every 15 minutes would bury the important one.
5. **Issue.** None. No test email was forced from this job.
6. **Fix.** Not needed.
7. **Interview concept.** Alert on failure, not on success, to avoid alert fatigue.

### 5.8.4 — Catch-Up and No-Duplicate Behavior

```text
pipeline down 10:00 -> consumer keeps writing files to S3 -> pipeline succeeds 10:15
        | Auto Loader checkpoint remembers processed files
        v
only the files that arrived in between are ingested   <- you are here
```

1. **What it is.** Built-in behavior of the existing pipeline, not extra code.
2. **Why we need it.** It guarantees a failed run loses nothing and a re-run duplicates nothing.
3. **How it connects.** Bronze uses Auto Loader (5.4), which stores the list of processed files in the pipeline checkpoint. Silver (5.6.1) reads only new Bronze rows.
4. **Configuration.** None beyond the pipeline itself. Evidence: Bronze stayed at 257 rows and Silver at 256 across several job runs while the consumer was stopped.
5. **Issue.** Counts stayed at 257 after job runs and looked like nothing was happening.
6. **Fix.** Nothing was broken: the consumer was stopped, so no new S3 files existed. Restarting the consumer resumed growth, and 5.8.5 now alerts on this case.
7. **Interview concept.** Checkpointing gives incremental, exactly-once-style file ingestion. A **Full refresh** clears the checkpoint and rebuilds everything, so avoid it unless a rebuild is intended.

### 5.8.5 — Consumer Health Check

```text
EC2 consumer --> S3 raw files
                    | newest file older than 10 min?
                    v
coinbase-consumer-health-check   <- you are here
        | fails -> email
```

1. **What it is.** A second job (`resources/monitoring_job.yml`) that runs `src/monitoring/consumer_freshness_check.py`. It reads S3 directly and exits with an error if the newest raw file is more than 10 minutes old.
2. **Why we need it.** If the consumer dies, `coinbase-bronze-job` still reports SUCCESS because it finds nothing new. Without this job there would be no email, and ticks sent by Coinbase while the consumer is down are lost permanently.
3. **How it connects.** It watches the output of the consumer (5.5), not the pipeline, so it works even when the pipeline is broken.
4. **Code.**
   ```yaml
   coinbase_consumer_health_check:
     name: coinbase-consumer-health-check
     schedule:
       quartz_cron_expression: "0 7/15 * * * ?"   # :07, :22, :37, :52 UTC
       pause_status: UNPAUSED
     email_notifications:
       on_failure: [pareshranjan7327@gmail.com]
     environments:
       - environment_key: default
         spec:
           environment_version: "3"
     tasks:
       - task_key: check_consumer_is_writing_to_s3
         environment_key: default
         spark_python_task:
           python_file: ../src/monitoring/consumer_freshness_check.py
   ```
   The script checks today's and yesterday's folders and fails with `ALERT: the Coinbase consumer looks stopped` when stale.
5. **Issue.** `Task requires a cluster or an environment`.
6. **Fix.** A Python task on serverless needs an `environments` entry with a matching `environment_key`.
7. **Interview concept.** Data freshness monitoring: "job succeeded" is not the same as "data is fresh". Monitor each stage independently.

**Verification.** With the consumer stopped, the test run failed with the alert message (newest file about 677 minutes old). After the consumer was restarted, new files appeared in S3 within seconds.

**Limits.** Emails repeat about every 15 minutes while the consumer is down. This only alerts; it does not restart the consumer. Email text cannot be customized, so the job and task names carry the context.

### 5.8.6 — Two Different Alerts

```text
Coinbase -> [EC2 consumer] -> S3 -> [Databricks job/pipeline] -> Bronze -> Silver
              alert A: consumer-health-check     alert B: coinbase-bronze-job
```

1. **What it is.** Two independent failure signals with different meanings.
2. **Why we need it.** The consumer and the pipeline fail independently and have different consequences.
3. **How it connects.** Alert A watches the S3 landing zone from 5.5; alert B watches the Databricks run from 5.8.1.
4. **Comparison.**

   | | Consumer | Pipeline / job |
   | --- | --- | --- |
   | Runs on | EC2 Python process | Databricks serverless |
   | Does | Coinbase to S3 | S3 to Bronze to Silver |
   | If it fails | No new files; ticks from the outage are lost for good | Files stay in S3; the next good run catches up |
   | Alert email | job `coinbase-consumer-health-check` | job `coinbase-bronze-job` |
   | Runs at (UTC) | `:07/:22/:37/:52` | `:00/:15/:30/:45` |

   The schedules are offset on purpose so the two emails do not arrive together.
5. **Issue.** The health check showed red marks on the Jobs page while the consumer was still down, which looked like a bug.
6. **Fix.** It was working correctly. The red runs were from before the consumer was restarted. Restart the consumer (for example in `tmux`), and the next health check passes.
7. **Interview concept.** Consumer failure loses data; pipeline failure delays data. Alert on both, separately. Auto-restart (`systemd`), reconnect, and upload retry were added in 5.9.

## Sub-Phase 5.9 — Consumer Reliability

Until now the consumer was a script run by hand in a terminal. The Phase 5.8 health check could tell you it was down, but nothing brought it back, and any WebSocket or S3 error ended it. 5.9 makes the consumer run as a supervised service that survives drops and errors.

Failure modes and the piece that handles each:

| Failure | Piece |
| --- | --- |
| Terminal closed, SSH or VS Code dropped, EC2 reboot, crash | 5.9.1 systemd service |
| WebSocket drops, or goes silently dead | 5.9.2 reconnect with backoff and ping |
| An S3 upload fails | 5.9.3 upload retry |
| S3 stays unreachable | 5.9.4 disk spool and buffer cap |
| Service stop or restart | 5.9.5 graceful flush on SIGTERM |
| Two batches in the same second | 5.9.6 unique file names |

Progressive architecture:

```text
systemd (supervisor)
   -> consumer process
        -> reconnect loop (WebSocket)
        -> event buffer
        -> upload with retry -> S3 raw
        -> disk spool if S3 stays down
   -> health check (5.8.5) is the last line of defense
```

All code is in `src/ingestion/coinbase_websocket_consumer.py`; the service definition is `deploy/coinbase-consumer.service`.

### 5.9.1 — systemd Service

```text
EC2 boot / crash / terminal closed
        |
        v
systemd  --starts and restarts-->  consumer process   <- you are here
```

1. **What it is.** systemd is the Linux service manager. A unit file describes the program; systemd runs it in the background, starts it at boot, and restarts it when it exits.
2. **Why we need it.** A manual `python3` run dies when the terminal closes and never comes back after a reboot. `tmux` survives a closed terminal but not a reboot or a crash.
3. **How it connects.** It supervises the consumer from 5.5. The consumer still uses the EC2 IAM role, because the service runs as the `ubuntu` user on the instance.
4. **Configuration.** `deploy/coinbase-consumer.service`:
   ```ini
   [Unit]
   Description=Coinbase WebSocket consumer (BTC-USD ticker to S3 raw)
   After=network-online.target
   Wants=network-online.target

   [Service]
   User=ubuntu
   WorkingDirectory=/home/ubuntu/data-engineering-devops-stack
   ExecStart=/home/ubuntu/data-engineering-devops-stack/.venv/bin/python -u src/ingestion/coinbase_websocket_consumer.py
   Restart=always
   RestartSec=5
   KillSignal=SIGTERM
   TimeoutStopSec=60

   [Install]
   WantedBy=multi-user.target
   ```
   - `Restart=always` with `RestartSec=5`: restart 5 seconds after any exit.
   - `python -u`: unbuffered output, so logs appear in the journal immediately.
   - The `.venv` Python is used so `websocket-client` and `boto3` are available.

   Install and operate:
   ```bash
   sudo cp deploy/coinbase-consumer.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now coinbase-consumer   # start now and on every boot
   systemctl status coinbase-consumer
   journalctl -u coinbase-consumer -f              # live logs
   sudo systemctl restart coinbase-consumer        # after a code change
   ```
5. **Issue.** Running a second copy of the consumer (the old terminal one plus the service) would write every tick twice. The two connections have different `sequence_num` values, so Silver's dedup key would not remove the duplicates.
6. **Fix.** Stop the terminal copy (`Ctrl+C`) before starting the service, and run only one consumer.
7. **Interview concept.** Service supervision and auto-restart (the same idea as Kubernetes restarting a crashed pod); systemd as the process manager on Linux.

### 5.9.2 — WebSocket Reconnect with Backoff and Ping

```text
Coinbase WebSocket  -- drops -->  consumer
        ^                            |
        +---- reconnect (1, 2, 4 ... 60 s) ----+   <- you are here
```

1. **What it is.** A loop around `ws.run_forever()` that reconnects after any disconnect, with exponential backoff, and a ping/pong heartbeat.
2. **Why we need it.** `run_forever()` returns when the connection closes, so the old script simply ended. A connection can also go silently dead: still open, but delivering nothing.
3. **How it connects.** `on_open` already sends the subscribe message, so every reconnect re-subscribes automatically. Before reconnecting, `on_close` flushes the buffer from 5.5.3.
4. **Code.**
   ```python
   delay = RECONNECT_MIN_SECONDS            # 1
   while not shutting_down:
       ws = websocket.WebSocketApp(WS_URL, on_open=..., on_message=..., on_error=..., on_close=...)
       connected_at = time.time()
       ws.run_forever(ping_interval=20, ping_timeout=10)
       if time.time() - connected_at >= STABLE_CONNECTION_SECONDS:   # 60
           delay = RECONNECT_MIN_SECONDS    # a long-lived connection resets the backoff
       time.sleep(delay)
       delay = min(delay * 2, RECONNECT_MAX_SECONDS)   # 1, 2, 4 ... 60
   ```
5. **Issue.** Events sent while disconnected are lost. Coinbase does not replay ticker history, and after a reconnect `sequence_num` restarts, which is why Silver's dedup key includes `event_time`.
6. **Fix.** Not fixable at the client; keep reconnect gaps short with a small initial delay. The health check (5.8.5) still alerts on a longer outage.
7. **Interview concept.** Exponential backoff, heartbeats/keepalives to detect half-open connections, and best-effort versus at-least-once delivery.

### 5.9.3 — S3 Upload Retry

```text
event buffer -> put_object ... fails -> wait 2, 4, 8, 16 s -> retry (5 attempts)   <- you are here
```

1. **What it is.** `upload()` retries `put_object` up to 5 times with growing waits. The boto3 client also has its own `standard` retry mode (`max_attempts` 5).
2. **Why we need it.** In the old code an S3 error raised an exception and lost the buffered events.
3. **How it connects.** It sits between the buffer (5.5.3) and S3. The batch is cleared from memory only after a successful upload.
4. **Code.**
   ```python
   def upload(key, body):
       for attempt in range(1, UPLOAD_ATTEMPTS + 1):
           try:
               s3.put_object(Bucket=S3_BUCKET, Key=key, Body=body, ContentType="application/json")
               return True
           except Exception as error:
               print(f"S3 upload failed (attempt {attempt}/{UPLOAD_ATTEMPTS}): {error}")
               if attempt < UPLOAD_ATTEMPTS:
                   time.sleep(2**attempt)
       return False
   ```
5. **Issue.** The retry waits run inside the WebSocket callback, so up to about 30 seconds of retrying can block message reading. Pings may time out and trigger a reconnect.
6. **Fix.** Accepted for now: the reconnect loop (5.9.2) recovers, and failed batches are kept by the spool (5.9.4). A queue and a separate uploader thread would remove the blocking.
7. **Interview concept.** Retry with backoff, and not discarding data until it is durably stored.

### 5.9.4 — Disk Spool and Buffer Cap

```text
upload fails after all retries -> /var/tmp/coinbase_spool/<key>   <- you are here
next successful flush (or restart) -> upload spooled files first-in, then delete
```

1. **What it is.** When all retries fail, the batch is written to local disk. The next successful flush, and every service start, uploads spooled batches. The in-memory buffer is also capped at 50,000 events (oldest dropped).
2. **Why we need it.** If S3 is unreachable for a while, retrying forever would grow memory without limit, and dropping the batch loses data.
3. **How it connects.** It is the fallback for 5.9.3. The spooled file keeps its intended S3 key (with `/` replaced by `__`), so it lands in the right time folder when it is finally uploaded.
4. **Code.**
   ```python
   SPOOL_DIR = Path("/var/tmp/coinbase_spool")
   MAX_BUFFER_EVENTS = 50_000

   if upload(key, body):
       event_buffer = []
       upload_spooled_batches()
   else:
       spool_batch(key, body)
       event_buffer = []
   ```
5. **Issue.** The spool does not protect against a hard crash (`kill -9`, power loss, instance failure) between flushes: up to about 15 seconds of events in memory are lost.
6. **Fix.** Accepted limit. Writing every event to disk before buffering would remove it at the cost of more I/O and code.
7. **Interview concept.** Bounded buffers and spill-to-disk, and the difference between a memory buffer (fast, volatile) and a durable log.

### 5.9.5 — Graceful Flush on Stop

```text
systemctl stop/restart -> SIGTERM -> KeyboardInterrupt -> on_close + final flush -> exit
```

1. **What it is.** A SIGTERM handler that turns a service stop into the same shutdown path as `Ctrl+C`.
2. **Why we need it.** systemd stops a service with SIGTERM, which by default kills Python without running `on_close`. The buffered events would be lost on every restart or deploy.
3. **How it connects.** It extends the graceful flush from 5.5.7 to the service world.
4. **Code.**
   ```python
   def handle_stop_signal(signum, frame):
       global shutting_down
       shutting_down = True
       raise KeyboardInterrupt

   signal.signal(signal.SIGTERM, handle_stop_signal)
   ...
   finally:
       flush_buffer()
       print("Consumer stopped")
   ```
   `TimeoutStopSec=60` in the unit gives the flush time to finish.
5. **Issue.** None observed.
6. **Fix.** Not needed.
7. **Interview concept.** Signal handling and graceful shutdown (SIGTERM versus SIGKILL).

### 5.9.6 — Unique File Names

1. **What it is.** The S3 key now includes microseconds: `events_YYYYMMDD_HHMMSS_ffffff.json`.
2. **Why we need it.** A batch replayed from the spool and a new batch can be written in the same second. With second-level names the second `put_object` silently overwrites the first.
3. **How it connects.** It changes only the file name from 5.5.6; the `coinbase/raw/YYYY/MM/DD/HH/` folders are the same, so Auto Loader and the health check are unaffected.
4. **Code.** `f"{S3_PREFIX}/{now:%Y/%m/%d/%H}/events_{now:%Y%m%d_%H%M%S_%f}.json"`
5. **Issue.** Found by the spool replay test: two batches written in the same second produced one object instead of two.
6. **Fix.** Add microseconds to the name.
7. **Interview concept.** Idempotent and collision-free object naming; silent overwrites are a data-loss risk in object storage.

### 5.9.7 — Verification

Tested with a mocked S3 client and a mocked WebSocket (no network):

| Test | Result |
| --- | --- |
| Upload fails twice then succeeds | One file written, buffer cleared, nothing spooled |
| Upload fails all 5 attempts | Batch spooled to disk, buffer cleared |
| S3 recovers on the next flush | New batch and spooled batch both uploaded, spool emptied |
| WebSocket closes twice, then stop | 3 connections made, loop exits cleanly, final flush runs |
| More than 50,000 events buffered | Buffer capped at 50,000 |

Live checks on EC2 (service installed and enabled with `systemctl enable`):

| Test | Result |
| --- | --- |
| `systemctl start coinbase-consumer` | `active`; the journal showed Connected, Subscribed, then `Wrote 51 events` and `Wrote 42 events` about 15 seconds apart, and the files appeared in S3 |
| `systemctl kill -s SIGKILL` (simulated crash) | New process ID (29000 to 29108) and state `active` about 9 seconds later, with `RestartSec=5` |
| `systemctl restart` (graceful stop) | Journal showed `Received signal 15; flushing and stopping`, then `Wrote 39 events`, `Consumer stopped`, and a clean start; no events lost at the stop |
| `systemctl is-enabled` | `enabled`, so the service starts on boot |

Operating notes: the old terminal copy had stopped before the service was started, so only one consumer ran. A harmless `WebSocket error:` line with an empty message appears in the log during a SIGTERM stop. A live reconnect after a real network drop was not simulated; that path was tested only with the mocked WebSocket.

**Remaining limits.** Up to about 15 seconds of events are lost on a hard crash; events during a WebSocket gap are lost; and a long S3 outage is only covered up to what fits on local disk. The health check (5.8.5) remains the final alert.

## Future Sub-Phases — Build Separately

### Sub-Phase 5.7 — Gold Delta

**Status: moved to Phase 7.** Build business-facing aggregates from the validated Silver data; agree on the use cases and grain before defining tables.

```text
Silver Delta -> business rules/aggregations -> Gold Delta
```

Completion check: each Gold table has an identified consumer, documented grain, and repeatable transformation from Silver.

CI/CD is covered in Phase 9.

## Current End-to-End Architecture

Final combined Phase 5 source-to-Bronze flow:

```text
Coinbase WebSocket (wss://advanced-trade-ws.coinbase.com, BTC-USD ticker)
  |
  v
AWS EC2  (VS Code Remote SSH from laptop; Python / uv / AWS CLI / Databricks CLI)
  |-- src/ingestion/coinbase_websocket_consumer.py
  |     websocket-client -> event buffer (~15 s) -> one JSON batch file
  |     boto3 put_object()
  |-- EC2 role: PareshCoinbaseEC2S3Role (temporary credentials, no access keys)
  v
Amazon S3: coinbase/raw/YYYY/MM/DD/HH/events_YYYYMMDD_HHMMSS_ffffff.json
  | Unity Catalog Storage Credential
  |   -> PareshDatabricksCoinbaseS3ReadAccess
  |   -> External Location: coinbase_raw_external_location
  v
Auto Loader (cloudFiles) -> serverless Lakeflow pipeline (data-engineering-pipeline)
  v
workspace.bronze.coinbase_bronze     (256 output records in the verified run)
  v
Silver Delta: workspace.silver.coinbase_ticker  (same pipeline, runs after Bronze)
  v
Gold Delta (future)

Scheduled by: coinbase-bronze-job (every 15 min, 3 retries, failure email)
Monitored by: coinbase-consumer-health-check (alert if S3 is stale > 10 min)
```

Two separate AWS roles are involved. The EC2 role writes to S3; the Databricks role reads from S3.

| Connection | Mechanism | Purpose |
| --- | --- | --- |
| Coinbase -> EC2 | websocket-client | Receive live BTC-USD ticker events |
| EC2 -> S3 | boto3 + EC2 IAM role | Durable raw landing |
| S3 -> Databricks | Storage Credential + External Location | Secure read access |
| External Location -> Bronze | Auto Loader + Lakeflow pipeline | Incremental append |

## Issues Faced

| Issue | Root cause | Fix |
| --- | --- | --- |
| `aws: command not found` | AWS CLI was not installed on EC2. | Install AWS CLI v2 using the official AWS ZIP installer. |
| Ubuntu `awscli` package unavailable | The configured Ubuntu package repositories had no install candidate. | Use the official AWS CLI v2 installer. |
| `sudo ./aws/install` failed | The installer directory did not exist because the ZIP had not been extracted. | Run `unzip awscliv2.zip` before the installer. |
| Bundle deployment reported zero resources | The resource YAML files were not included in the bundle. | Add `include: - resources/*.yml` to `databricks.yml`. |
| Workspace required serverless compute | The pipeline did not specify serverless. | Set `serverless: true`. |
| Pipeline required a catalog and schema | Unity Catalog target fields were missing. | Set `catalog: workspace` and `schema: bronze`. |
| Catalog `main` did not exist | The workspace had no catalog with that name. | Inspect available catalogs and use `workspace`. |
| Pipeline hit `LOCATION_OVERLAP` | The initial code manually configured Structured Streaming checkpoint/output state inside a managed Lakeflow pipeline. | Use the pipeline-native `@dp.table` function and let Lakeflow manage state. |
| `input_file_name()` unsupported with Unity Catalog | That function is unsupported in this pipeline context. | Read `col("_metadata.file_path")`. |
| Automatic file-event setup failed on `s3:GetBucketNotification` | The Databricks role is read-only for raw data and lacks notification provisioning permissions. | Keep core read/list access; do not rely on automatic file events yet. |
| `python: command not found` when starting the consumer | EC2 has `python3` and no `python` alias. | Run `python3 src/ingestion/coinbase_websocket_consumer.py`. |
| `git push -m` rejected | `-m` is a `git commit` option for the message. | `git commit -m "message"`, then `git push`. |
| Typing `pyproject.toml` or `uv.lock` in Bash failed | A bare file name is run as a command. | Use `cat` to view or `nano` to edit. |
| `Schema 'workspace.silver' does not exist` | The Silver schema had not been created. | `databricks schemas create silver workspace`. |
| `explode(events)` failed: `events` is `STRING` | Auto Loader reads JSON fields as text by default. | Parse with `from_json` and an explicit schema in Silver. |
| Update stuck in `RETRY_ON_FAILURE` | Pipeline auto-retried broken code. | Stop the pipeline, deploy the fix, run again. |
| Job cron change did not apply, job unpaused on the old 15-minute schedule | The `sed` pattern did not match. | Edit the YAML directly and redeploy; check the file before deploying. |
| `Task requires a cluster or an environment` | A Python task on serverless needs an environment. | Add `environments` and `environment_key`. |
| Push failed with `ECONNREFUSED ...vscode-git....sock` | Terminal held a stale VS Code credential-helper socket. | Open a new terminal or use a personal access token. |
| Count stayed at 257 after job runs | The consumer was stopped, so no new S3 files. | Run the consumer persistently; 5.8.2 now alerts on this. |

## Phase 5 Status Checklist

```text
✅ 5.1 Asset Bundle, dev target, resource include, and validation
✅ 5.2 EC2 role, AWS CLI, and S3 raw-prefix list/write tests
✅ 5.3 Databricks Storage Credential and External Location
✅ 5.4 Serverless Auto Loader pipeline and test JSON ingestion to Bronze
✅ 5.5 Live Coinbase WebSocket consumer, real events in S3, and 256 real-event records in Bronze
✅ 5.6 Silver transformations and data-quality rules (workspace.silver.coinbase_ticker)
✅ 5.8 Scheduled job (15 min), 3 retries, failure email, consumer health-check alert

➡️ 5.7 Gold business transformations: moved to Phase 7
✅ 5.9 Consumer reliability: systemd service, reconnect, upload retry, disk spool
➡️ CI/CD with GitHub Actions: Phase 9
```

Phase 5 is complete. Live Coinbase events are verified in Bronze and Silver; the Gold table is built in Phase 7. The consumer runs under systemd with reconnect and upload retry (5.9); a hard crash can still lose up to about 15 seconds of buffered events.

## What I Learned

- Databricks Asset Bundles separate project configuration, deployment targets, and resources.
- Bundle validation checks configuration without deploying resources.
- Source code and bundle-managed resources belong in distinct folders.
- A continuously connected WebSocket consumer needs a durable landing layer for downstream processing.
- EC2 instance roles provide temporary credentials and avoid long-lived AWS access keys.
- Least-privilege S3 permissions should be scoped to the required bucket and raw prefix.
- AWS CLI automatically uses the EC2 role's temporary credentials when no static credentials override them.
- `aws sts get-caller-identity` verifies the active identity, but its ARN can contain account and session identifiers.
- S3 list and upload operations verify separate read and write permissions.
- A small S3 raw landing layer decouples continuous ingestion from downstream Databricks processing.
- Temporary test files and installer downloads should not be committed as project source.
- A WebSocket is push-based and needs a long-running consumer, unlike REST polling.
- Buffering events into one file per window avoids the small-files problem.
- Newline-delimited JSON is a good raw format; Spark and Auto Loader read it one row per line.
- boto3 on EC2 uses the instance role through the default credential provider chain.
- Time-based S3 folders help with debugging and replay, and Auto Loader finds nested files under the prefix.
- Flushing in `on_close` protects against loss on graceful shutdown only, not on crashes.
- Medallion layers: Bronze keeps the raw shape, Silver cleans and types, Gold aggregates for business use.
- Auto Loader reads JSON fields as strings by default, so nested data must be parsed with an explicit schema.
- Expectations (`expect_all_or_drop`) enforce data-quality rules and report dropped-row counts.
- A succeeded job does not prove fresh data; monitor the source separately from the pipeline.
- Auto Loader's checkpoint means re-runs add no duplicates and a failed run catches up on the next success.
- A Full refresh clears pipeline state and rebuilds everything.
- Bundle-managed resources should be edited in YAML, not the UI.
- `python3`, not `python`, runs scripts on this EC2 image; `git commit -m` takes the message, not `git push`.

## Interview Questions

1. What is a Databricks Asset Bundle?
2. What does `databricks.yml` define?
3. What is a bundle target, and how can targets support `dev`, `test`, and `prod`?
4. What is the difference between a bundle, a target, and a resource?
5. What does `databricks bundle validate` verify, and does it deploy resources?
6. What is the difference between `src/` and `resources/`?
7. Why land WebSocket events in S3 before processing them in Databricks Bronze?
8. Why keep raw data minimally transformed?
9. What is an IAM role?
10. What is an IAM policy?
11. How do an IAM role and an IAM policy differ?
12. How does EC2 authenticate to S3 without permanent access keys?
13. What are AWS STS temporary credentials?
14. Why are IAM roles preferred over hard-coded access keys?
15. How do you check which AWS identity EC2 is using, and what sensitive details can the output contain?
16. How do you test S3 list access?
17. How do you test S3 write access?
18. What does least privilege mean, and why restrict access to `coinbase/raw/`?
19. Why is EC2 suitable for a continuously connected Coinbase WebSocket consumer?
20. How does S3 decouple Coinbase ingestion from Databricks transformations?
21. How do a Storage Credential and External Location differ?
22. Why are the EC2 and Databricks AWS roles separate?
23. What is Auto Loader, and how does it process new files incrementally?
24. Why append records to one Bronze table rather than create a table per file?
25. Why use a pipeline-native `@dp.table` function instead of manually setting a checkpoint?
26. Why is `_metadata.file_path` used instead of `input_file_name()`?
27. Why was automatic S3 file-event provisioning not enabled?
28. How does a WebSocket differ from REST polling, and why does it need a long-running consumer?
29. Why buffer events for about 15 seconds instead of writing one S3 file per event?
30. Why is newline-delimited JSON a good raw landing format?
31. How does boto3 get credentials on EC2 without access keys in code?
32. Why use a `year/month/day/hour` S3 layout, and is it the same as table partitioning?
33. What does the flush in `on_close` protect against, and what does it not protect against?
34. How does Auto Loader know which S3 files are new, and how does directory listing differ from file notifications?
35. Why does Bronze keep the nested `events` array instead of flattening it?
36. What would you add to make the consumer production-ready (reconnect, retry, durable buffer, scheduling)?
37. What is the medallion architecture, and what does each layer do here?
38. Why does Bronze `events` arrive as a string, and how does Silver handle it?
39. How are duplicates prevented in Bronze and in Silver?
40. What do `expect_all_or_drop` rules do, and where do you see the dropped counts?
41. What happens to the tables if the pipeline fails for an hour and then succeeds?
42. What does a Full refresh do, and why avoid it here?
43. Why have separate alerts for pipeline failure and consumer failure?
44. Why can a job report SUCCESS while data is missing, and how do you detect it?
45. How do task retries interact with failure email notifications?
46. Why use systemd instead of `tmux` or running the script by hand?
47. What does `Restart=always` do, and why does `KillSignal=SIGTERM` matter for a buffered consumer?
48. Why reconnect with exponential backoff, and why add ping/pong?
49. Why clear the in-memory buffer only after a successful upload?
50. Why does a second consumer instance cause duplicates that Silver's dedup key does not remove?
51. What data can still be lost after these changes, and how would you remove that risk?

## Phase 5 Status

Phase 5 is **complete**. Sub-phases 5.1–5.6, 5.8 and 5.9 are done: bundle deployment, EC2-to-S3, Databricks-to-S3, the live Coinbase consumer, Bronze, Silver, the 15-minute job with retries, and the failure and consumer-health alerts. Consumer reliability (5.9) is also complete. Gold (5.7) moved to Phase 7, and CI/CD is Phase 9.

## Commit Phase 5 Work

Review the worktree, then stage only project files intended for the branch:

```bash
git status
git add 05-databricks-asset-bundle.md databricks.yml resources/ src/
git commit -m "Document Phase 5 Silver, job, and alerting"
git push -u origin phase-5-databricks-s3-integration
```

Do not stage the temporary `test.json`, downloaded `awscliv2.zip`, or extracted AWS installer directory. `resources/job.yml` is planned and should only be committed after it contains a real job definition.

## Interview Summary

> EC2 writes raw files to S3 using an attached IAM role and temporary STS credentials. Databricks accesses the prefix through a Unity Catalog Storage Credential and External Location backed by a separate AWS role. A Python consumer on EC2 subscribes to the Coinbase BTC-USD ticker WebSocket, buffers events for about 15 seconds, and writes each batch with boto3 as one newline-delimited JSON file under a time-based `coinbase/raw/YYYY/MM/DD/HH/` prefix, using the EC2 role. A serverless Lakeflow pipeline uses Auto Loader to incrementally append the new files into `workspace.bronze.coinbase_bronze`; one verified run ingested 256 records. Silver (`workspace.silver.coinbase_ticker`) flattens and types the data with quality rules. A Databricks job runs the pipeline every 15 minutes with 3 retries and a failure email, and a separate health-check job alerts if the consumer stops writing to S3. The consumer runs under systemd with WebSocket reconnect, upload retry, and a disk spool. Gold remains planned work.

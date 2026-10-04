# Phase 5 — Databricks Asset Bundle, AWS S3 Integration, and Bronze Ingestion

## Phase Goal

Build and verify the deployment and ingestion foundation in small architectural slices. The implementation first proved EC2-to-S3 and S3-to-Bronze with a test JSON file (5.1–5.4), then replaced the test file with a live Coinbase WebSocket consumer on EC2 (5.5), added Silver (5.6) and a scheduled, monitored job (5.8). Gold (5.7) is a later stage.

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
| 5.7 | Gold business-ready transformations | ⏳ Future work (to be built later) |
| 5.8 | Job orchestration, retries, and failure/consumer alerts | ✅ Complete |

The completed slices establish `Coinbase -> EC2 -> S3 -> Databricks -> Auto Loader -> Bronze Delta`. Each new S3 file contributes rows to the same Bronze table; files do not get separate Bronze tables. Silver (5.6) and the scheduled job with alerting (5.8) are complete. Gold (5.7) is not implemented.

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
coinbase/raw/YYYY/MM/DD/HH/events_YYYYMMDD_HHMMSS.json
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

Example: `s3://paresh-data-engineering-coinbase-dev/coinbase/raw/2026/10/04/05/events_20261004_054913.json`

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

Job orchestration and scheduling were added afterward in 5.8, and the consumer's stopped-state is now monitored. The consumer itself still lacks auto-restart and these hardening items.

## Sub-Phase 5.6 — Silver Delta

Silver turns the raw, nested Bronze rows into one clean, typed row per BTC-USD price update. It is added to the same `data-engineering-pipeline`, so one pipeline update runs Bronze first and then Silver.

```text
workspace.bronze.coinbase_bronze
        | read as a stream (only new Bronze rows)
        v
parse JSON -> explode events -> explode tickers -> cast types -> quality rules -> dedupe
        v
workspace.silver.coinbase_ticker
```

### 5.6.1 — What Bronze Looks Like and Why It Is Not Analysis-Ready

**What it is.** One Bronze row is one Coinbase WebSocket message. Real data read from S3:

```json
{"channel": "ticker", "timestamp": "2026-10-04T05:50:33.553456409Z", "sequence_num": 216,
 "events": [{"type": "update", "tickers": [{"product_id": "BTC-USD", "price": "84895.29",
   "best_bid": "84895.29", "best_ask": "84895.3", "volume_24_h": "1806.10224538", "...": "..."}]}]}
```

**Why Silver is needed.**

| Problem in Bronze | Silver fix |
| --- | --- |
| Prices are nested inside `events[].tickers[]` | Explode both arrays into one row per update |
| Numbers are strings (`"84895.29"`) | Cast to `DECIMAL` |
| `timestamp` is a string with nanoseconds | Trim to microseconds, cast to `TIMESTAMP` |
| The old `test.json` row has no ticker data | Filter to `channel = 'ticker'` |
| The first message after subscribing is a `snapshot` | Keep it, tagged in `event_type` |
| The same message could be read twice | Deduplicate |

**Data observed (257 raw lines).** 255 `update` messages, 1 `snapshot` (`sequence_num` 0), 1 test row. Every message had exactly 1 event with exactly 1 ticker, and `sequence_num` was unique within the session (0 to 256).

**Interview concept.** Medallion architecture: Bronze keeps the raw shape, Silver cleans and standardizes, Gold aggregates for business use.

### 5.6.2 — The Silver Code

File: `src/silver/silver_pipeline.py`, registered in `resources/pipeline.yml` as a second library:

```yaml
      libraries:
        - file:
            path: ../src/bronze/bronze_pipeline.py
        - file:
            path: ../src/silver/silver_pipeline.py
```

Key parts:

```python
@dp.table(name="workspace.silver.coinbase_ticker", table_properties={"quality": "silver"})
@dp.expect_all_or_drop({
    "event_time_not_null": "event_time IS NOT NULL",
    "product_id_not_null": "product_id IS NOT NULL",
    "price_positive": "price > 0",
    "bid_not_above_ask": "best_bid <= best_ask",
})
def coinbase_ticker():
    return (
        dp.read_stream("coinbase_bronze")
        .where(col("channel") == "ticker")
        ...
        .withWatermark("event_time", "1 hour")
        .dropDuplicatesWithinWatermark(["product_id", "event_time", "sequence_num"])
    )
```

- **Fully qualified table name.** `workspace.silver.coinbase_ticker` writes into a different schema from the pipeline default (`bronze`). The `workspace.silver` schema had to be created first.
- **Safe casts.** `try_cast` turns a bad number into `NULL` instead of crashing the pipeline, and the `price > 0` rule then drops that row.
- **Dedup key.** `sequence_num` can restart when the consumer reconnects, so the key also includes `event_time`.
- **Quality rules.** `expect_all_or_drop` removes failing rows and counts them on the pipeline's Data quality tab.

**Interview concept.** Streaming table reading another table incrementally; expectations (data-quality rules) with drop semantics; watermark-based deduplication.

### 5.6.3 — Issue Faced and Fix

| Issue | Root cause | Fix |
| --- | --- | --- |
| `Schema 'workspace.silver' does not exist` | Silver writes to a schema that had not been created | `databricks schemas create silver workspace` |
| `Cannot resolve "explode(events)"` — `events` has type `STRING` | Auto Loader reads JSON fields as text by default, so Bronze `events` is a JSON string, not an array | Parse in Silver with `from_json` and an explicit schema; leave Bronze unchanged |
| A failed update stayed in `RETRY_ON_FAILURE` | The pipeline auto-retried the broken code | `databricks pipelines stop`, deploy the fix, run again |

**Interview concept.** Auto Loader infers JSON columns as strings unless `cloudFiles.inferColumnTypes` is enabled. Keeping Bronze raw and parsing in Silver is a deliberate design choice.

### 5.6.4 — Verification

| Check | Result |
| --- | --- |
| Bronze rows | 257 |
| Silver rows | 256 (the test row is excluded) |
| Distinct `sequence_num` in Silver | 256, no duplicates |
| `price` range | 84,889.97 to 84,897.99 |
| Snapshot rows | 1 |

Example Silver row: `BTC-USD | 2026-10-04T05:50:52.053Z | price 84895.29 | best_bid 84895.29 | best_ask 84895.30 | sequence_num 256`.

## Sub-Phase 5.8 — Job Orchestration and Alerting

Two Databricks jobs, both defined in the bundle, run independently.

```text
Consumer (EC2) --> S3 --> coinbase-bronze-job (every 15 min) --> Bronze --> Silver
                    |
                    +--> coinbase-consumer-health-check (every 15 min) --> alert if S3 is stale
```

### 5.8.1 — `coinbase-bronze-job`

**What it is.** A scheduled job in `resources/job.yml` with one `pipeline_task` that starts `data-engineering-pipeline`.

**Why we need it.** The pipeline does not run by itself. The job triggers it so new S3 files are appended to Bronze and then Silver.

```yaml
resources:
  jobs:
    coinbase_bronze_job:
      name: coinbase-bronze-job
      schedule:
        quartz_cron_expression: "0 0/15 * * * ?"   # every 15 minutes
        timezone_id: UTC
        pause_status: UNPAUSED
      max_concurrent_runs: 1
      email_notifications:
        on_failure:
          - pareshranjan7327@gmail.com
      tasks:
        - task_key: run_bronze_pipeline
          pipeline_task:
            pipeline_id: ${resources.pipelines.data_engineering_pipeline.id}
          max_retries: 3
          min_retry_interval_millis: 60000
          retry_on_timeout: true
```

- **Schedule.** Every 15 minutes, so data reaches Silver up to 15 minutes after it lands in S3. Serverless compute runs on each trigger, so the interval is also a cost choice.
- **Retries.** The task retries up to 3 times, 1 minute apart. The failure email is sent only when the run finally fails.
- **No overlap.** `max_concurrent_runs: 1`.
- **Created paused, then unpaused.** The schedule was first deployed as `PAUSED` and tested with a manual run, which succeeded, before it was unpaused.

**Incremental behavior.** Auto Loader keeps the list of processed files in the pipeline checkpoint, and Silver reads only new Bronze rows. If the pipeline is down for a while, the next successful run ingests only the files that arrived in the meantime. Re-running with no new files adds 0 rows; Bronze stayed at 257 and Silver at 256 across several runs while the consumer was stopped. A **Full refresh** would clear that state and rebuild everything, so do not use it unless a rebuild is intended.

**Interview concept.** Job vs pipeline (the job schedules, the pipeline transforms); bundle-managed jobs should be changed in YAML and redeployed, because UI edits are overwritten.

### 5.8.2 — `coinbase-consumer-health-check`

**What it is.** A second job in `resources/monitoring_job.yml` that runs `src/monitoring/consumer_freshness_check.py`. It fails when the newest raw file in S3 is more than 10 minutes old.

**Why we need it.** The consumer and the pipeline fail independently:

| | Consumer | Pipeline / job |
| --- | --- | --- |
| Runs on | EC2 Python process | Databricks serverless |
| Does | Coinbase to S3 | S3 to Bronze to Silver |
| If it fails | No new files; ticks from the outage are lost for good | Files stay in S3; the next good run catches up |
| Alert | `coinbase-consumer-health-check` | `coinbase-bronze-job` |

If the consumer dies, the Bronze job still reports SUCCESS because it simply finds nothing new. Without this job there would be no email.

```yaml
    coinbase_consumer_health_check:
      name: coinbase-consumer-health-check
      schedule:
        quartz_cron_expression: "0 7/15 * * * ?"   # :07, :22, :37, :52 UTC
        pause_status: UNPAUSED
      email_notifications:
        on_failure:
          - pareshranjan7327@gmail.com
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

The script reads S3 directly (today's and yesterday's folders), so a broken Bronze pipeline does not trigger it. It exits with code 1 when the newest file is stale.

**Issue and fix.** `Task requires a cluster or an environment`: a Python task on serverless needs an `environments` entry; added `environment_key: default`.

**Verification.** With the consumer stopped, the test run failed with `ALERT: the Coinbase consumer looks stopped` (newest file about 677 minutes old), as designed.

**Limits.** Emails repeat about every 15 minutes while the consumer is down. This only alerts; it does not restart the consumer. Email text cannot be customized, so the job and task names carry the context.

**Interview concept.** Monitor each stage independently; "job succeeded" is not the same as "data is fresh" (data freshness monitoring).

## Future Sub-Phases — Build Separately

### Sub-Phase 5.7 — Gold Delta

**Status: planned.** Build business-facing aggregates from the validated Silver data; agree on the use cases and grain before defining tables.

```text
Silver Delta -> business rules/aggregations -> Gold Delta
```

Completion check: each Gold table has an identified consumer, documented grain, and repeatable transformation from Silver.

Job orchestration and CI/CD remain follow-on work after the ingestion and transformation contracts are stable.

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
Amazon S3: coinbase/raw/YYYY/MM/DD/HH/events_YYYYMMDD_HHMMSS.json
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

⏳ 5.7 Gold business transformations (to be built later)
⏳ Consumer hardening: auto-restart (systemd), reconnect, upload retry
⏳ CI/CD with GitHub Actions
```

Phase 5 remains in progress until the planned transformation work is complete. Live Coinbase events are verified in Bronze and Silver; the Gold table does not exist yet. The consumer has no reconnect or upload-retry logic yet (see 5.5.10), and it was stopped at the time of the last data check.

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

## Phase 5 Status

Phase 5 is **in progress**. Sub-phases 5.1–5.6 and 5.8 are complete: bundle deployment, EC2-to-S3, Databricks-to-S3, the live Coinbase consumer, Bronze, Silver, the 15-minute job with retries, and the failure and consumer-health alerts. Gold (5.7) is planned for later, and consumer hardening and CI/CD remain follow-on work.

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

> EC2 writes raw files to S3 using an attached IAM role and temporary STS credentials. Databricks accesses the prefix through a Unity Catalog Storage Credential and External Location backed by a separate AWS role. A Python consumer on EC2 subscribes to the Coinbase BTC-USD ticker WebSocket, buffers events for about 15 seconds, and writes each batch with boto3 as one newline-delimited JSON file under a time-based `coinbase/raw/YYYY/MM/DD/HH/` prefix, using the EC2 role. A serverless Lakeflow pipeline uses Auto Loader to incrementally append the new files into `workspace.bronze.coinbase_bronze`; one verified run ingested 256 records. Silver (`workspace.silver.coinbase_ticker`) flattens and types the data with quality rules. A Databricks job runs the pipeline every 15 minutes with 3 retries and a failure email, and a separate health-check job alerts if the consumer stops writing to S3. Gold and consumer hardening (auto-restart, reconnect, retry) remain planned work.

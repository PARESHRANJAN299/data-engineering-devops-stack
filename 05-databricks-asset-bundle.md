# Phase 5 — Databricks Asset Bundle + Source Landing Foundation

## Phase Goal

Build the initial Databricks Asset Bundle structure and prepare the source landing architecture for the Coinbase data engineering pipeline.

```text
Coinbase WebSocket
				|
				v
AWS EC2 Ingestion Service
				|
				v
AWS S3 Raw Landing Zone
				|
				v
Databricks Bronze Delta
				|
				v
Silver Delta
				|
				v
Gold Delta
```

This phase establishes the bundle and development target, validates the bundle configuration, creates the source and resource layout, prepares the S3 raw landing zone and EC2 IAM role, and installs and validates the AWS CLI.

## Part 1 — Databricks Asset Bundle Setup

### Step 1 — Create a Phase 5 Git Branch

Phase 5 work is isolated from the trusted `main` branch:

```bash
git switch main
git pull origin main
git switch -c phase-5-databricks-asset-bundle
```

Verify the current branch:

```bash
git branch
```

The active branch is `phase-5-databricks-asset-bundle`.

### Step 2 — Create `databricks.yml`

The root bundle configuration identifies the Databricks project:

```yaml
bundle:
	name: data-engineering-devops-stack
```

### Step 3 — Configure the Development Target

Add a `dev` target that uses the Databricks workspace and OAuth profile configured in Phase 4:

```yaml
bundle:
	name: data-engineering-devops-stack

targets:
	dev:
		default: true
		workspace:
			host: https://<databricks-workspace-host>
```

The repository's `databricks.yml` contains the actual workspace host. This guide uses a placeholder so the workspace-specific value is not duplicated in documentation.

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

This confirms the CLI can resolve the bundle name, target, workspace configuration, authenticated user, and bundle workspace path. Validation checks configuration; it does not deploy the bundle.

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

`src/` holds application and transformation code. `resources/` holds bundle-managed resource definitions such as pipelines and jobs.

### Step 6 — Add the Initial Pipeline Resource

The initial pipeline resource shell is defined in `resources/pipeline.yml`:

```yaml
resources:
	pipelines:
		data_engineering_pipeline:
			name: data-engineering-pipeline
```

The resource declares the pipeline; transformation code remains under `src/`.

## Part 2 — Source Architecture Decision

The Coinbase WebSocket is a continuously connected source. An EC2-hosted Python consumer can maintain that connection and persist received events to durable object storage before Databricks processes them:

```text
Coinbase WebSocket -> EC2 ingestion service -> S3 raw landing -> Databricks
```

S3 is the durable source landing zone. Bronze, Silver, and Gold will later be managed as Delta tables in Databricks.

## Part 3 — Create the S3 Raw Landing Zone

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

## Part 4 — EC2-to-S3 IAM Security

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

## Part 5 — Install and Validate the AWS CLI

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

## Current End-to-End Architecture

```text
Laptop
	|
	| VS Code Remote SSH
	v
AWS EC2
	+-- Python and uv
	+-- Databricks CLI
	+-- AWS CLI
	|
	| attached IAM role
	v
AWS S3: coinbase/raw/
	|
	| Next: Databricks Storage Credential and External Location
	v
Bronze Delta -> Silver Delta -> Gold Delta
```

## Issues Faced

| Issue | Root cause | Fix |
| --- | --- | --- |
| `aws: command not found` | AWS CLI was not installed on EC2. | Install AWS CLI v2 using the official AWS ZIP installer. |
| Ubuntu `awscli` package unavailable | The configured Ubuntu package repositories had no install candidate. | Use the official AWS CLI v2 installer. |
| `sudo ./aws/install` failed | The installer directory did not exist because the ZIP had not been extracted. | Run `unzip awscliv2.zip` before the installer. |

## Phase 5 Status Checklist

```text
✅ Phase 5 Git branch created
✅ databricks.yml created and dev target configured
✅ Databricks workspace configured
✅ Bundle validation successful
✅ resources/ and src/ layout created
✅ bronze/silver/gold source folders created
✅ Initial pipeline resource created
✅ S3 bucket and Coinbase raw prefix created
✅ Least-privilege S3 IAM policy created
✅ EC2 IAM role created and attached
✅ AWS CLI v2 installed
✅ AWS identity verified as PareshCoinbaseEC2S3Role (ARN redacted)
✅ EC2-to-S3 list access verified
✅ EC2-to-S3 write access verified with a temporary test object

⏳ Databricks Storage Credential
⏳ Databricks External Location
⏳ S3-to-Bronze ingestion
⏳ Complete pipeline resource configuration
⏳ Job resource definition
⏳ Final bundle validation after resource integration
⏳ Phase 5 completion
```

The current bundle configuration validates successfully. Final validation will be repeated after the Storage Credential, External Location, and remaining resource definitions are integrated.

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
21. What Databricks components will enable access to S3 in the next step?

## Phase 5 Status

Phase 5 is **in progress**. The bundle configuration validates; EC2 assumed `PareshCoinbaseEC2S3Role`; and S3 list and write tests succeeded for the Coinbase raw prefix. Next is Databricks access through a Storage Credential and External Location, followed by Bronze ingestion and the remaining pipeline resources.

## Commit Phase 5 Work

Review the worktree, then stage only project files intended for the branch:

```bash
git status
git add 05-databricks-asset-bundle.md databricks.yml resources/pipeline.yml src/bronze/bronze_pipeline.py .gitignore
git commit -m "Build Phase 5 bundle and EC2 S3 integration"
git push -u origin phase-5-databricks-asset-bundle
```

Do not stage the temporary `test.json`, downloaded `awscliv2.zip`, or extracted AWS installer directory. The empty `resources/job.yml` is also left out until a job definition is added.

## Interview Summary

> For the source landing architecture, a Coinbase WebSocket consumer runs on EC2 and writes raw events to an S3 landing prefix. EC2 authenticates through an attached IAM role rather than static access keys. AWS STS provides temporary credentials, and a least-privilege policy restricts access to the Coinbase raw path. I verified the active role and tested S3 list and upload access. Databricks will consume the raw data through a Unity Catalog Storage Credential and External Location in the next step.

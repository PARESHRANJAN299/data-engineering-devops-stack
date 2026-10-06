# Phase 6 — Development Deployment

## Phase Goal

Define the repeatable way code and configuration move from the repo into the `dev` environment, with validation before and checks after. In this project that means two deployments: the Databricks bundle (pipeline and jobs) and the EC2 consumer service. How each piece was built is documented in Phase 5 (`05-databricks-asset-bundle.md`); this phase records the deployment pattern.

```text
Git repo (single source of truth)
   |-- databricks.yml + resources/*.yml + src/  --> bundle: validate -> deploy -> run -> verify --> Databricks dev
   |-- deploy/coinbase-consumer.service + src/ingestion/  --> git pull -> restart -> verify --> EC2 systemd service
```

## 6.1 — The `dev` Target

1. **What it is.** A bundle target named `dev` in `databricks.yml`. It is the default target, so commands run against dev without extra flags.
2. **Why we need it.** A target pins which Databricks workspace a deployment goes to. It is what later lets the same code be promoted to other environments.
3. **How it connects.** `databricks.yml` includes every file in `resources/` (the pipeline, the Bronze job and the health-check job), so one deploy ships all of them.
4. **Configuration.**
   ```yaml
   bundle:
     name: data-engineering-devops-stack

   include:
     - resources/*.yml

   targets:
     dev:
       default: true
       workspace:
         host: dbc-b4ee64e7-d2e5.cloud.databricks.com
   ```
   Authentication comes from the Databricks CLI profile set up in Phase 4, so no token is stored in the repo.
5. **Issue.** The first deploy reported zero resources.
6. **Fix.** The resource files were not included. Adding `include: - resources/*.yml` fixed it.
7. **Interview concept.** Bundle targets (`dev`, `test`, `prod`) separate environment settings from code; one bundle, many environments.

## 6.2 — Validate Before Deploying

1. **What it is.** `databricks bundle validate --target dev` checks the configuration without deploying anything.
2. **Why we need it.** It catches mistakes (missing fields, bad references, wrong settings) before they reach the workspace.
3. **How it connects.** It runs against the same `databricks.yml` and `resources/` that the deploy in 6.3 uses.
4. **Command.**
   ```bash
   databricks bundle validate --target dev
   ```
   A good run ends with `Validation OK!`.
5. **Issues caught by validation.**
   - `Task requires a cluster or an environment`: the health-check Python task needed an `environments` entry.
   - Earlier, deploy errors appeared only after deploying, such as the workspace requiring serverless compute and the pipeline needing a catalog and schema.
6. **Fix.** Correct the YAML, and run validate again until it passes.
7. **Interview concept.** Validate is not deploy: it checks configuration but changes nothing, and it does not prove the pipeline logic is right.

## 6.3 — Deploy the Bundle

1. **What it is.** `databricks bundle deploy --target dev` uploads the files and creates or updates the pipeline and jobs in the dev workspace.
2. **Why we need it.** It makes the workspace match the repo. The repo is the source of truth, so the workspace should never be edited by hand.
3. **How it connects.** It follows a passing validate and uses the same target. Its output lists what was created, changed, or left unchanged.
4. **Commands.**
   ```bash
   databricks bundle deploy --target dev
   databricks bundle summary --target dev     # lists deployed resources with links
   ```
   Deployed resources: `data-engineering-pipeline` (Bronze and Silver), `coinbase-bronze-job` and `coinbase-consumer-health-check`.
5. **Issues.**
   - A job schedule edit made with `sed` did not match, so the job was deployed unpaused on its old schedule.
   - `An active update already exists for pipeline` when a run was already in progress or retrying.
6. **Fix.**
   - Check the file contents before deploying.
   - Stop the retrying update (`databricks pipelines stop <pipeline-id>`), then deploy and run again.
7. **Interview concept.** Declarative, idempotent deployment: running deploy twice gives the same result. Changes made in the UI are overwritten by the next deploy.

## 6.4 — Run and Verify in Dev

1. **What it is.** After a deploy, run the job or pipeline and check the outcome.
2. **Why we need it.** A successful deploy only means the files were uploaded. Verification proves the pipeline works.
3. **How it connects.** It runs what 6.3 deployed and ends in the real tables in `workspace.bronze` and `workspace.silver`.
4. **Commands and checks.**
   ```bash
   databricks bundle run coinbase_bronze_job --target dev
   databricks bundle run coinbase_consumer_health_check --target dev
   ```
   Then confirm in the SQL editor that row counts and `max(event_time)` in `workspace.silver.coinbase_ticker` grow, and that the health check run passes.
5. **Issue.** Row counts stayed at 257 after job runs.
6. **Fix.** The consumer was stopped, so no new files arrived. The pipeline was fine. This led to the health check and the systemd service (Phase 5, 5.8 and 5.9).
7. **Interview concept.** "Job succeeded" is not the same as "data is correct or fresh". Verify the output, and monitor freshness separately.

## 6.5 — Deploy the Consumer on EC2

1. **What it is.** The consumer runs as the `coinbase-consumer` systemd service on EC2. Deploying it means getting the new code onto the instance and restarting the service.
2. **Why we need it.** The consumer is not part of the Databricks bundle, so `bundle deploy` does not update it.
3. **How it connects.** It feeds the S3 raw layer that the bundle's pipeline reads.
4. **Commands.**
   ```bash
   cd ~/data-engineering-devops-stack
   git pull origin main
   sudo systemctl restart coinbase-consumer
   systemctl status coinbase-consumer
   journalctl -u coinbase-consumer -f          # look for "Wrote N events"
   ```
   First-time setup of the service file is in Phase 5, 5.9.1. The restart is graceful: the service flushes its buffer before stopping.
5. **Issue.** Running a second copy by hand while the service is running writes every tick twice.
6. **Fix.** Run only the service, never the script by hand alongside it.
7. **Interview concept.** Not everything is deployed the same way. Databricks resources use a bundle; a long-running EC2 process needs a service manager and its own deploy step.

## Dev Deployment Checklist

```text
[ ] git pull on EC2 (latest code)
[ ] databricks bundle validate --target dev
[ ] databricks bundle deploy --target dev
[ ] databricks bundle run coinbase_bronze_job --target dev  -> SUCCESS
[ ] Bronze/Silver row counts and max(event_time) grew
[ ] sudo systemctl restart coinbase-consumer  (only if consumer code changed)
[ ] consumer logs show "Wrote N events"; health check job passes
```

## What I learned

- A deployment is validate, deploy, run, verify; each step catches a different kind of mistake.
- A single source of truth (the repo) plus declarative deploys prevents environment drift.
- Dev, `databricks.yml` targets and CLI authentication are separate concerns that work together.
- Verify the data, not just the job status.

## Interview questions

1. What is the purpose of a dev deployment stage?
2. What does `databricks bundle validate` check, and what does it not check?
3. What is a bundle target, and how would you add a `prod` target?
4. What is environment drift, and how does deploying from the repo prevent it?
5. Why are UI edits to a bundle-managed job overwritten?
6. How do you confirm a deployment really worked?
7. Why is the EC2 consumer deployed differently from the pipeline?

## Phase status ✅

Completed. The `dev` target is the default target, and the pipeline, both jobs and the consumer service are deployed and running in dev. Only `dev` exists; a separate `test` or `prod` target is not defined in this project.

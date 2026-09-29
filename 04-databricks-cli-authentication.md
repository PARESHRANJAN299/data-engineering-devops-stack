# Phase 4 — Databricks CLI Authentication

## Phase Goal

Connect the EC2 development server securely to the Databricks workspace using the Databricks CLI and OAuth. Create a named `dev` profile and verify authenticated access to the workspace API.

## Architecture

```text
Laptop
	|
	| VS Code Remote SSH
	v
AWS EC2 Ubuntu
	|
	v
Databricks CLI
	|
	v
OAuth Profile: dev
	|
	v
Databricks Workspace API
	|
	v
Workspace objects returned
```

## Step 1 — Check Whether the CLI Is Installed

Check the installed version:

```bash
databricks --version
```

Initially, the command returned:

```text
databricks: command not found
```

This confirmed that the Databricks CLI was not installed on the EC2 server.

## Step 2 — Install the Databricks CLI

The installer initially could not write to `/usr/local/bin`, which requires elevated permissions. Running the installer with `sudo` exposed a second missing prerequisite: `unzip`.

Install `unzip` and rerun the version-pinned official installer:

```bash
sudo apt update
sudo apt install -y unzip
curl -fsSL https://raw.githubusercontent.com/databricks/setup-cli/v1.18.0/install.sh | sudo sh
```

The installer reported:

```text
Installed Databricks CLI v1.18.0 at /usr/local/bin/databricks.
```

Verify the installation:

```bash
databricks --version
```

Output:

```text
Databricks CLI v1.18.0
```

## Databricks SDK vs. Databricks CLI

These are separate tools with different use cases:

```text
databricks-sdk = Python library used by Python applications
Databricks CLI = terminal tool used to interact with Databricks
```

The CLI can be used directly from the terminal; the SDK is imported by application code.

## Step 3 — Identify the Workspace Host

CLI authentication requires the workspace hostname, for example:

```text
https://<workspace-host>.cloud.databricks.com
```

The workspace hostname and SQL Warehouse HTTP path serve different purposes:

```text
Workspace hostname                 Used for workspace CLI authentication
/sql/1.0/warehouses/<warehouse-id> Used for SQL Warehouse connections
```

Use the workspace hostname with `databricks auth login`, not the SQL Warehouse HTTP path.

## Step 4 — Authenticate with OAuth

Start the interactive OAuth login with the workspace host:

```bash
databricks auth login --host https://<workspace-host>.cloud.databricks.com
```

When prompted for a profile name, use `dev`. The CLI confirmed:

```text
Profile dev was successfully saved
```

OAuth lets the CLI manage authentication for an interactive user login without putting a long-lived access token in source code. Never commit Databricks tokens, credentials, local authentication files, or other secrets to Git.

## Step 5 — Verify the Profile and Workspace Access

List configured profiles:

```bash
databricks auth profiles
```

The `dev` profile was shown as the default with a valid authentication status:

```text
Name           Host                                            Valid
dev (Default)  https://<workspace-host>.cloud.databricks.com   YES
```

Check the authenticated user:

```bash
databricks current-user me --profile dev
```

The returned user details included:

```json
"active": true
```

Finally, make a read-only Workspace API request:

```bash
databricks workspace list / --profile dev
```

The response included workspace directories such as `/Users`, `/Shared`, and `/Repos`. This verified end-to-end CLI authentication and Workspace API access.

## Issues Faced and Fixes

| Issue | Root cause | Fix |
| --- | --- | --- |
| `databricks: command not found` | The CLI was not installed. | Install the Databricks CLI using the official installer. |
| Installer could not write to `/usr/local/bin` | The destination is a system directory. | Run the installer with `sudo`. |
| `unzip: not found` | The Ubuntu server lacked the installer's extraction utility. | Install `unzip` with `sudo apt install -y unzip`, then rerun the installer. |
| Workspace host confused with HTTP path | Both values appear in SQL Warehouse connection details but have different uses. | Use the workspace hostname for CLI authentication; reserve the HTTP path for SQL Warehouse connections. |
| Generated profile name was unclear | The CLI offered a generated profile name. | Choose the descriptive local profile name `dev`. |

## Additional SSH Connectivity Issue

SSH from the MacBook temporarily returned:

```text
ssh: connect to host <EC2-IP> port 22: Network is unreachable
```

The EC2 instance was running, status checks passed, the security group allowed TCP port 22, the SSH service worked, and browser-based EC2 access succeeded. MacBook SSH later recovered without an EC2 configuration change.

`Network is unreachable` occurs before SSH authentication, so it does not by itself indicate a key problem. Troubleshoot in this order:

1. Check local internet connectivity.
2. Confirm the EC2 public IP address.
3. Check local reachability to port 22.
4. Check the EC2 security group.
5. Check EC2 instance health.
6. Check the SSH service.
7. Check SSH key authentication.

## What I Learned

- How to install and verify the Databricks CLI on Ubuntu.
- Why a system install location may require elevated privileges and why the installer needed `unzip`.
- The difference between the Databricks CLI and the Python SDK.
- How interactive OAuth authentication and named CLI profiles work.
- Why profile names such as `dev` are useful and do not create a new workspace.
- The difference between a workspace hostname and a SQL Warehouse HTTP path.
- How to validate the profile, authenticated user, and Workspace API access.
- Why authentication data and secrets must never be committed to Git.
- Why a network reachability error should be investigated before SSH keys.

## Interview Questions

1. What is the Databricks CLI, and how does it differ from the Databricks SDK?
2. Why use OAuth for interactive CLI authentication?
3. What is a Databricks CLI profile? Does it create a workspace?
4. How do you list CLI profiles and verify the authenticated user?
5. How do you test Workspace API access from the CLI?
6. How does a workspace hostname differ from a SQL Warehouse HTTP path?
7. Why must Databricks authentication data not be committed to Git?
8. What does `Network is unreachable` indicate during an SSH connection attempt?

## Phase 4 Completion Checklist

- [x] Databricks CLI installation checked and CLI installed.
- [x] `unzip` dependency installed and CLI version verified.
- [x] Workspace hostname identified.
- [x] OAuth login completed and `dev` profile created.
- [x] Authentication profile validated.
- [x] Current Databricks user verified.
- [x] Workspace API access tested and workspace directories returned.
- [x] SSH connectivity issue investigated and documented.
- [x] Learnings, troubleshooting, and interview questions documented.

## Phase Status — Completed

The EC2 environment is authenticated to the Databricks workspace through the CLI's OAuth `dev` profile, and Workspace API access has been verified. The next phase is **Phase 5 — Databricks Asset Bundle**, where `databricks.yml`, targets, resources, and job definitions will be introduced.

# Phase 2 — Python + uv Environment

## Phase Goal

Prepare the EC2 development server with a clean, isolated, and reproducible Python environment for the Data Engineering project.

This phase establishes the Python runtime, `uv` package manager, project virtual environment, dependency configuration, and Git-safe environment setup.

## Tools / Technologies

- Ubuntu 24.04 on AWS EC2
- Python 3.12
- `uv` 0.12.19
- `pyproject.toml` and `uv.lock`
- Python virtual environments
- Git and `.gitignore`
- pandas, requests, Databricks SDK, PyYAML, and XlsxWriter
- pytest, pytest-cov, Ruff, and mypy

## Architecture

```text
AWS EC2 Ubuntu Server
    |
    v
Python 3.12
    |
    v
uv Package Manager
    |
    v
Project Virtual Environment
    |
    +-- .venv/
          |
          +-- Runtime Dependencies
          |     +-- pandas
          |     +-- requests
          |     +-- databricks-sdk
          |     +-- pyyaml
          |     +-- xlsxwriter
          |
          +-- Development Dependencies
                +-- pytest
                +-- pytest-cov
                +-- ruff
                +-- mypy
```

The virtual environment is local to the project and ignored by Git. `pyproject.toml` and `uv.lock` describe the dependencies needed to recreate it.

## Step 1 — Verify Python

Command:

```bash
python3 --version
```

Output:

```text
Python 3.12.3
```

Python 3.12 is available on the EC2 development server.

## Step 2 — Install and verify uv

Initially, `uv` was not installed. Attempting to install it with `pip`:

```bash
pip install uv
```

returned:

```text
error: externally-managed-environment
```

Ubuntu 24.04 protects its system-managed Python environment under PEP 668. Instead of modifying system Python, `uv` was installed separately using the official Astral installer:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source "$HOME/.local/bin/env"
uv --version
```

Verified version: `uv 0.12.19`.

## Step 3 — Create and activate the virtual environment

Inside the project repository, the environment was created and activated with:

```bash
uv venv
source .venv/bin/activate
```

This created `.venv/`. After activation, the shell prompt showed:

```text
(data-engineering-devops-stack)
```

This indicates that the project virtual environment is active. A new terminal session must activate the environment again.

## What Is a Virtual Environment?

A virtual environment is an isolated Python environment for one project. Without isolation, packages from separate projects can conflict in the system Python environment:

```text
Ubuntu Python
	+-- Project A packages
	+-- Project B packages
	+-- Project C packages
```

With project environments, each project manages its own packages:

```text
Project A                     Project B                     Project C
	+-- .venv                     +-- .venv                     +-- .venv
```

This prevents dependency conflicts between projects.

## Step 4 — Initialize the Python project

The project was initialized with `uv init`, creating `pyproject.toml`. This is the main Python project configuration file. It contains:

- Project name and version
- Python version requirement
- Runtime dependencies
- Development dependencies
- Build configuration

The project description is:

```toml
description = "Production-style Data Engineering and DevOps project using Python, uv, Databricks, AWS, data quality, and CI/CD."
```

The resolved dependency versions are recorded in `uv.lock` for repeatable installs.

## Step 5 — Configure dependencies

The following runtime dependencies were added:

- `databricks-sdk` — interact with Databricks APIs and workspace resources.
- `pandas` — analyze, transform, validate, and report on tabular data.
- `pyyaml` — read YAML configuration files.
- `requests` — call REST APIs from Python.
- `xlsxwriter` — generate formatted Excel reports, including future data-quality reports.

`databricks-sdk` supports interactions with Databricks APIs and workspace resources. A typical integration path is:

```text
Python application
	|
	v
Databricks SDK
	|
	v
Databricks workspace, jobs, and APIs
```

`pandas` supports data analysis and transformation:

```text
CSV / Excel / API data
	   |
	   v
	 pandas
	   |
	   v
Filter / transform / validate
```

PyYAML reads configuration such as:

```yaml
environment: dev
catalog: data_engineering
schema: bronze
```

`requests` supports REST API calls and JSON responses. `xlsxwriter` can later generate formatted quality reports, for example:

```text
QC_Report.xlsx
    +-- Summary
    +-- Data Quality Results
    +-- Failed Records
    +-- Dashboard
```

## Development Dependencies

- `pytest` — run automated tests.
- `pytest-cov` — report test coverage.
- `ruff` — lint and check Python code.
- `mypy` — perform static type checking.

Runtime dependencies are needed by project code. Development dependencies support building and checking the project; they are unrelated to a Git development branch.

Ruff can identify unused imports, formatting problems, and common coding mistakes. Mypy can detect type mismatches, such as assigning a string where an integer is expected:

```python
age: int = "hello"
```

The dependency groups can be summarized as:

```text
Runtime:      pandas, requests, databricks-sdk, pyyaml, xlsxwriter
Development:  pytest, pytest-cov, ruff, mypy
```

## Step 6 — Verify the environment

After activating `.venv`, the following checks confirmed the project interpreter and Python version:

```bash
which python
python --version
```

The Python executable resolved to:

```text
/home/ubuntu/data-engineering-devops-stack/.venv/bin/python
```

The reported version was `Python 3.12.3`.

## Step 7 — Keep the environment out of Git

The repository `.gitignore` contains:

```gitignore
.venv/
```

The `.venv` directory contains installed packages and machine-specific environment files, so it should not be committed to GitHub. The environment can be recreated from the tracked project configuration:

```text
GitHub repository
    |
    +-- pyproject.toml and uv.lock
              |
              v
            uv sync
              |
              v
        recreated .venv
```

## Issues, Root Causes, and Fixes

### Issue 1 — `uv` command not found

**Issue:** The shell returned `uv: command not found`.

**Root cause:** `uv` was not installed on the EC2 server or its environment had not been loaded into the shell.

**Fix:** Install `uv` with the official Astral installer, load `$HOME/.local/bin/env`, and verify with `uv --version`.

### Issue 2 — pip reported an externally managed environment

**Issue:** `pip install uv` returned `externally-managed-environment`.

**Root cause:** Ubuntu 24.04 marks its system Python environment as externally managed under PEP 668 to protect OS-owned packages.

**Fix:** Leave system Python unchanged and install `uv` independently with the Astral installer.

### Issue 3 — Python command missing in a new terminal

**Issue:** After reconnecting, `which python` returned no path and `python --version` reported that the command was not found.

**Root cause:** The virtual environment existed, but each new shell session starts without it activated.

**Fix:** Activate it again with `source .venv/bin/activate`; verify that `which python` resolves inside `.venv`.

### Issue 4 — `.gitignore` did not exist

**Issue:** The project initially had no `.gitignore` file.

**Root cause:** The Python project setup had not yet defined which generated or machine-specific files Git should exclude.

**Fix:** Create `.gitignore` and add `.venv/` so the local environment is not committed.

## What I Learned

- Ubuntu's PEP 668 protection prevents unsafe changes to system-managed Python packages.
- `uv` can manage Python project dependencies and virtual environments.
- Creating a virtual environment and activating it are separate operations.
- A new shell session needs the environment activated again.
- `pyproject.toml` defines project metadata and dependency groups; `uv.lock` records resolved versions.
- Runtime and development dependencies serve different purposes.
- `.venv` should not be committed because it is local and can be recreated from project configuration.
- `which python` confirms which Python executable the active shell will use.

## Interview Questions

### 1. What is a Python virtual environment?

An isolated Python environment that lets a project use its own packages without changing system Python or other projects.

### 2. Why use a virtual environment?

It isolates dependencies and helps prevent version conflicts between projects.

### 3. What is `uv`?

`uv` is a Python project and package manager that can manage environments, dependencies, and project configuration.

### 4. What is `pyproject.toml`?

It is a standard Python project configuration file containing metadata, Python requirements, dependencies, and build configuration.

### 5. What is the difference between runtime and development dependencies?

Runtime dependencies are needed by the application. Development dependencies support tasks such as testing, linting, coverage, and type checking.

### 6. What does `which python` show?

It prints the path to the Python executable selected by the current shell.

### 7. Why should `.venv` be in `.gitignore`?

It contains local, machine-specific installed packages and can be recreated from the project dependency files.

### 8. What is PEP 668?

It defines a marker for externally managed Python installations, allowing distributions such as Ubuntu to protect system Python packages from unmanaged installs.

### 9. How can another developer recreate the environment?

Clone the repository and use `uv sync` to create or synchronize the environment from `pyproject.toml` and `uv.lock`.

### 10. Are development dependencies related to a Git development branch?

No. Development dependencies are Python tools used while working on the project. A Git branch is a separate line of source-control history.

## Phase Status

✅ Python 3.12 verified
✅ `uv` installed and verified
✅ Virtual environment created and activated
✅ `pyproject.toml` created and project description configured
✅ Runtime dependencies added
✅ Development dependencies added
✅ Excel report dependency (`xlsxwriter`) added
✅ Python verified to use `.venv`
✅ `.venv` added to `.gitignore`
✅ Issues, root causes, fixes, and learnings documented
✅ Interview questions and Phase 2 architecture documented

## Phase 2 — COMPLETED ✅

The EC2 Python environment is ready for data engineering development:

```text
EC2 Ubuntu
    |
    v
Python 3.12
    |
    v
uv and pyproject.toml / uv.lock
    |
    v
.venv with runtime and development dependencies
```

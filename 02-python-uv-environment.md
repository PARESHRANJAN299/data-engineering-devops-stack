# Phase 2 — Python + uv Environment Setup

## Phase Goal
Set up a clean Python development environment on the EC2 server and prepare it for project work using `uv` and a repeatable environment strategy.

## Step 1: Confirm Python baseline
- Check Python version.
- Validate package manager availability.
- Review OS package requirements.

## Step 2: Install uv
- Install `uv` for faster Python environment and dependency management.
- Verify installation and CLI usage.
- Confirm it works from the SSH terminal.

## Step 3: Create a project environment
- Initialize a virtual environment.
- Install required packages.
- Validate project execution from the remote server.

## Issues faced
- Missing or outdated Python tooling.
- Environment drift between local and remote setup.
- Package installation failed due to missing dependencies.

## Root cause
- The server did not yet have a standardized Python environment.
- Different tooling versions caused inconsistency.
- No isolated environment workflow was defined yet.

## Fix
- Install `uv` and standardize environment setup.
- Create isolated Python environments per project.
- Document required dependencies and setup commands.

## What I learned
- Virtual environments prevent dependency conflicts.
- `uv` can speed up Python workflows and simplifies setup.
- Remote servers need a repeatable setup procedure.
- A clean environment reduces onboarding friction.

## Interview questions
1. Why is a Python virtual environment important?
2. What is `uv`, and why use it?
3. How do you avoid dependency conflicts in a remote environment?
4. Why is reproducibility important in data engineering?
5. What is the value of automating environment setup?

## Phase status ✅
Completed: A clean Python environment was prepared and ready for project development.

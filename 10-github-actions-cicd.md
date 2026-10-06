# Phase 10 — GitHub Actions CI/CD

## Phase Goal
Implement a CI/CD pipeline using GitHub Actions to automate validation, delivery, and deployment workflows for the project.

## Step 1: Define pipeline triggers
- Decide when workflows should run.
- Use push, pull request, and manual triggers appropriately.
- Link pipeline execution to project stages.

## Step 2: Add automation steps
- Build validation checks.
- Run tests or project verification scripts.
- Package or deploy artifacts when conditions are met.

## Step 3: Validate deployment flow
- Trigger the workflow.
- Review logs and outputs.
- Correct failures and confirm the automation works end-to-end.

## Issues faced
- CI/CD automation had not yet been introduced.
- A standard deployment flow had to be defined.
- Validation and promotion steps needed structure.

## Root cause
- The project lacked a recurring automation mechanism.
- Manual deployment and validation were too informal.

## Fix
- Introduce GitHub Actions workflows.
- Define checks for validation and promotion.
- Use automation to enforce a repeatable deployment path.

## What I learned
- CI/CD reduces manual errors and makes releases more predictable.
- Automation works best when validation is explicit.
- GitHub Actions makes deployment workflow visible and traceable.

## Interview questions
1. What is the purpose of CI/CD?
2. Why is GitHub Actions useful for automation?
3. What is the difference between CI and CD?
4. How should a pipeline validate code before deployment?
5. What are the benefits of automated deployment logs?

## Phase status ✅
Completed: GitHub Actions CI/CD workflow was introduced and validated for project automation.

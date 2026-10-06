# 11 — CI/CD Interview Preparation

This file is a learning and interview document, kept separate from the implementation write-ups. It explains the CI/CD architecture this project was designed to have, what is in place today, and what is not implemented. No GitHub Actions workflow exists in the repository.

## 1. What CI/CD Architecture We Wanted

Target design (not implemented):

```text
Feature branch
   -> Pull Request
   -> GitHub Actions CI   (validate, tests, security checks)
   -> Approval
   -> Merge to main
   -> GitHub Actions CD
   -> OIDC (workload identity federation)
   -> Databricks service principal
   -> Asset Bundle deploy
   -> Databricks
```

Current implementation (what actually runs today):

```text
Developer -> EC2 + VS Code -> Git branch -> GitHub Pull Request (ruleset: approval, owner-only bypass)
   -> manual: databricks bundle validate --target dev
   -> manual: databricks bundle deploy --target dev
   -> Databricks
```

## 2. Why Service Principals Are Used

A service principal is a non-human identity (a robot user) in Databricks. Automation should log in as a service principal because:

- it is not tied to one person, so it keeps working when someone leaves;
- it can be given only the permissions the pipeline needs (least privilege);
- its actions appear in audit logs under a clear automation identity.

You = human user. Service principal = robot user.

## 3. Why Personal Credentials Should Not Be Used in CI

A personal access token or a personal OAuth login in CI:

- carries all of that person's permissions, which is more than a deploy needs;
- breaks when the person changes role or leaves;
- if leaked, exposes the whole account, and it is hard to tell a human action from an automated one in audit logs.

## 4. Client Secret vs OIDC

| | Client secret | OIDC (workload identity federation) |
| --- | --- | --- |
| What GitHub holds | A long-lived secret stored in GitHub secrets | No stored secret |
| How it logs in | Sends the client ID and secret to Databricks | Sends a short-lived signed token that GitHub issues for the run |
| Risk | A leaked secret works until someone rotates it | A token is valid for a short time and only for the matching repo, branch or environment |
| Maintenance | Rotate secrets on a schedule | Nothing to rotate |

OIDC is the stronger pattern. A client secret is the simpler fallback.

## 5. What Workload Identity Federation Means

Databricks trusts an external identity provider (here GitHub) instead of a password. You create a federation policy on the service principal that says: tokens from this issuer, for this audience, with this subject (for example a specific repository and branch) are allowed to act as this service principal. GitHub then proves who the workflow is with a signed token, and no secret is stored anywhere.

```text
GitHub Actions run -> asks GitHub for an ID token -> sends it to Databricks
Databricks checks issuer + audience + subject against the federation policy
-> match: short-lived access as the service principal
-> no match: rejected
```

## 6. GitHub `id-token: write`

A workflow can only request an OIDC token if it is granted that permission:

```yaml
permissions:
  id-token: write      # allows the workflow to request an OIDC token
  contents: read       # allows checkout
```

Without `id-token: write`, no token is issued and the login fails.

## 7. PR Validation Flow (CI)

```text
Pull request opened -> workflow runs on the PR
   -> checkout -> install Databricks CLI -> databricks bundle validate --target dev
   -> optional: lint, unit tests, secret scanning
   -> result shown as a check on the PR
```

CI only checks. It must not change the workspace. As a required status check in the branch ruleset, a failing check blocks the merge.

## 8. Main-Branch Deployment Flow (CD)

```text
Merge to main -> workflow runs on push to main
   -> OIDC login as the service principal
   -> databricks bundle deploy --target dev
   -> optional: run the job and check the output
```

For a production target, a GitHub Environment with required reviewers can pause the deploy until someone approves.

## 9. GitHub Branch Protection

The `main` branch has an active ruleset ("Protect main branch"), read from the GitHub API:

- a pull request is required, with 1 approving review;
- code owner review is required;
- force pushes and branch deletion are blocked;
- only the repository Admin role can bypass.

Open items: no `CODEOWNERS` file exists, so the code owner rule has nothing to enforce, and no required status checks are configured because there is no CI.

## 10. Why Admin Bypass Exists in This Solo Portfolio

The ruleset requires an approving review, but a solo owner cannot approve their own pull request. The owner-only bypass lets the owner merge their own PRs while everyone else must go through review. In a team, the bypass list would be empty or limited to a small group, and a second person would approve.

## 11. What Is Configured Today

- The branch ruleset described in section 9, used for every pull request in the project (#8 and later).
- The Databricks CLI on EC2, authenticated with an OAuth `dev` profile for the human user.
- A `dev` bundle target; validate and deploy are run manually from EC2.
- Pipeline, jobs, alerts and the consumer service deployed and running in dev.

## 12. What Was Not Completed

Full GitHub OIDC to Databricks federation was not implemented. The project owner's investigation found that the required account-level federation capability was not available in the Databricks Free Edition workspace used for this project. This is recorded as a platform limitation, not a gap in understanding of the architecture. I did not independently verify the Free Edition limitation; it is the owner's finding.

Because of that, no GitHub Actions workflow exists in the repository and CI is not a required check.

## 13. How It Would Be Implemented in Enterprise Databricks

Outline (check the current Databricks documentation for exact commands and field names):

1. Create a service principal at the Databricks account level and add it to the workspace.
2. Grant it only what the bundle needs (for example, permission to manage the pipeline and jobs, and to use the target catalog and schema).
3. Create a federation policy on the service principal for GitHub: issuer `https://token.actions.githubusercontent.com`, the audience Databricks expects, and a subject limited to this repository and branch (or a GitHub Environment).
4. Store only non-secret values as GitHub variables or secrets: the Databricks host and the service principal's client ID.
5. Add `ci.yml` (on pull request, `bundle validate`) and `cd.yml` (on push to `main`, `bundle deploy`) with `permissions: id-token: write`.
6. Make the CI check required in the ruleset, and add `CODEOWNERS`.
7. For prod, use a GitHub Environment with required reviewers.

## 14. Common Interview Questions and Answers

**Why a service principal instead of your own login?**
It is a dedicated non-human identity with least privilege. It survives staff changes and is easy to audit.

**Why is OIDC better than a stored client secret?**
There is no long-lived secret to leak or rotate. Tokens are short-lived and scoped to a repository, branch or environment.

**What does `id-token: write` do?**
It allows the workflow to request an OIDC token from GitHub. Without it, no token is issued.

**What is the difference between CI and CD?**
CI checks every change before merge (validate, tests). CD deploys after merge.

**What does `databricks bundle validate` check, and what does it not check?**
It checks the bundle configuration and references and changes nothing. It does not prove the pipeline logic or the data are correct.

**How do you stop a bad change reaching production?**
Branch protection with required review, a required CI check, and an approval gate on the production environment.

**Why does your repo have an admin bypass?**
Solo project: the owner cannot approve their own PR. In a team it would be removed or restricted.

**What did you not finish, and why?**
The OIDC deployment: the account-level federation capability was unavailable in the Free Edition workspace used. I designed the flow, documented it, and kept deployment manual with branch governance in place.

**How would you secure the pipeline's secrets?**
Prefer OIDC so there are none; otherwise use GitHub secrets, a dedicated service principal, least privilege and rotation.

**Why is validate-then-deploy split across two workflows?**
CI runs on untrusted PR code and must not change anything. CD runs only on the protected `main` branch and holds the deploy permission.

## 15. Full CI/CD Architecture Diagram

The animated login diagram is in the [README](README.md#how-github-actions-would-log-in-designed-not-implemented). The complete target flow:

```text
 Developer
    |  git push (feature branch)
    v
 GitHub: Pull Request ----------------------------+
    |                                             |
    v                                             v
 CI workflow (pull_request)                 Ruleset on main
    |-- bundle validate                       |-- 1 approving review
    |-- tests / lint / security checks        |-- code owner review
    |-- required status check                 |-- no force push / deletion
    v                                         |-- admin-only bypass
 Approval  <-------------------------------------+
    |
    v
 Merge to main
    |
    v
 CD workflow (push to main, permissions: id-token: write)
    |-- GitHub issues OIDC token
    |-- Databricks checks federation policy -> service principal access
    |-- databricks bundle deploy --target dev (prod: with environment approval)
    v
 Databricks workspace: pipeline, jobs, alerts
```

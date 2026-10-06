# Phase 7 — Approval-Based Deployment

## Phase Goal

Make sure no change reaches `main` without review and approval, and that only the repository owner can bypass that rule. In this project the approval gate is a GitHub ruleset on the default branch plus a pull request workflow. The ruleset was read from the GitHub API (`gh api repos/<owner>/data-engineering-devops-stack/rulesets`).

```text
feature branch --push--> Pull Request --1 approving review + code owner review--> main
                                                |
                    only the repository Admin role can bypass
```

## 7.1 — Protect the Default Branch

1. **What it is.** A branch ruleset named "Protect main branch", `enforcement: active`, applied to the default branch (`~DEFAULT_BRANCH`).
2. **Why we need it.** `main` is the trusted branch that gets deployed. Without protection, one direct push could break the pipeline or the consumer.
3. **How it connects.** It builds on the Git and GitHub workflow from Phase 3 (feature branches and pull requests) and on the dev deployment from Phase 6, which deploys what is on the branch.
4. **Configuration.** Rules in the ruleset: pull request required, deletion blocked, non-fast-forward (force push) blocked.
5. **Issue.** An earlier branch named `test-main-protection` was used to try the protection before relying on it.
6. **Fix.** Not needed; the ruleset is active.
7. **Interview concept.** Branch protection and rulesets enforce policy on the server, so it cannot be skipped by accident from a laptop.

## 7.2 — Pull Request With One Approving Review

1. **What it is.** Every change to `main` goes through a pull request with at least **1 approving review**.
2. **Why we need it.** A second look catches mistakes, and the pull request keeps a record of what changed and why.
3. **How it connects.** It is the gate that sits between a feature branch (Phase 3 workflow) and `main`.
4. **Configuration.**
   ```json
   "required_approving_review_count": 1,
   "dismiss_stale_reviews_on_push": false,
   "require_last_push_approval": false,
   "required_review_thread_resolution": false,
   "allowed_merge_methods": ["merge", "squash", "rebase"]
   ```
5. **Issue.** A push from the EC2 terminal failed with `ECONNREFUSED ...vscode-git....sock` and `Authentication failed`.
6. **Fix.** The terminal held a stale VS Code credential-helper socket. Opening a new terminal or pushing with a personal access token fixed it.
7. **Interview concept.** Review requirements (approval count, stale-review dismissal, last-push approval) are separate settings; here only the approval count is enforced.

## 7.3 — Code Owner Review

1. **What it is.** The ruleset sets `require_code_owner_review: true`.
2. **Why we need it.** It makes the people named as owners of a path review changes to it.
3. **How it connects.** It extends the approval rule from 7.2.
4. **Configuration.** The rule is enabled in the ruleset.
5. **Issue.** The repository has **no `CODEOWNERS` file**, so no one is named as a code owner and this rule has nothing to enforce.
6. **Fix.** Not done yet. Adding `.github/CODEOWNERS` with `* @PARESHRANJAN299` would make the rule take effect.
7. **Interview concept.** A rule that requires code owner review does nothing without a `CODEOWNERS` file. Always check that a control actually fires.

## 7.4 — Owner-Only Bypass

1. **What it is.** The ruleset lists one bypass actor: the repository **Admin role** (`actor_type: RepositoryRole`, `actor_id: 5`, `bypass_mode: always`).
2. **Why we need it.** As a solo owner you may need to merge your own pull request, since you cannot approve your own. Everyone else cannot bypass.
3. **How it connects.** It is the exception to 7.1 to 7.3.
4. **Configuration.** `bypass_actors: [{actor_id: 5, actor_type: RepositoryRole, bypass_mode: always}]`.
5. **Issue.** None observed.
6. **Fix.** Not needed.
7. **Interview concept.** Bypass lists should be as small as possible, and bypasses should be deliberate, visible actions.

## 7.5 — How the Workflow Is Used

Every change in this project has gone through a pull request: for example #8 to #18 (Phase 5 work, Silver, the job, consumer reliability and the documentation updates). Typical flow:

```bash
git checkout -b <branch>
git add <files> && git commit -m "message"
git push -u origin <branch>
gh pr create --base main --head <branch> --title "..." --body "..."
# review and merge on GitHub
git checkout main && git pull origin main
```

## Limits

- The gate controls what reaches `main`. The Databricks deploy itself (`databricks bundle deploy --target dev`) is still a manual command run from EC2; no automated approval step exists for it.
- Only the `dev` target exists, so there is no production promotion to approve yet.
- There are no required status checks, because CI does not exist yet (Phase 10).
- `CODEOWNERS` is missing (see 7.3).

## What I learned

- Server-side rules protect the trusted branch regardless of local habits.
- Approval and bypass are separate controls; both need to be set deliberately.
- Verify that a control works, not only that it is turned on.

## Interview questions

1. What does a branch ruleset enforce, and how does it differ from a local Git habit?
2. How does the pull request approval flow protect `main`?
3. What does code owner review need in order to work?
4. Who can bypass the ruleset here, and why only that role?
5. What is the difference between approving a merge and approving a deployment?

## Phase status ✅

Completed as designed: pull request approval, branch protection and an owner-only bypass are in place on `main`. Open items: add a `CODEOWNERS` file, and add required status checks once CI exists (Phase 10).

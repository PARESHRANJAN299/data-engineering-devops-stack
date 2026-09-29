# Phase 3 — Git + GitHub Workflow

## Phase Goal

Establish a reliable Git and GitHub workflow for version control, branch isolation, pull requests, protected main-branch merges, and approval control.

---

## Architecture

```text
EC2 Working Copy
      |
      v
Feature Branch
      |
      v
git add
      |
      v
git commit
      |
      v
git push
      |
      v
GitHub Pull Request
      |
      v
Main Branch Protection
      |
      +-- Pull Request required
      +-- 1 approval required
      +-- Code Owner review required
      +-- Force push blocked
      +-- Deletion restricted
      +-- Admin bypass allowed for solo repo
      |
      v
Merge to main
```

---

## Step 1 — Understand Branch Isolation
The `main` branch is treated as the trusted branch.

A separate branch was created for Phase 3:

```
git switch -c phase-3-git-github-workflow
```

Verification:

```
git branch
```

Output:

```
  main
  phase-2-python-uv-environment
* phase-3-git-github-workflow
```

The `*` indicates the currently active branch.

This allows Phase 3 work to remain isolated from `main` until it is reviewed and merged.

---

## Step 2 — Make Changes on the Feature Branch
A change was made to:

```
03-git-github-workflow.md
```

Git status was checked using:

```
git status
```

This allows us to see which files were modified before committing.

---

## Step 3 — Stage Changes
The changed file was staged using:

```
git add 03-git-github-workflow.md
```

`git add` moves the selected change into the staging area.

Conceptually:

```
Working directory
      |
      v
git add
      |
      v
Staging area
```

---

## Step 4 — Commit Changes
The staged change was committed:

```
git commit -m "Document manual Git workflow"
```

A commit represents a saved version of the project history.

Conceptually:

```
Staging area
      |
      v
git commit
      |
      v
Local Git history
```

---

## Step 5 — Push Branch to GitHub
The branch was pushed to GitHub:

```
git push -u origin phase-3-git-github-workflow
```

This created a remote branch:

```
origin/phase-3-git-github-workflow
```

The local and remote branches are now connected.

---

## Step 6 — Configure Git Identity
Git initially created commits using the EC2-generated identity.

Git identity was configured manually:

```
git config --global user.name "Paresh Ranjan Rout"
git config --global user.email "pareshranjan7327@gmail.com"
```

Verification:

```
git config --global user.name
git config --global user.email
```

This ensures future commits use the correct Git identity.

---

## Step 7 — Create Pull Request
A Pull Request was created with:

```
base: main
compare: feature branch
```

Correct direction:

```
feature branch
      |
      v
Pull Request
      |
      v
main
```

An important learning was that PR direction matters.

A reversed PR such as:

```
main
  |
  v
feature branch
```

does not test `main` branch protection.

---

## Step 8 — Protect the Main Branch
A GitHub Ruleset named:

```
Protect main branch
```

was created and activated.

The target branch is:

```
main
```

The following rules were configured:

```
✅ Require a pull request before merging
✅ Required approvals: 1
✅ Require review from Code Owners
✅ Restrict deletions
✅ Block force pushes
```

The following rules were intentionally left disabled for now:

```
❌ Restrict creations
❌ Restrict updates
❌ Require status checks to pass
❌ Require deployments to succeed
❌ Require code scanning results
❌ Require code quality results
❌ Restrict code coverage
```

Status checks and CI-related rules will be added later during the GitHub Actions phase.

---

## Step 9 — Test Direct Commit Protection
A change was attempted directly against `main`.

GitHub returned:

```
You can’t commit to main because it is a protected branch
```

GitHub forced the change into a separate branch and required a Pull Request.

This confirmed that direct changes to `main` are blocked.

---

## Step 10 — Test Approval Protection
A test branch was created:

```
test-main-protection
```

A Pull Request was opened with:

```
base: main
compare: test-main-protection
```

GitHub displayed:

```
Review required
At least 1 approving review is required.
```

And:

```
Merging is blocked
```

This confirmed that the approval rule is working correctly.

---

## Step 11 — Understand Assignee vs Reviewer
An assignee is not the same as a reviewer.

```
Assignee
= person responsible for the PR

Reviewer
= person who approves or requests changes
```

Assigning yourself to the PR does not count as approval.

---

## Step 12 — Understand Self-Approval Limitation
A pull request author cannot satisfy their own required approval.

So normally:

```
You create PR
      |
      v
Another reviewer approves
      |
      v
Merge allowed
```

For a real team repository, this provides strong independent review.

---

## Step 13 — Configure Admin Bypass for Solo Development
Because this is currently a solo learning repository, there is no second reviewer account available.

The ruleset bypass list includes:

```
Repository admin → Always allow
```

This means:

```
Normal contributor
      |
      v
PR required
      |
      v
Approval required

Repository admin
      |
      v
Can bypass rules when necessary
```

This allows the solo project to continue while still keeping the production-style protection model documented.

In a real team environment, the admin bypass should be used carefully and independent review should normally be required.

---

# Issues Faced

## Issue 1 — No File Change Detected
Commands such as:

```
git add
git commit
```

returned:

```
nothing to commit, working tree clean
```

### Root Cause
No actual file content had changed.

### Fix
A real file change was made before staging and committing.

---

## Issue 2 — Markdown Text Typed in Terminal
This was typed directly into the terminal:

```
# Phase 3 — Git & GitHub Workflow
```

### Root Cause
In Bash, text beginning with `#` is treated as a comment.

It did not modify the markdown file.

### Fix
The markdown file was edited directly using an editor.

---

## Issue 3 — Pull Request Direction Was Reversed
A Pull Request was created with:

```
main → feature branch
```

instead of:

```
feature branch → main
```

### Root Cause
The base and compare branches were selected in the wrong direction.

### Fix
The correct Pull Request direction was used:

```
base: main
compare: feature branch
```

---

## Issue 4 — Approval Rule Appeared Not to Work
Initially, the main branch approval rule seemed ineffective.

### Root Cause
The Pull Request was not targeting `main`.

The protection rules only apply when the protected branch is the destination.

### Fix
A new Pull Request was created correctly:

```
feature branch
      |
      v
main
```

GitHub then correctly blocked the merge pending approval.

---

## Issue 5 — Own Pull Request Cannot Be Self-Approved
The repository requires one approval before merge.

### Root Cause
The author of a Pull Request cannot satisfy the independent approval requirement with their own review.

### Fix
For the solo learning repository, repository-admin bypass was enabled.

In a team environment, another reviewer should approve the Pull Request.

---

# What I Learned
During this phase I learned:

- What a Git branch is.
- Why feature branches isolate work from `main`.
- How to create a branch manually.
- What `git status` shows.
- What `git add` does.
- What `git commit` does.
- What `git push` does.
- The difference between local and remote branches.
- Why Pull Request direction matters.
- Why `main` should be protected.
- How GitHub rulesets protect branches.
- The difference between assignee and reviewer.
- Why a Pull Request author cannot approve their own PR.
- How independent approval works.
- How repository-admin bypass works.
- Why owner bypass is useful for solo learning but should be controlled in a production team environment.
- Why force pushes should be blocked on `main`.
- Why direct commits to `main` should be prevented.

---

# Interview Questions

## 1. What is a Git branch?
A Git branch is an independent line of development that allows changes to be made without directly modifying the main branch.

---

## 2. Why should developers use feature branches?
Feature branches isolate development work and allow changes to be reviewed and tested before they are merged into the trusted main branch.

---

## 3. What does `git status` do?
`git status` shows the current branch and the state of modified, staged, and untracked files.

---

## 4. What does `git add` do?
`git add` moves selected changes from the working directory into the staging area.

---

## 5. What does `git commit` do?
`git commit` creates a saved snapshot of the staged changes in the local Git repository history.

---

## 6. What does `git push` do?
`git push` sends local commits to the remote Git repository, such as GitHub.

---

## 7. What is a Pull Request?
A Pull Request is a request to merge changes from one branch into another branch after review.

---

## 8. What is the correct Pull Request direction for a feature branch?

```
feature branch
      |
      v
main
```

The feature branch is the source and `main` is the destination.

---

## 9. Why protect the main branch?
To prevent accidental direct changes, force pushes, unauthorized deletion, and unreviewed code from entering the trusted branch.

---

## 10. What is the difference between an assignee and a reviewer?
An assignee is responsible for handling the Pull Request.

A reviewer examines the code and provides approval or requests changes.

---

## 11. Can a Pull Request author approve their own PR?
Their own approval does not satisfy an independent required-review rule.

Another eligible reviewer is normally required.

---

## 12. What is a GitHub ruleset?
A GitHub ruleset defines protection rules that GitHub enforces on selected branches or tags.

---

## 13. What is an admin bypass?
Admin bypass allows users with configured bypass permissions to override some branch protection rules when required.

---

## 14. Why allow admin bypass in this project?
This is currently a solo learning repository with no second reviewer available.

The bypass allows development to continue while preserving the Pull Request and branch-protection structure.

---

## 15. Would admin bypass normally be used for every production merge?
No.

In a team environment, independent review should normally be used. Bypass should be reserved for controlled exceptions.

---

# Phase 3 Completion Checklist

```
✅ Feature branch created manually
✅ Git branch verified
✅ File changes made
✅ git status used
✅ Changes staged with git add
✅ Changes committed
✅ Changes pushed to GitHub
✅ Git identity configured
✅ Pull Request created
✅ Correct PR direction understood
✅ Main branch ruleset created
✅ Pull Request required before merge
✅ Approval requirement configured
✅ Code Owner review configured
✅ Direct main commit tested and blocked
✅ Unapproved merge tested and blocked
✅ Force push blocked
✅ Deletion protection enabled
✅ Admin bypass configured for solo development
✅ Issues documented
✅ Root causes documented
✅ Fixes documented
✅ Learnings documented
✅ Interview questions documented
```

# Phase 3 — COMPLETED ✅

```
One small note: if you have not actually created a `.github/CODEOWNERS` file yet, keep the “Require review from Code Owners” setting in the documentation, but do not claim that a specific owner mapping is configured until we create that file.
```

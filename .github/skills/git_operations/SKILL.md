---
name: git_operations
description: Git workflow skill for large code changes, write meaningful commit messages, stage safely, and commit so users can easily revert when needed. Use only when making large multi-file changes.
---

## Purpose
Create safe, reversible checkpoints for large implementations by producing high-quality commit messages and making one or more clean commits.

## Use this skill when
- A task introduces large changes across multiple files
- A feature is substantial enough that rollback may be needed
- You need clear commit history for review and troubleshooting

## Do not use this skill when
- Change is tiny (for example 1 to 2 small-file edits)
- The user asked for no commit
- Work is still exploratory and unstable

## Large-change gate
Treat as large change when one or more are true:
- 5 or more files modified
- 150 or more total changed lines
- New feature, major refactor, or behavior change across layers
- User explicitly requests checkpoint commits

## Workflow
1. Check repo state first
- Run git status
- Review changed files and confirm scope

2. Safety check for secrets before staging
- Ensure sensitive files are not staged: .env, keys, tokens, local credential files
- If sensitive files are staged, unstage immediately and add ignore rules if appropriate

3. Group changes into logical commit units
- Prefer one feature commit when tightly related
- Split into 2 or more commits if there are distinct concerns (for example: UI changes vs tests vs docs)

4. Craft meaningful commit message
- Subject line format:
  - <type>: <what changed> for <why>
- Recommended types: feat, fix, refactor, test, docs, chore
- Keep subject concise and specific
- Add body when change is large:
  - What was changed
  - Why it was needed
  - Risks or migration notes

5. Stage intentionally
- Use targeted staging by file or hunk when needed
- Re-check with git status before commit

6. Commit and verify
- Run git commit with the prepared message
- Run git log -1 --stat to confirm commit content
- Report commit hash and summary to user

## Commit message templates
Single-line:
- feat: add mobile queue playback controls for smoother TV handoff
- fix: prevent duplicate queue inserts during rapid add requests

Subject + body:
- Subject: feat: add karaoke preparation pipeline checkpoints for easier recovery
- Body:
  - Introduce staged processing checkpoints for download, demucs, and render
  - Improves failure recovery and shortens rerun time
  - Adds route/service tests for regression coverage

## Completion checks
- Commit exists and includes only intended files
- No secret or local environment files committed
- Message clearly states what and why
- User receives hash + concise rollback hint (for example: git revert <hash>)

## Notes
- Prefer non-interactive git commands
- Never use destructive reset commands unless explicitly requested

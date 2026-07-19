# Pull Request Authoring

## Purpose

Procedure for drafting a Conventional Commit-formatted PR title and a template-compatible PR body from the actual state of a branch's changes. This produces a **draft** for the user to copy into `gh pr create` or the GitHub UI themselves. It never creates a commit, stages files, pushes a branch, or opens/publishes a pull request.

"PR message" means both the title and the body together.

## Authoritative inputs

- `.github/PULL_REQUEST_TEMPLATE.md` — the body's field structure.
- `CONTRIBUTING.md` — branch naming, Conventional Commit title format, and the rule that the PR title becomes the squash commit message.
- `.github/workflows/pr-policy.yml` — the CI check that enforces the title format; treat it as confirmation of the format, not a separate source of rules.
- `agent-workflows/references/verification.md` — what a completed check for a given layer looks like.
- The current `git status` and diff for the branch being described.
- Verification results actually run and reported earlier in the conversation, or told directly to the agent by the user.

## Contents

- [When this applies](#when-this-applies)
- [Gather evidence](#gather-evidence)
- [Select the title](#select-the-title)
- [Fill the template](#fill-the-template)
- [Avoid fabrication](#avoid-fabrication)
- [Render and hand off](#render-and-hand-off)
- [Final checklist](#final-checklist)

## When this applies

Use this procedure when asked to write, draft, or revise a PR title, PR description, PR body, or PR summary for the current branch's changes.

This is a drafting step only. Producing a draft never authorizes staging, committing, pushing, or creating/publishing an actual pull request — those remain separate, explicit actions the user takes themselves.

## Gather evidence

Before drafting anything:

1. Inspect the full set of changes the PR would contain: the diff of the branch against its base (e.g. `git diff main...HEAD`), plus any staged or unstaged working-tree changes on top of it. A clean working tree does not mean there's nothing to describe — most of a real PR's content is already committed on the branch. The draft describes what actually changed across all of that, not what the request implies changed.
2. If an issue was supplied or referenced earlier in the conversation, read it for the relationship it actually establishes (fixes it, is merely related to it, etc.) — don't assume closure just because one was mentioned.
3. Collect verification evidence **only from what has already been run and reported** — earlier in this conversation, or directly stated by the user. Do not run `mypy`/`eslint`/`tsc`/anything else from `verification.md` as part of drafting; this procedure reports on evidence that already exists, it doesn't generate it.
4. If the diff spans changes that don't obviously belong together (e.g. an unrelated refactor mixed into a bug fix), say so rather than presenting it as one clean, coherent PR.
5. If the branch matches its base and the working tree is clean — nothing to describe — say that plainly and ask for the missing evidence rather than inventing a summary.

## Select the title

- Format: `feat|fix|chore(optional-scope): description`, matching `CONTRIBUTING.md` and enforced by `pr-policy.yml`.
- Pick the type from what the diff actually does — `feat` for new capability, `fix` for a correction, `chore` for everything else (tooling, docs, maintenance).
- Add `!` before the colon only when a breaking change was explicitly confirmed (by the user or unambiguously by the diff itself) — never speculate about breaking-ness to decide this.
- The title becomes the squash commit message — keep it a single accurate line, not a summary of every file touched.

## Fill the template

Match `.github/PULL_REQUEST_TEMPLATE.md` exactly — do not add, remove, or reorder its sections.

- **Summary** — describe the behavior change and why, in prose. Not a file-by-file list; that's what the diff itself already shows.
- **Related Issue** — use `Closes #N` or `Fixes #N` only when the request or issue explicitly establishes that this PR resolves it. Use `Relates to #N` when the connection is looser. Keep the section heading even when no issue was supplied — write `_None_` rather than dropping the section (the template's sections are preserved exactly, per above); never invent a number.
- **Testing** — list only the verification commands actually run and reported, with their actual results. State plainly which applicable checks were not run rather than omitting them silently.
- **Checklist** — check a box only when the gathered evidence actually supports it. Leave a box unchecked when the evidence doesn't cover it, rather than checking it optimistically.

## Avoid fabrication

Never invent: an issue number, a test result, a screenshot, a "no breaking changes" claim, or a checklist state not backed by evidence gathered above. Where evidence is missing, the draft says so explicitly instead of presenting an optimistic guess as fact.

## Render and hand off

Present the complete title + body as the deliverable, then stop. Point out anything the user should double-check (an assumed issue relationship, a checklist item left unchecked for lack of evidence, a diff that looked mixed-scope). Do not stage, commit, push, or create/publish the PR — that is the user's action to take with the draft.

## Final checklist

- [ ] Evidence gathered from actual `git status`/diff, not assumed from the request
- [ ] Verification evidence used only from what was already run/reported — no checks run proactively by this procedure
- [ ] Title matches the enforced Conventional Commit format, with `!` only for confirmed breaking changes
- [ ] Body matches the current PR template's sections exactly, nothing added or removed
- [ ] Related Issue wording (`Closes`/`Fixes`/`Relates to`) matches the actual, stated relationship
- [ ] Testing section lists only real commands and real results; unrun checks stated plainly
- [ ] Checklist boxes reflect only what the evidence supports
- [ ] Draft handed off for the user to publish themselves — no git or GitHub action taken

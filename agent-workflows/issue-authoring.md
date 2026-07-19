# Issue Authoring

## Purpose

Procedure for turning a bug report, feature idea, or improvement request into a reviewable draft issue for this repository. This file owns the investigation, evidence-handling, scoping, and acceptance-criteria procedure. Field structure lives in `.github/ISSUE_TEMPLATE/*.yml`; implementation detail lives in `references/*.md`.

This produces a **draft** for the user to review. It does not publish anything to GitHub.

## Authoritative inputs

- `.github/ISSUE_TEMPLATE/bug.yml`
- `.github/ISSUE_TEMPLATE/feature.yml`
- `.github/ISSUE_TEMPLATE/enhancement.yml`
- `agent-workflows/references/architecture.md`, `database.md`, `sync.md`, `api.md`, `frontend.md`, `verification.md`
- The current source code — authoritative over any reference file or prior issue when they disagree.

## Contents

- [When this applies](#when-this-applies)
- [Select the template](#select-the-template)
- [Inspect current behavior](#inspect-current-behavior)
- [Search related work](#search-related-work)
- [Track evidence and uncertainty](#track-evidence-and-uncertainty)
- [Define scope and outcomes](#define-scope-and-outcomes)
- [Write acceptance criteria](#write-acceptance-criteria)
- [Render the draft](#render-the-draft)
- [Review boundary](#review-boundary)
- [Final checklist](#final-checklist)

## When this applies

Use this procedure when asked to:

- draft a new issue;
- improve an existing issue draft;
- investigate whether some reported behavior warrants an issue;
- convert an informal request ("hey can we...", a Slack message, a one-line complaint) into a reviewable repository issue.

Three distinct activities live under this umbrella — keep them distinct in what you say to the user:

- **Investigating and drafting** — reading code, forming a description, proposing acceptance criteria. This is the default and requires no special authorization.
- **Editing a local draft** — revising a draft already in progress based on feedback. Still just drafting.
- **Publishing or modifying a GitHub issue** — actually creating/editing a real issue via `gh issue create`/`gh issue edit` or the GitHub UI. This is a separate action (see [Review boundary](#review-boundary)) and is never implied by the act of drafting.

## Select the template

Inspect all three templates before choosing. Selection rules:

| Template | Use when |
|---|---|
| `bug.yml` | Existing behavior is broken, incorrect, or inconsistent with an established contract (a documented API shape, a schema constraint, a UI behavior described in `references/frontend.md`) |
| `feature.yml` | Entirely new user- or system-facing functionality is being proposed — nothing currently does this |
| `enhancement.yml` | Existing functionality, workflow, performance, maintainability, or usability should improve, but nothing is actually broken |

If classification is ambiguous (e.g. "the sync scheduler should also email on failure" is arguably a feature or an enhancement to sync), record the ambiguity explicitly in the draft rather than silently blending two templates' field structures. Pick the single closest template and note the alternative considered.

## Inspect current behavior

Never draft "current behavior" from a reference file alone. Before writing a Description:

1. Identify the affected application layer (backend route, DB query, sync stage, frontend page/component).
2. Load only the reference(s) relevant to that layer:

   | Area | Reference |
   |---|---|
   | System boundaries / runtime lifecycle | `references/architecture.md` |
   | Database schema, queries, aggregation | `references/database.md` |
   | Sync pipeline, scheduling, scope | `references/sync.md` |
   | HTTP endpoints, params, response shape | `references/api.md` |
   | Pages, components, types, styling | `references/frontend.md` |
   | Commands, PR checklist | `references/verification.md` |
3. Inspect the actual current implementation directly (read the file, don't rely on the reference's paraphrase).
4. Trace enough data/control flow to verify the reported behavior actually happens the way it's claimed to — for a bug, this usually means finding the specific line(s) responsible; for a feature/enhancement, it means confirming the described gap actually exists.
5. Record concrete files and symbols (`backend/database.py:183` style) when they clarify the report.
6. If a reference file and the source code disagree, trust the code, and say so in the draft rather than silently picking one.

## Search related work

When GitHub access is available, do a read-only search before finalizing scope. Search across several signals, not just one:

- user-facing terminology (what a user would call the problem);
- component or page names (`VideoAnalytics`, `SyncStatus`);
- endpoint paths (`/analytics/videos/top`);
- backend helper or frontend symbol names (`get_top_videos_by_traffic_source`, `toTopVideoShape`);
- exact error messages, if any were reported.

Look specifically for: direct duplicates, similar symptoms/requests, dependencies (issues this one would need to wait on), blocked-or-superseding work, and related PRs already in flight.

Record the outcome as exactly one of:

- **Duplicate found** — link it, stop drafting a new issue unless asked to proceed anyway.
- **Related work found** — link it, note the relationship, continue drafting.
- **No related issue found** — state this plainly.
- **Search unavailable** — state this plainly and continue. Missing GitHub access must never block drafting; it just means the draft says duplicate-checking wasn't done.

## Track evidence and uncertainty

Every draft maintains four distinct buckets — don't let them blur together:

- **Verified facts** — confirmed by reading code, configuration, or an existing issue; or independently reproduced.
- **Assumptions** — reasonable, but not independently confirmed (e.g. "this likely affects the Shorts case too, but that path wasn't traced").
- **Unresolved decisions** — choices that need maintainer or product direction, not something resolvable by reading more code (e.g. "should this be a hard error or a silent fallback?").
- **Related work** — relevant issues, PRs, or dependencies surfaced during the search above.

An unsupported assumption must never be presented as current behavior — phrase it as an assumption, explicitly. If an assumption would materially change scope or acceptance criteria depending on which way it resolves, promote it to an unresolved decision instead of leaving it buried as an assumption.

## Define scope and outcomes

The draft's Description should cover:

- the problem or opportunity;
- why it matters (impact, who's affected);
- current verified behavior (from direct inspection, not a reference file's paraphrase);
- desired outcome — described as **observable behavior**, not a prescribed implementation;
- affected users or workflows;
- relevant edge cases;
- explicit non-goals (what this issue deliberately does not cover).

Implementation detail may be included only when: it was confirmed by inspected code, it's required by a compatibility constraint worth flagging (e.g. "must preserve the existing `sort_by` allow-list pattern"), or the user explicitly asked for a specific implementation.

## Write acceptance criteria

Each criterion:

- is a Markdown checkbox;
- describes exactly one observable result;
- is independently verifiable (someone else could check it without asking the author what they meant);
- avoids vague wording like "works correctly" or "handles edge cases properly" — name the actual edge case;
- includes compatibility/non-regression expectations where relevant (e.g. "existing `/videos` sort behavior is unchanged").

For documentation-only work, criteria should name the expected files, which reference file canonically owns the content, what validation was run, and confirm no runtime/application files changed.

Do not turn a speculative implementation step ("refactor X to use Y") into an acceptance criterion — acceptance criteria describe outcomes, not a plan.

## Render the draft

### Bug (`bug.yml` fields)

```markdown
## Description

### Current behavior
### Expected behavior
### Verified facts
### Assumptions
### Unresolved decisions
### Non-goals

## Reproduction steps

## Logs or screenshots

## Acceptance criteria

## Confirmation
```

Include the repository's required secrets/personal-data confirmation checkbox — never skip it.

### Feature or Enhancement (`feature.yml` / `enhancement.yml` fields)

```markdown
## Description

### Current context
### Desired outcome
### Verified facts
### Assumptions
### Unresolved decisions
### Edge cases
### Non-goals

## Acceptance criteria

## Additional context
```

`Additional context` holds related issues, dependencies, alternatives considered, or supporting evidence gathered during the search step.

Do not add empty subheadings just to look complete. Omit a subsection that has nothing in it, or write "None identified" only where that absence is itself meaningful information (e.g. "Assumptions: None identified" tells the reader the whole draft rests on confirmed facts — worth stating; an empty "Non-goals" with nothing to say is usually better just omitted).

## Review boundary

This procedure ends at a reviewable draft, not a published issue. Before considering the draft done:

1. Present the complete draft to the user.
2. Summarize the assumptions and unresolved decisions in a short list — don't make the user re-read the whole draft to find them.
3. Report whether GitHub duplicate/related-work searching was actually performed, and what it found (or that it was unavailable).
4. If unresolved decisions remain, ask the user for direction on those specifically rather than guessing.

Creating or editing an actual GitHub issue is a separate, explicit action outside this procedure's scope — never assumed just because a draft was produced.

## Final checklist

- [ ] Correct template selected (or ambiguity recorded and closest template chosen)
- [ ] Current behavior confirmed by inspecting actual code, not asserted from a reference file alone
- [ ] Relevant references consulted (only the ones for the affected layer)
- [ ] GitHub search performed, or explicitly noted as unavailable — never silently skipped
- [ ] Verified facts, assumptions, unresolved decisions, and related work kept distinct
- [ ] Desired outcome stated as observable behavior, not an unverified implementation
- [ ] Edge cases and non-goals included
- [ ] Acceptance criteria are observable, verifiable, and free of vague wording
- [ ] Draft presented for review, with assumptions/unresolved decisions summarized

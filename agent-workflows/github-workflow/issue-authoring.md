# Issue Authoring

## Purpose

Procedure for turning a bug report, feature idea, or improvement request into a reviewable draft issue for the destination repository. This file owns the investigation, evidence-handling, scoping, and acceptance-criteria procedure. Field structure lives in that repository's own issue templates; implementation detail lives in its own documentation.

This produces a **draft** for the user to review. It does not publish anything to GitHub.

## Authoritative inputs

- The destination repository's own issue templates (for example, under `.github/ISSUE_TEMPLATE/`).
- The destination repository's own documentation for the affected area (architecture, data model, API, UI, or equivalent).
- The current source code — authoritative over any documentation or prior issue when they disagree.

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
- convert an informal request ("hey can we...", a chat message, a one-line complaint) into a reviewable repository issue.

Three distinct activities live under this umbrella — keep them distinct in what you say to the user:

- **Investigating and drafting** — reading code, forming a description, proposing acceptance criteria. This is the default and requires no special authorization.
- **Editing a local draft** — revising a draft already in progress based on feedback. Still just drafting.
- **Publishing or modifying a GitHub issue** — actually creating/editing a real issue via the GitHub CLI or the GitHub UI. This is a separate action (see [Review boundary](#review-boundary)) and is never implied by the act of drafting.

## Select the template

Inspect every available issue template before choosing, and select the one whose intent actually matches the request — for example, a template for broken/incorrect existing behavior, a template for entirely new functionality, and a template for improving something that already works but isn't broken. Names and exact field sets vary by repository; discover them rather than assuming a fixed set.

If classification is ambiguous (a change could plausibly fit more than one template), record the ambiguity explicitly in the draft rather than silently blending two templates' field structures. Pick the single closest template and note the alternative considered.

## Inspect current behavior

Never draft "current behavior" from documentation alone. Before writing a description:

1. Identify the affected application layer.
2. Load only the destination repository's documentation relevant to that layer.
3. Inspect the actual current implementation directly (read the file, don't rely on a reference's paraphrase).
4. Trace enough data/control flow to verify the reported behavior actually happens the way it's claimed to — for a bug, this usually means finding the specific line(s) responsible; for a feature/enhancement, it means confirming the described gap actually exists.
5. Record concrete files and symbols (e.g. `path/to/file.py:183`) when they clarify the report.
6. If a reference and the source code disagree, trust the code, and say so in the draft rather than silently picking one.

## Search related work

When GitHub access is available, do a read-only search before finalizing scope. Search across several signals, not just one:

- user-facing terminology (what a user would call the problem);
- component, page, or module names;
- endpoint or route paths;
- backend or frontend symbol names;
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
- **Assumptions** — reasonable, but not independently confirmed (e.g. "this likely affects a related case too, but that path wasn't traced").
- **Unresolved decisions** — choices that need maintainer or product direction, not something resolvable by reading more code (e.g. "should this be a hard error or a silent fallback?").
- **Related work** — relevant issues, PRs, or dependencies surfaced during the search above.

An unsupported assumption must never be presented as current behavior — phrase it as an assumption, explicitly. If an assumption would materially change scope or acceptance criteria depending on which way it resolves, promote it to an unresolved decision instead of leaving it buried as an assumption.

## Define scope and outcomes

The draft's Description should cover:

- the problem or opportunity;
- why it matters (impact, who's affected);
- current verified behavior (from direct inspection, not a reference's paraphrase);
- desired outcome — described as **observable behavior**, not a prescribed implementation;
- affected users or workflows;
- relevant edge cases;
- explicit non-goals (what this issue deliberately does not cover).

Implementation detail may be included only when: it was confirmed by inspected code, it's required by a compatibility constraint worth flagging, or the user explicitly asked for a specific implementation.

## Write acceptance criteria

Each criterion:

- is a Markdown checkbox carrying a sequential identifier — `- [ ] **AC-1:** ...`, `- [ ] **AC-2:** ...`, and so on, numbered without gaps;
- describes exactly one observable result;
- covers an outcome that is essential to considering the issue done;
- does not duplicate or substantially overlap another criterion;
- is independently verifiable (someone else could check it without asking the author what they meant);
- avoids vague wording like "works correctly" or "handles edge cases properly" — name the actual edge case;
- includes compatibility/non-regression expectations where relevant.

Consolidate criteria that describe the same observable result. Two checkboxes that a reviewer would verify with the same check are one criterion, not two — merge them and keep the wording that names the outcome most concretely.

Five criteria is the default maximum. Exceeding it is allowed only when the additional criteria are independently essential, describe distinct outcomes, and cannot reasonably be consolidated — never as a way to enumerate implementation steps or restate the same result in different words.

For documentation-only work, criteria should name the expected files, which document canonically owns the content, what validation was run, and confirm no runtime/application files changed.

Do not turn a speculative implementation step ("refactor X to use Y") into an acceptance criterion — acceptance criteria describe outcomes, not a plan.

## Render the draft

Render the issue title and every issue-form field as separate user-facing items:

- Present the proposed title as ordinary text outside a code fence: `Title: <proposed title>`.
- Present each issue-form label as ordinary text outside a code fence.
- Immediately follow each label with its own fenced `markdown` block containing only the value to paste into that field.
- Never wrap the entire issue in one large code fence.
- Never put field labels such as `## Description` or explanatory text such as "copy this" inside a field's code block.
- Keep template selection, search results, assumptions/unresolved-decision summaries, and other handoff commentary as ordinary text outside all copyable blocks.
- Preserve the template's field order. Optional fields still get their own block when they have content; omit an optional field entirely when it has no content.

Use this output shape for a bug-style draft:

````text
Title: `Proposed issue title`

Description

```markdown
### Current behavior
...

### Expected behavior
...
```

Reproduction steps

```markdown
1. ...
2. ...
```

Logs or screenshots

```markdown
...
```

Acceptance criteria

```markdown
- [ ] **AC-1:** First verifiable outcome confirming the reported behavior is fixed
- [ ] **AC-2:** Second verifiable outcome covering the named edge case
```

Confirmation

```markdown
- [x] I have removed secrets, tokens, and personal data from this report
```
````

Include any repository-required secrets/personal-data confirmation field — never skip it if the template has one. `Reproduction steps` and `Logs or screenshots` are optional and should be omitted when they have no content.

Use this output shape for a feature- or enhancement-style draft:

````text
Title: `Proposed issue title`

Description

```markdown
### Current context
...

### Desired outcome
...
```

Acceptance criteria

```markdown
- [ ] **AC-1:** First verifiable outcome describing the completed behavior
- [ ] **AC-2:** Second verifiable outcome covering compatibility or a named edge case
```

Additional context

```markdown
...
```
````

`Additional context` holds related issues, dependencies, alternatives considered, or supporting evidence gathered during the search step. It is optional and should be omitted when it has no content.

Do not add empty subheadings just to look complete. Omit a subsection that has nothing in it, or write "None identified" only where that absence is itself meaningful information.

## Review boundary

This procedure ends at a reviewable draft, not a published issue. Before considering the draft done:

1. Present the complete draft to the user.
2. Summarize the assumptions and unresolved decisions in a short list — don't make the user re-read the whole draft to find them.
3. Report whether GitHub duplicate/related-work searching was actually performed, and what it found (or that it was unavailable).
4. If unresolved decisions remain, ask the user for direction on those specifically rather than guessing.

Creating or editing an actual GitHub issue is a separate, explicit action outside this procedure's scope — never assumed just because a draft was produced.

## Final checklist

- [ ] Correct template selected (or ambiguity recorded and closest template chosen)
- [ ] Current behavior confirmed by inspecting actual code, not asserted from documentation alone
- [ ] Relevant local documentation consulted (only what's relevant to the affected layer)
- [ ] GitHub search performed, or explicitly noted as unavailable — never silently skipped
- [ ] Verified facts, assumptions, unresolved decisions, and related work kept distinct
- [ ] Desired outcome stated as observable behavior, not an unverified implementation
- [ ] Edge cases and non-goals included
- [ ] Acceptance criteria are observable, verifiable, and free of vague wording
- [ ] Every criterion is essential; overlapping or duplicate criteria consolidated into one
- [ ] Criteria carry sequential `AC-1`, `AC-2`, ... identifiers with no gaps
- [ ] No more than five criteria, unless the extras are distinct essential outcomes that cannot reasonably be consolidated
- [ ] Title and field labels rendered as ordinary text; each populated field has its own `markdown` code block containing only pasteable field content
- [ ] No single code block wraps multiple issue-form fields or handoff commentary
- [ ] Draft presented for review, with assumptions/unresolved decisions summarized

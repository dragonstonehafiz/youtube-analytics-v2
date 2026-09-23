# Documentation Maintenance

## Purpose

Procedure for keeping this repository's root instructions and `docs/` reference documentation current without reintroducing duplication. This file is itself a procedure, not application knowledge.

Code and authoritative policy remain the source of truth; documentation follows them, never the reverse. Documentation work does not authorize implementation. See [`repository-rules.md`](../repository-rules.md) for this repository's safety and permission boundaries — never create commits, run `git push`, or publish documentation remotely; destructive deletion or reset requires explicit approval.

## When this applies

Use this workflow when:

- application behavior changes;
- a verification command changes;
- a coding or safety rule changes;
- a task procedure changes;
- a reference is found to be stale;
- files are renamed or documentation paths change;
- issue templates or contribution rules change.

Documentation updates accompany the implementation they describe — they are not deferred to a later cleanup pass.

## Contents

- [When this applies](#when-this-applies)
- [Find the ownership map](#find-the-ownership-map)
- [Update workflow](#update-workflow)
- [Layer boundaries](#layer-boundaries)
- [Keep documentation implementation-derived](#keep-documentation-implementation-derived)
- [Control duplication](#control-duplication)
- [Maintain links and paths](#maintain-links-and-paths)
- [Verification](#verification)
- [Action boundaries](#action-boundaries)
- [Final checklist](#final-checklist)

## Find the ownership map

[`README.md`](../README.md) is this repository's canonical-documentation ownership map — which subject lives in which file. A fact not covered by that map doesn't have an obvious canonical home yet; flag this rather than guessing where it belongs.

Every fact should have exactly one canonical home. A file not in the ownership map doesn't own application knowledge — it either summarizes or links to the file that does.

## Update workflow

1. Inspect the implementation or policy change.
2. Identify which canonical document owns the affected information, using [`README.md`](../README.md)'s ownership map.
3. Update only confirmed current behavior — verify against the actual code or policy, don't paraphrase from memory of what it used to say.
4. Remove or correct stale statements rather than appending a correction next to them.
5. Check related documents for links or summaries that also need updating (a root-file one-liner, a cross-reference in another reference file, a routing entry in `AGENTS.md`).
6. Avoid copying the same detail into multiple files — link instead.
7. Run documentation validation (see [Verification](#verification)).
8. Confirm no unrelated runtime/application files changed.

Code remains authoritative for application behavior. Repository policy files remain authoritative for workflow and safety requirements.

## Layer boundaries

### Root instructions

`AGENTS.md` contains only rules that apply to virtually every task: a one-line pointer to [`repository-rules.md`](../repository-rules.md) and direct links to each `docs/` page for planning, drafting, documentation maintenance, project discovery, and verification.

Component behavior, endpoint details, schema descriptions, and page-specific conventions do not belong in `AGENTS.md`.

### Task procedures

`docs/programming-workflow/implementation-planning.md`, `docs/github-workflow/issue-authoring.md`, `docs/github-workflow/pull-request-authoring.md`, and this file own procedures: how to draft an issue, how to create an implementation plan, how to maintain documentation. They link to references instead of embedding detailed application knowledge.

### References

References own detailed application knowledge. Each fact has one practical canonical home. Cross-links between references are allowed, but an agent should never need to follow a long chain to find relevant information.

## Keep documentation implementation-derived

Canonical documentation describes current behavior only. Exclude:

- migration commentary such as "added since the previous documentation";
- live experiment logs;
- temporary debugging findings;
- obsolete behavior retained for historical interest;
- unsupported implementation assumptions;
- approximate operational claims that cannot be verified.

When code and a reference disagree:

1. Verify the current implementation.
2. Correct the canonical reference.
3. Check whether other references repeat the stale statement.
4. Do not preserve the obsolete statement merely as history.

## Control duplication

Limited duplication is allowed only when necessary:

- concise root verification commands in `AGENTS.md` may summarize `docs/references/verification.md`'s canonical guidance.

Detailed behavior is not duplicated across references. When duplication is unavoidable, state which file is canonical and which files contain summaries.

## Maintain links and paths

When moving or renaming documentation:

- update `AGENTS.md`'s direct links;
- update every cross-link between `docs/` pages;
- confirm every relative path resolves from the file containing it.

Do not leave compatibility copies of obsolete documentation unless explicitly required.

## Verification

This repository has no automated documentation validator. Manually confirm instead:

- every local Markdown link from `AGENTS.md` and the changed `docs/` pages resolves, including heading fragments;
- statements accurately reflect the current code;
- content lives in its correct canonical file, not a duplicate;
- no unnecessary duplication was introduced;
- application files changed only when the task genuinely required it (see `docs/references/verification.md`'s Documentation verification section).

## Action boundaries

- Documentation work does not authorize implementation.
- Agents do not create commits.
- Agents do not run `git push`.
- Agents do not publish documentation or issues remotely.
- Destructive deletion or reset requires explicit approval.

## Final checklist

- [ ] Change traced to its canonical document via `README.md`'s ownership map
- [ ] Only confirmed current behavior written; stale statements corrected, not appended around
- [ ] Related cross-links and summaries checked and updated
- [ ] No detail duplicated across references beyond what's explicitly allowed
- [ ] No migration commentary, experiment logs, or unverifiable operational claims introduced
- [ ] Renamed or moved files have every cross-link and `AGENTS.md` reference updated
- [ ] Local links manually followed and confirmed; application files confirmed untouched for docs-only work
- [ ] No commit, push, or remote publication performed

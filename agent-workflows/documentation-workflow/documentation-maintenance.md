# Documentation Maintenance

## Purpose

Procedure for keeping a repository's root instructions, shared playbooks, skill entrypoints, and reference documentation current without reintroducing duplication. This file is itself a procedure, not application knowledge — it applies to any destination repository's own documentation set.

## When this applies

Use this workflow when:

- application behavior changes;
- a verification command changes;
- a coding or safety rule changes;
- an agent workflow changes;
- a reference is found to be stale;
- files are renamed or documentation paths change;
- a skill entrypoint changes;
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

Every destination repository supplies its own canonical-documentation ownership map — which subject lives in which file. Discover it rather than assuming a fixed list: look for a project-local documentation router or an equivalent index, or infer it from existing cross-references if no explicit index exists. A fact not covered by that map doesn't have an obvious canonical home yet; flag this rather than guessing where it belongs.

Every fact should have exactly one canonical home. A file not in the ownership map doesn't own application knowledge — it either summarizes or links to the file that does.

## Update workflow

1. Inspect the implementation or policy change.
2. Identify which canonical document owns the affected information, using the destination repository's ownership map.
3. Update only confirmed current behavior — verify against the actual code or policy, don't paraphrase from memory of what it used to say.
4. Remove or correct stale statements rather than appending a correction next to them.
5. Check related documents for links or summaries that also need updating (a root-file one-liner, a cross-reference in another reference file, a routing entry in a skill entrypoint).
6. Avoid copying the same detail into multiple files — link instead.
7. Run documentation validation (see [Verification](#verification)).
8. Confirm no unrelated runtime/application files changed.

Code remains authoritative for application behavior. Repository policy files remain authoritative for workflow and safety requirements.

## Layer boundaries

### Root instructions

Root instruction files (for example `AGENTS.md`/`CLAUDE.md` or an equivalent) contain only rules that apply to virtually every task: coding conventions, dependency restrictions, verification expectations, safety and permission boundaries, and pointers to repo-local skills.

Component behavior, endpoint details, schema descriptions, and page-specific conventions do not belong in the roots.

### Shared playbooks

Playbooks own procedures: how to draft an issue, how to create an implementation plan, how to maintain documentation. They link to references instead of embedding detailed application knowledge.

### Skill entrypoints

Native skill entrypoints contain triggering descriptions, workflow selection, direct paths to shared playbooks and references, and progressive-loading guidance. They do not maintain independent copies of the workflows themselves.

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

- mandatory rules may appear in multiple root files across native agents (for example, one per agent);
- multiple native entrypoints for the same skill may contain equivalent routing;
- concise root verification commands may summarize canonical verification guidance.

Detailed behavior is not duplicated across references. When duplication is unavoidable, state which file is canonical and which files contain summaries.

## Maintain links and paths

When moving or renaming documentation:

- update every native skill entrypoint that routes to it;
- update playbook/reference cross-links;
- update root pointers;
- update the destination repository's documentation validator, if any;
- confirm every relative path resolves from the file containing it;
- avoid references deeper than one directory below a skill entrypoint where practical.

Do not leave compatibility copies of obsolete documentation unless explicitly required.

## Verification

Run the destination repository's own documentation validator, if one exists, and note its exact command and what it checks — treat that command as authoritative rather than assuming this file's own examples still apply. A validator of this kind typically confirms: skill entrypoints exist with valid frontmatter, entrypoints route to the same shared targets consistently, and every routing target actually resolves to a real file.

Also manually confirm what an automated validator cannot determine:

- whether statements accurately reflect the current code;
- whether content lives in its correct canonical file, not a duplicate;
- whether unnecessary duplication was introduced;
- whether application files changed unintentionally.

## Action boundaries

- Documentation work does not authorize implementation.
- Agents do not create commits.
- Agents do not run `git push`.
- Agents do not publish documentation or issues remotely.
- Destructive deletion or reset requires explicit approval.

## Final checklist

- [ ] Change traced to its canonical document via the destination repository's ownership map
- [ ] Only confirmed current behavior written; stale statements corrected, not appended around
- [ ] Related cross-links, summaries, and routing entries checked and updated
- [ ] No detail duplicated across references beyond what's explicitly allowed
- [ ] No migration commentary, experiment logs, or unverifiable operational claims introduced
- [ ] Renamed or moved files have every cross-link and skill-entrypoint reference updated
- [ ] Verification run using the destination repository's own validator; application files confirmed untouched for docs-only work
- [ ] No commit, push, or remote publication performed

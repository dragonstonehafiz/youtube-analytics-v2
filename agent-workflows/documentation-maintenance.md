# Documentation Maintenance

## Purpose

Procedure for keeping root instructions, shared playbooks, skill entrypoints, and project references current without reintroducing duplication. This file is itself a procedure, not application knowledge — it lives beside `issue-authoring.md` and `implementation-planning.md`, not under `references/`.

## When this applies

Use this workflow when:

- application behavior changes;
- a verification command changes;
- a coding or safety rule changes;
- an agent workflow changes;
- a reference is found to be stale;
- files are renamed or documentation paths change;
- either skill entrypoint changes;
- issue templates or contribution rules change.

Documentation updates accompany the implementation they describe — they are not deferred to a later cleanup pass.

## Contents

- [When this applies](#when-this-applies)
- [Documentation ownership](#documentation-ownership)
- [Update workflow](#update-workflow)
- [Layer boundaries](#layer-boundaries)
- [Route changes to canonical documents](#route-changes-to-canonical-documents)
- [Keep documentation implementation-derived](#keep-documentation-implementation-derived)
- [Control duplication](#control-duplication)
- [Maintain links and paths](#maintain-links-and-paths)
- [Verification](#verification)
- [Action boundaries](#action-boundaries)
- [Final checklist](#final-checklist)

## Documentation ownership

| Subject | Canonical file |
|---|---|
| System architecture and repository layout | `references/architecture.md` |
| Schema, relationships, and query behavior | `references/database.md` |
| Sync and ingestion behavior | `references/sync.md` |
| HTTP contracts | `references/api.md` |
| Frontend types, clients, pages, components, styling | `references/frontend.md` |
| Verification commands and implementation patterns | `references/verification.md` |
| Issue-drafting procedure | `issue-authoring.md` |
| Implementation-planning procedure | `implementation-planning.md` |
| Documentation maintenance | `documentation-maintenance.md` |
| Always-applicable agent rules | `AGENTS.md` and `CLAUDE.md` |
| Agent-specific discovery and routing | Both repo-local `SKILL.md` entrypoints |
| User setup and usage | `README.md` |
| Contributor and PR conventions | `CONTRIBUTING.md` and `.github/` templates |

Every fact has exactly one canonical home from this table. A file not listed here doesn't own application knowledge — it either summarizes or links to the file that does.

## Update workflow

1. Inspect the implementation or policy change.
2. Identify which canonical document owns the affected information, using the ownership table above.
3. Update only confirmed current behavior — verify against the actual code or policy, don't paraphrase from memory of what it used to say.
4. Remove or correct stale statements rather than appending a correction next to them.
5. Check related documents for links or summaries that also need updating (a root-file one-liner, a cross-reference in another `references/*.md`, a routing entry in a skill entrypoint).
6. Avoid copying the same detail into multiple files — link instead.
7. Run documentation validation (see [Verification](#verification)).
8. Confirm no unrelated runtime files changed.

Code remains authoritative for application behavior. Repository policy files remain authoritative for workflow and safety requirements.

## Layer boundaries

### Root instructions

`AGENTS.md` and `CLAUDE.md` contain only rules that apply to virtually every task: coding conventions, dependency restrictions, verification expectations, safety and permission boundaries, and pointers to repo-local skills.

Component behavior, endpoint details, schema descriptions, and page-specific conventions do not belong in the roots.

### Shared playbooks

Playbooks own procedures: how to draft an issue, how to create an implementation plan, how to maintain documentation. They link to references instead of embedding detailed application knowledge.

### Skill entrypoints

The two `SKILL.md` files contain triggering descriptions, workflow selection, direct paths to shared playbooks and references, and progressive-loading guidance. They do not maintain independent copies of the workflows themselves.

### References

References own detailed application knowledge. Each fact has one practical canonical home. Cross-links between references are allowed, but an agent should never need to follow a long chain to find relevant information.

## Route changes to canonical documents

| Implementation change | Required documentation review |
|---|---|
| Add or alter a database column | `database.md`; possibly `api.md`, `frontend.md`, and `sync.md` |
| Change sync scope or checkpoint behavior | `sync.md`; possibly `api.md` and `frontend.md` |
| Add or change an endpoint | `api.md`; frontend reference if consumed by the UI |
| Change a TypeScript response type | `frontend.md`; confirm `api.md` remains aligned |
| Change page filters or URL parameters | `frontend.md`; possibly `api.md` |
| Add a verification command | `verification.md`; roots only if universally applicable |
| Change issue-template fields | `issue-authoring.md` |
| Change planning requirements | `implementation-planning.md` |
| Rename a playbook/reference | both skill entrypoints and validation expectations |
| Add a universal coding rule | both roots; detailed explanation elsewhere only if needed |

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

- mandatory rules may appear in both root files;
- both skill entrypoints may contain equivalent routing;
- concise root verification commands may summarize canonical verification guidance.

Detailed behavior is not duplicated across references. When duplication is unavoidable, state which file is canonical and which files contain summaries.

## Maintain links and paths

When moving or renaming documentation:

- update both skill entrypoints;
- update playbook/reference cross-links;
- update root pointers;
- update the dedicated validation script;
- confirm every relative path resolves from the file containing it;
- avoid references deeper than one directory below a skill entrypoint where practical.

Do not leave compatibility copies of obsolete documentation unless explicitly required.

## Verification

Until the dedicated validation script exists, use:

```bash
find agent-workflows -maxdepth 2 -type f -print
rg -n '^#|^##' agent-workflows
rg -n 'references/|issue-authoring.md|implementation-planning.md|documentation-maintenance.md' agent-workflows
rg -n '[[:blank:]]+$' agent-workflows
git status --short -- backend frontend
```

Also manually confirm:

- referenced paths exist;
- roots were updated only when a universal rule changed;
- both skill entrypoints remain aligned;
- no stale implementation-history wording was introduced;
- application files remain untouched for documentation-only work.

Once the dedicated validation script exists, this playbook names that script as the primary check rather than duplicating its implementation.

## Action boundaries

- Documentation work does not authorize implementation.
- Agents do not create commits.
- Agents do not run `git push`.
- Agents do not publish documentation or issues remotely.
- Destructive deletion or reset requires explicit approval.

## Final checklist

- [ ] Change traced to its canonical document via the ownership table
- [ ] Only confirmed current behavior written; stale statements corrected, not appended around
- [ ] Related cross-links, summaries, and routing entries checked and updated
- [ ] No detail duplicated across references beyond what's explicitly allowed
- [ ] No migration commentary, experiment logs, or unverifiable operational claims introduced
- [ ] Renamed or moved files have every cross-link and skill-entrypoint reference updated
- [ ] Verification run; application files confirmed untouched for docs-only work
- [ ] No commit, push, or remote publication performed

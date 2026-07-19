---
name: youtube-analytics-workflow
description: Use for repository workflow tasks in this project — drafting or revising a GitHub issue, creating or revising an implementation plan, maintaining agent instructions/playbooks/skills/references, or inspecting architecture/database/sync/API/frontend behavior before making a change.
---

# YouTube Analytics Workflow

## Choose the workflow

- Issue drafting or revision: read `../../../agent-workflows/issue-authoring.md` in full before drafting.
- Implementation planning or revision: read `../../../agent-workflows/implementation-planning.md` in full before planning.
- Documentation maintenance (roots, playbooks, skills, or references): read `../../../agent-workflows/documentation-maintenance.md` in full before editing.
- Application implementation (writing actual code): load only the affected references below, inspect current code and trace the affected flow, implement only when explicitly requested, verify using `../../../agent-workflows/references/verification.md`, then update the canonical reference for whatever behavior changed.

Start with the matching playbook; load another only if the task's scope expands (for example, an application change that turns out to also require `documentation-maintenance.md` afterward).

## Load project references

| Task area | Reference |
|---|---|
| Architecture and runtime boundaries | `../../../agent-workflows/references/architecture.md` |
| Database schema and queries | `../../../agent-workflows/references/database.md` |
| Synchronization and ingestion | `../../../agent-workflows/references/sync.md` |
| HTTP endpoints and contracts | `../../../agent-workflows/references/api.md` |
| Frontend behavior and styling | `../../../agent-workflows/references/frontend.md` |
| Verification and implementation patterns | `../../../agent-workflows/references/verification.md` |

Load only the references relevant to the current task; expand to another reference only when tracing the code reveals a dependency on it. Inspect current source code before asserting how something behaves — treat the code as authoritative whenever a reference conflicts with it, and correct the stale reference through `documentation-maintenance.md`.

## Working rules

- Load only what the task requires — never all playbooks or all references by default.
- Inspect current code before asserting behavior; do not draft from a reference alone.
- Treat code as authoritative over any reference or prior plan.
- Drafting an issue never authorizes publishing it; planning never authorizes implementing it; implementation happens only on explicit request.
- Never create commits, run `git push`, or publish issues/documentation remotely. Destructive actions (resets, deletions) require explicit approval.

# Implementation Planning

## Purpose

Procedure for turning an approved issue or scoped request into an evidence-backed, dependency-ordered implementation plan. This produces a **plan**, not a change — it never implements, commits, or pushes anything.

## Authoritative inputs

- The approved issue or current request, and its acceptance criteria.
- Related issues, PRs, or dependencies already identified.
- `agent-workflows/issue-authoring.md`, when the request originated from a drafted issue.
- `agent-workflows/references/architecture.md`, `database.md`, `sync.md`, `api.md`, `frontend.md`, `verification.md`.
- The current source code and current working-tree state — both take priority over references and any prior plan when they disagree.

## Contents

- [When this applies](#when-this-applies)
- [Establish scope](#establish-scope)
- [Select references by affected area](#select-references-by-affected-area)
- [Inspect the implementation](#inspect-the-implementation)
- [Trace data and control flow](#trace-data-and-control-flow)
- [Assess affected layers](#assess-affected-layers)
- [Track evidence and uncertainty](#track-evidence-and-uncertainty)
- [Control scope](#control-scope)
- [Order implementation steps](#order-implementation-steps)
- [Plan existing-data handling](#plan-existing-data-handling)
- [Define focused verification](#define-focused-verification)
- [Render the plan](#render-the-plan)
- [Review boundary](#review-boundary)
- [Final checklist](#final-checklist)

## When this applies

Use this procedure when asked to:

- create an implementation plan;
- break an issue into implementation steps;
- identify affected files and application layers;
- assess migration or compatibility impact;
- revise an existing plan after requirements change.

Three distinct activities live under this umbrella:

- **Investigating the implementation** — reading code, tracing flow, forming the plan. The default; needs no special authorization.
- **Producing or revising a plan** — still just planning, even across multiple rounds of feedback.
- **Implementing the plan** — writing actual code changes. A separate action, never implied by having a plan (see [Review boundary](#review-boundary)).

## Establish scope

Start from:

- the approved issue or current request;
- its acceptance criteria;
- related issues/dependencies already identified;
- applicable references;
- current source code;
- current working-tree state, when local uncommitted changes could affect the plan (check `git status` before assuming a clean baseline).

If the request and the issue it references disagree, record the conflict explicitly rather than silently picking one interpretation.

## Select references by affected area

Load only what's relevant to the areas the change touches — expand as tracing reveals a dependency, don't load everything up front.

| Area | Reference |
|---|---|
| System boundaries and runtime lifecycle | `references/architecture.md` |
| Schema, queries, and aggregation | `references/database.md` |
| Ingestion and scheduling | `references/sync.md` |
| HTTP contracts | `references/api.md` |
| Types, clients, components, pages, styling | `references/frontend.md` |
| Checks and implementation patterns | `references/verification.md` |
| Original issue evidence and scope | `issue-authoring.md`, when applicable |

## Inspect the implementation

Before proposing steps:

1. Identify the user-visible or system-level entrypoint.
2. Locate the relevant files and symbols.
3. Read their current implementation.
4. Trace callers and downstream consumers.
5. Inspect related types, API functions, queries, and styles.
6. Check what pattern the codebase already uses for similar behavior.
7. Check whether related local changes already exist in the working tree.

A plan must not name a file or symbol as fact unless it was actually verified this way. When an exact location can't be confirmed, mark it as an assumption rather than inventing a plausible-looking path.

## Trace data and control flow

Where the work crosses layer boundaries, give a concise description of the affected flow:

```text
External source
  → sync/fetch logic
  → database writes
  → database query helper
  → FastAPI route
  → frontend API client
  → shared TypeScript type
  → page/component
  → styling and user interaction
```

Identify: where data originates, where it's transformed, where it's persisted, where it's exposed, where it's consumed, which layer owns validation/defaults, and which state must remain compatible across the change. A diagram isn't needed for simple single-layer work.

## Assess affected layers

Evaluate every layer below. Mark each **affected** or **not applicable**, with a brief reason — don't silently skip a row just because it seems unaffected.

| Layer | Questions |
|---|---|
| Database schema | Are tables, columns, keys, indexes, or constraints changing? |
| Existing data handling | Does the current database need a migration, backfill, or approved reset? |
| Database helpers | Do reads, writes, filters, sorting, aggregation, or zero-filling change? |
| Synchronization | Do stages, scopes, checkpoints, API requests, or row counts change? |
| Backend/API | Do routes, validation, errors, defaults, or response shapes change? |
| Frontend types | Must interfaces or unions change? |
| Frontend API client | Are paths, parameters, or result handling affected? |
| Pages/components | Which state, rendering, and interactions change? |
| Styling/responsive behavior | Are CSS, tables, layout, or breakpoints affected? |
| Compatibility | Are URLs, saved filters, API clients, databases, or existing behavior affected? |
| Documentation | Which reference file must be updated? |
| Verification | Which focused checks demonstrate completion? |

## Track evidence and uncertainty

Maintain four distinct categories:

- **Confirmed details** — verified from current code or configuration.
- **Assumptions** — plausible, not yet verified.
- **Unresolved decisions** — choices requiring user or maintainer direction.
- **Risks and compatibility concerns** — ways the implementation could regress existing behavior.

If an unresolved decision would materially change the implementation order or architecture, stop before presenting one approach as final — present the decision and the affected alternatives instead of picking one silently. Minor assumptions may remain in the plan if clearly labeled and paired with a verification step that would catch them being wrong.

## Control scope

Restate: desired outcome, in-scope behavior, explicit non-goals, affected users/workflows, compatibility expectations.

Every implementation step must map to one of: an acceptance criterion, a confirmed dependency, required verification, or required documentation maintenance. Unrelated cleanup, refactoring, dependency upgrades, and style changes are excluded unless explicitly approved — when useful cleanup is spotted along the way, list it as follow-up work rather than folding it into the plan.

## Order implementation steps

Order by dependency, not by UI order. Typical sequence:

1. Schema or compatibility mechanism.
2. Database helpers.
3. Synchronization or backend business logic.
4. API contract and route.
5. Shared frontend types.
6. Frontend API client.
7. Shared components.
8. Pages and state handling.
9. Styling and responsive behavior.
10. Documentation.
11. Focused verification.

Skip unaffected layers — the reason should already be visible in the layer-impact assessment above. Avoid code-level pseudocode unless a fragile algorithm genuinely requires it.

## Plan existing-data handling

When schema or persistent-state behavior changes, determine how the existing local database reaches the required state. Specify whether the change requires a small migration or an explicitly approved database reset/rebuild, and identify any necessary defaults or backfills. Backward compatibility between application versions, rolling deployments, and rollback support are not required unless the issue explicitly requests them.

`init_db()` (see `references/database.md`) uses `CREATE TABLE IF NOT EXISTS`, so editing `schema.sql` does not update an existing database. The plan must identify how the schema change will be applied. Any destructive reset or data deletion requires explicit approval.

## Define focused verification

Select checks from `references/verification.md`, scoped to what actually changed:

- backend file change: `mypy` on each changed Python file;
- frontend file change: file-scoped ESLint plus `tsc --noEmit`;
- API change: exercise success, validation, error, and compatibility cases;
- query change: verify filtering, sorting, joins, empty data, and boundary dates;
- sync change: verify incremental/year/all behavior and partial-failure handling where relevant;
- UI change: verify loading, empty, error, filtered, and responsive states;
- documentation-only change: documentation checks plus a runtime-directory status check.

A full build is never the default verification step — it still requires explicit approval per `references/verification.md`. Verification should prove the acceptance criteria are met, not merely that files compile.

## Render the plan

```markdown
# Implementation Plan

## Objective
## Confirmed current behavior
## Scope
## Non-goals
## Affected data and control flow
## Layer impact
## Assumptions
## Unresolved decisions
## Risks and compatibility
## Implementation steps
### 1. ...
### 2. ...
## Verification
## Documentation updates
```

Each numbered step:

```markdown
### N. Step title

- Files and symbols:
- Change:
- Dependencies:
- Compatibility:
- Verification:
```

Omit a section only when its absence is obvious; state "None identified" for Assumptions or Unresolved decisions when that confirmation itself improves confidence in the plan.

## Review boundary

Before declaring the plan ready:

1. Present the complete plan.
2. Summarize assumptions and unresolved decisions.
3. Identify any destructive or compatibility-sensitive steps.
4. Confirm every acceptance criterion is covered by at least one step or verification item.
5. Ask for direction on any material unresolved decision.
6. Wait for explicit authorization before implementing anything.

Producing a plan is never itself authorization to implement it, and the git restrictions in `references/verification.md` apply throughout — no commits, no pushes, no remote publication, regardless of how much of the plan has been reviewed.

## Final checklist

- [ ] Scope established from the approved issue/request, with any conflict against it recorded
- [ ] Only relevant references loaded, expanded as needed
- [ ] Relevant files and symbols actually inspected, not assumed
- [ ] Data/control flow traced where the work crosses layers
- [ ] Every layer in the impact table marked affected or not applicable, with a reason
- [ ] Confirmed details, assumptions, unresolved decisions, and risks kept distinct
- [ ] Non-goals stated; unrelated work excluded or listed as follow-up
- [ ] Steps ordered by dependency, each with files/symbols, change, dependencies, compatibility, and verification
- [ ] Existing-data handling addressed explicitly wherever schema or persistent state changes
- [ ] Verification is focused per layer, not a default full build
- [ ] Every acceptance criterion maps to a step or verification item
- [ ] Plan presented for review; implementation requires explicit authorization, while commits, pushes, and remote publication remain prohibited

# Implementation Planning

## Purpose

Procedure for turning an approved issue, local issue file, or scoped request into an evidence-backed, dependency-ordered implementation plan. This produces a **plan**, not a change — it never implements, commits, or pushes anything.

## Authoritative inputs

- The approved issue, local issue file, or current scoped request, and its acceptance criteria.
- Related issues, PRs, or dependencies already identified.
- The destination repository's own documentation (architecture, data model, API, UI, or equivalent layer references) and local instructions.
- The current source code and current working-tree state — both take priority over documentation and any prior plan when they disagree.

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
- break an issue or request into implementation steps;
- identify affected files and application layers;
- assess migration or compatibility impact;
- revise an existing plan after requirements change.

Three distinct activities live under this umbrella:

- **Investigating the implementation** — reading code, tracing flow, forming the plan. The default; needs no special authorization.
- **Producing or revising a plan** — still just planning, even across multiple rounds of feedback.
- **Implementing the plan** — writing actual code changes. A separate action, never implied by having a plan (see [Review boundary](#review-boundary)).

## Establish scope

Start from:

- the approved issue, local issue file, or current request;
- its acceptance criteria;
- related issues/dependencies already identified;
- applicable local documentation;
- current source code;
- current working-tree state, when local uncommitted changes could affect the plan (check `git status` before assuming a clean baseline).

If the request and the issue or file it references disagree, record the conflict explicitly rather than silently picking one interpretation.

## Select references by affected area

Load only what's relevant to the areas the change touches — expand as tracing reveals a dependency, don't load everything up front. The destination repository's own documentation defines what layers exist and where each is documented — for example, a project-local documentation router, or root instructions pointing to specific reference files. Discover that mapping before planning rather than assuming a fixed set of layers or reference paths.

## Inspect the implementation

Before proposing steps:

1. Identify the user-visible or system-level entrypoint.
2. Locate the relevant files and symbols.
3. Read their current implementation.
4. Trace callers and downstream consumers.
5. Inspect related types, interfaces, queries, and styles.
6. Check what pattern the codebase already uses for similar behavior.
7. Check whether related local changes already exist in the working tree.

A plan must not name a file or symbol as fact unless it was actually verified this way. When an exact location can't be confirmed, mark it as an assumption rather than inventing a plausible-looking path.

## Trace data and control flow

Where the work crosses layer boundaries, give a concise description of the affected flow, ordered from where data originates to where it's ultimately consumed and rendered — for example: external source, ingestion/business logic, persistence, a query/read layer, an API contract, a client integration, shared types, and a user-facing surface. Identify: where data originates, where it's transformed, where it's persisted, where it's exposed, where it's consumed, which layer owns validation/defaults, and which state must remain compatible across the change. A diagram isn't needed for simple single-layer work.

## Assess affected layers

Evaluate every layer that actually exists in the destination repository's own architecture — discover this from its documentation or instructions rather than assuming a fixed list. Mark each **affected** or **not applicable**, with a brief reason — don't silently skip a layer just because it seems unaffected. Typical categories to check for, when the destination repository uses them, include: persistent schema, data-access helpers, existing-data handling, background/ingestion processing, API contracts, shared client-side types, client integration, shared components, pages/state, styling and responsive behavior, compatibility, documentation, and verification — but defer to the actual project structure over this generic list.

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

Order by dependency, not by UI order. A typical dependency order moves from persistent state outward to the user interface: schema or compatibility mechanism, data-access layer, business logic or background processing, API contract, shared client-side types, client integration, shared components, pages and state handling, styling and responsive behavior, documentation, then focused verification.

Skip unaffected layers — the reason should already be visible in the layer-impact assessment above. Avoid code-level pseudocode unless a fragile algorithm genuinely requires it.

## Plan existing-data handling

When schema or persistent-state behavior changes, determine how existing stored data reaches the required state. Specify whether the change requires a small migration or an explicitly approved reset/rebuild, and identify any necessary defaults or backfills. Backward compatibility between application versions, rolling deployments, and rollback support are not required unless the issue or request explicitly requests them.

Confirm from the destination repository's own schema-management approach — for example, whether its initialization logic is idempotent-only and therefore does not retroactively apply schema edits to an existing database — before assuming a schema change takes effect automatically. Any destructive reset or data deletion requires explicit approval.

## Define focused verification

Select checks proportional to what actually changed, using the destination repository's own verification commands (type checks, linters, tests) scoped to the changed files or layer rather than a full project-wide build by default. Typical proportionate selection:

- a changed server-side file: run its type checker/linter scoped to that file;
- a changed client-side file: run its linter and type checker scoped to that file;
- an API change: exercise success, validation, error, and compatibility cases;
- a data-layer change: verify filtering, sorting, joins/relations, empty data, and boundary values;
- a background/ingestion change: verify its distinct execution modes and partial-failure handling where relevant;
- a UI change: verify loading, empty, error, filtered, and responsive states;
- a documentation-only change: documentation checks plus confirmation that no application files changed.

A full build is never the default verification step — it still requires explicit approval per the destination repository's own policy. Verification should prove the acceptance criteria are met, not merely that files compile.

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

Producing a plan is never itself authorization to implement it, and the destination repository's own git and safety restrictions apply throughout — no commits, no pushes, no remote publication, regardless of how much of the plan has been reviewed.

## Final checklist

- [ ] Scope established from the approved issue/request, with any conflict against it recorded
- [ ] Only relevant local documentation loaded, expanded as needed
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

---
name: programming-workflow
description: Use for implementation planning — turning an approved issue, local issue file, or scoped request into an evidence-backed, dependency-ordered implementation plan; investigating code, tracing data/control flow, assessing affected layers, and selecting proportionate verification before any code is written.
---

# Programming Workflow

## When this applies

Use this skill when asked to plan an implementation, break a request into ordered steps, assess affected layers or compatibility impact, or revise an existing plan after requirements change.

Read `implementation-planning.md` in full before planning.

## Discover local context first

This skill is project-independent and portable — it carries no dependency on any specific application, architecture, or toolchain. Before planning, discover from the destination repository:

- its own coding rules, architecture, and layer boundaries (root instructions, or an equivalent project-documentation router if one exists);
- its verification commands (type checkers, linters, test runners, build commands) and which are safe to run without approval;
- its safety and permission boundaries (what requires approval, what is never allowed).

Treat these as required local inputs, not assumptions baked into this skill.

## Working rules

- Load only what the task requires.
- Inspect current code before asserting behavior; never plan from memory or a stale reference alone.
- Treat code as authoritative over any documentation or prior plan.
- Producing a plan never authorizes implementing it.
- Never create commits, run `git push`, or publish anything remotely. Destructive actions require explicit approval.

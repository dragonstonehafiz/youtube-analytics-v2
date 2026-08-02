---
name: documentation-workflow
description: Use for documentation writing and maintenance — updating root instructions, playbooks, skill entrypoints, or reference documentation to stay current with actual code or policy, without reintroducing duplication. Use when application behavior changes, a verification command changes, a coding/safety rule changes, a workflow changes, or a reference is found to be stale.
---

# Documentation Workflow

## When this applies

Read `documentation-maintenance.md` in full before editing any documentation.

## Discover local context first

This skill is project-independent and portable — it carries no dependency on any specific application, file layout, or validator. Before editing, discover from the destination repository:

- its own canonical-documentation ownership map (which file owns which subject) — a project-local documentation router, if one exists, is the fastest way to find this;
- its own documentation validator or equivalent verification command, if any;
- its safety and permission boundaries around destructive changes and remote publication.

Treat these as required local inputs, not assumptions baked into this skill.

## Working rules

- Code and authoritative policy remain the source of truth; documentation follows them, never the reverse.
- Documentation work does not authorize implementation.
- Never create commits, run `git push`, or publish documentation remotely. Destructive deletion or reset requires explicit approval.

---
name: github-workflow
description: Use for GitHub artifact drafting — writing or revising a GitHub issue draft from the repository's own issue templates, or writing or revising a pull request title/description/body from the actual branch diff and the repository's own PR template. Produces drafts only; never publishes, comments, or opens anything on GitHub.
---

# GitHub Workflow

## Choose the procedure

- Drafting or revising an issue: read `issue-authoring.md` in full before drafting.
- Drafting or revising a PR title/description/body/summary: read `pull-request-authoring.md` in full before drafting.

## Discover local context first

This skill is project-independent and portable — it carries no dependency on any specific application, template set, or contribution policy. Before drafting, discover from the destination repository:

- its issue templates (form fields, template types) and contribution guide;
- its PR template, branch-naming/commit-title conventions, and any CI check that enforces them;
- its own coding/architecture documentation, needed to describe current behavior accurately;
- its safety and permission boundaries around publishing.

Treat these as required local inputs, not assumptions baked into this skill.

## Working rules

- Investigating and drafting is the default; it requires no special authorization.
- Publishing or modifying anything on GitHub (issue/PR creation or editing, via CLI or the web UI) is a separate, explicit action never implied by producing a draft.
- Inspect current code and the actual diff before asserting behavior — never draft from memory or a stale reference alone.
- Never create commits, run `git push`, or publish anything remotely.

---
name: project-docs
description: Use for YouTube Analytics codebase discovery — routing to the canonical architecture, database, sync, API, frontend, and verification references before making or describing a change in this repository.
---

# Project Docs

## Load project references

| Task area | Reference |
|---|---|
| Architecture and runtime boundaries | `../references/architecture.md` |
| Database schema and queries | `../references/database.md` |
| Synchronization and ingestion | `../references/sync.md` |
| HTTP endpoints and contracts | `../references/api.md` |
| Frontend behavior and styling | `../references/frontend.md` |
| Verification and implementation patterns | `../references/verification.md` |

Load only the references relevant to the current task; expand to another reference only when tracing the code reveals a dependency on it. Inspect current source code before asserting how something behaves — treat the code as authoritative whenever a reference conflicts with it, and correct the stale reference using the documentation workflow skill.

## Documentation ownership

| Subject | Canonical file |
|---|---|
| System architecture and repository layout | `../references/architecture.md` |
| Schema, relationships, and query behavior | `../references/database.md` |
| Sync and ingestion behavior | `../references/sync.md` |
| HTTP contracts | `../references/api.md` |
| Frontend types, clients, pages, components, styling | `../references/frontend.md` |
| Verification commands and implementation patterns | `../references/verification.md` |
| Issue-drafting and PR-drafting procedure | The portable GitHub workflow skill |
| Implementation-planning procedure | The portable programming workflow skill |
| Documentation maintenance procedure | The portable documentation workflow skill |
| Always-applicable agent rules | `AGENTS.md` and `CLAUDE.md` |
| Agent-specific discovery and routing | This file and its Codex/Claude entrypoints |
| User setup and usage | `README.md` |
| Contributor and PR conventions | `CONTRIBUTING.md` and `.github/` templates |

Every fact has exactly one canonical home from this table. A file not listed here doesn't own application knowledge — it either summarizes or links to the file that does.

## Working rules

- Load only what the task requires — never all references by default.
- Inspect current code before asserting behavior; do not draft from a reference alone.
- Treat code as authoritative over any reference.
- This skill only identifies what documentation exists here and where. For writing or correcting documentation, hand off to the documentation workflow skill.

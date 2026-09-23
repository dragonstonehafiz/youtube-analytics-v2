# Repository Rules

Coding rules, verification expectations, and safety/permission boundaries that apply to virtually every task in this repository. Component behavior, endpoint details, schema descriptions, and page-specific conventions belong in the references linked from [`README.md`](README.md), not here.

## Coding rules

- use parameterized queries in all DB helpers — never string concatenation
- qualify all column names with table aliases in any query that joins multiple tables
- use type hints and docstrings on all backend functions
- use explicit TypeScript types; avoid `any`
- use HTML `<table>` with `table-layout: fixed` for all data tables — the comments feed (`CommentsPanel`) is a deliberate exception; comment bodies are prose, not cells
- keep CSS in colocated `.css` files; no inline styles
- use `@/` alias imports (e.g. `import { getVideos } from '@/api'`)
- keep `.method()` on the same line as its object in Python — no chained calls starting on a new line
- no `console.log` in frontend code
- no new heavy dependencies without approval
- no unrelated refactoring — keep changes scoped to the task
- use existing design tokens and named constants; no hardcoded colors or magic numbers

## Verification

Run backend commands through `backend/.venv`'s interpreter, not a global `python`/`pip` — `mypy`, `pytest`, and other dev dependencies are installed there, not system-wide. See [`verification.md`](verification.md) for the full command set, including the backend venv requirement and layer-specific checks.

Run the relevant command against every changed file, not just the examples in `verification.md`. A full frontend build (`npm run build`) requires explicit approval — it is not part of the default verification loop.

## Safety and permissions

Allowed without asking:
- read files, list files, search
- type check, lint single files
- run backend server locally

Ask first:
- `pip install` / `npm install` new packages
- deleting files or DB records
- full project builds

Never:
- stage files (`git add`) or create commits
- run `git push`
- publish issues or documentation remotely
- treat drafting or planning as authorization to implement

## Scope control

When a request is ambiguous or would require a large speculative change, ask a clarifying question or propose a short plan before proceeding. Do not push wide refactors without confirmation.

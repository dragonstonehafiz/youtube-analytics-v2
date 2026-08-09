# AGENTS.md

YouTube analytics dashboard — FastAPI + React/TypeScript + SQLite.

## Repository workflow

- Implementation planning: `.agents/skills/programming-workflow/SKILL.md`.
- Issue and pull request drafting: `.agents/skills/github-workflow/SKILL.md`.
- Documentation writing and maintenance: `.agents/skills/documentation-workflow/SKILL.md`.
- YouTube Analytics codebase discovery (architecture, database, sync, API, frontend, verification references): `.agents/skills/project-docs/SKILL.md`.

The programming, GitHub, and documentation skills are portable and project-independent; the coding rules, commands, and permissions below are the local inputs they discover here. `project-docs` is specific to this repository.

## Coding rules

- use parameterized queries in all DB helpers — never string concatenation
- qualify all column names with table aliases in any query that joins multiple tables
- use type hints and docstrings on all backend functions
- use explicit TypeScript types; avoid `any`
- use HTML `<table>` with `table-layout: fixed` for all data tables
- keep CSS in colocated `.css` files; no inline styles
- use `@/` alias imports (e.g. `import { getVideos } from '@/api'`)
- keep `.method()` on the same line as its object in Python — no chained calls starting on a new line
- no `console.log` in frontend code
- no new heavy dependencies without approval
- no unrelated refactoring — keep changes scoped to the task
- use existing design tokens and named constants; no hardcoded colors or magic numbers

## Verification

Run backend commands through `backend/.venv`'s interpreter, not a global `python`/`pip` — `mypy`, `pytest`, and other dev dependencies are installed there, not system-wide.

```bash
cd backend && .venv/Scripts/python.exe -m mypy database/connection.py   # Windows
cd backend && .venv/bin/python -m mypy database/connection.py            # macOS/Linux
cd backend && uvicorn server:app --reload
cd frontend && npx oxlint src/pages/Videos.tsx --fix
cd frontend && npx tsc --noEmit
```

Run the relevant command against every changed file, not just the ones above. A full frontend build (`npm run build`) requires explicit approval — it is not part of the default verification loop.

## Safety and permissions

Allowed without asking:
- read files, list files, search
- type check, lint single files
- run backend server locally
- run `python scripts/validate_agent_workflows.py`

Ask first:
- `pip install` / `npm install` new packages
- deleting files or DB records
- full project builds

Never:
- create commits
- run `git push`
- publish issues or documentation remotely
- treat drafting or planning as authorization to implement

## Scope control

When a request is ambiguous or would require a large speculative change, ask a clarifying question or propose a short plan before proceeding. Do not push wide refactors without confirmation.

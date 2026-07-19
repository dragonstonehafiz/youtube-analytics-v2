# AGENTS.md

YouTube analytics dashboard — FastAPI + React/TypeScript + SQLite.

## Repository workflow

Use `.agents/skills/youtube-analytics-workflow/SKILL.md` for issue drafting, implementation planning, documentation maintenance, and on-demand project references (architecture, database, sync, API, frontend, verification).

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

```bash
cd backend && python -m mypy database.py
cd backend && uvicorn server:app --reload
cd frontend && npx eslint src/pages/Videos.tsx --fix
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

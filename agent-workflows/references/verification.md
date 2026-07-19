# Verification and Implementation Patterns

## Purpose

Commands to run when checking work, and recurring patterns for extending the codebase (new route, new page). Layer-specific behavioral detail lives in `database.md`/`sync.md`/`api.md`/`frontend.md` — this file is about *how to check* changes to those layers, not what they contain.

## Contents

- [Git restrictions](#git-restrictions)
- [Verification principles](#verification-principles)
- [Backend verification](#backend-verification)
- [Frontend verification](#frontend-verification)
- [Documentation verification](#documentation-verification)
- [Adding a backend route](#adding-a-backend-route)
- [Adding a frontend page](#adding-a-frontend-page)
- [Layer-specific checks](#layer-specific-checks)
- [Pull request checks](#pull-request-checks)

## Git restrictions

The agent must never run `git commit`, `git push`, or any other command that creates commits or uploads changes to a remote, regardless of what verification or implementation task is in progress. Verification in this file means running local checks (`mypy`, `eslint`, `tsc`, `git diff`) — it never extends to committing or pushing the result. Staging (`git add`) and committing are the user's call to make, not something a verification pass triggers automatically.

## Verification principles

- Prefer a file-scoped check over a project-wide build. Run the full frontend build (`npm run build`) only when explicitly requested — it is not part of the default verification loop.
- Match the check to the layer touched: a backend-only change doesn't need `tsc`/`eslint`; a docs-only change doesn't need either.
- Current code is authoritative. If a reference file conflicts with what a verification command reveals, trust the command output and correct the reference — don't assume the doc predates the drift without checking.

## Backend verification

```bash
cd backend && python -m mypy database.py      # type check a single changed file
cd backend && uvicorn server:app --reload     # run the server locally
```

Run `mypy` against every backend `.py` file actually changed, not just `database.py` — substitute the filename.

## Frontend verification

```bash
cd frontend && npx eslint src/pages/Videos.tsx --fix   # lint a single changed file
cd frontend && npx tsc --noEmit                          # type check (whole project — tsc has no cheap single-file mode here)
cd frontend && npm run build                              # full build — requires explicit approval before running
```

## Documentation verification

For documentation-only changes (no `backend/`/`frontend/` files touched):

```bash
python scripts/validate_agent_workflows.py    # validates skill frontmatter and shared routing
git diff --check                              # flag trailing whitespace / whitespace errors
git status --short -- backend frontend        # confirm no application code changed (tracked or untracked)
```

The last command should produce no output when the change is genuinely docs-only. Use `git status --short`, not `git diff --name-only` — the latter only sees tracked files and would miss a new untracked file added under `backend/`/`frontend/`.

## Adding a backend route

1. Add the handler in `backend/routes.py`.
2. Add the corresponding DB helper in `backend/database.py` if the query doesn't already exist — follow the parameterized-query and table-alias conventions in `database.md`.
3. Update `api.md` with the new route's method, path, params, and response shape.
4. Run `python -m mypy routes.py database.py`.

## Adding a frontend page

1. Create `frontend/src/pages/<PageName>.tsx` + a colocated `<PageName>.css`.
2. Import shared types from `@/types`, API calls from `@/api`.
3. Add a `<Route>` entry in `frontend/src/App.tsx`.
4. Follow the URL-param-as-state convention described in `frontend.md` if the page has any filters.
5. Update `frontend.md`'s page table with the new page's behavior.
6. Run `npx eslint src/pages/<PageName>.tsx --fix` and `npx tsc --noEmit`.

## Layer-specific checks

| Task | Reference(s) to consult | Verification |
|---|---|---|
| Database query change | `database.md` | `mypy` on the changed file |
| Sync bug | `sync.md`, possibly `database.md` | `mypy` on `sync.py`/`youtube.py`; manual `POST /sync/trigger` against a local run if behavior-sensitive |
| New endpoint | `api.md`, likely `database.md` | `mypy` on `routes.py`/`database.py`; update `api.md` |
| Frontend API integration | `api.md`, `frontend.md` | `tsc --noEmit`; `eslint --fix` on changed files |
| Page or component change | `frontend.md` | `eslint --fix`, `tsc --noEmit`; manual check in a running dev server for UI-facing changes |
| Verification selection itself | this file | — |
| Cross-layer feature | `architecture.md` plus every affected layer reference | all of the above, scoped to what actually changed |

## Pull request checks

- `python -m mypy <file>.py` on every changed backend file
- `npx eslint src/... --fix` on every changed frontend file — no errors left afterward
- `npx tsc --noEmit` — no type errors
- No `console.log` in frontend code
- No hardcoded colors or magic numbers (use `index.css` tokens / named constants)
- No new heavy dependencies without prior approval
- `git status --short` reviewed before committing to confirm only intended files are staged

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

The agent must never run `git commit`, `git push`, or any other command that creates commits or uploads changes to a remote, regardless of what verification or implementation task is in progress. Verification in this file means running local checks (`mypy`, `oxlint`, `tsc`, `git diff`) — it never extends to committing or pushing the result. Staging (`git add`) and committing are the user's call to make, not something a verification pass triggers automatically.

## Verification principles

- Prefer a file-scoped check over a project-wide build. Run the full frontend build (`npm run build`) only when explicitly requested — it is not part of the default verification loop.
- Match the check to the layer touched: a backend-only change doesn't need `tsc`/`oxlint`; a docs-only change doesn't need either.
- Current code is authoritative. If a reference file conflicts with what a verification command reveals, trust the command output and correct the reference — don't assume the doc predates the drift without checking.

## Backend verification

Run every backend command through the `backend/.venv` interpreter, not a global
`python`/`pip` — `mypy`, `pytest`, and the other dev dependencies are installed there,
not system-wide.

```bash
cd backend
.venv/Scripts/python.exe -m mypy database/connection.py   # Windows; type check a single changed file (package-qualified path)
.venv/bin/python -m mypy database/connection.py            # macOS/Linux
uvicorn server:app --reload                                 # run the server locally (from an activated venv, or .venv/Scripts/uvicorn)
```

Run `mypy` against every backend `.py` file actually changed, not just the example above — substitute the path, e.g. `routes/videos.py`, `sync/orchestration.py`, `youtube/auth.py`. `database.py`, `routes.py`, `sync.py`, and `youtube.py` no longer exist as single files — each is now a package (`database/`, `routes/`, `sync/`, `youtube/`) of focused modules; see `architecture.md` for the layout.

Run the test suite the same way: `.venv/Scripts/python.exe -m pytest` (Windows) or
`.venv/bin/python -m pytest` (macOS/Linux) — `pytest.ini` sets `testpaths = tests`, so no
path argument is needed, and this is the exact command CI runs. `pytest` is the only
supported runner: an autouse `tests/conftest.py` fixture fails any real network
connection or OAuth credential fetch, and running the same test classes through raw
`unittest discover` skips that fixture. See `backend/README.md`'s Testing section for
the isolated-database harness (`tests/support.py`) and what each test group
mocks/isolates.

## Frontend verification

```bash
cd frontend && npx oxlint src/pages/Videos.tsx --fix   # lint a single changed file (oxlint, not eslint — no eslint config exists; `npm run lint` runs oxlint over the project)
cd frontend && npm run typecheck                          # type check — the exact command CI runs (`tsc -b`)
cd frontend && npm test                                   # run every component test (`vitest run`)
cd frontend && npx vitest run tests/Sync.test.tsx         # run a single test file (tests live in frontend/tests/)
cd frontend && npm run build                              # full build — requires explicit approval before running
```

Always type check with `npm run typecheck` (`tsc -b`), never bare `npx tsc --noEmit`.
`tsconfig.json` at the project root declares `"files": []` with only
`references` to `tsconfig.app.json`/`tsconfig.node.json` — a solution file with no
source of its own. Plain `tsc`/`tsc --noEmit` reads that root config and, finding no
files, does essentially nothing; it does **not** build the referenced projects. Only
`-b` (project-reference build mode) follows `references` and actually type-checks
`tsconfig.app.json`, which is what caught a real generic-inference mismatch in
`src/lib/requestState.ts`'s `track()` that a plain `tsc --noEmit` run had silently
missed. `npm run build`'s first step is the same `tsc -b`, and CI runs a dedicated
`npm run typecheck` step before `npm run build`, so `npm run typecheck` locally is
exactly what CI checks — not an approximation of it. Vitest is not a substitute either:
it transpiles TypeScript for speed but does not type-check it, so a test suite passing
under `npm test` says nothing about type errors.

Component tests run on Vitest with `@testing-library/react` and `jsdom`. There is no Vitest
config or setup file — Vitest reads `vite.config.ts`, and each test file declares its own
`// @vitest-environment jsdom`; see `frontend.md`'s Tests section for the conventions a new
test file must follow. Prefer the focused single-file form while iterating, the same way
`mypy` is run against the file actually changed.

## Documentation verification

For documentation-only changes (no `backend/`/`frontend/` files touched):

```bash
python scripts/validate_agent_workflows.py    # validates skill frontmatter and shared routing
git diff --check                              # flag trailing whitespace / whitespace errors
git status --short -- backend frontend        # confirm no application code changed (tracked or untracked)
```

The last command should produce no output when the change is genuinely docs-only. Use `git status --short`, not `git diff --name-only` — the latter only sees tracked files and would miss a new untracked file added under `backend/`/`frontend/`.

## Adding a backend route

1. Add the handler in the matching `backend/routes/<resource>.py` (`videos.py`, `playlists.py`, `analytics.py`, `comments.py`, `synchronization.py`, or `metadata.py`).
2. Add the corresponding DB helper in the matching `backend/database/<domain>.py` if the query doesn't already exist — follow the parameterized-query and table-alias conventions in `database.md`.
3. Update `api.md` with the new route's method, path, params, and response shape.
4. Run `.venv/Scripts/python.exe -m mypy routes/<resource>.py database/<domain>.py` (from `backend/`, using the venv interpreter — see [Backend verification](#backend-verification)).

## Adding a frontend page

1. Create `frontend/src/pages/<PageName>.tsx` + a colocated `<PageName>.css`.
2. Import shared types from `@/types`, API calls from `@/api`.
3. Add a `<Route>` entry in `frontend/src/App.tsx`.
4. Follow the URL-param-as-state convention described in `frontend.md` if the page has any filters.
5. Update `frontend.md`'s page table with the new page's behavior.
6. Run `npx oxlint src/pages/<PageName>.tsx --fix` and `npm run typecheck`.

## Layer-specific checks

| Task | Reference(s) to consult | Verification |
|---|---|---|
| Database query change | `database.md` | `mypy` on the changed file under `database/` |
| Sync bug | `sync.md`, possibly `database.md` | `mypy` on the changed file(s) under `sync/`/`youtube/`; manual `POST /sync/trigger` against a local run if behavior-sensitive |
| New endpoint | `api.md`, likely `database.md` | `mypy` on the changed file(s) under `routes/`/`database/`; update `api.md` |
| Frontend API integration | `api.md`, `frontend.md` | `npm run typecheck`; `oxlint --fix` on changed files |
| Page or component change | `frontend.md` | `oxlint --fix`, `npm run typecheck`; `npx vitest run` on the page's test file where one exists; manual check in a running dev server for UI-facing changes |
| Verification selection itself | this file | — |
| Cross-layer feature | `architecture.md` plus every affected layer reference | all of the above, scoped to what actually changed |

## Pull request checks

- `mypy <file>.py` (via the `backend/.venv` interpreter — see [Backend verification](#backend-verification)) on every changed backend file
- `npx oxlint src/... --fix` on every changed frontend file — no errors left afterward
- `npm run typecheck` (`tsc -b`) — no type errors; this is the exact command CI runs, not `npx tsc --noEmit`
- `npm test` — every component test passes
- No `console.log` in frontend code
- No hardcoded colors or magic numbers (use `index.css` tokens / named constants)
- No new heavy dependencies without prior approval
- `git status --short` reviewed before committing to confirm only intended files are staged

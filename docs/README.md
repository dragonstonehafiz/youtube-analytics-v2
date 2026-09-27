# Documentation

Canonical home for this repository's rules, task procedures, and application references. `AGENTS.md` is a short entry point that links here.

## Human-readable documentation

Visual overviews of the current system in [`human/`](human/), as HTML pages that open directly in a browser with no build step. They share [`human/human-docs.css`](human/human-docs.css) and [`human/human-docs.js`](human/human-docs.js) (the nav dropdowns); a page with styles of its own has a `.css` file of the same name next to it.

| Topic | Page |
|---|---|
| System data flow: user action → frontend → API route → database → response, and YouTube → sync → database, with the sync triggers actually wired | [`app-flow/overview.html`](human/app-flow/overview.html) |
| What each backend part does, package dependencies, and call paths | [`architecture/backend-architecture.html`](human/architecture/backend-architecture.html) |
| What every backend file does, and each route's call chain down to the database | [`architecture/backend-reference.html`](human/architecture/backend-reference.html) |
| Where data is stored, how the reader and writer move table rows in and out of row objects, and how read results become API JSON | [`architecture/data-storage.html`](human/architecture/data-storage.html) |
| What each reader and writer function does and where the app uses it | [`architecture/reader-writer.html`](human/architecture/reader-writer.html) |
| Frontend routes, pages, component reuse, and unused components | [`architecture/frontend-components.html`](human/architecture/frontend-components.html) |
| Code, markup, and CSS repeated across backend and frontend files, ranked by copy count | [`suggestions/repeated-code.html`](human/suggestions/repeated-code.html) |
| Backend and frontend code that does more work than its result needs, ordered by how often it runs | [`suggestions/efficiency.html`](human/suggestions/efficiency.html) |
| Backend functions and routes, frontend components, exports, CSS, and dependencies that nothing in the running app uses | [`suggestions/dead-code.html`](human/suggestions/dead-code.html) |
| Requests per page and component: endpoint, trigger, dependencies, deferral, polling, concurrency | [`app-flow/requests.html`](human/app-flow/requests.html) |

These pages summarize and visualize; the references below stay canonical for contracts and behavior detail. When a change affects what one of them shows, update that page in the same change — see [`documentation-maintenance.md`](documentation-workflow/documentation-maintenance.md#human-readable-views).

## Load project references

| Task area | Reference |
|---|---|
| Architecture and runtime boundaries | [`architecture.md`](references/architecture.md) |
| Database schema and queries | [`database.md`](references/database.md) |
| Synchronization and ingestion | [`sync.md`](references/sync.md) |
| HTTP endpoints and contracts | [`api.md`](references/api.md) |
| Frontend behavior and styling | [`frontend.md`](references/frontend.md) |
| Verification and implementation patterns | [`verification.md`](references/verification.md) |

Load only the references relevant to the current task; expand to another reference only when tracing the code reveals a dependency on it. Inspect current source code before asserting how something behaves — treat the code as authoritative whenever a reference conflicts with it, and correct the stale reference following [`documentation-maintenance.md`](documentation-workflow/documentation-maintenance.md).

## Documentation ownership

| Subject | Canonical file |
|---|---|
| System architecture and repository layout | [`architecture.md`](references/architecture.md) |
| Schema, relationships, and query behavior | [`database.md`](references/database.md) |
| Sync and ingestion behavior | [`sync.md`](references/sync.md) |
| HTTP contracts | [`api.md`](references/api.md) |
| Frontend types, clients, pages, components, styling | [`frontend.md`](references/frontend.md) |
| Verification commands and implementation patterns | [`verification.md`](references/verification.md) |
| Coding rules, safety/permission boundaries, scope control | [`repository-rules.md`](repository-rules.md) |
| Implementation-planning procedure | [`implementation-planning.md`](programming-workflow/implementation-planning.md) |
| Issue-drafting procedure | [`issue-authoring.md`](github-workflow/issue-authoring.md) |
| PR-drafting procedure | [`pull-request-authoring.md`](github-workflow/pull-request-authoring.md) |
| Documentation maintenance procedure | [`documentation-maintenance.md`](documentation-workflow/documentation-maintenance.md) |
| Visual system data flow and wired sync triggers | [`human/app-flow/overview.html`](human/app-flow/overview.html) |
| Backend part overview, package dependencies, call paths, and consolidation observations | [`human/architecture/backend-architecture.html`](human/architecture/backend-architecture.html) |
| Per-file backend duties and route-to-database call chains | [`human/architecture/backend-reference.html`](human/architecture/backend-reference.html) |
| Visual storage map, row-object, reader and writer walkthroughs, and the storage-to-response flow | [`human/architecture/data-storage.html`](human/architecture/data-storage.html) |
| Reader and writer function guide with examples and uses | [`human/architecture/reader-writer.html`](human/architecture/reader-writer.html) |
| Frontend component usage counts and unused components | [`human/architecture/frontend-components.html`](human/architecture/frontend-components.html) |
| Repeated backend code, frontend code, and CSS | [`human/suggestions/repeated-code.html`](human/suggestions/repeated-code.html) |
| Sync, API-read, and frontend efficiency observations | [`human/suggestions/efficiency.html`](human/suggestions/efficiency.html) |
| Unused code, CSS, and dependencies | [`human/suggestions/dead-code.html`](human/suggestions/dead-code.html) |
| Per-page request triggers, timing, and unnecessary-request observations | [`human/app-flow/requests.html`](human/app-flow/requests.html) |
| Shared styling and nav script for the HTML views | [`human/human-docs.css`](human/human-docs.css), [`human/human-docs.js`](human/human-docs.js) |
| Project discovery and documentation ownership map | This file |
| User setup and usage | `../README.md` |
| Contributor and PR conventions | `../CONTRIBUTING.md` and `.github/` templates |

Every fact has exactly one canonical home from this table. A file not listed here doesn't own application knowledge — it either summarizes or links to the file that does. Each `human/` page owns only its own observations and maps (component usage, request maps, call chains, repeated code, efficiency, dead code, consolidation and unnecessary-request observations) and summarizes the references for everything else.

## Working rules

- Load only what the task requires — never all references by default.
- Inspect current code before asserting behavior; do not draft from a reference alone.
- Treat code as authoritative over any reference.
- For writing or correcting documentation, follow [`documentation-maintenance.md`](documentation-workflow/documentation-maintenance.md).
- A code change that alters anything a `human/` page shows updates that page in the same change as the code and references.

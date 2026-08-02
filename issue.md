### Description

### Current context

The current skill combines two different responsibilities:

- General development workflows, including issue authoring, implementation planning, documentation maintenance, PR drafting, scope control, safety boundaries, and verification principles.
- YouTube Analytics–specific documentation discovery, including routing to architecture, database, synchronization, API, frontend, and repository verification references.

The root `AGENTS.md` and `CLAUDE.md` files point only to this combined skill. The validation script also hardcodes the current skill name, entrypoint paths, and complete routing target list.

This works within this repository, but the general programming guidance cannot be reused easily in another personal project without also copying or editing YouTube Analytics–specific names, paths, and documentation routes.

### Desired outcome

Separate the current guidance into two independently usable responsibilities:

1. A reusable general programming workflow skill.
2. A YouTube Analytics–specific skill for identifying and loading relevant project documentation.

The general programming skill should preserve reusable practices such as:

- drafting issues from available repository templates;
- producing evidence-backed implementation plans;
- maintaining agent documentation;
- drafting pull request titles and descriptions;
- separating verified facts, assumptions, and unresolved decisions;
- controlling scope and avoiding unrelated refactoring;
- selecting proportionate verification;
- preserving safety and permission boundaries.

The general skill should be self-contained and project-independent so it can be copied into another personal repository without also copying the YouTube Analytics documentation skill or removing project-specific references.

Repository-specific templates, commands, paths, architecture, and technology conventions should be supplied by each project’s local instructions rather than embedded as assumptions in the reusable skill.

The YouTube Analytics documentation skill should progressively route agents to the canonical documentation for:

- architecture and runtime boundaries;
- database schema and query behavior;
- synchronization and ingestion;
- HTTP endpoints and contracts;
- frontend behavior and styling;
- repository-specific implementation and verification patterns.

Codex and Claude should expose equivalent responsibilities and route to the same canonical content without duplicating detailed guidance.

### Non-goals

- Publishing or distributing the reusable skill.
- Creating a marketplace package, plugin, installer, or release process.
- Automatically synchronizing the skill between repositories.
- Changing backend, frontend, database, API, or synchronization behavior.
- Rewriting valid guidance solely to change its wording.

### Acceptance criteria

- [ ] Codex and Claude each provide a separately triggerable general programming workflow skill.
- [ ] Codex and Claude each provide a separately triggerable YouTube Analytics documentation-discovery skill.
- [ ] The general programming skill contains no dependency on the `youtube-analytics-v2` name, application architecture, project reference paths, or project-specific verification commands.
- [ ] The complete general programming skill can be copied into another personal repository without also copying the YouTube Analytics skill.
- [ ] Copying the general skill into another repository does not leave broken links to files that exist only in this repository.
- [ ] The general skill obtains repository-specific templates, commands, and conventions from the destination repository’s local instructions.
- [ ] The YouTube Analytics skill progressively routes tasks to the canonical architecture, database, sync, API, frontend, and verification references.
- [ ] Every rule and workflow currently reachable through `youtube-analytics-workflow` is deliberately classified as reusable guidance or YouTube Analytics–specific guidance; none is silently dropped.
- [ ] General workflow content has one canonical owner, and native agent entrypoints reference that owner instead of maintaining independent copies.
- [ ] YouTube Analytics application knowledge remains canonically owned by the appropriate files under `agent-workflows/references/`.
- [ ] `AGENTS.md`, `CLAUDE.md`, `agent-workflows/documentation-maintenance.md`, and affected cross-references describe the new skill boundaries and triggering behavior.
- [ ] `scripts/validate_agent_workflows.py` validates the new entrypoints, expected skill names, routing parity, and referenced files without requiring the former combined structure.
- [ ] `python scripts/validate_agent_workflows.py` completes successfully.
- [ ] `git diff --check` completes successfully.
- [ ] `git status --short -- backend frontend` confirms that no application files changed.

### Additional context

### Related work

- #19 established the current consolidated agent workflow and is closed as completed. This issue builds on that structure by separating personally reusable programming guidance from project-specific documentation discovery.

### Verified facts

- `.agents/skills/youtube-analytics-workflow/SKILL.md` and `.claude/skills/youtube-analytics-workflow/SKILL.md` currently expose the same combined responsibilities.
- Both entrypoints route to shared workflow playbooks and all six project reference files.
- `AGENTS.md` and `CLAUDE.md` each point only to the combined skill.
- `scripts/validate_agent_workflows.py` currently expects the combined `youtube-analytics-workflow` name and paths.
- `agent-workflows/references/verification.md` currently combines general verification principles with repository-specific commands and implementation patterns.
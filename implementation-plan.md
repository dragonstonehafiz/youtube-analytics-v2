# Implementation Plan

## Objective

Split the current `youtube-analytics-workflow` into four separately triggerable responsibilities for both Codex and Claude:

1. a portable programming skill for implementation planning, code investigation, scope control, and verification selection;
2. a portable general GitHub workflow for issue and pull request authoring; and
3. a portable documentation workflow for writing and maintaining accurate repository documentation; and
4. a project-local `project-docs` skill whose only responsibility is progressively routing agents to this codebase's canonical documentation.

The change is limited to agent workflow documentation, native skill entrypoints, and their validator. It does not authorize implementation, publication, commits, or changes to the application.

## Confirmed current behavior

- `.agents/skills/youtube-analytics-workflow/SKILL.md` and `.claude/skills/youtube-analytics-workflow/SKILL.md` are separate, equivalent copies with the same `name: youtube-analytics-workflow` frontmatter.
- Each current entrypoint combines workflow selection, project-reference discovery, progressive-loading rules, evidence rules, scope boundaries, and safety restrictions.
- `agent-workflows/issue-authoring.md`, `implementation-planning.md`, `documentation-maintenance.md`, and `pull-request-authoring.md` own shared procedures, but they directly name repository files, templates, reference paths, commands, and policies. Their reusable programming, GitHub, and documentation-writing responsibilities are therefore not currently independently portable.
- `agent-workflows/references/verification.md` mixes reusable verification principles and safety boundaries with repository-specific Python, frontend, API, sync, and documentation commands.
- `AGENTS.md` and `CLAUDE.md` each point only to their agent's combined skill. They also contain the repository-specific coding rules, commands, permissions, and safety boundaries that a portable workflow should discover as local inputs.
- `agent-workflows/documentation-maintenance.md` describes the current combined ownership model and hardcodes the old validator behavior in its verification section.
- `scripts/validate_agent_workflows.py` uses single global skill-name, skill-path, and routing-target constants. It validates only the two combined entrypoints and assumes both expose all four playbooks plus all six project references.
- `CONTRIBUTING.md` describes the current workflow layout and links directly to `agent-workflows/documentation-maintenance.md`; it is therefore an affected cross-reference even though it was not named explicitly in the issue acceptance criteria.
- `issue.md` describes a two-part split between a general programming workflow and YouTube Analytics documentation discovery. The user's later direction supersedes that proposed boundary for this plan by separating programming, GitHub authoring, documentation authoring/maintenance, and project-document discovery. The issue text and acceptance criteria will therefore need corresponding revision during implementation or before this plan is treated as approved issue scope.
- The only current working-tree change is the untracked issue input, `issue.md`. It must be preserved and not treated as implementation output.

## Scope

- Create a self-contained portable programming skill bundle for implementation planning, code investigation, scope control, risk/compatibility analysis, and proportionate verification selection.
- Create one self-contained portable GitHub workflow bundle covering both issue and pull request authoring. It consumes the destination repository's templates and contribution rules instead of embedding this repository's choices.
- Create a self-contained portable documentation workflow for drafting, revising, and maintaining documentation from verified code/policy evidence, including canonical ownership, duplication control, link maintenance, and proportionate documentation verification.
- Add thin Codex and Claude entrypoints for all three portable workflows.
- Replace the current combined entrypoints with a project-local `project-docs` skill for both agents. It progressively routes to relevant project references but does not own general documentation-writing procedure.
- Reclassify every rule currently reachable from the combined skill across programming, GitHub, documentation writing/maintenance, project-document discovery, or repository-local policy without silently dropping guidance.
- Update roots and cross-references to explain when to use each skill and where canonical content lives.
- Refactor the validator to understand all four skill responsibilities, both native agent surfaces, routing parity, valid links, and portability constraints.

## Non-goals

- Publishing, packaging, installing, or automatically synchronizing the portable workflows.
- Creating a marketplace entry, plugin, release process, or external repository.
- Changing backend, frontend, database, API, or synchronization behavior.
- Rewriting guidance solely for stylistic variation.
- Adding dependencies or running a full application/frontend build.
- Treating implementation planning as GitHub-only; it must also work from a local issue file or scoped request.
- Preserving the obsolete combined skill as a compatibility copy unless a maintainer explicitly requests that behavior.

## Proposed ownership and routing

Use three canonical, independently copyable bundles for reusable procedures. Each of the four responsibilities gets its own dedicated subfolder directly under `agent-workflows/` — no shared top-level playbook files remain — so a bundle can be identified, copied, or dropped as a single directory:

- `agent-workflows/programming-workflow/` with `SKILL.md` and `implementation-planning.md`;
- `agent-workflows/github-workflow/` with its own `SKILL.md`, `issue-authoring.md`, and `pull-request-authoring.md`; and
- `agent-workflows/documentation-workflow/` with `SKILL.md` and a project-independent `documentation-maintenance.md`.

Every internal link in each portable bundle must resolve within that bundle. The project-specific routing map lives in its own subfolder, `agent-workflows/project-docs/SKILL.md`; thin Codex and Claude `project-docs` entrypoints point to it, and it routes to the six files under `agent-workflows/references/`.

```text
GitHub issue request
  -> github-workflow native entrypoint
  -> issue-authoring procedure
  -> approved issue or scoped request

Implementation plan or programming request
  -> programming-workflow native entrypoint
  -> portable programming bundle
  -> project-docs skill and current source code
  -> proportionate checks from repository-local policy

Documentation writing or maintenance request
  -> documentation-workflow native entrypoint
  -> portable documentation bundle
  -> project-docs skill and current source/policy
  -> canonical project document and local documentation checks

YouTube Analytics codebase discovery request
  -> project-docs native entrypoint
  -> affected file(s) under agent-workflows/references/
  -> current source code when application behavior must be confirmed

Pull request drafting request
  -> github-workflow native entrypoint
  -> pull-request-authoring procedure
  -> repository PR template and actual branch evidence
```

This layout keeps programming, GitHub artifacts, and documentation-writing procedure independently reusable. Each project then supplies a small `project-docs` router that tells those workflows where its actual codebase documentation lives. Native entrypoints remain thin and equivalent; the proposed names are recorded under **Assumptions**.

## Guidance classification

Every currently reachable responsibility should be assigned deliberately during the move:

| Current guidance | Canonical destination |
|---|---|
| Issue investigation, evidence handling, scope, acceptance criteria, rendering, and publish boundary | Portable GitHub workflow |
| Repository issue-template filenames, available template types/fields, and confirmation wording | Repository-local templates/instructions consumed by the GitHub workflow |
| Implementation investigation, flow tracing, layer assessment, assumptions/decisions/risks, dependency ordering, and review boundary | Portable programming skill |
| Documentation writing from verified evidence, canonical ownership principles, anti-duplication, link maintenance, stale-content handling, and action boundaries | Portable documentation workflow |
| YouTube Analytics layer names, reference paths, SQLite migration detail, and exact verification commands | Project references, `project-docs`, and roots |
| This repository's canonical-document map, native entrypoint paths, validator command, and application-reference update matrix | Project-local `project-docs` skill and repository documentation |
| PR evidence gathering, non-fabrication, template fidelity, title/body drafting, and publish boundary | Portable GitHub workflow |
| This repository's PR template path, allowed Conventional Commit types, branch policy, and CI workflow | Repository-local templates/instructions consumed by the GitHub workflow |
| Proportionate/file-scoped verification, matching checks to affected layers, and separating planning from implementation | Portable programming skill |
| `backend/.venv`, `mypy`, `pytest`, `eslint`, `tsc`, server, sync, API, documentation-validator, and build-approval details | `agent-workflows/references/verification.md` and roots |
| Progressive project-document loading and the route map to architecture/database/sync/API/frontend/verification | Project-local `project-docs` skill |
| Source/policy-over-document precedence when writing or correcting documentation | Portable documentation workflow; `project-docs` supplies the relevant local sources |
| Scope control and separation of drafting, planning, implementation, and publication | Matching portable programming/GitHub skill, with cross-skill handoff boundaries kept explicit |
| No commit/push/publication, dependency-install approval, deletion approval, and full-build approval | Repository roots as always-applicable local policy; every portable skill discovers and obeys local permission boundaries |

As part of review, compare the old entrypoints and every currently routed playbook/reference against this table so no rule is removed without an explicit destination or an intentional, documented deduplication.

## Layer impact

| Layer | Impact |
|---|---|
| Database schema | Not applicable; no tables, columns, keys, indexes, or constraints change. |
| Existing data handling | Not applicable; there is no migration, backfill, reset, or database write. |
| Database helpers | Not applicable; query behavior is unchanged. |
| Synchronization | Not applicable; ingestion, checkpoints, scopes, and scheduling are unchanged. |
| Backend/API | Not applicable; routes, validation, defaults, errors, and response contracts are unchanged. |
| Frontend types | Not applicable; TypeScript contracts are unchanged. |
| Frontend API client | Not applicable; no paths, parameters, or response handling change. |
| Pages/components | Not applicable; no rendering, state, or interaction changes. |
| Styling/responsive behavior | Not applicable; no CSS, table, layout, or breakpoint changes. |
| Compatibility | Affected for agent discovery: the former combined skill path/name is replaced by four triggers per agent. Portability must be verified for all three reusable bundles, and both native agents must retain equivalent behavior. Application/runtime compatibility is unaffected. |
| Documentation | Affected across three portable bundles, a project-local routing bundle, four entrypoint pairs, both roots, verification guidance, and contribution cross-references. |
| Verification | Affected; the validator must model eight native entrypoints, four responsibility-specific routing sets, canonical ownership, path validity, pair parity, portable-bundle independence, and project-doc routing completeness. |

## Assumptions

- The portable bundle/native adapter names will be `programming-workflow`, `github-workflow`, and `documentation-workflow`; the project-local adapter will be `project-docs`. If maintainers prefer different names, update directory names, frontmatter, roots, validator expectations, and cross-references together.
- `implementation-planning.md` will move into the programming bundle, while `issue-authoring.md` and `pull-request-authoring.md` will move together into the GitHub bundle. They will not remain as compatibility copies because copies would create competing canonical owners.
- Reusable content from `agent-workflows/documentation-maintenance.md` will move into the portable documentation bundle. Its project-specific ownership map, reference routes, and validation details will move into `agent-workflows/project-docs/SKILL.md` or the existing canonical references.
- `agent-workflows/references/verification.md` will remain the canonical YouTube Analytics verification reference after reusable principles are extracted from it.
- Root files will retain repository-specific commands, coding conventions, and permission rules. Each portable skill will instruct agents to load equivalent local policy from its destination repository.

## Unresolved decisions

None that block the plan. Naming is recorded as an explicit, consistently replaceable assumption above.

## Risks and compatibility

- Removing or renaming the former combined entrypoint can break stale links or manual invocations. A repository-wide old-name/path search and validator checks must catch every in-repository reference; external consumers are outside this issue's scope.
- The current playbooks rely on repository-specific templates and policies in subtle ways, especially fixed issue categories/fields, Conventional Commit types, PR body sections, layer tables, and command examples. A mechanical move would fail portability even if paths resolve.
- Extracting reusable verification and safety guidance could accidentally weaken repository policy. The roots and YouTube Analytics verification reference must remain authoritative for exact local commands and permissions.
- Thin Codex and Claude adapters can drift in trigger descriptions or routing. Responsibility-specific parity validation should compare their expected names and link sets.
- Cross-skill boundaries can become circular: issue authoring may hand off to programming planning, programming may load project documentation, and PR authoring consumes implementation evidence. Each skill must link only to an optional handoff, not require another portable bundle to be copied with it.
- The documentation workflow and `project-docs` can easily overlap. The former must own how to write and maintain documentation; the latter must own only what documentation exists here and where to find it.
- A link can resolve in this repository while still making a reusable bundle non-portable. Portability needs an isolation check for all three portable bundles, not only the existing repository-root containment check.
- Deleting the obsolete combined skill directories and moved top-level playbooks is destructive under repository policy. Implementation must obtain explicit approval immediately before those removals, even though replacement is implied by the accepted design.

## Implementation steps

### 1. Establish the portable programming skill

- Files and symbols:
  - new `agent-workflows/programming-workflow/SKILL.md`
  - relocated/reworked `agent-workflows/programming-workflow/implementation-planning.md`
  - relevant reusable planning/verification principles extracted from `agent-workflows/references/verification.md`
- Change:
  - Make the canonical `SKILL.md` own implementation planning, code investigation, data/control-flow tracing, layer assessment, scope control, compatibility analysis, implementation boundaries, and proportionate verification selection.
  - Rewrite repository-bound inputs as discovery requirements: inspect the destination repository's local instructions, project documentation, source tree, verification commands, and permission rules.
  - Accept an approved GitHub issue, local issue file, or scoped request as equivalent planning inputs; do not depend on the GitHub workflow.
  - Remove YouTube Analytics layer names, reference paths, schema behavior, exact commands, and fixed plan assumptions while retaining the evidence-backed planning procedure.
  - Keep all required supporting links internal to the programming bundle so it can be copied independently.
  - Use the classification table above as a migration checklist and record intentional deduplications during review.
- Dependencies: None; this creates the canonical owner required by subsequent entrypoints.
- Compatibility: Planning remains evidence-backed and permission-aware but no longer depends on GitHub or a fixed application architecture.
- Verification: Search the bundle for project-specific names, paths, layers, and commands; validate every Markdown link after copying only the programming bundle into a temporary fixture.

### 2. Establish one portable general GitHub workflow

- Files and symbols:
  - new `agent-workflows/github-workflow/SKILL.md`
  - relocated/reworked `agent-workflows/github-workflow/issue-authoring.md`
  - relocated/reworked `agent-workflows/github-workflow/pull-request-authoring.md`
- Change:
  - Make the canonical `SKILL.md` select the issue-authoring or pull-request-authoring procedure based on the requested GitHub artifact.
  - Put issue investigation, template discovery, evidence/uncertainty handling, acceptance criteria, related-work search, rendering, and publish boundaries in the issue procedure.
  - Put branch/diff evidence, title selection, repository PR-template fidelity, non-fabrication, testing-report rules, rendering, and publish boundaries in the PR procedure.
  - Replace this repository's fixed templates, allowed title types, CI paths, and form fields with requirements to inspect the destination repository's GitHub templates and contribution policy.
  - Define optional handoffs: issue output can feed the programming skill, while PR authoring consumes completed change and verification evidence. The GitHub bundle does not require the programming bundle to be present.
  - Keep the GitHub bundle internally self-contained and independently copyable.
- Dependencies: None; the GitHub bundle is a peer of the programming bundle.
- Compatibility: Existing issue and PR drafting behavior remains available through one dedicated GitHub trigger; implementation planning moves out of the GitHub concern.
- Verification: Copy and inspect the GitHub bundle independently; validate internal links and search for YouTube Analytics names, local template paths, fixed contribution rules, and project commands. Confirm both issue and PR requests select the correct internal procedure.

### 3. Establish the portable documentation workflow

- Files and symbols:
  - new `agent-workflows/documentation-workflow/SKILL.md`
  - relocated/reworked `agent-workflows/documentation-workflow/documentation-maintenance.md`
- Change:
  - Own the reusable procedure for drafting and revising documentation from current source code or authoritative policy.
  - Preserve canonical-ownership selection, stale-statement correction, evidence/uncertainty handling, duplication control, related-link updates, link/path maintenance, documentation verification selection, and action boundaries.
  - Replace this repository's document map, skill paths, application-layer matrix, validator command, and root filenames with requirements to inspect the destination repository's local instructions and project-document router.
  - Treat `project-docs` as an optional local discovery input rather than a required dependency so the documentation bundle remains independently copyable.
  - Keep all required links internal to the documentation bundle.
- Dependencies: None; this reusable workflow is a peer of the programming and GitHub bundles.
- Compatibility: Documentation maintenance behavior remains evidence-backed, but codebase-specific destinations and commands come from each project.
- Verification: Copy the documentation bundle alone into a temporary fixture; validate internal links and search for YouTube Analytics names, reference paths, local validator commands, fixed root filenames, and application-layer assumptions.

### 4. Create the project-local `project-docs` router and retain local verification guidance

- Files and symbols:
  - new `agent-workflows/project-docs/SKILL.md`
  - `agent-workflows/references/verification.md`
  - `agent-workflows/references/architecture.md`, `database.md`, `sync.md`, `api.md`, and `frontend.md`
  - superseded project-specific portions of `agent-workflows/documentation-maintenance.md`
- Change:
  - Keep this skill narrowly focused on what canonical codebase documentation exists, which task areas map to which references, and how to load those references progressively.
  - Preserve the rule that current source code is authoritative when a reference conflicts, but hand actual documentation writing or correction to `documentation-workflow`.
  - Keep exact project commands, implementation patterns, layer-specific checks, document ownership, and the application-change-to-reference map on the project-specific side.
  - Keep architecture, database, sync, API, frontend, and verification facts in their existing canonical references rather than copying them into the router.
  - Do not embed generic prose-writing, documentation-maintenance, scope, or verification-selection procedure in `project-docs`.
- Dependencies: Step 3 establishes the portable owner for documentation-writing procedure.
- Compatibility: Application knowledge remains under `agent-workflows/references/`; no application contract or command changes are introduced.
- Verification: Confirm all six reference files remain reachable, every documented task area has a progressive route, and the router contains no duplicated application detail or general documentation-writing procedure.

### 5. Add eight thin native entrypoints and retire the combined entrypoints

- Files and symbols:
  - new `.agents/skills/programming-workflow/SKILL.md`
  - new `.claude/skills/programming-workflow/SKILL.md`
  - new `.agents/skills/github-workflow/SKILL.md`
  - new `.claude/skills/github-workflow/SKILL.md`
  - new `.agents/skills/documentation-workflow/SKILL.md`
  - new `.claude/skills/documentation-workflow/SKILL.md`
  - new `.agents/skills/project-docs/SKILL.md`
  - new `.claude/skills/project-docs/SKILL.md`
  - obsolete `.agents/skills/youtube-analytics-workflow/SKILL.md`
  - obsolete `.claude/skills/youtube-analytics-workflow/SKILL.md`
- Change:
  - Give each adapter valid, responsibility-specific frontmatter and non-overlapping trigger descriptions.
  - Route the programming, GitHub, and documentation adapter pairs only to their matching canonical portable bundles.
  - Route both `project-docs` adapters to the canonical project-local router, which progressively exposes architecture, database, sync, API, frontend, and repository verification references.
  - Keep Codex and Claude behavior equivalent without copying detailed procedures or project application knowledge into their adapters.
  - After explicit deletion approval, remove the two obsolete combined skill directories and the four top-level playbooks superseded by Steps 1-3.
- Dependencies: Steps 1-4 provide all routing targets and ownership boundaries.
- Compatibility: This is the agent-facing rename/split. No compatibility shim is planned because it would preserve the forbidden combined structure and duplicate responsibility.
- Verification: Validate each entrypoint's frontmatter, exact expected name, non-empty body, expected responsibility-specific links, resolved in-repository targets, and Codex/Claude parity.

### 6. Update root instructions and repository cross-references

- Files and symbols:
  - `AGENTS.md` (`Repository workflow`, and any wording affected by the ownership split)
  - `CLAUDE.md` (equivalent sections)
  - `agent-workflows/project-docs/SKILL.md`
  - `CONTRIBUTING.md` (`Agent workflow documentation`)
  - any additional matches found by a repository-wide search for the old skill and moved playbook paths
- Change:
  - Point each root to the programming adapter for planning/implementation work, the GitHub adapter for issue/PR work, the documentation adapter for writing/maintenance work, and `project-docs` for codebase-document discovery.
  - State that local coding rules, templates, commands, and permissions feed the relevant portable skills rather than being embedded in them.
  - Update the ownership table, layout description, triggering guidance, validator description, and moved-file links.
  - Preserve equivalent root policy for both agents and avoid duplicating detailed workflow content.
- Dependencies: Step 5 fixes the final paths and names.
- Compatibility: Exact repository safety and verification rules remain always applicable; only discovery routes change.
- Verification: Search for `youtube-analytics-workflow` and every former top-level playbook path; any remaining match must be intentional and explained. Manually compare `AGENTS.md` and `CLAUDE.md` workflow responsibilities and local policy.

### 7. Refactor workflow validation around responsibility-specific specifications

- Files and symbols:
  - `scripts/validate_agent_workflows.py`
  - `REQUIRED_FILES`, `SKILL_PATHS`, `EXPECTED_SKILL_NAME`, `REQUIRED_ROUTING_TARGETS`, `_LINK_PATTERN`, `check_skill_frontmatter`, `check_routing_targets`, and `check_shared_routing_parity`
- Change:
  - Replace the single combined-skill constants with data describing programming, GitHub, documentation writing, and project-doc discovery responsibilities and their Codex/Claude entrypoints.
  - Validate all eight native entrypoints, their responsibility-specific expected names, descriptions/bodies, required targets, resolved paths, and parity within each Codex/Claude pair.
  - Validate the three canonical portable bundles independently from one another and from `project-docs` and the YouTube Analytics references.
  - Add portability checks that reject links escaping each reusable bundle and detect prohibited project-specific names/paths/commands, while allowing generic instructions to discover destination-repository policy.
  - Continue using only the Python standard library and preserve `--root` fixture support, deterministic read-only behavior, type hints, and docstrings.
  - Remove assumptions that the former combined path, name, or complete routing target list exists.
- Dependencies: Steps 1-6 define the final expected structure.
- Compatibility: The validator's command-line interface and success/failure exit behavior remain unchanged; only its structural model expands.
- Verification: Exercise the validator against the real repository and targeted temporary fixtures that demonstrate missing entrypoints, wrong names, mismatched pair routing, unresolved/out-of-repository links, portable-bundle link escape, and leaked project-specific content are rejected.

### 8. Remove superseded structure and perform a completeness audit

- Files and symbols:
  - obsolete combined skill directories
  - former top-level reusable playbooks after their portable replacements exist
  - all files returned by `rg` for old names and paths
- Change:
  - With explicit deletion approval, remove only files proven superseded by the new canonical bundle and entrypoints.
  - Review the final diff against the guidance-classification table and every acceptance criterion, confirming each old rule has one deliberate destination and no detailed guidance has competing owners.
  - Preserve `issue.md` and any unrelated user changes.
- Dependencies: Steps 1-7 must be complete and validating before removal.
- Compatibility: No runtime files or data are touched. The old manual skill path intentionally stops being supported.
- Verification: Confirm the former combined structure is absent, all new links resolve, no unintended duplicates remain, and `git status --short -- backend frontend` is empty.

## Verification

Run the documentation-only checks after all edits:

```bash
python scripts/validate_agent_workflows.py
git diff --check
git status --short -- backend frontend
```

Also perform focused behavioral checks that the acceptance criteria require but the current validator does not cover:

- Copy `agent-workflows/programming-workflow/`, `agent-workflows/github-workflow/`, and `agent-workflows/documentation-workflow/` independently to isolated temporary repository shapes and confirm all internal Markdown links resolve without the other bundles, `project-docs`, or `agent-workflows/references/`.
- Search all three portable bundles for the project name, YouTube/application-specific routes, repository reference paths, fixed template filenames, local commands, framework names, and repository-specific permission text; review all matches rather than relying on one token.
- Run the validator against controlled `--root` fixtures for each important failure mode listed in Step 7, then confirm the unmodified real structure passes.
- Compare all four Codex/Claude entrypoint pairs for names, descriptions, responsibility-specific routes, and triggering guidance.
- Confirm the programming skill can plan from a local issue/request without GitHub, and that the GitHub skill can independently select issue authoring or PR authoring without the programming bundle.
- Confirm the documentation workflow can guide a documentation change using destination-repository instructions alone, while `project-docs` only selects this repository's relevant canonical references and hands writing work to the documentation workflow.
- Search the entire repository for the former combined skill name and moved paths; confirm no broken or stale cross-reference remains.
- Inspect `git status --short` to ensure `issue.md` remains unchanged and only the intended documentation/validator files are part of the implementation.
- Do not run backend checks, frontend checks, or `npm run build`; no application files are in scope, and a full build requires separate approval.

## Documentation updates

- The programming bundle becomes the sole canonical owner of reusable implementation-planning and programming procedures.
- The general GitHub bundle is the sole owner of reusable issue and pull request authoring procedures.
- The documentation bundle becomes the sole canonical owner of reusable documentation-writing and maintenance procedure.
- The project-local `project-docs` skill owns only progressive codebase-document discovery and routing, not writing procedure or application facts.
- `agent-workflows/references/architecture.md`, `database.md`, `sync.md`, `api.md`, `frontend.md`, and `verification.md` remain the canonical application/repository knowledge owners.
- `AGENTS.md` and `CLAUDE.md` remain the canonical local policy inputs and point to all four separately triggerable skills for their native agent.
- `CONTRIBUTING.md` and `project-docs` describe the new layout and validation command without duplicating reusable procedure or application detail.

## Acceptance-criteria coverage

| Acceptance criteria group | Covered by |
|---|---|
| Separate programming, GitHub, documentation-writing, and project-doc discovery skills for Codex and Claude | Steps 1-5; eight-entrypoint validator checks |
| Programming, GitHub, and documentation workflows are project-independent, self-contained, and independently copyable | Steps 1-3; portability/isolation verification |
| Implementation planning works from GitHub issues, local issues, or scoped requests | Step 1 and cross-skill independence checks |
| Repository-local templates, commands, and conventions supply project details | Steps 1-4 and 6 |
| Documentation writing is separate from project-document discovery | Steps 3 and 4; boundary verification |
| Progressive routing to all six canonical project references | Steps 4 and 5; routing validation |
| No existing rule silently dropped | Guidance classification and Step 8 completeness audit |
| One canonical owner per reusable procedure; canonical application-reference ownership retained | Proposed ownership, Steps 1-6, and duplication review |
| Roots, project-doc routing, and affected cross-references describe the split | Step 6 |
| Validator supports new names, eight entrypoints, pair parity, portability, and links without the combined structure | Step 7 and its fixture checks |
| Validator, whitespace, and no-application-change checks pass | Final verification commands and Step 8 |

## Review boundary

This file is a plan only. Implementation requires separate explicit authorization. Before implementation removes the obsolete combined skill directories or superseded playbook files, obtain the repository-required approval for deletion. Commits, pushes, remote publication, and full builds remain outside the authorized scope.

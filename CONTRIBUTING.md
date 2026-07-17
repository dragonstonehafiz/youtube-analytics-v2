# Contributing

## Workflow

- Branch from the latest `main`.
- Never push directly to `main` — all changes go through a pull request.
- PRs are merged with **squash and merge** only; the PR title becomes the squash commit message.
- Keep each PR focused on a single change.
- Update tests and documentation alongside the code they cover.

## Branch naming

```
feat/<short-kebab-case-description>
fix/<short-kebab-case-description>
chore/<short-kebab-case-description>
```

Examples:

```
feat/channel-comparison
fix/incorrect-date-filter
chore/update-docker-image
```

## Commit messages

Commits follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<optional-scope>): <description>
```

Common types: `feat`, `fix`, `chore`, `docs`, `refactor`, `test`.

Examples:

```
feat(analytics): add channel comparison
fix(sync): prevent duplicate analytics rows
chore(deps): update frontend dependencies
docs: document local development
refactor(database): split query helpers
test(sync): cover incremental date ranges
```

Mark breaking changes with `!` before the colon:

```
feat(api)!: change analytics response format
```

Branches and commits both use the same Conventional Commit types (`feat`, `fix`, `chore`, ...), so a branch name and its PR title/commit message share the same prefix.

### Local commit-msg hook

A `commit-msg` hook that rejects non-Conventional-Commit subjects is checked into `.githooks/`. Enable it once per clone:

```bash
git config core.hooksPath .githooks
```

This runs locally before each commit is created (in addition to the `pr-policy` GitHub Actions check, which re-validates on the PR).

## Pull requests

- Target `main`.
- Branch name must start with `feat/`, `fix/`, or `chore/`.
- Title must follow Conventional Commits — it becomes the squash commit message.
- Include a summary, testing notes, and any linked issues.
- All required checks must pass before merging.
- The source branch is deleted after merging.

See `.github/PULL_REQUEST_TEMPLATE.md` for the PR checklist.

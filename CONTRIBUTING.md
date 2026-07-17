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

PRs are squash-merged, so the **PR title** becomes the final commit message and is the only thing enforced by CI. It follows [Conventional Commits](https://www.conventionalcommits.org/), restricted to the same three types as branch names:

```
feat(<optional-scope>): <description>
fix(<optional-scope>): <description>
chore(<optional-scope>): <description>
```

Example:

```
Branch:   fix/frontend-build-failure
PR title: fix(frontend): resolve build failure
```

Mark breaking changes with `!` before the colon:

```
feat(api)!: change analytics response format
```

Individual commits within a branch can follow the same format, but the PR workflow does not validate every intermediate commit — only the branch name and the final PR title. This means temporary or automatic commits (e.g. merge commits from syncing with `main`) never block a PR.

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

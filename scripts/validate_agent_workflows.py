#!/usr/bin/env python3
"""Dependency-free validator for agent-workflows/.claude/.agents structure.

Checks, using only the Python standard library:
  - required shared files exist (playbooks, references, skill entrypoints)
  - both SKILL.md files have valid, minimal frontmatter
  - both skills route to the same shared playbook/reference targets, and
    every referenced target actually resolves to a real file inside the repo

Read-only and deterministic. Does not require network access, PyYAML, or any
platform-specific tooling (WSL, Codex, Claude CLI).

Usage:
    python scripts/validate_agent_workflows.py [--root PATH]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    ".agents/skills/youtube-analytics-workflow/SKILL.md",
    ".claude/skills/youtube-analytics-workflow/SKILL.md",
    "agent-workflows/issue-authoring.md",
    "agent-workflows/implementation-planning.md",
    "agent-workflows/documentation-maintenance.md",
    "agent-workflows/pull-request-authoring.md",
    "agent-workflows/references/architecture.md",
    "agent-workflows/references/database.md",
    "agent-workflows/references/sync.md",
    "agent-workflows/references/api.md",
    "agent-workflows/references/frontend.md",
    "agent-workflows/references/verification.md",
]

SKILL_PATHS = [
    ".agents/skills/youtube-analytics-workflow/SKILL.md",
    ".claude/skills/youtube-analytics-workflow/SKILL.md",
]

EXPECTED_SKILL_NAME = "youtube-analytics-workflow"

REQUIRED_ROUTING_TARGETS = [
    "../../../agent-workflows/issue-authoring.md",
    "../../../agent-workflows/implementation-planning.md",
    "../../../agent-workflows/documentation-maintenance.md",
    "../../../agent-workflows/pull-request-authoring.md",
    "../../../agent-workflows/references/architecture.md",
    "../../../agent-workflows/references/database.md",
    "../../../agent-workflows/references/sync.md",
    "../../../agent-workflows/references/api.md",
    "../../../agent-workflows/references/frontend.md",
    "../../../agent-workflows/references/verification.md",
]

# Matches any relative link pointing into agent-workflows/, so we can compare
# the two skill entrypoints' shared routing sets without assuming they are
# byte-identical.
_LINK_PATTERN = re.compile(r"\.\./\.\./\.\./agent-workflows/[^\s`)\]]+")


def check_required_files(root: Path) -> list[str]:
    """Return one problem string per missing required file."""
    problems = []
    for rel in REQUIRED_FILES:
        if not (root / rel).is_file():
            problems.append(f"missing required file: {rel}")
    return problems


def parse_frontmatter(text: str) -> tuple[dict[str, str], str, list[str]]:
    """Parse a minimal '---'-delimited frontmatter block.

    Returns (fields, body, problems). Not a full YAML parser — this format
    is deliberately simple (flat `key: value` lines), so a full parser is
    unnecessary.
    """
    problems: list[str] = []
    lines = text.splitlines()

    if not lines or lines[0].strip() != "---":
        problems.append("frontmatter does not begin with '---'")
        return {}, text, problems

    closing_index = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            closing_index = i
            break

    if closing_index is None:
        problems.append("frontmatter has no closing '---'")
        return {}, "", problems

    fields: dict[str, str] = {}
    for line in lines[1:closing_index]:
        if not line.strip() or line.strip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        fields[key] = value

    body = "\n".join(lines[closing_index + 1 :])
    return fields, body, problems


def check_skill_frontmatter(root: Path, rel_path: str) -> tuple[list[str], str]:
    """Validate one SKILL.md's frontmatter. Returns (problems, raw text)."""
    problems: list[str] = []
    full_path = root / rel_path
    text = full_path.read_text(encoding="utf-8")

    fields, body, fm_problems = parse_frontmatter(text)
    problems.extend(f"{rel_path}: {p}" for p in fm_problems)

    if fm_problems:
        return problems, text

    name = fields.get("name", "")
    description = fields.get("description", "")

    if not name:
        problems.append(f"{rel_path}: frontmatter 'name' is empty or missing")
    elif name != EXPECTED_SKILL_NAME:
        problems.append(
            f"{rel_path}: frontmatter name is '{name}', expected '{EXPECTED_SKILL_NAME}'"
        )

    if not description.strip():
        problems.append(f"{rel_path}: frontmatter 'description' is empty or missing")

    if not body.strip():
        problems.append(f"{rel_path}: no body content after frontmatter")

    return problems, text


def check_routing_targets(root: Path, rel_path: str, text: str) -> list[str]:
    """Confirm every required routing target is present and resolves to a real,
    in-repo file when read from rel_path's own directory."""
    problems: list[str] = []
    skill_dir = (root / rel_path).parent

    for target in REQUIRED_ROUTING_TARGETS:
        if target not in text:
            problems.append(f"{rel_path}: missing required routing link to '{target}'")
            continue

        resolved = (skill_dir / target).resolve()

        try:
            resolved.relative_to(root.resolve())
        except ValueError:
            problems.append(
                f"{rel_path}: routing link '{target}' resolves outside the repository ({resolved})"
            )
            continue

        if not resolved.is_file():
            problems.append(
                f"{rel_path}: routing link '{target}' does not resolve to a file ({resolved})"
            )

    return problems


def check_shared_routing_parity(texts: dict[str, str]) -> list[str]:
    """Compare the two skills' extracted agent-workflows/ links. They need not be
    byte-identical, but their shared routing targets must match."""
    problems: list[str] = []
    link_sets = {rel: set(_LINK_PATTERN.findall(text)) for rel, text in texts.items()}

    paths = list(link_sets.keys())
    if len(paths) != 2:
        return problems

    a, b = paths
    only_in_a = link_sets[a] - link_sets[b]
    only_in_b = link_sets[b] - link_sets[a]

    if only_in_a:
        problems.append(
            f"routing mismatch: {a} links to {sorted(only_in_a)} not present in {b}"
        )
    if only_in_b:
        problems.append(
            f"routing mismatch: {b} links to {sorted(only_in_b)} not present in {a}"
        )

    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root to validate (defaults to the real repo root; "
        "useful for pointing at a temporary fixture during testing).",
    )
    args = parser.parse_args()
    root = args.root.resolve()

    problems: list[str] = []

    problems.extend(check_required_files(root))

    skill_texts: dict[str, str] = {}
    for rel_path in SKILL_PATHS:
        if not (root / rel_path).is_file():
            # Already reported by check_required_files; skip further checks on it.
            continue
        fm_problems, text = check_skill_frontmatter(root, rel_path)
        problems.extend(fm_problems)
        skill_texts[rel_path] = text
        problems.extend(check_routing_targets(root, rel_path, text))

    if len(skill_texts) == 2:
        problems.extend(check_shared_routing_parity(skill_texts))

    if problems:
        print("Agent workflow validation failed:")
        for p in problems:
            print(f"- {p}")
        return 1

    print("Agent workflow validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Dependency-free validator for agent-workflows/.claude/.agents structure.

Models four separately triggerable responsibilities — programming, GitHub,
documentation, and project-docs — each exposed through an Codex (`.agents/skills/`)
and Claude (`.claude/skills/`) entrypoint pair:

  - required files exist for every portable bundle, the project-docs router, and
    all eight native entrypoints;
  - every native entrypoint has valid, minimal frontmatter with the expected
    skill name and routes to its bundle's canonical `SKILL.md`;
  - each Codex/Claude entrypoint pair has matching name and description text;
  - every routing link resolves to a real file inside the repository;
  - the programming, GitHub, and documentation bundles are portable: no internal
    link escapes its own bundle directory, and no project-specific name, path,
    or command appears in their content;
  - `project-docs` routes to all six canonical references under
    `agent-workflows/references/`.

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
from typing import NamedTuple

REPO_ROOT = Path(__file__).resolve().parents[1]

NATIVE_ROOTS = [".agents/skills", ".claude/skills"]

REFERENCE_FILES = [
    "agent-workflows/references/architecture.md",
    "agent-workflows/references/database.md",
    "agent-workflows/references/sync.md",
    "agent-workflows/references/api.md",
    "agent-workflows/references/frontend.md",
    "agent-workflows/references/verification.md",
]

# Relative links (as they appear from agent-workflows/project-docs/SKILL.md)
# that must be present so project-docs actually routes to every reference.
PROJECT_DOCS_REQUIRED_LINKS = [f"../references/{Path(p).name}" for p in REFERENCE_FILES]

# Case-insensitive substrings that must never appear inside a portable bundle —
# each one names this repository's application, stack, or exact local commands
# rather than a destination-repository-agnostic instruction.
FORBIDDEN_PORTABLE_TOKENS = [
    "youtube",
    "backend/",
    "frontend/",
    ".venv",
    "mypy",
    "eslint",
    "tsc ",
    "fastapi",
    "sqlite",
    "uvicorn",
    "agent-workflows/references",
    "youtube-analytics-v2",
]


class SkillSpec(NamedTuple):
    """Describes one of the four responsibility-specific skills."""

    name: str
    canonical: str  # path to the bundle's canonical SKILL.md, relative to repo root
    bundle_dir: str  # directory containing the whole bundle, relative to repo root
    bundle_files: list[str]  # every file belonging to the bundle, relative to repo root
    portable: bool  # whether this bundle must be project-independent


SKILL_SPECS: list[SkillSpec] = [
    SkillSpec(
        name="programming-workflow",
        canonical="agent-workflows/programming-workflow/SKILL.md",
        bundle_dir="agent-workflows/programming-workflow",
        bundle_files=[
            "agent-workflows/programming-workflow/SKILL.md",
            "agent-workflows/programming-workflow/implementation-planning.md",
        ],
        portable=True,
    ),
    SkillSpec(
        name="github-workflow",
        canonical="agent-workflows/github-workflow/SKILL.md",
        bundle_dir="agent-workflows/github-workflow",
        bundle_files=[
            "agent-workflows/github-workflow/SKILL.md",
            "agent-workflows/github-workflow/issue-authoring.md",
            "agent-workflows/github-workflow/pull-request-authoring.md",
        ],
        portable=True,
    ),
    SkillSpec(
        name="documentation-workflow",
        canonical="agent-workflows/documentation-workflow/SKILL.md",
        bundle_dir="agent-workflows/documentation-workflow",
        bundle_files=[
            "agent-workflows/documentation-workflow/SKILL.md",
            "agent-workflows/documentation-workflow/documentation-maintenance.md",
        ],
        portable=True,
    ),
    SkillSpec(
        name="project-docs",
        canonical="agent-workflows/project-docs/SKILL.md",
        bundle_dir="agent-workflows/project-docs",
        bundle_files=[
            "agent-workflows/project-docs/SKILL.md",
        ],
        portable=False,
    ),
]

# Matches a backtick-quoted relative Markdown path, e.g. `implementation-planning.md`
# or `../references/architecture.md`. Deliberately excludes absolute paths and URLs.
_RELATIVE_MD_LINK_PATTERN = re.compile(r"`((?:\.\./|[A-Za-z0-9_-])[A-Za-z0-9_\-./]*\.md)`")

# Bare filenames that are commonly mentioned by name (e.g. in an ownership table)
# without implying a resolvable relative path from the mentioning file's own
# directory — not treated as links to validate.
_AMBIGUOUS_ROOT_MENTIONS = {"AGENTS.md", "CLAUDE.md", "README.md", "CONTRIBUTING.md"}


def required_files() -> list[str]:
    """Every file that must exist for the structure to be complete."""
    files: list[str] = list(REFERENCE_FILES)
    for spec in SKILL_SPECS:
        files.extend(spec.bundle_files)
    for native_root in NATIVE_ROOTS:
        for spec in SKILL_SPECS:
            files.append(f"{native_root}/{spec.name}/SKILL.md")
    return files


def check_required_files(root: Path) -> list[str]:
    """Return one problem string per missing required file."""
    problems = []
    for rel in required_files():
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


def check_skill_frontmatter(root: Path, rel_path: str, expected_name: str) -> tuple[list[str], str]:
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
    elif name != expected_name:
        problems.append(f"{rel_path}: frontmatter name is '{name}', expected '{expected_name}'")

    if not description.strip():
        problems.append(f"{rel_path}: frontmatter 'description' is empty or missing")

    if not body.strip():
        problems.append(f"{rel_path}: no body content after frontmatter")

    return problems, text


def resolve_link(root: Path, from_file: Path, link: str) -> tuple[Path, bool]:
    """Resolve a relative link found in from_file. Returns (resolved, is_in_repo)."""
    resolved = (from_file.parent / link).resolve()
    try:
        resolved.relative_to(root.resolve())
        return resolved, True
    except ValueError:
        return resolved, False


def check_native_entrypoints(root: Path) -> tuple[list[str], dict[str, dict[str, dict[str, str]]]]:
    """Validate all eight native entrypoints. Returns (problems, fields_by_root_by_skill)."""
    problems: list[str] = []
    fields_by_root: dict[str, dict[str, dict[str, str]]] = {r: {} for r in NATIVE_ROOTS}

    for spec in SKILL_SPECS:
        for native_root in NATIVE_ROOTS:
            rel_path = f"{native_root}/{spec.name}/SKILL.md"
            if not (root / rel_path).is_file():
                continue  # already reported by check_required_files

            fm_problems, text = check_skill_frontmatter(root, rel_path, spec.name)
            problems.extend(fm_problems)
            if fm_problems:
                continue

            fields, body, _ = parse_frontmatter(text)
            fields_by_root[native_root][spec.name] = fields

            expected_link = f"../../../{spec.canonical}"
            if expected_link not in body:
                problems.append(
                    f"{rel_path}: missing required routing link to '{expected_link}'"
                )
                continue

            resolved, in_repo = resolve_link(root, root / rel_path, expected_link)
            if not in_repo:
                problems.append(
                    f"{rel_path}: routing link '{expected_link}' resolves outside the repository ({resolved})"
                )
            elif not resolved.is_file():
                problems.append(
                    f"{rel_path}: routing link '{expected_link}' does not resolve to a file ({resolved})"
                )

    return problems, fields_by_root


def check_pair_parity(
    fields_by_root: dict[str, dict[str, dict[str, str]]],
) -> list[str]:
    """Confirm each skill's Codex and Claude entrypoints agree on name and description."""
    problems: list[str] = []
    if len(NATIVE_ROOTS) != 2:
        return problems
    codex_root, claude_root = NATIVE_ROOTS

    for spec in SKILL_SPECS:
        codex_fields = fields_by_root[codex_root].get(spec.name)
        claude_fields = fields_by_root[claude_root].get(spec.name)
        if codex_fields is None or claude_fields is None:
            continue  # already reported as missing/invalid

        for key in ("name", "description"):
            codex_value = codex_fields.get(key, "")
            claude_value = claude_fields.get(key, "")
            if codex_value != claude_value:
                problems.append(
                    f"{spec.name}: '{key}' differs between {codex_root} and {claude_root} "
                    f"('{codex_value}' vs '{claude_value}')"
                )

    return problems


def extract_relative_md_links(text: str) -> list[str]:
    """Return every backtick-quoted relative Markdown path referenced in text."""
    return [
        link
        for link in _RELATIVE_MD_LINK_PATTERN.findall(text)
        if link not in _AMBIGUOUS_ROOT_MENTIONS
    ]


def check_bundle_links(root: Path, spec: SkillSpec) -> list[str]:
    """Confirm every internal link in a bundle resolves to a real file.

    For portable bundles, also confirm the link stays inside the bundle's own
    directory — a link escaping it would break the bundle when copied alone
    into another repository.
    """
    problems: list[str] = []
    bundle_dir = (root / spec.bundle_dir).resolve()

    for rel_file in spec.bundle_files:
        full_path = root / rel_file
        if not full_path.is_file():
            continue  # already reported by check_required_files

        text = full_path.read_text(encoding="utf-8")
        for link in extract_relative_md_links(text):
            resolved, in_repo = resolve_link(root, full_path, link)

            if not in_repo:
                problems.append(
                    f"{rel_file}: link '{link}' resolves outside the repository ({resolved})"
                )
                continue

            if not resolved.is_file():
                problems.append(f"{rel_file}: link '{link}' does not resolve to a file ({resolved})")
                continue

            if spec.portable:
                try:
                    resolved.relative_to(bundle_dir)
                except ValueError:
                    problems.append(
                        f"{rel_file}: link '{link}' escapes the portable bundle '{spec.bundle_dir}' "
                        f"({resolved}) — this bundle must be self-contained when copied alone"
                    )

    return problems


def check_portability_tokens(root: Path, spec: SkillSpec) -> list[str]:
    """Flag project-specific names/paths/commands leaking into a portable bundle."""
    problems: list[str] = []
    if not spec.portable:
        return problems

    for rel_file in spec.bundle_files:
        full_path = root / rel_file
        if not full_path.is_file():
            continue

        text_lower = full_path.read_text(encoding="utf-8").lower()
        for token in FORBIDDEN_PORTABLE_TOKENS:
            if token in text_lower:
                problems.append(
                    f"{rel_file}: contains project-specific token '{token.strip()}', "
                    "which is not allowed in a portable bundle"
                )

    return problems


def check_project_docs_routing(root: Path) -> list[str]:
    """Confirm project-docs routes to all six canonical references."""
    problems: list[str] = []
    project_docs_spec = next(spec for spec in SKILL_SPECS if spec.name == "project-docs")
    full_path = root / project_docs_spec.canonical
    if not full_path.is_file():
        return problems  # already reported by check_required_files

    text = full_path.read_text(encoding="utf-8")
    for link in PROJECT_DOCS_REQUIRED_LINKS:
        if link not in text:
            problems.append(f"{project_docs_spec.canonical}: missing required routing link to '{link}'")

    return problems


def check_bundle_canonical_frontmatter(root: Path) -> list[str]:
    """Validate each bundle's own canonical SKILL.md frontmatter."""
    problems: list[str] = []
    for spec in SKILL_SPECS:
        if not (root / spec.canonical).is_file():
            continue  # already reported by check_required_files
        fm_problems, _ = check_skill_frontmatter(root, spec.canonical, spec.name)
        problems.extend(fm_problems)
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
    problems.extend(check_bundle_canonical_frontmatter(root))

    entrypoint_problems, fields_by_root = check_native_entrypoints(root)
    problems.extend(entrypoint_problems)
    problems.extend(check_pair_parity(fields_by_root))

    for spec in SKILL_SPECS:
        problems.extend(check_bundle_links(root, spec))
        problems.extend(check_portability_tokens(root, spec))

    problems.extend(check_project_docs_routing(root))

    if problems:
        print("Agent workflow validation failed:")
        for p in problems:
            print(f"- {p}")
        return 1

    print("Agent workflow validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Validate local Markdown links, heading fragments, and explicit `docs/`
path mentions across this repository's documentation and backend source.

Read-only, standard-library only. See `docs/references/verification.md` for
when to run this and `docs/documentation-workflow/documentation-maintenance.md`
for the workflow it replaces.

Supported forms:

- Inline Markdown links/images: `[text](target)`, `![alt](target)`, with an
  optional `<target>` angle-bracket wrapper (needed when the target contains
  a space), an optional `"title"`, and an optional `#fragment`, resolved
  relative to the containing file. A bare `#fragment` resolves against that
  same file's own headings. An unbracketed target may contain one level of
  balanced parentheses, e.g. `docs/a(b).md`; a target needing more than that
  should use the `<target>` form instead.
- Heading anchors follow GitHub's slug rules: markdown link/image syntax in
  a heading is reduced to its visible text first, then the result is
  lowercased, characters outside `[a-z0-9_- ]` are dropped (backticks
  removed first), spaces become hyphens, and a repeated slug in the same
  file gets a `-1`, `-2`, ... suffix in order of appearance.
- Reference-style links and images (`[text][id]`, `[text][]`, `![alt][id]`)
  are reported as an unsupported link form rather than silently skipped.
- Explicit `docs/...`, `./docs/...`, and `../docs/...` path mentions inside
  Markdown inline-code spans, and inside backend Python comments and
  docstrings. `docs/...` resolves from the repository root; `./`/`../` forms
  resolve from the file that mentions them. A Markdown link's own label and
  destination are not re-checked here — the link check above already covers
  them.

Link-shaped text inside an inline-code span (e.g. an illustrative
`` `[text](target)` `` used to show syntax) is masked out before the link
scan, the same way a fenced code block is, so it is never treated as an
actual link.

Not checked: external URLs (skipped without a network request), content
inside fenced code blocks, factual accuracy, and bare words that are not a
link or one of the explicit `docs/` path forms above.
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import sys
import tokenize
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

NAMED_MARKDOWN_FILES = (
    "AGENTS.md",
    "README.md",
    "CONTRIBUTING.md",
    "backend/README.md",
    "frontend/README.md",
)

PRUNE_DIR_NAMES = {"__pycache__", "data", "secrets", "node_modules"}

FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
HEADING_RE = re.compile(r"^ {0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
LINK_RE = re.compile(
    r"(!?)\[([^\]]*)\]\("
    r"\s*(?:<([^<>\n]*)>|((?:[^()\s]|\([^()]*\))*))"
    r'(?:\s+(?:"[^"]*"|\'[^\']*\'))?'
    r"\s*\)"
)
REFERENCE_LINK_RE = re.compile(r"!?\[[^\]]+\]\[[^\]]*\]")
CODE_SPAN_RE = re.compile(r"`([^`\n]+)`")
DOCS_PATH_RE = re.compile(r"(?:\.\./|\./)?docs/[A-Za-z0-9_.\-/]+")


@dataclass(frozen=True)
class Diagnostic:
    path: str
    line: int
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.message}"


def rel(path: Path, root: Path) -> str:
    return str(path.resolve().relative_to(root)).replace(os.sep, "/")


def iter_unfenced_lines(lines: list[str]):
    """Yield (1-based line number, line) for lines outside fenced code blocks."""
    in_fence = False
    fence_char = ""
    fence_len = 0
    for lineno, line in enumerate(lines, start=1):
        m = FENCE_RE.match(line)
        if m:
            marker = m.group(1)
            if not in_fence:
                in_fence = True
                fence_char = marker[0]
                fence_len = len(marker)
                continue
            if marker[0] == fence_char and len(marker) >= fence_len:
                in_fence = False
                continue
        if in_fence:
            continue
        yield lineno, line


_HEADING_LINK_RE = re.compile(r"!?\[([^\]]*)\]\((?:[^()]|\([^()]*\))*\)")
_HEADING_REFERENCE_LINK_RE = re.compile(r"\[([^\]]*)\]\[[^\]]*\]")


def slugify(heading_text: str) -> str:
    text = _HEADING_LINK_RE.sub(r"\1", heading_text)
    text = _HEADING_REFERENCE_LINK_RE.sub(r"\1", text)
    text = text.replace("`", "").lower()
    text = re.sub(r"[^\w\- ]", "", text, flags=re.UNICODE)
    return text.replace(" ", "-")


_ANCHOR_CACHE: dict[Path, dict[str, int]] = {}


def collect_anchors(path: Path) -> dict[str, int]:
    resolved = path.resolve()
    if resolved in _ANCHOR_CACHE:
        return _ANCHOR_CACHE[resolved]
    anchors: dict[str, int] = {}
    counts: dict[str, int] = {}
    try:
        lines = resolved.read_text(encoding="utf-8").splitlines()
    except OSError:
        _ANCHOR_CACHE[resolved] = anchors
        return anchors
    for lineno, line in iter_unfenced_lines(lines):
        m = HEADING_RE.match(line)
        if not m:
            continue
        slug = slugify(m.group(2))
        n = counts.get(slug, 0)
        counts[slug] = n + 1
        anchor = slug if n == 0 else f"{slug}-{n}"
        anchors.setdefault(anchor, lineno)
    _ANCHOR_CACHE[resolved] = anchors
    return anchors


def check_link_target(raw_target: str, source_path: Path) -> str | None:
    target = unquote(raw_target)
    if "#" in target:
        path_part, frag = target.split("#", 1)
    else:
        path_part, frag = target, None

    if path_part == "":
        target_file = source_path
    else:
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:", path_part):
            return None  # external scheme (http, https, mailto, ...)
        target_file = (source_path.parent / path_part).resolve()
        if not target_file.exists():
            return f"missing file: {raw_target}"

    if frag is not None and target_file.suffix.lower() == ".md" and target_file.exists():
        if frag not in collect_anchors(target_file):
            return f"missing heading: {raw_target}"

    return None


def mask_links(line: str) -> str:
    return LINK_RE.sub(lambda m: " " * len(m.group(0)), line)


def mask_code_spans(line: str) -> str:
    return CODE_SPAN_RE.sub(lambda m: " " * len(m.group(0)), line)


def check_markdown_links(path: Path, root: Path) -> tuple[list[Diagnostic], int]:
    diagnostics: list[Diagnostic] = []
    checked = 0
    lines = path.read_text(encoding="utf-8").splitlines()
    for lineno, line in iter_unfenced_lines(lines):
        # Inline-code spans are masked first so link-shaped example syntax
        # inside backticks (e.g. an illustrative `[text](target)`) is not
        # treated as an actual link or flagged as an unsupported one.
        scan_line = mask_code_spans(line)
        for ref_m in REFERENCE_LINK_RE.finditer(scan_line):
            checked += 1
            diagnostics.append(
                Diagnostic(rel(path, root), lineno, f"unsupported link form: {ref_m.group(0)}")
            )
        for m in LINK_RE.finditer(scan_line):
            raw_target = m.group(3) if m.group(3) is not None else m.group(4)
            if not raw_target:
                continue
            checked += 1
            message = check_link_target(raw_target, path)
            if message:
                diagnostics.append(Diagnostic(rel(path, root), lineno, message))
    return diagnostics, checked


def check_docs_path(raw: str, source_path: Path, root: Path) -> str | None:
    if raw.startswith("docs/"):
        target = (root / raw).resolve()
    elif raw.startswith("./docs/") or raw.startswith("../docs/"):
        target = (source_path.parent / raw).resolve()
    else:
        return None
    if not target.exists():
        return f"missing path: {raw}"
    return None


def check_markdown_docs_paths(path: Path, root: Path) -> tuple[list[Diagnostic], int]:
    diagnostics: list[Diagnostic] = []
    checked = 0
    lines = path.read_text(encoding="utf-8").splitlines()
    for lineno, line in iter_unfenced_lines(lines):
        masked = mask_links(line)
        for span_m in CODE_SPAN_RE.finditer(masked):
            content = span_m.group(1).strip()
            if not DOCS_PATH_RE.fullmatch(content):
                continue
            checked += 1
            message = check_docs_path(content, path, root)
            if message:
                diagnostics.append(Diagnostic(rel(path, root), lineno, message))
    return diagnostics, checked


def scan_docs_paths_in_text(
    text: str, source_path: Path, root: Path, lineno: int
) -> tuple[list[Diagnostic], int]:
    diagnostics: list[Diagnostic] = []
    checked = 0
    for m in DOCS_PATH_RE.finditer(text):
        checked += 1
        message = check_docs_path(m.group(0), source_path, root)
        if message:
            diagnostics.append(Diagnostic(rel(source_path, root), lineno, message))
    return diagnostics, checked


def check_python_file(path: Path, root: Path) -> tuple[list[Diagnostic], int]:
    diagnostics: list[Diagnostic] = []
    checked = 0
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()

    try:
        for tok in tokenize.generate_tokens(iter(source.splitlines(keepends=True)).__next__):
            if tok.type == tokenize.COMMENT:
                diags, n = scan_docs_paths_in_text(tok.string, path, root, tok.start[0])
                diagnostics.extend(diags)
                checked += n
    except (tokenize.TokenizeError, SyntaxError, IndentationError):
        pass

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return diagnostics, checked

    docstring_nodes = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    for node in ast.walk(tree):
        if not isinstance(node, docstring_nodes):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if not (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            continue
        start = first.lineno
        end = first.end_lineno or start
        for lineno in range(start, end + 1):
            diags, n = scan_docs_paths_in_text(lines[lineno - 1], path, root, lineno)
            diagnostics.extend(diags)
            checked += n

    return diagnostics, checked


def discover_markdown_files(root: Path) -> list[Path]:
    files: set[Path] = set()
    for name in NAMED_MARKDOWN_FILES:
        candidate = root / name
        if candidate.is_file():
            files.add(candidate.resolve())
    for subdir in (".github", "docs"):
        base = root / subdir
        if base.is_dir():
            files.update(p.resolve() for p in base.rglob("*.md"))
    return sorted(files)


def discover_python_files(root: Path) -> list[Path]:
    backend_dir = root / "backend"
    if not backend_dir.is_dir():
        return []
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(backend_dir):
        dirnames[:] = sorted(
            d for d in dirnames if not d.startswith(".") and d not in PRUNE_DIR_NAMES
        )
        for filename in sorted(filenames):
            if filename.endswith(".py"):
                files.append(Path(dirpath) / filename)
    return sorted(files)


def run(root: Path) -> tuple[list[Diagnostic], int, int, int, int]:
    _ANCHOR_CACHE.clear()
    markdown_files = discover_markdown_files(root)
    python_files = discover_python_files(root)

    diagnostics: list[Diagnostic] = []
    link_count = 0
    docs_path_count = 0

    for path in markdown_files:
        diags, checked = check_markdown_links(path, root)
        diagnostics.extend(diags)
        link_count += checked
        diags, checked = check_markdown_docs_paths(path, root)
        diagnostics.extend(diags)
        docs_path_count += checked

    for path in python_files:
        diags, checked = check_python_file(path, root)
        diagnostics.extend(diags)
        docs_path_count += checked

    diagnostics.sort(key=lambda d: (d.path, d.line, d.message))
    return diagnostics, len(markdown_files), len(python_files), link_count, docs_path_count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Repository root to scan (defaults to this script's repository).",
    )
    args = parser.parse_args(argv)
    root = (args.root or Path(__file__).resolve().parent.parent).resolve()

    diagnostics, md_count, py_count, link_count, docs_path_count = run(root)

    if diagnostics:
        for diagnostic in diagnostics:
            print(diagnostic)
        print(f"FAIL: {len(diagnostics)} broken reference(s)", file=sys.stderr)
        return 1

    print(
        f"OK: {md_count} markdown file(s), {py_count} python file(s) scanned; "
        f"{link_count} link(s), {docs_path_count} docs-path mention(s) checked"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Fixture tests for scripts/validate_docs.py."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import validate_docs  # noqa: E402


def write(root: Path, relative: str, content: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


class TempRootTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def run_validate(self) -> tuple[list[validate_docs.Diagnostic], int]:
        diagnostics, *_ = validate_docs.run(self.root)
        exit_code = validate_docs.main(["--root", str(self.root)])
        return diagnostics, exit_code


class ValidTreePasses(TempRootTestCase):
    def test_valid_tree_produces_no_diagnostics(self) -> None:
        write(
            self.root,
            "AGENTS.md",
            "# Agents\n\n"
            "See [`docs/guide.md`](docs/guide.md) and its "
            "[Second Heading](docs/guide.md#second-heading).\n"
            "External: [site](https://example.com).\n"
            "Same page: [top](#agents).\n",
        )
        write(
            self.root,
            "docs/guide.md",
            "# Guide\n\n"
            "## Second Heading\n\n"
            "## Shared types (`src/types/index.ts`)\n\n"
            "```markdown\n"
            "[broken](docs/does-not-exist.md)\n"
            "```\n"
            "See `docs/guide.md` and `../docs/guide.md` from a nested page.\n"
            "Link with unrelated label: [`docs/nope.md`](guide.md).\n",
        )
        write(
            self.root,
            "docs/nested/other.md",
            "# Other\n\nBack to [guide](../guide.md) and `docs/guide.md`.\n",
        )
        write(
            self.root,
            "backend/logging_config.py",
            '"""Module docstring referencing `docs/guide.md` for details."""\n\n'
            "# See docs/guide.md for the routing rules.\n"
            "X = 1\n",
        )

        diagnostics, exit_code = self.run_validate()
        self.assertEqual(diagnostics, [])
        self.assertEqual(exit_code, 0)


class DuplicateHeadingsDedup(TempRootTestCase):
    def test_second_duplicate_heading_gets_dash_one_suffix(self) -> None:
        write(
            self.root,
            "docs/guide.md",
            "# Guide\n\n## Setup\n\nSome text.\n\n## Setup\n\nMore text.\n",
        )
        write(
            self.root,
            "AGENTS.md",
            "[first](docs/guide.md#setup) and [second](docs/guide.md#setup-1).\n",
        )
        diagnostics, exit_code = self.run_validate()
        self.assertEqual(diagnostics, [])
        self.assertEqual(exit_code, 0)


class MissingFileLink(TempRootTestCase):
    def test_broken_relative_link_reported(self) -> None:
        write(self.root, "AGENTS.md", "See [missing](docs/missing.md) for details.\n")
        write(self.root, "docs/guide.md", "# Guide\n")

        diagnostics, exit_code = self.run_validate()
        self.assertEqual(exit_code, 1)
        self.assertEqual(len(diagnostics), 1)
        diag = diagnostics[0]
        self.assertEqual(diag.path, "AGENTS.md")
        self.assertEqual(diag.line, 1)
        self.assertIn("missing file: docs/missing.md", diag.message)


class MissingFragment(TempRootTestCase):
    def test_broken_fragment_reported_separately_from_missing_file(self) -> None:
        write(self.root, "docs/guide.md", "# Guide\n\n## Real Heading\n")
        write(
            self.root,
            "AGENTS.md",
            "See [broken](docs/guide.md#does-not-exist).\n",
        )
        diagnostics, exit_code = self.run_validate()
        self.assertEqual(exit_code, 1)
        self.assertEqual(len(diagnostics), 1)
        self.assertIn("missing heading: docs/guide.md#does-not-exist", diagnostics[0].message)


class ReferenceStyleLinkUnsupported(TempRootTestCase):
    def test_reference_style_link_flagged_as_unsupported(self) -> None:
        write(self.root, "AGENTS.md", "See [the guide][guide-ref] for details.\n")
        diagnostics, exit_code = self.run_validate()
        self.assertEqual(exit_code, 1)
        self.assertEqual(len(diagnostics), 1)
        self.assertIn("unsupported link form", diagnostics[0].message)


class FencedCodeIsIgnored(TempRootTestCase):
    def test_link_shaped_text_in_fenced_code_block_is_skipped(self) -> None:
        write(
            self.root,
            "AGENTS.md",
            "```markdown\n[broken](docs/does-not-exist.md)\n```\n",
        )
        diagnostics, exit_code = self.run_validate()
        self.assertEqual(diagnostics, [])
        self.assertEqual(exit_code, 0)


class BrokenDocsPathInMarkdownCodeSpan(TempRootTestCase):
    def test_broken_root_relative_path_in_code_span_reported(self) -> None:
        write(self.root, "backend/README.md", "See `docs/does-not-exist.md` for details.\n")
        write(self.root, "docs/guide.md", "# Guide\n")
        diagnostics, exit_code = self.run_validate()
        self.assertEqual(exit_code, 1)
        self.assertEqual(len(diagnostics), 1)
        self.assertEqual(diagnostics[0].path, "backend/README.md")
        self.assertIn("missing path: docs/does-not-exist.md", diagnostics[0].message)

    def test_broken_source_relative_path_in_code_span_reported(self) -> None:
        write(
            self.root,
            "backend/README.md",
            "See `../docs/does-not-exist.md` for details.\n",
        )
        write(self.root, "docs/guide.md", "# Guide\n")
        diagnostics, exit_code = self.run_validate()
        self.assertEqual(exit_code, 1)
        self.assertIn("missing path: ../docs/does-not-exist.md", diagnostics[0].message)


class BrokenDocsPathInPython(TempRootTestCase):
    def test_broken_path_in_comment_reported(self) -> None:
        write(
            self.root,
            "backend/youtube/auth.py",
            "# See docs/does-not-exist.md for the scope list.\nX = 1\n",
        )
        write(self.root, "docs/guide.md", "# Guide\n")
        diagnostics, exit_code = self.run_validate()
        self.assertEqual(exit_code, 1)
        self.assertEqual(diagnostics[0].path, "backend/youtube/auth.py")
        self.assertEqual(diagnostics[0].line, 1)
        self.assertIn("missing path: docs/does-not-exist.md", diagnostics[0].message)

    def test_broken_path_in_docstring_reported(self) -> None:
        write(
            self.root,
            "backend/logging_config.py",
            '"""Module docstring.\n\nSee docs/does-not-exist.md for routing rules.\n"""\n\nX = 1\n',
        )
        write(self.root, "docs/guide.md", "# Guide\n")
        diagnostics, exit_code = self.run_validate()
        self.assertEqual(exit_code, 1)
        self.assertEqual(diagnostics[0].path, "backend/logging_config.py")
        self.assertEqual(diagnostics[0].line, 3)
        self.assertIn("missing path: docs/does-not-exist.md", diagnostics[0].message)

    def test_ordinary_string_literal_is_not_checked(self) -> None:
        write(
            self.root,
            "backend/module.py",
            'X = "docs/does-not-exist.md"\n',
        )
        diagnostics, exit_code = self.run_validate()
        self.assertEqual(diagnostics, [])
        self.assertEqual(exit_code, 0)


class VenvAndDataDirsPruned(TempRootTestCase):
    def test_files_under_venv_and_data_are_not_scanned(self) -> None:
        write(
            self.root,
            "backend/.venv/lib/broken.py",
            "# docs/does-not-exist.md\n",
        )
        write(
            self.root,
            "backend/data/generated.py",
            "# docs/does-not-exist.md\n",
        )
        diagnostics, exit_code = self.run_validate()
        self.assertEqual(diagnostics, [])
        self.assertEqual(exit_code, 0)


class LinkLabelNotRecheckedAsPath(TempRootTestCase):
    def test_valid_link_with_unrelated_backtick_label_produces_no_diagnostic(self) -> None:
        write(self.root, "docs/target.md", "# Target\n")
        write(
            self.root,
            "AGENTS.md",
            "See [`docs/does-not-exist.md`](docs/target.md) for details.\n",
        )
        diagnostics, exit_code = self.run_validate()
        self.assertEqual(diagnostics, [])
        self.assertEqual(exit_code, 0)


class AngleBracketTargetWithSpace(TempRootTestCase):
    def test_angle_bracket_target_containing_space_is_resolved(self) -> None:
        write(self.root, "docs/a b.md", "# A B\n")
        write(self.root, "AGENTS.md", "See [guide](<docs/a b.md>) for details.\n")
        diagnostics, exit_code = self.run_validate()
        self.assertEqual(diagnostics, [])
        self.assertEqual(exit_code, 0)

    def test_angle_bracket_target_containing_space_reports_when_missing(self) -> None:
        write(self.root, "AGENTS.md", "See [guide](<docs/missing name.md>) for details.\n")
        diagnostics, exit_code = self.run_validate()
        self.assertEqual(exit_code, 1)
        self.assertIn("missing file: docs/missing name.md", diagnostics[0].message)


class BalancedParensInTarget(TempRootTestCase):
    def test_target_with_balanced_parens_resolves_when_present(self) -> None:
        write(self.root, "docs/a(b).md", "# A B\n")
        write(self.root, "AGENTS.md", "See [guide](docs/a(b).md) for details.\n")
        diagnostics, exit_code = self.run_validate()
        self.assertEqual(diagnostics, [])
        self.assertEqual(exit_code, 0)

    def test_target_with_balanced_parens_reports_when_missing(self) -> None:
        write(self.root, "AGENTS.md", "See [guide](docs/a(b).md) for details.\n")
        diagnostics, exit_code = self.run_validate()
        self.assertEqual(exit_code, 1)
        self.assertEqual(len(diagnostics), 1)
        self.assertIn("missing file: docs/a(b).md", diagnostics[0].message)


class ReferenceStyleImageUnsupported(TempRootTestCase):
    def test_reference_style_image_flagged_as_unsupported(self) -> None:
        write(self.root, "AGENTS.md", "![diagram][missing-ref]\n")
        diagnostics, exit_code = self.run_validate()
        self.assertEqual(exit_code, 1)
        self.assertEqual(len(diagnostics), 1)
        self.assertIn("unsupported link form", diagnostics[0].message)


class LinkShapedTextInInlineCodeIsIgnored(TempRootTestCase):
    def test_link_shaped_inline_code_example_is_not_checked_as_a_link(self) -> None:
        write(
            self.root,
            "AGENTS.md",
            "Use `[example](docs/missing.md)` syntax to link a page.\n",
        )
        diagnostics, exit_code = self.run_validate()
        self.assertEqual(diagnostics, [])
        self.assertEqual(exit_code, 0)


class HeadingContainingLinkResolvesToVisibleText(TempRootTestCase):
    def test_heading_with_link_syntax_produces_anchor_from_label(self) -> None:
        write(
            self.root,
            "docs/guide.md",
            "# Guide\n\n## [Intro](other.md)\n",
        )
        write(self.root, "docs/other.md", "# Other\n")
        write(self.root, "AGENTS.md", "See [intro](docs/guide.md#intro).\n")
        diagnostics, exit_code = self.run_validate()
        self.assertEqual(diagnostics, [])
        self.assertEqual(exit_code, 0)


class HeadingLinkTargetWithBalancedParens(TempRootTestCase):
    def test_heading_link_with_parens_in_target_still_anchors_to_label(self) -> None:
        write(
            self.root,
            "docs/guide.md",
            "# Guide\n\n## [Intro](a(b).md)\n",
        )
        write(self.root, "docs/a(b).md", "# A B\n")
        write(self.root, "AGENTS.md", "See [intro](docs/guide.md#intro).\n")
        diagnostics, exit_code = self.run_validate()
        self.assertEqual(diagnostics, [])
        self.assertEqual(exit_code, 0)


class DeterministicSortedOutput(TempRootTestCase):
    def test_diagnostics_are_sorted_by_path_then_line(self) -> None:
        write(
            self.root,
            "README.md",
            "[missing](docs/missing-b.md)\n",
        )
        write(
            self.root,
            "AGENTS.md",
            "line one\n[missing](docs/missing-a.md)\n",
        )
        diagnostics, exit_code = self.run_validate()
        self.assertEqual(exit_code, 1)
        paths = [d.path for d in diagnostics]
        self.assertEqual(paths, sorted(paths))
        self.assertEqual(diagnostics[0].path, "AGENTS.md")
        self.assertEqual(diagnostics[0].line, 2)


if __name__ == "__main__":
    unittest.main()

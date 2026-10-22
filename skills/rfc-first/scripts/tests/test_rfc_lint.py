"""Regression checks for observable RFC lint decisions (stdlib only)."""
import contextlib
import importlib.util
import io
import os
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / 'rfc_lint.py'
spec = importlib.util.spec_from_file_location('rfc_lint', MODULE)
linter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(linter)

ENGLISH = (
    '# Agreed fix\n\n'
    'Decision: approved within the task.\n'
    'Implementation and verification: checked locally.\n'
    'Source of requirements: an explicit instruction from the user.\n\n'
    '## Goal and contract\nFix a known boundary.\n\n'
    '## Verified facts\n'
    '| Fact | Proof | Date |\n|---|---|---|\n'
    '| Boundary confirmed | test:12 | 2026-10-22 |\n\n')
NO_SOURCE_LINE = 'Source of requirements: an explicit instruction from the user.\n'


class LintTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='rfc-first-lint-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def doc(self, extra='', body=None):
        p = self.root / 'RFC.md'
        p.write_text(body if body is not None else ENGLISH + extra, encoding='utf-8')
        return p

    def test_short_completed_record_needs_no_future_step_or_fixed_sections(self):
        self.assertEqual(linter.lint(self.doc()), ([], []))

    def test_headings_inside_fenced_code_are_not_sections(self):
        p = self.doc(body='# Example\n\n```md\n## Goal\n## Facts\n```\n')
        errors, _ = linter.lint(p)
        self.assertEqual(len([e for e in errors if 'missing section' in e]), 2)

    def test_tilde_fence_and_longer_closer_hide_links(self):
        p = self.doc('~~~md\n[spec](spec/ABSENT.md)\n~~~~\n')
        self.assertEqual(linter.lint(p), ([], []))

    def test_unclosed_fence_does_not_leak_fake_headings(self):
        p = self.doc(body='# Example\n\n````md\n```\n## Goal\n## Facts\n')
        errors, _ = linter.lint(p)
        self.assertEqual(len([e for e in errors if 'missing section' in e]), 2)

    def test_inline_example_path_is_not_a_spec_link(self):
        p = self.doc('Example name: `spec/EXAMPLE.md`.\nMarkdown example: `[text](spec/FAKE.md)`.\n')
        self.assertEqual(linter.lint(p), ([], []))

    def test_missing_real_markdown_link_is_an_error(self):
        errors, _ = linter.lint(self.doc('[Requirements](spec/MISSING.md)\n'))
        self.assertTrue(any('MISSING.md' in e for e in errors))

    def test_existing_spec_with_fragment_is_valid(self):
        (self.root / 'spec').mkdir()
        (self.root / 'spec/TICKET.md').write_text('# Requirements\n')
        self.assertEqual(linter.lint(self.doc('[Spec](spec/TICKET.md#item)\n')), ([], []))

    def test_explicit_source_field_with_backticked_missing_path_is_an_error(self):
        errors, _ = linter.lint(self.doc('Spec: `spec/MISSING.md`.\n'))
        self.assertTrue(any('MISSING.md' in e for e in errors))

    def test_reference_style_link_is_checked(self):
        errors, _ = linter.lint(self.doc('[Spec][req]\n\n[req]: spec/MISSING.md\n'))
        self.assertTrue(any('MISSING.md' in e for e in errors))

    def test_project_relative_source_field_in_docs_rfc_uses_project_root(self):
        folder = self.root / 'docs/rfc'
        (folder / 'spec').mkdir(parents=True)
        (folder / 'spec/TICKET.md').write_text('# Requirements\n')
        p = folder / 'RFC.md'
        p.write_text(ENGLISH + 'Spec: `docs/rfc/spec/TICKET.md`.\n')
        self.assertEqual(linter.lint(p), ([], []))

    def no_source_doc(self, folder, extra):
        p = folder / 'RFC.md'
        p.write_text(ENGLISH.replace(NO_SOURCE_LINE, extra))
        return p

    def test_source_field_in_the_middle_of_a_line_is_found(self):
        folder = self.root / 'docs/rfc'
        (folder / 'spec').mkdir(parents=True)
        (folder / 'spec/TICKET.md').write_text('# Requirements\n')
        p = self.no_source_doc(folder, 'Status: implemented. Spec: `docs/rfc/spec/TICKET.md`.\n')
        self.assertEqual(linter.lint(p), ([], []))

    def test_missing_file_in_mid_line_source_field_is_an_error(self):
        p = self.no_source_doc(self.root, 'Status: draft. Requirements verbatim: `spec/MISSING.md`.\n')
        errors, _ = linter.lint(p)
        self.assertTrue(any('MISSING.md' in e for e in errors))

    def test_mid_line_code_without_source_keyword_is_not_a_spec_link(self):
        p = self.no_source_doc(self.root, 'Status: see the example `spec/MISSING.md`.\n')
        errors, warns = linter.lint(p)
        self.assertEqual(errors, [])
        self.assertTrue(any('verbatim spec' in w for w in warns))

    def test_rfc_folder_at_repository_root_resolves_source_field(self):
        folder = self.root / 'rfc'
        (folder / 'spec').mkdir(parents=True)
        (folder / 'spec/TICKET.md').write_text('# Requirements\n')
        p = self.no_source_doc(folder, 'Status: draft. Spec: `rfc/spec/TICKET.md`.\n')
        self.assertEqual(linter.lint(p), ([], []))

    def test_relative_cli_path_still_resolves_project_source_field(self):
        folder = self.root / 'docs/rfc'
        (folder / 'spec').mkdir(parents=True)
        (folder / 'spec/TICKET.md').write_text('# Requirements\n')
        p = self.no_source_doc(folder, 'Status: done. Spec: `docs/rfc/spec/TICKET.md`.\n')
        cwd = os.getcwd()
        os.chdir(folder)
        self.addCleanup(os.chdir, cwd)
        self.assertEqual(linter.lint(p.name), ([], []))

    def test_markdown_link_is_still_relative_to_document_not_project(self):
        folder = self.root / 'docs/rfc'
        (folder / 'spec').mkdir(parents=True)
        (folder / 'spec/TICKET.md').write_text('# Requirements\n')
        p = folder / 'RFC.md'
        p.write_text(ENGLISH + '[Spec](docs/rfc/spec/TICKET.md)\n')
        errors, _ = linter.lint(p)
        self.assertTrue(any('docs/rfc/spec/TICKET.md' in e for e in errors))

    def test_web_spec_link_is_not_treated_as_a_local_file(self):
        self.assertEqual(linter.lint(self.doc('[Spec](https://example.org/spec/TICKET.md)\n')), ([], []))

    def test_html_comment_and_indented_examples_are_not_sections_or_links(self):
        p = self.doc('<!-- [spec](spec/MISSING.md) -->\n    [example](spec/MISSING.md)\n')
        self.assertEqual(linter.lint(p), ([], []))

    def test_empty_proof_is_found_even_if_date_column_is_filled(self):
        p = self.doc(body=ENGLISH.replace('| test:12 |', '| |'))
        _, warns = linter.lint(p)
        self.assertTrue(any('without proof' in w for w in warns))

    def test_english_hedge_in_facts_is_a_warning(self):
        p = self.doc(body=ENGLISH.replace('| Boundary confirmed |', '| Boundary is probably confirmed |'))
        _, warns = linter.lint(p)
        self.assertTrue(any('hypothesis' in w for w in warns))

    def test_nested_detail_is_not_a_second_next_step(self):
        p = self.doc('## Next step\n- Check the contract.\n  - Start with null.\n')
        _, warns = linter.lint(p)
        self.assertFalse(any('several nearest' in w for w in warns))

    def test_two_top_level_next_steps_are_a_warning_not_an_error(self):
        errors, warns = linter.lint(self.doc('## Next step\n- Check A.\n- Check B.\n'))
        self.assertFalse(errors)
        self.assertTrue(any('several nearest' in w for w in warns))

    def test_cli_warn_is_success_error_is_failure_and_missing_file_is_reported(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            p = self.doc(body='# Example\n\n## Goal\nFix.\n## Facts\nObservation.\n')
            self.assertEqual(linter.main(['lint', str(p)]), 0)
            p.write_text('# Empty RFC\n')
            self.assertEqual(linter.main(['lint', str(p)]), 1)
            self.assertEqual(linter.main(['lint', str(self.root / 'missing.md')]), 1)
        self.assertIn('cannot check the file', output.getvalue())


class OutputEncodingTests(unittest.TestCase):
    def test_non_ascii_messages_survive_a_pipe_with_cp1252_locale(self):
        with tempfile.TemporaryDirectory(prefix='rfc-first-enc-') as tmp:
            p = Path(tmp) / 'RFC.md'
            p.write_text('# Fix\n\n## Verified facts\nIt probably works: \u0394t \u2192 \u2264 1 ms.\n', encoding='utf-8')
            env = dict(os.environ, PYTHONIOENCODING='cp1252')
            result = subprocess.run([sys.executable, str(MODULE), str(p)], env=env,
                                    capture_output=True, check=False)
        self.assertEqual(result.returncode, 1, result.stderr.decode('utf-8', 'replace'))
        self.assertNotIn(b'UnicodeEncodeError', result.stderr)
        self.assertIn('\u0394t \u2192 \u2264 1 ms', result.stdout.decode('utf-8'))


if __name__ == '__main__':
    unittest.main()

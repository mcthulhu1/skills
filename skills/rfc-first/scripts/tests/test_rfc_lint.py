"""Regression checks for observable RFC lint decisions (stdlib only)."""
import contextlib
import importlib.util
import io
import json
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


# Team words in other languages, escaped to keep the sources ASCII.
RU = {
    'goal': '\u0426\u0435\u043b\u044c \u0438 \u043a\u043e\u043d\u0442\u0440\u0430\u043a\u0442',
    'facts': '\u041f\u0440\u043e\u0432\u0435\u0440\u0435\u043d\u043d\u044b\u0435 \u0444\u0430\u043a\u0442\u044b',
    'next': '\u0421\u043b\u0435\u0434\u0443\u044e\u0449\u0438\u0439 \u0448\u0430\u0433',
    'decision': '\u0420\u0435\u0448\u0435\u043d\u0438\u0435',
    'source': '\u0422\u0440\u0435\u0431\u043e\u0432\u0430\u043d\u0438\u044f',
    'proof': '\u0414\u043e\u043a\u0430\u0437\u0430\u0442\u0435\u043b\u044c\u0441\u0442\u0432\u043e',
    'hedge': '\u0432\u0435\u0440\u043e\u044f\u0442\u043d\u043e',
}
JA = {
    'goal': '\u76ee\u7684',
    'facts': '\u78ba\u8a8d\u6e08\u307f\u306e\u4e8b\u5b9f',
    'status': '\u72b6\u614b',
    'source': '\u8981\u4ef6',
    'proof': '\u8a3c\u62e0',
    'hedge': '\u304a\u305d\u3089\u304f',
}
RU_CONFIG = {
    'sections': {'goal': [RU['goal']], 'facts': [RU['facts'].lower()], 'next_step': [RU['next']]},
    'fields': {'status': [RU['decision']], 'source': [RU['source']]},
    'proof_column': [RU['proof']],
    'hedges': [RU['hedge']],
}
RU_DOC = (
    '# X-1\n\n'
    f'{RU["decision"]}: approved.\n'
    f'{RU["source"]}: [spec](spec/X-1.md).\n\n'
    f'## {RU["goal"]}\nFix.\n\n'
    f'## {RU["facts"]}\n'
    f'| ID | Fact | {RU["proof"]} |\n|---|---|---|\n'
    '| F1 | Boundary | test:12 |\n')


class TeamWordsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='rfc-first-words-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'spec').mkdir()
        (self.root / 'spec' / 'X-1.md').write_text('# X-1\n', encoding='utf-8')

    def doc(self, body, config=None):
        if config is not None:
            text = config if isinstance(config, str) else json.dumps(config, ensure_ascii=False)
            (self.root / linter.CONFIG_NAME).write_text(text, encoding='utf-8')
        p = self.root / 'X-1.md'
        p.write_text(body, encoding='utf-8')
        return p

    def test_native_headings_without_config_are_an_error_with_a_hint(self):
        errors, _ = linter.lint(self.doc(RU_DOC))
        self.assertEqual(len([e for e in errors if 'missing section' in e]), 2)
        self.assertIn(linter.CONFIG_NAME, errors[0])

    def test_native_headings_fields_and_proof_column_pass_with_config_next_to_rfc(self):
        self.assertEqual(linter.lint(self.doc(RU_DOC, RU_CONFIG)), ([], []))

    def test_english_headings_still_pass_with_config(self):
        self.assertEqual(linter.lint(self.doc(ENGLISH, RU_CONFIG)), ([], []))

    def test_native_empty_proof_hedge_and_two_next_steps_are_warnings(self):
        body = RU_DOC + f'| F2 | {RU["hedge"]} ok |  |\n\n## {RU["next"]}\n- a\n- b\n'
        _, warns = linter.lint(self.doc(body, RU_CONFIG))
        self.assertTrue(any('row without proof' in w for w in warns), warns)
        self.assertTrue(any('hypothesis' in w for w in warns), warns)
        self.assertTrue(any('several nearest' in w for w in warns), warns)

    def test_cjk_words_and_full_width_colon_without_spaces(self):
        config = {'sections': {'goal': [JA['goal']], 'facts': [JA['facts']]},
                  'fields': {'status': [JA['status']], 'source': [JA['source']]},
                  'proof_column': [JA['proof']], 'hedges': [JA['hedge']]}
        body = (f'# X-1\n\n{JA["status"]}\uff1aok\n{JA["source"]}\uff1a`spec/ABSENT.md`\n\n'
                f'## {JA["goal"]}\nx\n\n## {JA["facts"]}\n'
                f'| ID | {JA["proof"]} |\n|---|---|\n| F1 |  |\n'
                f'\u3053\u308c\u306f{JA["hedge"]}\u6b63\u3057\u3044\n')
        errors, warns = linter.lint(self.doc(body, config))
        self.assertEqual(errors, ['the spec link points to a missing file: spec/ABSENT.md'])
        self.assertEqual(len(warns), 2, warns)  # empty proof, hedge inside a sentence with no spaces

    def test_bad_config_is_an_error_naming_the_file_and_key(self):
        cases = [('{"section": {}}', "unknown key 'section'"),
                 ('{"sections": {"goals": ["x"]}}', "sections.'goals'"),
                 ('{"hedges": "x"}', 'hedges must be a non-empty list'),
                 ('{"hedges": [""]}', 'hedges must be a non-empty list'),
                 ('{"hedges": [', 'bad config')]
        for text, expected in cases:
            with self.subTest(text=text):
                errors, warns = linter.lint(self.doc(RU_DOC, text))
                self.assertEqual(len(errors), 1, errors)
                self.assertIn(linter.CONFIG_NAME, errors[0])
                self.assertIn(expected, errors[0])

    def test_cli_config_flag_applies_a_config_from_elsewhere(self):
        other = self.root / 'elsewhere'
        other.mkdir()
        config = other / 'words.json'
        config.write_text(json.dumps(RU_CONFIG), encoding='utf-8')
        p = self.doc(RU_DOC)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(linter.main(['lint', str(p)]), 1)
            self.assertEqual(linter.main(['lint', '--config', str(config), str(p)]), 0)
            self.assertEqual(linter.main(['lint', str(p), '--config']), 2)
        self.assertIn(f'OK {p}', output.getvalue())


class OutputEncodingTests(unittest.TestCase):
    def test_non_ascii_messages_survive_a_pipe_with_cp1252_locale(self):
        with tempfile.TemporaryDirectory(prefix='rfc-first-enc-') as tmp:
            p = Path(tmp) / 'RFC.md'
            p.write_text('# Fix\n\n## Verified facts\nIt probably works: \u0394t \u2192 \u2264 1 ms.\n', encoding='utf-8')
            # Only what the child interpreter needs (SYSTEMROOT on Windows), not the whole environment.
            env = {k: os.environ[k] for k in ('PATH', 'SYSTEMROOT') if k in os.environ}
            env['PYTHONIOENCODING'] = 'cp1252'
            result = subprocess.run([sys.executable, str(MODULE), str(p)], env=env,
                                    capture_output=True, check=False)
        self.assertEqual(result.returncode, 1, result.stderr.decode('utf-8', 'replace'))
        self.assertNotIn(b'UnicodeEncodeError', result.stderr)
        self.assertIn('\u0394t \u2192 \u2264 1 ms', result.stdout.decode('utf-8'))


if __name__ == '__main__':
    unittest.main()

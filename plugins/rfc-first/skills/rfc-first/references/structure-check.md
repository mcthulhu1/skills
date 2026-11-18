# RFC structure check

Run this check on every RFC you create or edit (modes new, update, implement) and at the start of the validate mode. It checks form only: it does not check what the proof means, authority or approval.

## Words to match

Match headings and fields case-insensitively. A heading or field matches when it contains one of the English words below, or one of the team's words from `rfc-lint.json` in the RFC storage ([format](rfc-lint-config.md)). The team's words are added to the English ones and match as plain substrings.

| Key | English words |
|---|---|
| `goal` | goal, scope, summary, problem, context, requirement, contract |
| `facts` | fact, proof, evidence, current behavior (behaviour), how … works, diagnos(is/tics) |
| `next_step` | next step |
| `status` | Status, Decision, Implementation and verification |
| `source` | Source, Source of requirements, Requirements, Requirements verbatim, Verbatim requirements, Spec, Specification |
| `proof_column` | Proof, Evidence, Source, Verified by |
| `hedges` | probably, apparently, presumably, most likely, seems to, it seems |

Fields end with `:` or the full-width colon (U+FF1A). Ignore everything inside code blocks (fenced or indented) and HTML comments. Headings are Markdown `#` headings.

## Must fix (FAIL)

1. The first non-empty line is a level-1 heading: `# <ID/topic>`.
2. There is a level-2 or deeper heading matching `goal`, and one matching `facts`.
3. Every link to a verbatim spec points to an existing file. A spec link is a relative path to `spec/<name>.md`: a Markdown link, a reference-style link, or a backticked path after a `source` field (`` Spec: `spec/INV-42.md` ``). Resolve the path from the RFC's directory. In a `source` field, a path starting with `docs/rfc/spec/` or `rfc/spec/` may be relative to the project root instead.
4. If `rfc-lint.json` exists, it is valid by [its format](rfc-lint-config.md): the top level has only `sections`, `fields`, `proof_column` and `hedges`; `sections` is an object with only `goal`, `facts`, `next_step`, and `fields` an object with only `status`, `source`; every other value (`proof_column`, `hedges` and each key inside `sections` and `fields`) is a non-empty list of non-empty strings.

## Review (WARN)

A WARN that is a real defect is fixed where you may edit the RFC (see Result) and reported otherwise. Leave a false positive as it is, and do not add sections only to silence a WARN.

5. The first 15 lines contain a line that starts with a `status` field: a short decision or implementation status.
6. There is a `source` field or a spec link. It is required when the task has written requirements.
7. The facts section is not empty.
8. In a facts table with a `proof_column` column, every row has a non-empty proof cell.
9. A line in the facts section contains a `hedges` word: check that a hypothesis is not presented as a fact.
10. The next-step section lists more than one top-level item: name the first dependent step.

## Result

Report the result for each RFC as `<OK|WARN|FAIL> <path>`, followed by each finding with its rule number. What you do with the findings depends on the mode:

- new, update, implement, or validate with a request to fix: fix every must-fix finding before showing the RFC to the user, then re-run the check.
- validate without a request to edit: do not change the RFC; give each finding with the fix it needs.

# RFC validation

The validate mode checks an existing RFC. Start with the linter: `python3 <skill_dir>/scripts/rfc_lint.py <rfc.md>` (on Windows `py -3` or `python`); every ERROR is a finding, include a WARN when it is a real defect. Without a request to edit, do not change the document or the code. A finding: place in the RFC → scenario and consequences → evidence → the required fix. Keep out-of-scope remarks apart from defects of the decision. Check key claims independently; do not retell someone else's review.

## Requirements and decisions

- The requirements are saved verbatim in `spec/<ID>.md` (not as a link), with source and date, and the RFC links to that file instead of restating the requirements.
- Every material scope item is linked to a change and to acceptance. A paraphrase does not replace the source; old code/data/tests do not override a requirement.
- No undeclared widening of scope and no hidden deviation from a requirement. A real downstream effect that was found is described, even if that consumer does not change.
- A material interpretation stays a proposal until an explicit decision. Silence, a reviewer's conclusion or an answer to one question are not approval of the whole RFC.
- Closed questions are linked to specific decisions and are no longer listed as blockers. The source, date/author of a decision are given as far as known; nothing unknown is invented.

## Evidence

- Open the sources the decision depends on: file/method, call path, consumer, tree state or environment. There is no quota of links and no need to walk the whole repository.
- The commit the code was read at is given, and its freshness against the remote is checked with `git ls-remote` (or the remote UI/API). A local `git log`/`show` does not prove the remote; if they disagree, the status is unconfirmed.
- Units, boundaries, rounding, null/missing/empty list and the material branches of a flag match the requirement.
- Disputed behavior is checked on the relevant version and configuration. A declared dependency is not presented as resolved/runtime, a unit test with mocks is not presented as database behavior.
- Refuted hypotheses are withdrawn together with dependent risks and blockers. Do not create a question for the owner about a fact that an allowed check can settle.

For a disputed premise or a verification status read [evidence-and-review.md](evidence-and-review.md).

## Acceptance and operational consequences

- Acceptance checks the result and the material invariants; when needed there is a negative control that catches the stated defect.
- API change: both sides and mixed versions, including the library/serialization/consumer.
- Migration: locks, data, partial success and re-run; rollout order and rollback are proportionate to the change.
- Schema restore is not called restore of deleted data; the point of no return is marked.

## Currency and proportion

- Decision status is separate from implementation and verification. Local tests do not prove deployment/E2E.
- The summary and the current sections agree; a late note does not leave an old open question or a contradicting formula behind.
- A short fix does not need the full set of sections. A finished record needs no artificial next step.
- The structural linter is a hint about form, not proof of quality and not permission to act.

---
name: rfc-first
description: >-
  Strict RFC-first process: prepare, update, review and validate an RFC, implement an approved RFC and
  report its status. Use when the user asks about an RFC, when working from written requirements (ticket,
  wiki page, BRD), and for any new substantive change the user has not approved yet. Do not start a new
  RFC for review, analysis or diagnostics without changes, a trivial mechanical edit that does not change
  behavior, a direct instruction to make a specific edit without an RFC, or executing an already approved
  plan within its scope; the validate, implement and status modes still apply to an existing RFC.
metadata:
  version: "1.1.1"
  opencode/slash: "true"
---

# RFC-first

Chain: `requirement → verified facts → decision → plan → change → verification`.
This skill does not by itself authorize implementation, messages, Git writes or rollout. Follow the applicable global and project instructions; their prohibitions and any approval already given stay in force.

Write the RFC body in the language the user works in. Take the section headings and header field names from the [RFC template](references/rfc-template.md) in English, unless the RFC storage has `rfc-lint.json`: then use the team's words from it. If the user wants headings in their language and the file is missing, prepare it as described in [rfc-lint-config.md](references/rfc-lint-config.md).

## 1. Pick the mode and the scale

| Request | Mode | Result |
|---|---|---|
| Prepare an RFC / a decision for new requirements | **new** | Research and a concrete proposal; ask only about the remaining material choice |
| Update an RFC after an owner's answer or new facts | **update** | Current facts, decisions and dependent sections within the allowed scope |
| Review / validate an existing RFC | **validate** | Linter result (section 3) and findings from the [review checklist](references/review-checklist.md); no edits to the document or code unless asked |
| Implement an approved RFC | **implement** | Plan, implementation and checks within the already approved scope |
| Check the status of an RFC or its implementation | **status** | The proven level and the specific unverified remainder; no automatic file edits |

A new RFC is needed for every new substantive change the user has not approved yet. No new RFC is needed for: review, analysis and diagnostics without changes; a trivial mechanical edit that does not change behavior; a direct instruction from the user to make a specific edit without an RFC; executing an already approved plan, and fixing a deviation from it within the allowed scope, without a new architectural decision. These cases do not lift project prohibitions or acceptance checks, and an existing RFC is still reviewed, implemented and reported through the validate, implement and status modes. When asked to document a fix, write a short record.

## 2. Find the requirements and the RFC storage

- Read the applicable AGENTS.md / CLAUDE.md and any RFC workflow of the project. Do not carry one project's paths, stack and constraints over to another.
- Look for an existing RFC or spec for the ticket or topic and continue it; do not create a copy per conversation. Memory is an index of paths and decisions, not proof of the current state.
- Find the RFC storage (`<RFC_DIR>`) in this order:
  1. A path the user gave explicitly.
  2. The project instructions: a line such as `RFC storage: <path>` in AGENTS.md / CLAUDE.md, or another explicit RFC path there.
  3. An existing `docs/rfc/` (or `rfc/`) directory in the target repository.
  4. Otherwise `docs/rfc/` at the root of the target repository. Offer once to record `RFC storage: docs/rfc/` in the project's AGENTS.md so the next session finds it.

  Ask only when the target project or storage is materially ambiguous. A storage path never authorizes writing into an unrelated project.
- Name files `<RFC_DIR>/<ID>-<slug>.md`, where `<ID>` is the ticket key or a short topic.
- Before any code, save the requirements text **verbatim** to `<RFC_DIR>/spec/<ID>.md` ([spec template](references/spec-template.md)). The source is a copy-paste from the ticket, wiki page or BRD. A link to the source does not replace the copy: requirements live in the repository, not in the session context or on an external page.
- Store only material you are allowed to copy. If policy, license or confidentiality forbids keeping the text in this repository, do not copy it: tell the user and agree on a permitted form (an approved excerpt, a summary marked as non-verbatim, or another storage location) before dependent work. Never store secrets or customers' personal data.
- If the requirements came as an image, transcribe it into that file before dependent work and keep a link to the original or an accessible copy. Do not rely on the image being available after the context changes.
- The RFC links to the spec file and does not restate the requirements: a paraphrase is not a requirement. Each source item is linked to its implementation and its verification.
- If the requirements text is neither in the context nor in `spec/`, ask the user for it before writing code. Do not reconstruct requirements from legacy code.
- Keep the source text, your interpretation and the current behavior apart. OCR is not a verbatim copy until checked against an accessible original. Mark a new revision as current and the previous one as superseded, keep the date/source and the link between them; never leave two equal versions of a requirement.
- Required behavior is set by the current requirements and explicit owner decisions. Old code, data and tests describe facts but do not authorize changing a requirement. If a material contract is missing, obtain it by an available means first; do not reconstruct it from legacy behavior.

## 3. Verify facts and prepare the RFC

Use the [adaptable RFC template](references/rfc-template.md); do not fill every section for the sake of form. A small decision needs only a short contract, the facts, the change and acceptance. Options are needed when there is a real choice; migration/rollout/rollback when the change calls for it. Do not invent questions or alternatives for a decision that is already given.

- State the goal, the scope and material exclusions. Link requirement items to the change and to a check; for boundaries and formulas show "before → after" on a concrete input.
- Proof ledger: claim → object/state → file:line, or command + cwd + result/artifact → limitation. For code, name the repository and the commit you read; check the freshness of remote refs with `git ls-remote` or the remote UI/API, because local `git show`/`log`/`merge-base` only prove the objects available locally. If refs disagree or the remote is unavailable, call the status unconfirmed. Check versions on the component that matters; a declared dependency is not the resolved or runtime one. Read the [evidence rules](references/evidence-and-review.md) when a premise is disputed or a verification status is needed.
- Before deciding, check the input, the execution path, the callers, the consumers, units, boundaries and the material branches of a flag. Choose the smallest check that tells the options apart; do not widen diagnostics into a full audit on your own.
- Separate an unknown fact that can be checked from an owner's decision. Find the fact yourself by an available, allowed means. Question Q: options, recommendation, consequences, and what it blocks — code, rollout or nothing.
- For an incompatible change, check producer and consumer and mixed versions. For a migration, give the order, observable gates to the next stage and recovery after partial success. Schema rollback is separate from data recovery; mark the point of no return.
- Examples of the right scale and of process mistakes are in [RFC patterns](references/patterns.md); a complete synthetic RFC with its spec is in [examples/](examples/docs/rfc/INV-42-line-rounding.md). Read them when needed.

**Run the linter after every creation or edit of an RFC** (modes new, update, implement):

```bash
python3 <skill_dir>/scripts/rfc_lint.py <rfc.md>
```

On Windows use `py -3` instead of `python3`, or `python` if that is missing. Python 3.9+, no dependencies.

`<skill_dir>` is the directory this SKILL.md was loaded from. Fix every ERROR (exit 1) before showing the RFC to the user. Review each WARN: fix a real defect, leave a false positive, do not add sections just to silence a WARN. Report the linter result (OK / WARN / FAIL) in your answer. The linter checks form only: it does not check what the proof means, authority or approval.

## 4. Ask for approval of the new choice only

- Gather the available evidence before asking. Show the RFC path and its material revision, your recommendation and the specific open decision. If everything needed is already approved, continue the allowed work.
- Interpretation I is a proposal with its basis and impact. A material choice without an explicit decision is not accepted by silence or by the absence of objections. A reviewer's conclusion does not replace the owner's decision.
- Decision D: the exact known answer, its scope, date/author/channel as far as known, and the source. Do not invent metadata; keep a verbatim answer apart from a paraphrase. An answer to Q1 is not approval of the whole RFC; an explicit decision may override an earlier one.
- Close a Q where it is stated, with a link to its D. While waiting for an answer, stop only the dependent changes; continue reading, diagnostics and independent allowed steps.
- After approval do not ask again for every file, class or list item. When scope, contract, risk or budget changes materially, get approval for the part that changed.

## 5. Implement and keep the state current

- Run the linter after every edit of the RFC (checklist, status, findings) — see section 3.
- Before editing, check for existing changes; use Git within the standing policy. A plan does not authorize branches, commit/push or external actions.
- Keep the trace: `requirement item | not started / implemented / verified / diverges | file/test | evidence`. Fix a deviation from a clear requirement within the allowed scope; nearby findings do not widen the scope.
- Run the affected checks and record the command, cwd, test set and actual result. An empty or skipped-only run, a fresh report or exit 0 do not by themselves prove the required behavior. Put large logs into artifacts and link them.
- When a fact is refuted, withdraw it together with the dependent risks, blockers, plan and conclusions. Update the top and the current sections of the RFC, not only a note at the end. Do not erase the material history of decisions and do not leave contradicting conclusions.
- Approval, implementation and verification are different statuses. Also tell apart code, target branch, artifact, deployed version/config and observed runtime/E2E behavior. Check only the levels the task needs. Reuse evidence while the relevant inputs and conditions have not changed.
- Say what was not verified and why. A missing response record is not a successful E2E. Do not call the whole RFC done because one stage is ready.

In your answer give the RFC link, the result of the stage and the nearest open question or check if work remains. Do not invent a next step for finished work. Update memory with a link only within the allowed memory rules.

## Integration

The skill works without MCP servers or paid APIs and needs no delegation or hooks. Installation and invocation in Claude Code, Codex, OpenCode and other agents: https://github.com/mcthulhu1/skills#readme.

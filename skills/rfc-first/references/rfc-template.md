# <ID, if any> — <the specific change>

<!-- Adapt the structure to the task. Delete hints and sections you do not need. A short fix needs only the contract, facts, change and acceptance. Write the body in the user's language; keep headings and header field names in English. -->

Date/revision: <date and material revision>.
Decision: <proposed / approved — which scope and source / superseded>.
Implementation and verification: <what is done, what is verified, limitations>.
Requirements verbatim: [`spec/<ID>.md`](spec/<ID>.md). The RFC does not restate the requirements.
Affected: <repositories/components>; out of scope: <material exclusions>.

## Goal and contract

<The result for the user. How it works now, with proof; how it must work, with a link to the current requirement item. For a material boundary give the input and the result before/after. A paraphrase does not replace the source requirement.>

## Verified facts

Code read at: `<repo>` `<commit>` (= remote per `git ls-remote`, <date>); environment and date of observation.

| ID | Fact and where it applies | Proof | Limitation |
|---|---|---|---|
| F1 | <claim> | <file:line, or command + cwd + result/artifact> | <what this does not prove, if material> |

## Decision and changes

<Changed contracts, files/methods, schema and config. Real alternatives, a recommendation and the switching condition — if the choice is open. Do not add options for a decision that is already given.>

## Interpretations and questions

<I1: a proposal where the requirement is ambiguous; its basis, impact and whether a decision is needed. Silence does not make a material interpretation accepted.>

| ID | Question, options and recommendation | What it blocks | Status/decision |
|---|---|---|---|
| Q1 | <a new choice that cannot be settled by a check> | <code / rollout / nothing> | <open / closed by D1> |

## Owner decisions

| ID | Known explicit decision and its scope | Source, date, author/channel |
|---|---|---|
| D1 | <the exact answer, which questions it closes and what it replaces; keep interpretation apart> | <do not invent unknown details> |

<Do not add questions, interpretations or decisions for the sake of form. If a decision is superseded, show the current one and link it to the previous one.>

## Acceptance and implementation plan

| Requirement item | Change/stage | Check and expected result | Status and proof |
|---|---|---|---|
| <item/link> | <action, object, file/method and tool> | <observable behavior; boundaries and a negative control when needed> | <not started / implemented / verified / diverges> |

## Compatibility, rollout and rollback

<For changes that need it: producer/consumer and mixed versions, order, flags, go/stop signals, recovery after interruption and re-run. Schema reversibility separately from data, point of no return. Remove the section if there is no such change.>

## Risks and limitations

<A concrete scenario, consequences, evidence and mitigation. Do not turn an old out-of-scope problem into a blocker without a causal link.>

## Withdrawn / superseded

<Only material withdrawn conclusions/decisions: what refuted or replaced them and which dependent sections were updated. Keep the current truth in the current sections.>

## Current state

<The confirmed levels that matter: decision, code, checks, branch, artifact, deployment, behavior. Which levels are not verified and why. Large logs/reviews as links.>

<The nearest actionable step/question if work remains. A finished task needs no new step.>

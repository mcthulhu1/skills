# RFC patterns

Read this to choose the scale of an RFC and its checks. These are lessons from real RFCs, described without their sources.

## Short fix: a rounding formula

A value was rounded as a fraction instead of as a percentage, and the result fed a threshold, buckets and a database column. The useful RFC was short: input → old formula → new formula → expected values at the boundary → affected consumers.

Apply: do not invent options when the formula is already given unambiguously. A historical sample does not prove a universal upper bound of the error. When a later clarification changes the scale, update both the summary and the change section; otherwise the top and the body describe different states.

## Verifying a premise and recovery: a concurrent database operation

A non-blocking database operation was checked with two sessions, cancellation midway, the pending state it leaves behind and a re-run. The first recommendation was withdrawn explicitly: forbidding the next step after an error broke recovery after partial success.

Apply: test the normal path, interruption, re-run and a leftover object from another iteration. Before writing "safe", check recovery, not only the happy path. Evidence from a local environment is not proof under production load.

## Consequences and removing a false blocker: a local threshold

Changing a local threshold affected a downstream selection and an independent split. At the same time, a suspected new failure path turned out to be unreachable earlier in the chain; the hypothesis and the blocking data request were withdrawn.

Apply: prove that a scenario is reachable and that it differs from the previous behavior. A real effect found outside the changed method does not widen the scope automatically: describe the consequence and the decision it needs.

## Destructive migration: dropping a table

The rollout order was tied to removing readers/writers and disabling a schedule; code rollback was kept apart from restoring deleted data, and the point of no return was marked. A quarantine period was discussed as an option, not as an accepted decision.

Apply: dependency → change → observable gate to the next stage. When questions close, sync the headers and blockers: a late answer at the end must not leave an active "do not start coding" in the middle.

## A traceability table: one feature across several repositories

One RFC linked several requirement items, decisions D and questions Q, contract changes in several repositories and the release order. A newly accepted decision overrode an earlier one from another ticket.

Apply: source item → contract → repository → check; Q → a specific D with its source. Do not copy the formula "accepted unless someone objects": a material interpretation without an explicit decision stays a proposal. Closing a technical question by reading code does not replace approval of a new business rule.

## Partial rollout and false success: a config table

The RFC told apart the contents of a config, code in a branch, the contents of an artifact, declared environment versions and the absence of an E2E check. A generator that replaced the whole table had already lost data once, so the full set had to be compared, not only the new row. A missing response record must not be read as a successful request.

Apply: check the generator semantics (delta or full replacement), preservation of old data and the fact of the observation itself. Date the status; a local config copy does not prove the current deployment.

## A linked producer/consumer contract: an identifier through two writes

One identifier travelled from the generating call to two records via a DTO and the database. Acceptance checked real serialization, compatibility with an old payload and that the test fails when the field is lost. A decision recorded at the top already closed the library choice, while an "Open question" section stayed behind as history.

Apply: check that the value actually passes along the whole chain; reuse an explicit decision instead of asking a closed question again. When updating, move old alternatives to history and close the matching question.

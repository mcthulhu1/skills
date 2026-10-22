# Evidence and RFC review

Read this for disputed premises, reviews or recording implementation results. Check whether the evidence is sufficient for the specific decision; do not run a full system audit on your own.

## How to record a fact

Link a claim to an object, its state and a check:

- Code: repository/file/method, the material revision or tree state, the call path and the consumer. One `rg` without a defined search area does not prove "the only place in the whole system".
- Environment: component, version/config, environment and time of observation. A local copy of a deployment config proves the contents of that copy, not the config applied in production.
- Run: command, cwd, test set/inputs, process outcome and the actual result. Exit 0 with zero tests or skipped-only tests does not prove the required set passed.
- Requirement: the source item and its revision. Keep the source text, the interpretation and an accepted change of the requirement apart. A copy of an old decision does not override a new explicit owner decision.

Keep only the diagnostics you need; remove secrets and real customer data. Do not put raw logs or personal examples into a distributed artifact.

## How to choose a check

A check must tell apart the real options the decision depends on.

- Threshold/formula: the boundary, both sides of it, units, scale and rounding order; follow later comparisons/buckets. A numerical experiment on a sample is an observed estimate, not a proven universal maximum.
- SQL/concurrency: the specific DBMS and transaction mode, two sessions for a disputed lock, cancellation midway and a re-run. A unit test with mocks does not prove locking behavior.
- Contract/DTO: producer → serialization → transport → consumer deserialization; null/missing/empty list; an old producer with a new consumer and the reverse, if both can exist during rollout.
- Destructive migration: all actual readers/writers, schedulers/cleanup jobs, the order of dropping dependencies, schema restore separately from data restore.
- Fallback/selection: an uncovered input, a match on the wrong branch and the absence of an observation. Do not turn a missing response row into a success through a default/COALESCE.

Run the needed local check before asking the owner, if it is allowed. Do not ask for production access when a local probe can tell the hypotheses apart. Do not switch to a live database, change infrastructure or pay for an API just to fill in the RFC.

## How to read a status

Statuses answer different questions:

| Level | Evidence that is sufficient in meaning |
|---|---|
| Decision approved | An explicit decision with a known scope and source |
| Code implemented | Actual changes to the right object; a file existing does not mean acceptance passed |
| Check passed | The result of an applicable run on the material current inputs |
| In the target branch | Confirmed inclusion of the specific change |
| In an artifact | A link between the version/build and the change; a version name alone is not enough |
| Deployed | The observed version and config of the relevant environment |
| Behavior confirmed | A specific request/scenario and the observed expected result in a named environment |

Check the levels the task needs. When inputs relevant to a check change, repeat the affected check or withdraw the earlier status. Do not redo a full verification after an editorial change that does not affect the conclusion.

## Review and keeping the RFC current

Look first for a defect of the decision: a wrong premise, a missed consumer, an incompatibility, an unconfirmed interpretation, unrecoverable data or acceptance that lets the stated defect through. A finding names the place in the RFC, the scenario and consequences, the source and the required fix. Do not list every possible generic risk.

Check another reviewer's conclusion independently. A reviewer's recommendation is not a business decision. If a remark needs a new owner choice, leave the question open; if a remark is refuted, withdraw the dependent risk and the artificial blocker.

In a long RFC update the current sections, not only a note at the end. The history of material decisions can be kept compact: "superseded by D3 of <date>, reason/source". A known contradiction without a current decision must not be hidden under a "done" status.

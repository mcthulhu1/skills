# INV-42 — round invoice lines before summing

<!-- Synthetic example: the project, code and numbers are invented to show a finished RFC. -->

Date/revision: 2026-03-05, revision 3 (after D1 and verification).
Decision: approved by the product owner on 2026-03-03 (D1), scope: new invoices only.
Implementation and verification: implemented and verified by local unit tests; merge, deployment and production behavior not verified.
Requirements verbatim: [`spec/INV-42.md`](spec/INV-42.md). The RFC does not restate the requirements.
Affected: `billing` service, `InvoiceCalculator`, `InvoiceRenderer`; out of scope: PDF layout. Issued invoices must stay unchanged (item 3).

## Goal and contract

Now the total is computed from unrounded line amounts and rounded once (F1), so the printed lines can sum to a different value. Required: items 1–3 of the spec.

| Input (3 lines of 0.335) | Before | After |
|---|---|---|
| Printed lines | 0.34 + 0.34 + 0.34 | 0.34 + 0.34 + 0.34 |
| Total | round(1.005) = 1.01 | 0.34 × 3 = 1.02 |

## Verified facts

Code read at: `billing` `4f2c9a1` (= remote `main` per `git ls-remote`, 2026-03-03).

| ID | Fact and where it applies | Proof | Limitation |
|---|---|---|---|
| F1 | The total is `sum(lines)` of unrounded lines, rounded once to 2 places with HALF_UP | `InvoiceCalculator.java:58` | — |
| F2 | Lines are rounded only when rendered, with HALF_EVEN | `InvoiceRenderer.java:31` | Only the PDF path was read |
| F3 | Issued invoices store the total and are never recomputed | `InvoiceRepository.java:44`, test `IssuedInvoiceTest` | — |
| F4 | Two consumers read the total: PDF and the `invoice.created` event | `rg -n "getTotal" src/` in `billing` at `4f2c9a1`, 2 hits | Consumers outside `billing` were not searched |

## Decision and changes

`InvoiceCalculator.total()` rounds each line with `setScale(2, HALF_UP)` and sums the rounded values; the renderer prints the same rounded line values. No migration: F3 keeps issued invoices unchanged (item 3).

## Interpretations and questions

I1: "half up" means HALF_UP on the absolute value (−2.345 → −2.35), as in the spec notes. Accepted by D1.

| ID | Question, options and recommendation | What it blocks | Status/decision |
|---|---|---|---|
| Q1 | HALF_UP (spec) differs from HALF_EVEN in the renderer (F2). Recommend HALF_UP everywhere so lines and total match | Code | Closed by D1 |

## Owner decisions

| ID | Known explicit decision and its scope | Source, date, author/channel |
|---|---|---|
| D1 | "HALF_UP for lines and renderer, new invoices only." Closes Q1 and accepts I1 | Ticket comment, 2026-03-03, product owner |

## Acceptance and implementation plan

| Requirement item | Change/stage | Check and expected result | Status and proof |
|---|---|---|---|
| 1 | Round each line in `InvoiceCalculator` | 0.335 → 0.34; −2.345 → −2.35 | verified: `InvoiceCalculatorTest`, 6 cases, `./gradlew test` in `billing`, 2026-03-05 |
| 2 | Sum rounded lines, no second rounding | 3 × 0.335 → 1.02; negative control: the old code gives 1.01 and the test fails on it | verified: same run; the test fails on `4f2c9a1` |
| 3 | No change to issued invoices | An issued invoice keeps 1.01 after the change | verified: `IssuedInvoiceTest`, same run |

## Risks and limitations

Consumers of `invoice.created` outside `billing` were not searched (F4). The value format does not change, only the amount for new invoices.

## Current state

Decision: approved (D1). Code: implemented in branch `inv-42`. Checks: unit tests passed locally (above). Not verified: merge to `main`, deployment, behavior in production.

Next step: open the pull request for `inv-42`.

# Approval brief

A question that asks the owner to choose (an RFC decision, a scope change, a paid run, a method) comes with a brief. The owner can decide from the brief alone, without opening the RFC. Build it from the current revision of the RFC and its Q/D records. The decision itself is recorded in the RFC (section "Owner decisions"), not in the brief.

## Full brief

1. **What is wrong now**: the fact, with its proof (F-id, file:line or command).
2. **How it will work**, step by step.
3. **One example on real data**: input → before → after.
4. **What is affected**: components, consumers, data, documents.
5. **Cost and size**: work, run time or money as far as measured; say "not measured" instead of guessing.
6. **Risks and their protection**: a concrete scenario and what limits it.
7. **Recommendation** and the alternatives with the condition that would make another one better.
8. **What "yes" authorizes**, and what still needs its own approval (merge, push, release, deployment, paid runs, messages).

## Short brief

For a small choice that does not change scope, a contract, a risk or a budget: what is wrong now, one example, the recommendation, what "yes" authorizes. Use the full brief whenever in doubt.

## When approval is reopened

After a material change to an approved RFC (scope, contract, risk or budget), add the section "Changes since approval" to the RFC ([template](rfc-template.md)) and put its table into the brief. Ask only about the affected rows: decisions in rows that did not change stay in force. Editorial changes do not reopen approval.

| Approved baseline | What changed | Affected contract and checks | Decision needed | Work that continues |
|---|---|---|---|---|
| <D-n, date> | <new or changed requirement, or a refuted fact> | <items, files, tests> | <the open question> | <independent work that does not wait> |

## Example (the synthetic RFC [INV-42](../examples/docs/rfc/INV-42-line-rounding.md))

> **Decision needed: the rounding mode for invoice lines (INV-42, Q1).**
>
> 1. Now the total is rounded once from unrounded lines (F1, `InvoiceCalculator.java:58`), so printed lines may not add up to the total.
> 2. It will be: round each line to 2 places, then sum the rounded lines; the PDF prints the same rounded lines. Open: the mode. The spec says HALF_UP, the renderer uses HALF_EVEN (F2).
> 3. Three lines of 0.335: before 0.34 + 0.34 + 0.34 with total 1.01; after the same lines with total 1.02.
> 4. Affected: `InvoiceCalculator`, `InvoiceRenderer` and the `invoice.created` event (F4). Issued invoices are never recomputed (F3).
> 5. Size: two classes and their tests; not measured in time.
> 6. Risk: consumers of `invoice.created` outside `billing` were not searched (F4); the format does not change, only the amount of new invoices. Protection: ask their owners before release.
> 7. Recommendation: HALF_UP for lines and the renderer, new invoices only: lines and total then always match. Keeping HALF_EVEN in the renderer would print 0.34 for a line of 0.345 that the total counts as 0.35.
> 8. "Yes" authorizes code and tests in `billing`. Merge, release and deployment need their own approval.

A later change, as a row of "Changes since approval":

| Approved baseline | What changed | Affected contract and checks | Decision needed | Work that continues |
|---|---|---|---|---|
| D1, 2026-03-03 | new item: invoices in JPY have no minor units | rounding precision per currency; a new test for JPY | precision for JPY: 0 places, or the currency's minor units from ISO 4217 | rounding for the other currencies |

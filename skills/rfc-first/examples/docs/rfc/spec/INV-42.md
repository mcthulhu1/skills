# INV-42 — source requirements

Source: ticket INV-42 "Invoice total differs from the sum of its lines", revision of 2026-03-02 (synthetic example).
Received: 2026-03-02, product owner, ticket comment.
Current revision: 2026-03-02, items 1–3.
Form: original text, copied from the ticket.

## Current text (verbatim)

> Customers see an invoice total that is 1 cent off the sum of the lines printed above it.
>
> 1. Round every line amount to 2 decimal places, half up, before it is added to the total.
> 2. The invoice total is the sum of the rounded line amounts. Do not round the total again.
> 3. Invoices already issued must not change.

## Notes (not part of the requirements)

- "Half up" is read as ROUND_HALF_UP on the absolute value (2.345 → 2.35, −2.345 → −2.35). This is interpretation I1 in the RFC, not part of the source.

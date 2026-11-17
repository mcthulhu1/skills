# Headings in the team's language: rfc-lint.json

By default the [structure check](structure-check.md) recognizes the English headings and header fields of the [RFC template](rfc-template.md). A team that writes RFCs with headings in its own language puts `rfc-lint.json` into the RFC storage, next to the RFCs. The check then accepts the English words and the team's words. Without the file nothing changes. The file name is kept from earlier versions, which ran a script for this check.

```json
{
  "sections": {
    "goal": ["<heading for 'Goal and contract'>"],
    "facts": ["<heading for 'Verified facts'>"],
    "next_step": ["<words for 'Next step'>"]
  },
  "fields": {
    "status": ["<field for 'Decision'>", "<field for 'Implementation and verification'>"],
    "source": ["<field for 'Requirements verbatim'>"]
  },
  "proof_column": ["<column name for 'Proof'>"],
  "hedges": ["<'probably'>", "<'apparently'>", "<'it seems'>"]
}
```

| Key | What the structure check does with it |
|---|---|
| `sections.goal`, `sections.facts` | Required sections: a heading must contain one of the words, or the RFC fails (rule 2) |
| `sections.next_step` | Warns when the section lists several first steps (rule 10) |
| `fields.status` | Expects a short status at the start of a line in the first 15 lines (rule 5) |
| `fields.source` | Finds the link to the verbatim spec, including `` <field>: `spec/<ID>.md` `` (rules 3, 6) |
| `proof_column` | Finds the proof column in the facts table and warns about rows with an empty proof (rule 8) |
| `hedges` | Warns when a fact contains a word that marks a guess (rule 9) |

- Every key is optional; each value is a non-empty list of strings. An unknown key or a wrong type fails the check (rule 4), so a typo is not silently ignored.
- A word matches as a case-insensitive substring of the heading, cell or line, because Chinese, Japanese and Thai text has no spaces between words. Use whole words or phrases, not short stems that also occur elsewhere.
- Fields accept both `:` and the full-width colon (U+FF1A).
- The check reads `rfc-lint.json` from the directory of each RFC. A path the user names explicitly replaces it.

When the user wants headings in their language and the file is missing: translate the template's headings, field names and the proof column, add the usual words for a guess, show the file to the user, and create it in the RFC storage after approval. Then write every RFC with these headings.

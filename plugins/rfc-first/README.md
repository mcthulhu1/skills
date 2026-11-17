# RFC-first

Agents fail in the same few ways: they paraphrase the requirements and then implement the paraphrase, present a guess as a fact, take silence for approval, and call work "done" when only the unit tests ran. `rfc-first` is a **strict RFC-first process** for Claude Code, Codex, OpenCode, Copilot, Gemini CLI, Cursor and any other agent that supports the [Agent Skills](https://agentskills.io) format. It makes the chain explicit:

```
requirement → verified facts → decision → plan → change → verification
```

- **Verbatim spec, required.** Before any code the agent copies the requirements word for word into `spec/<ID>.md` next to the RFC. A link to a ticket is not a copy, and a paraphrase is not a requirement. This is the core of the approach: the requirements live in your repository, not in a chat window or on a page that may change.
- **Every fact has proof**: file:line, or command + cwd + result. Hypotheses are marked as hypotheses and withdrawn when refuted.
- **Only the new choice is asked.** The agent checks what it can check itself and asks the owner only about real decisions, with a recommendation. An answer to one question is not approval of the whole RFC.
- **Status is layered**: approved ≠ implemented ≠ verified ≠ merged ≠ in a build artifact ≠ deployed ≠ behavior confirmed.
- **The scale fits the task**: a short fix gets a short record.
- **A structure check** ([checklist](skills/rfc-first/references/structure-check.md)): the agent checks every RFC it writes for the required sections, a status line and working links to the verbatim spec.

RFCs go to the project's RFC storage: a path from AGENTS.md / CLAUDE.md (`RFC storage: <path>`), an existing `docs/rfc/`, or `docs/rfc/` by default. The agent writes the RFC in your language. Section headings stay in English by default; to have them in your language too, the agent prepares `rfc-lint.json` with your headings in the RFC storage, and the structure check accepts both ([format](skills/rfc-first/references/rfc-lint-config.md)).

A finished synthetic example: [spec](skills/rfc-first/examples/docs/rfc/spec/INV-42.md) → [RFC with the decision and verification](skills/rfc-first/examples/docs/rfc/INV-42-line-rounding.md).

> **Copy only what you may copy.** The verbatim spec is stored in your repository, so save there only requirements you are allowed to copy. If a license, policy or confidentiality rule forbids it, the agent stops and asks you for a permitted form: an approved excerpt, a summary marked as non-verbatim, or another location. Never store secrets or customers' personal data.

## What it runs and sends

The plugin has no hooks, MCP servers, commands or agents, and nothing runs when it is installed. It is one skill: Markdown instructions and templates that the agent uses during a session, with the permissions you give the agent.

- **Runs**: nothing. The plugin contains no scripts or programs; the structure check is a checklist the agent applies by reading the RFC.
- **Writes**: RFCs and verbatim specs as Markdown files in your project's RFC storage (`docs/rfc/` by default), and `rfc-lint.json` there if you approve one. The agent offers once to add an `RFC storage:` line to your AGENTS.md and does not add it without your answer.
- **Asks the agent to check**: facts in your project the usual way, such as reading files, running your tests, or `git ls-remote` to see whether a remote branch is up to date. These are your agent's ordinary tools and follow its permission settings.
- **Sends**: nothing. The plugin has no telemetry and no endpoints of its own.

## Install

Pick one route per agent: installing the skill twice gives you two copies.

<details open>
<summary><strong>Claude Code</strong></summary>

```bash
claude plugin install rfc-first --marketplace mcthulhu1/skills
```

Needs Claude Code 2.1.292+. On older versions run `claude plugin marketplace add mcthulhu1/skills`, then `claude plugin install rfc-first@mcthulhu1`.

Third-party marketplaces do not auto-update by default. Turn it on once in `/plugin` → **Marketplaces** → `mcthulhu1` → **Enable auto-update**, or update by hand with `claude plugin update rfc-first@mcthulhu1`.

</details>

<details>
<summary><strong>Codex</strong></summary>

```bash
codex plugin marketplace add mcthulhu1/skills
codex plugin add rfc-first@mcthulhu1
```

</details>

<details>
<summary><strong>GitHub Copilot</strong> (CLI and VS Code)</summary>

```bash
copilot plugin marketplace add mcthulhu1/skills
copilot plugin install rfc-first@mcthulhu1
```

In VS Code: **Chat: Install Plugin From Source** → `https://github.com/mcthulhu1/skills`.

</details>

<details>
<summary><strong>Gemini CLI</strong></summary>

```bash
gemini skills install https://github.com/mcthulhu1/skills.git --path plugins/rfc-first/skills
```

Re-run the command to update.

</details>

<details>
<summary><strong>OpenCode, Cursor and any other agent</strong></summary>

```bash
npx skills@latest add mcthulhu1/skills --skill rfc-first -a opencode   # or cursor, windsurf, amp, ...
```

Add `-g` to install for all projects. By default the CLI links the skill into the agent's directory; `--copy` copies the files instead. Update with `npx skills@latest update`.

</details>

### Upgrading from `mcthulhu1-skills`

Up to 1.1.5 this skill was installed as the plugin `mcthulhu1-skills`. Remove it and install `rfc-first` as above:

```bash
claude plugin uninstall mcthulhu1-skills@mcthulhu1
codex plugin remove mcthulhu1-skills@mcthulhu1
```

### Compatibility

"Verified" means the route was run against a local copy of this repository and the client listed the skill (no model call); "documented" means it follows the client's documentation but has not been run yet. Reports and pull requests are welcome.

| Client | Version | Route | Status |
|---|---|---|---|
| Claude Code | 2.1.319 | `plugin install --marketplace <clone>`; `marketplace add` → `install` | Verified 2026-11-09 on Linux: `plugin details` lists the skill |
| Codex | 0.167.0 | `plugin marketplace add <clone>` → `plugin add` | Verified 2026-11-09 on Linux: plugin installed, `SKILL.md` in the Codex plugin cache |
| Gemini CLI | 0.67.0 | `skills install <clone> --path plugins/rfc-first/skills` | Verified 2026-11-09 on Linux: `gemini skills list` shows `rfc-first [Enabled]`. Asks for confirmation; `--consent` skips it in scripts |
| skills CLI | 1.7.6 | `npx skills add <clone> --skill rfc-first -a opencode` | Verified 2026-11-09 on Linux |
| OpenCode | 1.19.5 | Loading the skill placed by the skills CLI | Verified 2026-11-09 on Linux: `opencode debug skill` lists `rfc-first` |
| GitHub Copilot | — | `copilot plugin marketplace add` | Documented |
| Install from GitHub | as above | `mcthulhu1/skills` instead of a local clone | Documented for this layout; verified for 1.1.x on 2026-10-22 |

## Use

Start a new agent session, then:

- Claude Code: `/rfc-first:rfc-first <task>`
- Codex: `$rfc-first <task>`
- OpenCode and others: `/rfc-first <task>` where supported, or "use the rfc-first skill for <task>"

The agent also picks the skill up by itself for a new change that has not been approved yet. Typical requests:

- "Prepare an RFC for PROJ-123, the requirements are below" — new RFC, verbatim spec, open questions with recommendations.
- "Validate docs/rfc/PROJ-123-*.md" — review findings without edits.
- "The RFC is approved, implement it" — implementation and checks within the approved scope.
- "What is the status of PROJ-123?" — confirmed levels and what is not verified.

## Troubleshooting

- **The skill does not show up.** Start a new agent session after installing. In Claude Code check `claude plugin list`; with the skills CLI check that the skill is in your agent's skills directory. Install through one route per agent, or you get two copies.
- **The structure check reports a missing section for an RFC with headings in your language.** Add `rfc-lint.json` with your headings to the RFC storage ([format](skills/rfc-first/references/rfc-lint-config.md)).
- **The agent stores RFCs in the wrong place.** Add `RFC storage: <path>` to your AGENTS.md or CLAUDE.md.
- **Something else.** Open an issue: https://github.com/mcthulhu1/skills/issues. Report security problems privately, as described in [SECURITY.md](https://github.com/mcthulhu1/skills/blob/main/SECURITY.md).

Changes: [CHANGELOG.md](CHANGELOG.md). License: [MIT](LICENSE).

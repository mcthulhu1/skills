# Skills

<img src="assets/icon.png" alt="" width="96" align="right">

Agent skills for Claude Code, Codex, OpenCode, Copilot, Gemini CLI, Cursor and any other agent that supports the [Agent Skills](https://agentskills.io) format.

| Skill | What it does |
|---|---|
| [`rfc-first`](skills/rfc-first/SKILL.md) | A strict RFC-first process: the requirements are saved verbatim, every fact has proof, the owner approves the decision before code, and the status says exactly what was verified |

## rfc-first

Agents fail in the same few ways: they paraphrase the requirements and then implement the paraphrase, present a guess as a fact, take silence for approval, and call work "done" when only the unit tests ran. `rfc-first` is a **strict RFC-first process** that makes the chain explicit:

```
requirement → verified facts → decision → plan → change → verification
```

- **Verbatim spec, required.** Before any code the agent copies the requirements word for word into `spec/<ID>.md` next to the RFC. A link to a ticket is not a copy, and a paraphrase is not a requirement. This is the core of the approach: the requirements live in your repository, not in a chat window or on a page that may change.
- **Every fact has proof**: file:line, or command + cwd + result. Hypotheses are marked as hypotheses and withdrawn when refuted.
- **Only the new choice is asked.** The agent checks what it can check itself and asks the owner only about real decisions, with a recommendation. An answer to one question is not approval of the whole RFC.
- **Status is layered**: approved ≠ implemented ≠ verified ≠ merged ≠ in a build artifact ≠ deployed ≠ behavior confirmed.
- **The scale fits the task**: a short fix gets a short record.
- **A built-in linter** (`scripts/rfc_lint.py`, Python 3.9+, stdlib only) checks the structure of every RFC the agent writes.

RFCs go to the project's RFC storage: a path from AGENTS.md / CLAUDE.md (`RFC storage: <path>`), an existing `docs/rfc/`, or `docs/rfc/` by default. The agent writes the RFC in your language. Section headings stay in English by default; to have them in your language too, the agent prepares `rfc-lint.json` with your headings in the RFC storage, and the linter accepts both ([format](skills/rfc-first/references/rfc-lint-config.md)).

A finished synthetic example: [spec](skills/rfc-first/examples/docs/rfc/spec/INV-42.md) → [RFC with the decision and verification](skills/rfc-first/examples/docs/rfc/INV-42-line-rounding.md).

> **Copy only what you may copy.** The verbatim spec is stored in your repository, so save there only requirements you are allowed to copy. If a license, policy or confidentiality rule forbids it, the agent stops and asks you for a permitted form: an approved excerpt, a summary marked as non-verbatim, or another location. Never store secrets or customers' personal data.

## Install

Pick one route per agent: installing the skill twice gives you two copies.

<details open>
<summary><strong>Claude Code</strong></summary>

```bash
claude plugin install mcthulhu1-skills --marketplace mcthulhu1/skills
```

Needs Claude Code 2.1.292+. On older versions run `claude plugin marketplace add mcthulhu1/skills`, then `claude plugin install mcthulhu1-skills@mcthulhu1`.

Third-party marketplaces do not auto-update by default. Turn it on once in `/plugin` → **Marketplaces** → `mcthulhu1` → **Enable auto-update**, or update by hand with `claude plugin update mcthulhu1-skills@mcthulhu1`.

</details>

<details>
<summary><strong>Codex</strong></summary>

```bash
codex plugin marketplace add mcthulhu1/skills
codex plugin add mcthulhu1-skills@mcthulhu1
```

</details>

<details>
<summary><strong>GitHub Copilot</strong> (CLI and VS Code)</summary>

```bash
copilot plugin marketplace add mcthulhu1/skills
copilot plugin install mcthulhu1-skills@mcthulhu1
```

In VS Code: **Chat: Install Plugin From Source** → `https://github.com/mcthulhu1/skills`.

</details>

<details>
<summary><strong>Gemini CLI</strong></summary>

```bash
gemini skills install https://github.com/mcthulhu1/skills.git --path skills
```

Re-run the command to update.

</details>

<details>
<summary><strong>OpenCode, Cursor and any other agent</strong></summary>

```bash
npx skills@latest add mcthulhu1/skills -a opencode   # or cursor, windsurf, amp, ...
```

Add `-g` to install for all projects. By default the CLI links the skill into the agent's directory; `--copy` copies the files instead. Update with `npx skills@latest update`.

</details>

Python 3.9+ is needed for the linter (`py -3` or `python` on Windows).

### Compatibility

"Verified" means the route was run against this repository and the client listed the skill (no model call); "documented" means it follows the client's documentation but has not been run yet. Reports and pull requests are welcome.

| Client | Version | Route | Status |
|---|---|---|---|
| Claude Code | 2.1.308 | `plugin install --marketplace <clone>`; `marketplace add` → `install` | Verified 2026-10-22 on macOS and Linux: `plugin details` lists the skill |
| Codex | 0.163.0 | `plugin marketplace add <clone>` → `plugin add` | Verified 2026-10-22 on Linux: plugin installed, `SKILL.md` in the Codex plugin cache |
| Gemini CLI | 0.65.0 | `skills install <clone>` | Verified 2026-10-22 on Linux: `gemini skills list` shows `rfc-first [Enabled]`. Asks for confirmation; `--consent` skips it in scripts |
| skills CLI | 1.7.4 | `npx skills add <clone> -a opencode` | Verified 2026-10-22 on macOS and Linux |
| OpenCode | 1.19.4 | Loading the skill placed by the skills CLI | Verified 2026-10-22 on macOS and Linux: `opencode debug skill` lists `rfc-first` |
| GitHub Copilot | — | `copilot plugin marketplace add` | Documented |
| Install from GitHub | as above | `mcthulhu1/skills` instead of a local clone | Verified 2026-10-22 for Claude Code, Codex, Gemini CLI, skills CLI and OpenCode |

## Use

Start a new agent session, then:

- Claude Code: `/mcthulhu1-skills:rfc-first <task>`
- Codex: `$rfc-first <task>`
- OpenCode and others: `/rfc-first <task>` where supported, or "use the rfc-first skill for <task>"

The agent also picks the skill up by itself for a new change that has not been approved yet. Typical requests:

- "Prepare an RFC for PROJ-123, the requirements are below" — new RFC, verbatim spec, open questions with recommendations.
- "Validate docs/rfc/PROJ-123-*.md" — review findings without edits.
- "The RFC is approved, implement it" — implementation and checks within the approved scope.
- "What is the status of PROJ-123?" — confirmed levels and what is not verified.

## Development

```bash
python3 -B -m unittest discover -s skills/rfc-first/scripts/tests
python3 -B scripts/check_manifests.py
claude plugin validate . --strict
```

CI (`.github/workflows/ci.yml`) runs the tests, the example lint and the manifest check on Linux, macOS and Windows with Python 3.9 and 3.13. When you change a skill, bump `version` in `.claude-plugin/plugin.json` (installed plugins update only when it changes) and add a section for it to [CHANGELOG.md](CHANGELOG.md); the manifest check fails without one.

## License

[MIT](LICENSE)

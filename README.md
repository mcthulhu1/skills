# Skills

<img src="plugins/rfc-first/assets/icon.png" alt="" width="96" align="right">

[![skills.sh](https://skills.sh/b/mcthulhu1/skills)](https://skills.sh/mcthulhu1/skills)

Agent skills for Claude Code, Codex, OpenCode, Copilot, Gemini CLI, Cursor and any other agent that supports the [Agent Skills](https://agentskills.io) format. The repository is a plugin marketplace named `mcthulhu1`: each skill is its own plugin under [`plugins/`](plugins), with its own README, version and changelog.

| Plugin | What it does |
|---|---|
| [`rfc-first`](plugins/rfc-first) | A strict RFC-first process: the requirements are saved verbatim, every fact has proof, the owner approves the decision before code, and the status says exactly what was verified |
| [`appsec-scan`](plugins/appsec-scan) | A local pre-PR security scan with opengrep and trivy: SAST, SCA and container images, which findings are new against your base branch, and where each vulnerable dependency comes from |

## Install

Each plugin's README has the commands for every agent. In Claude Code, for example:

```bash
claude plugin install rfc-first --marketplace mcthulhu1/skills
```

Up to 1.1.5 `rfc-first` was installed as the plugin `mcthulhu1-skills`; see [upgrading](plugins/rfc-first#upgrading-from-mcthulhu1-skills).

## Development

```bash
claude plugin validate plugins/rfc-first --strict
python3 -m unittest discover -s tests/appsec-scan -p 'test_*.py'   # appsec-scan report tests
bash tests/appsec-scan/run_integration.sh                          # appsec-scan fixtures (needs trivy, cosign)
```

`appsec-scan` is distributed only through this repository: it holds scripts, so it is not submitted to the Claude plugin directory. Its tests live in [`tests/appsec-scan`](tests/appsec-scan), outside the plugin folder, so they are not installed. A plugin that goes to the Claude plugin directory may hold only Markdown, text, JSON, YAML and images, with no file starting with `#!`: the directory accepts scripts only from verified organizations. CI (`.github/workflows/ci.yml`) checks the file types of those plugins, the manifests and the changelog entries. When you change a plugin, bump `version` in its `.claude-plugin/plugin.json` (installed plugins update only when it changes) and add a section for it to the plugin's `CHANGELOG.md`; CI fails without one. Releases are tagged `<plugin>-vX.Y.Z`.

Security: [SECURITY.md](SECURITY.md). License: [MIT](LICENSE).

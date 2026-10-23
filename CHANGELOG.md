# Changelog

All notable changes to this repository. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [Semantic Versioning](https://semver.org/) and match `version` in `.claude-plugin/plugin.json`.

## [1.1.5] - 2026-10-23

### Added

- README: the skills.sh install count badge.

## [1.1.4] - 2026-10-23

### Added

- `SECURITY.md`: report vulnerabilities privately through GitHub.
- README: Troubleshooting.

### Changed

- `rfc-first`: the skill no longer mentions the agent's memory. It neither reads nor updates it; earlier notes and answers are still treated as pointers, not proof.

## [1.1.3] - 2026-10-23

### Added

- Listing links in `plugin.json`: documentation (README), support (GitHub issues) and privacy (the README section "What it runs and sends").

## [1.1.2] - 2026-10-23

### Changed

- Author, marketplace owner and copyright holder: Ilia Shiriaev instead of the GitHub login. The marketplace name `mcthulhu1` and install commands do not change.

## [1.1.1] - 2026-10-23

### Added

- README: "What it runs and sends" lists what the plugin runs, writes and sends, for users and for the plugin directory's review.
- `displayName` "RFC-first" in `plugin.json`, the name shown in plugin lists.

### Changed

- CI can be started by hand (`workflow_dispatch`), for when a push event is lost.
- The encoding test runs the linter in-process against a cp1252 stream instead of a child process with a modified environment; the tests no longer read environment variables.
- `assets/make_icon.py` takes the output path as its argument and no longer names the icon file.

### Removed

- `.gitattributes`: the plugin directory refuses to validate a repository whose attributes rewrite file contents (`text`, `eol`). The scripts read files with universal newlines, so CRLF checkouts still work.

## [1.1.0] - 2026-10-22

### Added

- `rfc-first`: RFC headings in the team's language. Put `rfc-lint.json` next to the RFCs and the linter accepts the team's headings, header fields, proof column, next-step words and guess words in addition to the English ones. The format is in [`references/rfc-lint-config.md`](https://github.com/mcthulhu1/skills/blob/main/skills/rfc-first/references/rfc-lint-config.md).
- `rfc_lint.py --config <path>` to use a file from another location.
- Header fields accept the full-width colon (U+FF1A) used in Chinese and Japanese.

### Changed

- `SKILL.md`: the agent uses the team's headings when the file exists, and prepares the file for approval when the user asks for headings in their language.
- A missing section error without a config now says that other languages need `rfc-lint.json`.
- CI uses `actions/checkout@v7` and `actions/setup-python@v7` (Node 24).
- README: installing from GitHub is verified for Claude Code, Codex, Gemini CLI, the skills CLI and OpenCode.

## [1.0.0] - 2026-10-22

### Added

- `rfc-first` skill: a strict RFC-first process (`requirement → verified facts → decision → plan → change → verification`) with the new, update, validate, implement and status modes.
- The verbatim spec in `spec/<ID>.md`, the RFC and spec templates, the review checklist, evidence rules and patterns, and a synthetic example (INV-42).
- `rfc_lint.py`, a structural linter for RFCs (Python 3.9+, stdlib only), with tests.
- Plugin and marketplace manifests for Claude Code, Codex and GitHub Copilot; install routes for Gemini CLI, OpenCode and other agents through the skills CLI.
- CI on Linux, macOS and Windows with Python 3.9 and 3.13.

[1.1.5]: https://github.com/mcthulhu1/skills/compare/v1.1.4...v1.1.5
[1.1.4]: https://github.com/mcthulhu1/skills/compare/v1.1.3...v1.1.4
[1.1.3]: https://github.com/mcthulhu1/skills/compare/v1.1.2...v1.1.3
[1.1.2]: https://github.com/mcthulhu1/skills/compare/v1.1.1...v1.1.2
[1.1.1]: https://github.com/mcthulhu1/skills/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/mcthulhu1/skills/compare/ad6ed2e...v1.1.0
[1.0.0]: https://github.com/mcthulhu1/skills/commit/ad6ed2e

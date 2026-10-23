# Security policy

## Reporting a vulnerability

Report security problems privately through GitHub: open the [Security tab](https://github.com/mcthulhu1/skills/security) of this repository and select **Report a vulnerability**. Do not open a public issue for a security problem.

Include the affected file or skill, the version (`version` in `.claude-plugin/plugin.json`), the steps to reproduce and the impact. You will get an answer within 7 days.

## Supported versions

Only the latest release is supported. Fixes are released as a new version; see [CHANGELOG.md](CHANGELOG.md).

## Scope

The plugin is Markdown instructions, templates and a local Python linter. It has no hooks, MCP servers or network access of its own. Relevant reports include instructions that make an agent act beyond what the README describes, and linter behavior that reads or writes files other than the RFCs passed to it.

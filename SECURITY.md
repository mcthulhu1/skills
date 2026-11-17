# Security policy

## Reporting a vulnerability

Report security problems privately through GitHub: open the [Security tab](https://github.com/mcthulhu1/skills/security) of this repository and select **Report a vulnerability**. Do not open a public issue for a security problem.

Include the affected plugin and file, its version (`version` in `plugins/<plugin>/.claude-plugin/plugin.json`), the steps to reproduce and the impact. You will get an answer within 7 days.

## Supported versions

Only the latest release of each plugin is supported. Fixes are released as a new version; see the plugin's `CHANGELOG.md`.

## Scope

Each plugin's README lists what it runs and sends in "What it runs and sends". `rfc-first` is Markdown instructions and templates with no scripts, hooks, MCP servers or network access of its own. Relevant reports include instructions or scripts that make an agent act beyond what the plugin's README describes.

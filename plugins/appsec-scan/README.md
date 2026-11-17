# appsec-scan

**A local pre-PR security scan: new findings vs your base branch, with evidence.** Before you open a pull request, the agent runs open-source scanners on your repository, marks which findings your branch added, and reviews every new one in the code. It works with Claude Code, Codex, OpenCode, Copilot, Gemini CLI, Cursor and any other agent that supports the [Agent Skills](https://agentskills.io) format.

- **SAST** with [opengrep](https://github.com/opengrep/opengrep) (`--taint-intrafile`): Java, Kotlin, Go, Rust, Python, JavaScript, TypeScript.
- **SCA** with [trivy](https://trivy.dev): the real Gradle or Maven runtime classpath (the project is built), and lock files: `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`, `requirements*.txt`, `poetry.lock`, `uv.lock`, `Pipfile.lock`, `go.mod`, `Cargo.lock`. Nothing is installed with npm or pip.
- **New vs existing**: the same scans run on the merge-base of your base branch (`git archive`, your working tree is not touched). Every SAST and SCA finding is `new`, `existing` or `?` when the comparison is not possible, and the report lists what the branch fixed.
- **Where it comes from**: for Gradle and Maven, the path from your project to each vulnerable jar; for lock files, the path from the dependency graph when the lock file has one.
- **Container images**, on request: `--image REF` scans an image you already have, `--docker-build` builds your Dockerfiles first. An image is a full snapshot, not compared with a base.
- **Honest failures**: every part writes `ok`, `fail` or `skip` with the reason. A part that failed is reported as not checked, never as zero findings.

It complements Claude Code's built-in `/security-review` (a model reviewing the diff): these are deterministic scanners with output you can check, a comparison with the base, and the dependency path, with no accounts and no cloud.

## What it runs and sends

Install adds one skill: instructions, a bash script and two Python helpers (standard library only). Nothing runs at install time. The agent runs the scan only when you ask for it, with the permissions you give the agent.

- **Runs by itself**: `git` (read-only: `rev-parse`, `merge-base`, `archive`, `ls-files`), `opengrep`, `trivy`, `cosign` (to verify opengrep), `curl` (all downloads go through one function in `scan.sh`), `python3`.
- **Runs from your project**: the Gradle or Maven build (`./gradlew` or `gradle`, `./mvnw` or `mvn`) to resolve the runtime classpath, for HEAD and for the base. The build scripts execute with your permissions. With `--docker-build`, also `docker build` with your Dockerfiles, which runs their `RUN` steps. **Scan only repositories whose build you trust.**
- **Writes**: `~/.cache/appsec-scan` (or `$XDG_CACHE_HOME/appsec-scan`): opengrep (with its unpacked runtime and log, which it would otherwise put in `~/.cache/opengrep` and `~/.opengrep`), rules, the trivy database and one directory per run with the report. Your project's build writes as usual: `build/` or `target/`, and the Gradle or Maven caches in your home directory. Nothing in your source, build or lock files is changed; the Gradle project cache goes into the run directory, not `.gradle/`.
- **Connects to**: `api.github.com` and `github.com` (the latest opengrep release), the Sigstore services used by `cosign verify-blob` (signature check), `semgrep.dev` (rules, unless `--rules`), the trivy database registries (`mirror.gcr.io`, `ghcr.io`), and the dependency repositories your build uses. `--image` may pull the image from its registry.
- **Telemetry**: trivy runs with `--disable-telemetry --skip-version-check --offline-scan`, opengrep with `--disable-version-check`. With `--no-update` and the tools, rules and database already cached, a scan of a lock-file project makes no network connections (checked with `strace` in a network namespace, see [tests](../../tests/appsec-scan)). Your code is not sent anywhere by the skill.

## Requirements

| Tool | Needed for | Install |
|---|---|---|
| bash 3.2+, git, python3 3.9+, curl, tar | always | preinstalled on macOS; your distribution's packages on Linux |
| [cosign](https://docs.sigstore.dev/cosign/system_config/installation/) | installing and updating opengrep | `brew install cosign` |
| [trivy](https://trivy.dev/latest/getting-started/installation/) 0.63+ | SCA and images | `brew install trivy` |
| JDK, Gradle or Maven (or the project's wrapper) | Java and Kotlin SCA | as for building the project |
| docker | `--docker-build` | [Docker](https://docs.docker.com/get-started/get-docker/) |

Platforms: macOS (arm64, x86_64) and Linux (glibc or musl, x86_64, aarch64). Windows: through WSL. The script installs nothing with a package manager: a missing tool fails only the part that needs it, with the install command.

opengrep is downloaded from its GitHub release into the cache and installed only after `cosign verify-blob` accepts its signature from the opengrep release workflow (`.github/workflows/rolling-release.yml` on `refs/heads/release-<tag>` for 1.x or `refs/heads/main` for 2.x, issuer `https://token.actions.githubusercontent.com`) run on exactly the commit the release tag points to. The checked sha256 is recorded, and a binary that does not match it is never run.

### Rules

By default the SAST rules are the [Semgrep registry](https://semgrep.dev/explore) packs for the languages found in the repository (`p/java`, `p/python`, ...), downloaded to your machine at scan time. They are licensed under the [Semgrep Rules License v1.0](https://semgrep.dev/legal/rules-license), which allows use only for your own internal business purposes: they are not part of this repository. To use your own rules, pass `--rules <file or directory>`; then nothing is requested from semgrep.dev.

## Install

Pick one route per agent: installing the skill twice gives you two copies.

<details open>
<summary><strong>Claude Code</strong></summary>

```bash
claude plugin install appsec-scan --marketplace mcthulhu1/skills
```

Needs Claude Code 2.1.292+. On older versions run `claude plugin marketplace add mcthulhu1/skills`, then `claude plugin install appsec-scan@mcthulhu1`. Update with `claude plugin update appsec-scan@mcthulhu1`; remove with `claude plugin uninstall appsec-scan@mcthulhu1`.

</details>

<details>
<summary><strong>Codex</strong></summary>

```bash
codex plugin marketplace add mcthulhu1/skills
codex plugin add appsec-scan@mcthulhu1
```

</details>

<details>
<summary><strong>GitHub Copilot</strong> (CLI and VS Code)</summary>

```bash
copilot plugin marketplace add mcthulhu1/skills
copilot plugin install appsec-scan@mcthulhu1
```

</details>

<details>
<summary><strong>Gemini CLI</strong></summary>

```bash
gemini skills install https://github.com/mcthulhu1/skills.git --path plugins/appsec-scan/skills
```

</details>

<details>
<summary><strong>OpenCode, Cursor and any other agent</strong></summary>

```bash
npx skills@latest add mcthulhu1/skills --skill appsec-scan -a opencode   # or cursor, windsurf, amp, ...
```

</details>

### Compatibility

"Verified" means the route was run against a local copy of this repository; "documented" means it follows the client's documentation but has not been run yet. Reports and pull requests are welcome.

| Client | Version | Route | Status |
|---|---|---|---|
| Claude Code | 2.1.319 | `plugin install --marketplace <clone>`; `marketplace add` → `install` | Verified 2026-11-09 on Linux: `plugin details` lists the skill, `scan.sh` is in the plugin cache |
| Codex | 0.167.0 | `plugin marketplace add <clone>` → `plugin add` | Verified 2026-11-09 on Linux: `SKILL.md` in the Codex plugin cache |
| Gemini CLI | 0.67.0 | `skills install <clone> --path plugins/appsec-scan/skills` | Verified 2026-11-09 on Linux: `gemini skills list` shows `appsec-scan [Enabled]` |
| skills CLI | latest on 2026-11-09 | `npx skills add <clone> --skill appsec-scan -a opencode` | Verified 2026-11-09 on Linux; the installed `scan.sh` scanned a fixture as expected |
| OpenCode | 1.19.5 | Loading the skill placed by the skills CLI | Verified 2026-11-09 on Linux: `opencode debug skill` lists `appsec-scan` |
| GitHub Copilot | — | `copilot plugin marketplace add` | Documented |
| Install from GitHub | as above | `mcthulhu1/skills` instead of a local clone | Documented |

Installing runs nothing and needs none of the scanners: the checks above ran without trivy, cosign or opengrep on `PATH`, and no cache was created until the first scan.

## Use

Start a new agent session in your repository, then ask, for example:

- Claude Code: `/appsec-scan:appsec-scan`; Codex: `$appsec-scan`; others: "run the appsec-scan skill".
- "Scan this branch for security issues before I open the PR."
- "Scan against `origin/develop`" (the agent passes `--base origin/develop`).
- "Also scan the image `ghcr.io/me/app:1.4`" (`--image`).

The agent runs `scan.sh`, reads the report, opens the code of every new SAST finding and says whether it is a real issue, groups the vulnerable dependencies with their path and how to close them, and leaves the decision to you. It changes nothing in your code.

You can also run the script yourself:

```bash
bash ~/.claude/plugins/cache/mcthulhu1/appsec-scan/0.1.1/skills/appsec-scan/scan.sh . --help
```

That is the Claude Code path; Codex uses `~/.codex/plugins/cache/mcthulhu1/appsec-scan/0.1.1/`, the skills CLI `.agents/skills/appsec-scan/` in your project. The script prints `REPORT=<path>/report.md` at the end.

## Limitations

- Results depend on the rule set and the vulnerability database: other scanners may find more or less, and rate severity differently.
- The base is compared through local refs only: run `git fetch` first if your base branch may be stale. `git archive` does not include submodules or Git LFS objects and honours `export-ignore`, so findings there are not compared.
- A SAST finding is matched by rule, file, enclosing function and the text of the line, so moving code within a function keeps it `existing`. Code outside any function is matched by file. The function is found with regular expressions per language and, for brace languages, a brace count that ignores string literals and `//` comments; it is not a parser.
- The rule packs are chosen by the languages of HEAD and of the base together. If a pack cannot be downloaded and is not cached, SAST is marked failed for both and its findings are `?`: a language without rules is never reported as clean.
- For lock files without a dependency graph (such as `requirements.txt`) the report says "direct/transitive: unknown". Requirements without a pinned `==` version are listed as not checked.
- Symlinks that point outside the repository are never followed: a build file, wrapper, lock file or Dockerfile that is such a symlink fails its part; any other is excluded and listed in the report.

## Troubleshooting

- **`tools-opengrep: fail`**: install cosign, check that `github.com` is reachable, then run again. A failed update keeps using the previous verified binary.
- **`sca: fail` with a Gradle or Maven error**: the build could not resolve dependencies (network, credentials for a private repository, or a JDK the build does not accept). Run the build yourself with the same JDK; `scan.log` in the run directory has the full output.
- **Everything is `?`**: there was no base to compare with (no `origin/main`, `origin/master`, `main` or `master`); pass `--base REF`.
- **Something else**: open an issue at https://github.com/mcthulhu1/skills/issues. Report security problems privately, as described in [SECURITY.md](https://github.com/mcthulhu1/skills/blob/main/SECURITY.md).

Changes: [CHANGELOG.md](CHANGELOG.md). License: [MIT](LICENSE).

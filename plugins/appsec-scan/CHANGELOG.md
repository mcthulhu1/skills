# Changelog

All notable changes to the `appsec-scan` plugin. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [Semantic Versioning](https://semver.org/) and match `version` in `.claude-plugin/plugin.json`. Releases are tagged `appsec-scan-vX.Y.Z`.

## [0.1.4] - 2026-11-18

### Fixed

- A lock file trivy read on one side only no longer gives false results: a base finding in a lock file trivy recognized nothing in at HEAD is not reported as fixed, and a HEAD finding in a lock file it recognized nothing in at the base is `?`. Before, such findings were "fixed in the branch" or "new".
- Gradle: jars declared as files (`files('libs/x.jar')`, `fileTree`) are scanned, with the declared file as their origin; a declared file that does not exist fails the SCA part. Before, they were left out without a note.
- The base is resolved with its own build system: a branch that moves from Maven to Gradle no longer fails the base and turns every JVM finding into `?`.
- A failed image scan is reported as not checked, never as an image with 0 vulnerabilities, and is not counted in the image total.
- `--docker-build` with Gradle puts the Gradle project cache into the run directory too, not `.gradle/` in the repository.
- Tests: the wrong-identity case of the opengrep install now differs from a good release only in the signing identity, so a loosened identity check fails it.

## [0.1.3] - 2026-11-18

### Fixed

- README: with `-a claude-code` the skills CLI installs the skill into `.claude/skills/appsec-scan/`, not `.agents/skills/appsec-scan/`; the path now depends on the agent.

### Changed

- README: installing from GitHub is verified for Claude Code (both routes) and the skills CLI with `-a claude-code`.

## [0.1.2] - 2026-11-18

### Fixed

- opengrep no longer fails to install behind a shared IP (CI runners, corporate NAT): the latest release tag now comes from the redirect of `github.com/opengrep/opengrep/releases/latest` and the commit of the tag from `git ls-remote` (peeled for an annotated tag), so no request goes to the GitHub REST API, whose limit without a token is 60 requests an hour per IP. The signature check is unchanged.

## [0.1.1] - 2026-11-17

### Fixed

- opengrep 2.x installs again. Since 2.0.0 opengrep signs releases from the workflow on `main`, not on a `release-<tag>` branch, so 0.1.0 rejected the signature and left SAST without opengrep. The signature is now accepted from either branch and must come from a workflow run on exactly the commit the release tag points to (`cosign --certificate-github-workflow-sha`); the commit is read from the GitHub API.
- Linux: opengrep 2.x ships one static binary (`opengrep_linux_x86`, `opengrep_linux_aarch64`) instead of separate glibc and musl builds; the asset is chosen by the release version.

## [0.1.0] - 2026-11-09

### Added

- First release: `scan.sh` runs SAST (opengrep with `--taint-intrafile`) for Java, Kotlin, Go, Rust, Python, JavaScript and TypeScript, SCA (trivy) over the Gradle or Maven runtime classpath and over npm, yarn, pnpm, pip, Poetry, uv, Pipenv, Go and Cargo lock files, and container images with `--image` or `--docker-build`.
- New vs existing against the merge-base of the base branch, with "fixed in the branch"; a part is compared only when its HEAD and base scans both succeeded, otherwise its findings are marked `?` with the reason.
- The dependency path for every vulnerable package: from Gradle and Maven, and from the lock file's dependency graph where it has one.
- opengrep is installed only after `cosign verify-blob` against the exact release workflow identity; the verified sha256 is checked before every run.
- `--rules PATH` to scan with your own rules and make no requests to semgrep.dev.

# Changelog

All notable changes to the `appsec-scan` plugin. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [Semantic Versioning](https://semver.org/) and match `version` in `.claude-plugin/plugin.json`. Releases are tagged `appsec-scan-vX.Y.Z`.

## [0.1.0] - 2026-11-09

### Added

- First release: `scan.sh` runs SAST (opengrep with `--taint-intrafile`) for Java, Kotlin, Go, Rust, Python, JavaScript and TypeScript, SCA (trivy) over the Gradle or Maven runtime classpath and over npm, yarn, pnpm, pip, Poetry, uv, Pipenv, Go and Cargo lock files, and container images with `--image` or `--docker-build`.
- New vs existing against the merge-base of the base branch, with "fixed in the branch"; a part is compared only when its HEAD and base scans both succeeded, otherwise its findings are marked `?` with the reason.
- The dependency path for every vulnerable package: from Gradle and Maven, and from the lock file's dependency graph where it has one.
- opengrep is installed only after `cosign verify-blob` against the exact release workflow identity; the verified sha256 is checked before every run.
- `--rules PATH` to scan with your own rules and make no requests to semgrep.dev.

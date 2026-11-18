---
name: appsec-scan
description: >-
  Local pre-PR security scan of one git repository with open-source scanners: SAST (opengrep with intra-file taint),
  SCA (trivy over the real Gradle/Maven runtime classpath and over npm, yarn, pnpm, pip, Poetry, uv, Pipenv, Go and
  Cargo lock files) and, on request, container images (trivy image). Marks which SAST and SCA findings are new against
  the merge-base of the base branch, shows where each vulnerable dependency comes from, then reviews every new finding
  in the code. Use only when the user explicitly asks for a security scan: it runs the project's build scripts and uses
  the network.
metadata:
  version: "0.2.0"
---

# appsec-scan

Goal: before a pull request, show the user what open-source scanners find in the branch, which findings are new
against the base branch, and where each one comes from. The user decides what to fix. **Do not change source code,
build files or lock files.**

## Run

The script is `scan.sh` in the directory of this `SKILL.md`. Run it with bash on macOS or Linux (Windows: WSL):

```
bash <directory of this SKILL.md>/scan.sh <repository> [options]
```

Options:

- `--base REF`: base for "new vs existing"; default the first of `origin/main`, `origin/master`, `main`, `master`.
  Local refs only, nothing is fetched; tell the user to fetch first if the base may be stale.
- `--no-base`: no comparison; all findings get `?`.
- `--no-update`: use the cached opengrep, rules and trivy database.
- `--rules PATH`: the user's own opengrep rules instead of the Semgrep registry; no requests to semgrep.dev.
- `--image REF`: scan an existing container image (repeatable). The image is not built; the SCA part still
  resolves Gradle or Maven dependencies as it does without the flag.
- `--docker-build`: build each Dockerfile of the repository and scan the image. This runs the Dockerfile's `RUN`
  steps: use it only when the user asks for it.
- `--parts LIST`: only these parts, comma-separated from `sast`, `sca`, `image` (`image` needs `--image` or
  `--docker-build`). Pass it only when the user narrows the scan ("only SAST", "without the build"); by default scan
  everything. Say which parts were not requested.

A run can take minutes (the first one downloads opengrep and the trivy database). If your client can run commands in
the background, run it in the background and wait for it to finish instead of polling. The last line of the output is
`REPORT=<path>/report.md`.

Before the first run in a repository, tell the user once that the scan runs the project's Gradle or Maven build
(its build scripts execute with the user's permissions) and downloads tools, rules and the vulnerability database.
Scan only repositories whose build the user trusts.

## Read the result

Read `report.md`. If a part failed, read `scan.log` next to it and name the cause (missing tool, no network to the
dependency repositories, the build failed, a symlink points outside the repository). A failed part is not "no
findings": say what was not checked.

## Answer the user

Conclusion first, then the tables.

1. **SAST, new findings.** For each one open the code at `file:line` and decide: a real vulnerability or a false
   positive, with the argument from the code (where the data comes from, what sanitizes it). Existing findings: one
   line with the count. "Fixed in the branch": list them.
2. **SCA.** Start from the report's "What to change in the build": one row per direct dependency, new findings
   first, with the version that fixes all CVEs of each package. For a transitive package the report names no
   version of the parent: find it in the parent's release notes or dependency metadata, or offer a version
   constraint or override in the build. Mention "first path found" when it applies. Rely on the report, the build
   files or a primary source for every version and ID; do not name versions from memory.
3. **Images.** Separate OS packages of the image (closed by a newer base image or a package upgrade in the
   Dockerfile) from application libraries (the same as SCA: refer to SCA, do not repeat).
4. **Limitations**, one line: results depend on the rule set and the vulnerability database; other scanners may find
   more or less and rate severity differently. Mention lines from the report's "Limitations" and symlinks that were
   not scanned.
5. **The decision is the user's**: options (fix the code, mark as a false positive, upgrade, add a constraint) without
   doing them. Change nothing until the user asks.

Give the path to `report.md` at the end.

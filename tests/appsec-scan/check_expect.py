"""Checks one appsec-scan run against an expectation file: python3 check_expect.py RUN_DIR EXPECT_JSON [CASE_DIR]

Expectation keys (all optional):
  status            {part: "ok" | "fail" | "skip"}         state of the part in status.tsv
  status_contains   {part: text}                           text in the part's comment
  status_absent     [prefix]                               no status.tsv line starts with prefix
  sast              [[status, file, function]]             exact multiset of SAST findings
  sast_fixed        [[file, function]]                     exact multiset of "fixed in the branch"
  sast_rules        [[status, rule, file, function]]       exact multiset with the rule id (last part of check_id)
  sast_fixed_rules  [[rule, file, function]]               exact multiset of "fixed in the branch" with the rule id
  sca_packages      [[status, type, package]]              exact set of (status, type, package) of SCA findings
  sca_ids           [[status, package, id]]                these SCA findings must exist (the CVE list grows)
  sca_fixed_packages [package]                             exact set of packages "fixed in the branch"
  sca_origin        [[package, text]]                      origin of the package contains text
  report_contains / report_absent / log_absent [text]
  files_absent      [name]                                 no file with this name under CASE_DIR or RUN_DIR
  repo_absent       [path]                                 nothing at this path in the scanned repository (CASE_DIR/repo)
Prints one line per failed check and exits 1 if any failed or if no check ran.
"""
import collections
import json
import os
import sys


def main():
    run, expect_path = sys.argv[1], sys.argv[2]
    with open(expect_path, encoding="utf-8") as f:
        exp = json.load(f)
    status = {}
    with open(os.path.join(run, "status.tsv"), encoding="utf-8") as f:
        for line in f:
            part, state, comment = (line.rstrip("\n").split("\t") + ["", ""])[:3]
            status[part] = (state, comment)
    summary_path = os.path.join(run, "summary.json")
    summary = json.load(open(summary_path, encoding="utf-8")) if os.path.isfile(summary_path) else {"findings": {}}
    found = summary.get("findings", {})
    report = open(os.path.join(run, "report.md"), encoding="utf-8").read() if os.path.isfile(os.path.join(run, "report.md")) else ""
    log = open(os.path.join(run, "scan.log"), encoding="utf-8", errors="replace").read()
    checks, failures = 0, []

    def check(ok, what):
        nonlocal checks
        checks += 1
        if not ok:
            failures.append(what)

    for part, state in exp.get("status", {}).items():
        got = status.get(part, ("missing", ""))
        check(got[0] == state, f"status {part}: expected {state}, got {got[0]} ({got[1]})")
    for part, text in exp.get("status_contains", {}).items():
        got = status.get(part, ("missing", ""))
        check(text in got[1], f"status {part}: comment {got[1]!r} lacks {text!r}")
    for prefix in exp.get("status_absent", []):
        bad = [p for p in status if p.startswith(prefix)]
        check(not bad, f"status lines {bad} start with {prefix!r}")
    if "sast" in exp:
        want = collections.Counter(tuple(x) for x in exp["sast"])
        got = collections.Counter((x["status"], x["file"], x["func"]) for x in found.get("sast", []))
        check(want == got, f"sast: expected {sorted(want.elements())}, got {sorted(got.elements())}")
    if "sast_fixed" in exp:
        want = collections.Counter(tuple(x) for x in exp["sast_fixed"])
        got = collections.Counter((x["file"], x["func"]) for x in found.get("sast_fixed", []))
        check(want == got, f"sast_fixed: expected {sorted(want.elements())}, got {sorted(got.elements())}")
    rid = lambda x: x["rule"].split(".")[-1]  # noqa: E731 - check_id = <dotted path of the rules file>.<rule id>
    if "sast_rules" in exp:
        want = collections.Counter(tuple(x) for x in exp["sast_rules"])
        got = collections.Counter((x["status"], rid(x), x["file"], x["func"]) for x in found.get("sast", []))
        check(want == got, f"sast_rules: expected {sorted(want.elements())}, got {sorted(got.elements())}")
    if "sast_fixed_rules" in exp:
        want = collections.Counter(tuple(x) for x in exp["sast_fixed_rules"])
        got = collections.Counter((rid(x), x["file"], x["func"]) for x in found.get("sast_fixed", []))
        check(want == got, f"sast_fixed_rules: expected {sorted(want.elements())}, got {sorted(got.elements())}")
    if "sca_packages" in exp:
        want = {tuple(x) for x in exp["sca_packages"]}
        got = {(x["status"], x["type"], x["pkg"]) for x in found.get("sca", [])}
        check(want == got, f"sca_packages: expected {sorted(want)}, got {sorted(got)}")
    for st, pkg, vid in exp.get("sca_ids", []):
        got = {(x["status"], x["pkg"], x["id"]) for x in found.get("sca", [])}
        check((st, pkg, vid) in got, f"sca: missing {st} {pkg} {vid}")
    if "sca_fixed_packages" in exp:
        want = set(exp["sca_fixed_packages"])
        got = {x["pkg"] for x in found.get("sca_fixed", [])}
        check(want == got, f"sca_fixed_packages: expected {sorted(want)}, got {sorted(got)}")
    for pkg, text in exp.get("sca_origin", []):
        origins = [x["origin"] for x in found.get("sca", []) if x["pkg"] == pkg]
        check(any(text in o for o in origins), f"sca origin of {pkg}: {origins} lacks {text!r}")
    for text in exp.get("report_contains", []):
        check(text in report, f"report lacks {text!r}")
    for text in exp.get("report_absent", []):
        check(text not in report, f"report contains {text!r}")
    for text in exp.get("log_absent", []):
        check(text not in log, f"scan.log contains {text!r}")

    roots = [run] + sys.argv[3:4]
    for name in exp.get("files_absent", []):
        hits = [os.path.join(top, n) for root in roots for top, _, files in os.walk(root) for n in files if n == name]
        check(not hits, f"file {name} exists: {hits}")

    for rel in exp.get("repo_absent", []):
        if len(sys.argv) > 3:
            path = os.path.join(sys.argv[3], "repo", rel)
            check(not os.path.lexists(path), f"{rel} exists in the repository")
        else:
            check(False, "repo_absent needs CASE_DIR")

    for f in failures:
        print(f"  FAIL {f}")
    if checks == 0:
        print("  FAIL no checks ran")
        return 1
    print(f"  {checks - len(failures)}/{checks} checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

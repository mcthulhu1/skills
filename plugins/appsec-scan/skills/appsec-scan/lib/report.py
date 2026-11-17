"""appsec-scan report: reads the artifacts of one run directory and prints Markdown to stdout.

New vs existing: a HEAD finding is "existing" if the same finding is in the base (merge-base) of the same part.
SAST findings match by (rule, path, enclosing function, line text), SCA findings by (type, target, package, id),
both with multiplicity. A part is compared only when its HEAD and its base both finished "ok"; otherwise its
findings get "?" and the report says why. Standard library only, Python 3.9+.
"""
import collections
import glob
import json
import os
import re
import sys

NEW, EXISTING, UNKNOWN = "new", "existing", "?"
SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "ERROR": 1, "MEDIUM": 2, "WARNING": 2, "LOW": 3, "INFO": 4, "UNKNOWN": 5}
DOCKER_ROW_LIMIT = 80
JVM_TARGET = "runtime classpath"

# Declarations that name the enclosing function of a finding, by language.
JVM_DECL = re.compile(
    r"^\s*(?:(?:public|private|protected|static|final|synchronized|abstract|override|suspend|internal|open|default)\s+)*"
    r"(?:fun\s+|func\s+(?:\([^)]*\)\s*)?|(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?(?:unsafe\s+)?fn\s+|\w[\w<>\[\],.?\s]*\s+)"
    r"(\w+)\s*(?:<[^>]*>)?\s*\(")
JVM_NOT_DECL = re.compile(r"^\s*(?:return|new|else|if|for|while|switch|catch|throw)\b|=")
PY_DECL = re.compile(r"^(\s*)(?:async\s+)?def\s+(\w+)\s*\(")
JS_DECL = [
    re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*(\w+)\s*[<(]"),
    re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*(?::[^=]+)?=\s*(?:async\s+)?(?:function\b|\([^)]*\)\s*(?::[^=]+)?=>|\w+\s*=>)"),
    re.compile(r"^\s*(\w+)\s*[:=]\s*(?:async\s+)?(?:function\b|\([^)]*\)\s*=>|\w+\s*=>)"),
    re.compile(r"^\s*(?:(?:public|private|protected|static|async|readonly|override|abstract|get|set)\s+)*\*?\s*"
               r"(?!(?:if|for|while|switch|catch|function|return|with)\b)(\w+)\s*(?:<[^>]*>)?\s*\([^)]*\)\s*(?::\s*[^{=]+)?\{\s*$"),
]
JS_EXT = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts")
STRING_OR_COMMENT = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|`(?:\\.|[^`\\])*`|//.*$')
_source_cache = {}


def brace_delta(text):
    """Opening minus closing braces of a line, outside string literals and // comments."""
    code = STRING_OR_COMMENT.sub("", text)
    return code.count("{") - code.count("}")


def source_lines(path):
    if path not in _source_cache:
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                _source_cache[path] = f.read().splitlines()
        except OSError:
            _source_cache[path] = []
    return _source_cache[path]


def enclosing_function(path, line):
    """Name of the nearest declaration above the line: the same code in two functions gives two findings."""
    lines = source_lines(path)
    start = min(line or 0, len(lines)) - 1
    if start < 0:
        return ""
    if path.endswith((".py", ".pyi")):
        m = PY_DECL.match(lines[start])
        if m:
            return m.group(2)
        indent = len(lines[start]) - len(lines[start].lstrip())
        for i in range(start - 1, -1, -1):
            text = lines[i]
            if not text.strip() or text.lstrip().startswith("#"):
                continue
            ind = len(text) - len(text.lstrip())
            if ind < indent:
                m = PY_DECL.match(text)
                if m:
                    return m.group(2)
                indent = ind
                if indent == 0:
                    return ""
        return ""
    # Brace languages: a declaration above encloses the line only if its block is still open at the line
    # (more { than } from the declaration down to the line above); a line after a closed function is outside.
    js = path.endswith(JS_EXT)
    depth = 0
    for i in range(start, -1, -1):
        text = lines[i]
        if i < start:
            depth += brace_delta(text)
        if i < start and depth <= 0:
            continue
        if js:
            for rx in JS_DECL:
                m = rx.match(text)
                if m:
                    return m.group(1)
        elif ";" not in text and not JVM_NOT_DECL.search(text):
            m = JVM_DECL.match(text)
            if m:
                return m.group(1)
    return ""


def load_json(path):
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except ValueError:
        return None


def load_meta(run):
    meta = load_json(os.path.join(run, "meta.json"))
    return {str(k): str(v) for k, v in meta.items()} if isinstance(meta, dict) else {}


def load_status(run):
    rows = []
    path = os.path.join(run, "status.tsv")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                parts = line.rstrip("\n").split("\t")
                if len(parts) == 3:
                    rows.append(parts)
    return rows


def md(text):
    return str(text).replace("|", "\\|").replace("`", "'").replace("\n", " ").strip()


def sev_key(sev):
    return SEVERITY_ORDER.get(str(sev).upper(), 9)


def norm_path(path):
    return os.path.normpath(path).replace(os.sep, "/")


# ------------------------------------------------------------------ comparison
def mark(head, base, key_fn, comparable):
    """Sets the status of HEAD findings; returns the base findings missing in HEAD (fixed in the branch)."""
    if not comparable:
        for item in head:
            item["status"] = UNKNOWN
        return []
    pool = collections.Counter(key_fn(b) for b in base)
    for item in head:
        k = key_fn(item)
        if pool[k] > 0:
            pool[k] -= 1
            item["status"] = EXISTING
        else:
            item["status"] = NEW
    fixed = []
    for b in base:
        k = key_fn(b)
        if pool[k] > 0:
            pool[k] -= 1
            fixed.append(b)
    return fixed


class Parts:
    """Status of each part from status.tsv: part -> (state, comment)."""

    def __init__(self, rows):
        self.rows = rows
        self.state = {}
        for stage, st, comment in rows:
            self.state[stage] = (st, comment)

    def get(self, part):
        return self.state.get(part, ("missing", "not run"))

    def ok(self, part):
        return self.get(part)[0] == "ok"

    def why_not_comparable(self, part):
        """None if HEAD and base of the part are ok, else the reason."""
        for name, label in ((part, "HEAD"), (part + "-base", "base")):
            st, comment = self.get(name)
            if st != "ok":
                return f"{label} {st}: {comment}"
        return None


# ------------------------------------------------------------------ SAST
def sast_findings(data, root):
    result = []
    if not data:
        return result
    for r in data.get("results", []) or []:
        path = r.get("path", "")
        full = path if os.path.isabs(path) else os.path.join(root, path)
        rel = norm_path(os.path.relpath(full, root))
        extra = r.get("extra", {}) or {}
        text = extra.get("lines", "") or ""
        line = (r.get("start") or {}).get("line")
        result.append({
            "func": enclosing_function(full, line),
            "rule": r.get("check_id", "").split(".")[-1],
            "rule_full": r.get("check_id", ""),
            "file": rel,
            "line": line,
            "key_text": text.strip(),
            "code": re.sub(r"\s+", " ", text).strip(),
            "severity": extra.get("severity", ""),
            "cwe": ", ".join(str(c).split(":")[0] for c in (extra.get("metadata", {}) or {}).get("cwe", []) or []),
            "message": extra.get("message", ""),
        })
    return result


def sast_key(x):
    return (x["rule_full"], x["file"], x["func"], x["key_text"])


# ------------------------------------------------------------------ SCA
def load_gradle_paths(deps_dir):
    """group:name:version -> path of origin (Gradle init script)."""
    paths = {}
    for tsv in sorted(glob.glob(os.path.join(deps_dir, "paths", "*.tsv"))):
        project = os.path.basename(tsv)[:-4]
        with open(tsv, encoding="utf-8") as f:
            for line in f:
                if "\t" in line:
                    key, path = line.rstrip("\n").split("\t", 1)
                    paths.setdefault(key, f"[{project}] {path}")
    return paths


def load_maven_tree(deps_dir):
    """group:name:version -> path from mvn dependency:tree."""
    paths = {}
    tree = os.path.join(deps_dir, "tree", "tree.txt")
    if not os.path.isfile(tree):
        return paths
    stack = []
    with open(tree, encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            m = re.match(r"^([| ]*[+\\]- )?(.*)$", line)
            prefix, coord = (m.group(1) or ""), m.group(2)
            depth = len(prefix) // 3
            parts = coord.split(":")
            if len(parts) < 4:
                continue
            # group:artifact:type:version[:scope], or group:artifact:type:classifier:version:scope
            gav = f"{parts[0]}:{parts[1]}:{parts[4] if len(parts) >= 6 else parts[3]}"
            stack = stack[:depth] + [gav]
            paths.setdefault(gav, " <- ".join(reversed(stack)))
    return paths


def graph_origin(result, pkg_id):
    """Path from a package to a direct dependency, from trivy's Packages[].DependsOn."""
    packages = result.get("Packages") or []
    by_id = {p.get("ID"): p for p in packages if p.get("ID")}
    if not any(p.get("DependsOn") for p in packages) and not any(p.get("Relationship") for p in packages):
        return "direct/transitive: unknown (no dependency graph in the lock file)"
    parents = collections.defaultdict(list)
    for p in packages:
        for d in p.get("DependsOn") or []:
            parents[d].append(p.get("ID"))
    me = by_id.get(pkg_id, {})
    if me.get("Relationship") in ("direct", "root"):
        return "direct dependency"
    queue, seen = [[pkg_id]], {pkg_id}
    while queue:
        path = queue.pop(0)
        for parent in sorted(parents.get(path[-1], [])):
            if parent in seen:
                continue
            seen.add(parent)
            rel = by_id.get(parent, {}).get("Relationship")
            if rel in ("direct", "root"):
                chain = path + [parent] if rel == "direct" else path
                return " <- ".join(chain) + (" (direct)" if rel == "direct" else "")
            queue.append(path + [parent])
    return "transitive: path not found in the dependency graph"


def sca_findings(data, origin=None, jvm=False):
    found = {}
    if not data:
        return []
    for res in data.get("Results", []) or []:
        rtype = res.get("Type", "")
        target = JVM_TARGET if jvm else norm_path(res.get("Target", ""))
        for v in res.get("Vulnerabilities", []) or []:
            pkg, ver, vid = v.get("PkgName", ""), v.get("InstalledVersion", ""), v.get("VulnerabilityID", "")
            key = (rtype, target, pkg, ver, vid)
            item = found.get(key)
            if item is None:
                if jvm:
                    where = (origin or {}).get(f"{pkg}:{ver}", "") or "path not found"
                else:
                    where = graph_origin(res, v.get("PkgID") or f"{pkg}@{ver}")
                item = {
                    "type": rtype, "target": target, "pkg": pkg, "version": ver, "id": vid,
                    "severity": v.get("Severity", ""), "fixed": v.get("FixedVersion", "") or "-",
                    "title": (v.get("Title") or "")[:90], "modules": set(), "origin": where,
                }
                found[key] = item
            if jvm:
                pkg_path = norm_path(v.get("PkgPath", "") or res.get("Target", ""))
                m = re.search(r"jars/([^/]+)/", pkg_path)
                module = m.group(1) if m else (pkg_path.split("/")[0] if "/" in pkg_path else "")
                if module:
                    item["modules"].add(module)
    return sorted(found.values(), key=lambda x: (sev_key(x["severity"]), x["pkg"], x["id"], x["target"]))


def sca_key(x):
    return (x["type"], x["target"], x["pkg"], x["id"])


def lock_limitations(inventory, data):
    """Lock files trivy did not recognize, unpinned requirements, unsupported lock formats."""
    notes = []
    if not inventory:
        return notes
    targets = {norm_path(r.get("Target", "")) for r in (data or {}).get("Results", []) or []}
    if data is not None:
        for path in inventory.get("lockfiles", []):
            if norm_path(path) not in targets:
                notes.append(f"`{md(path)}`: trivy recognized no packages in it; its dependencies are not checked")
    for item in inventory.get("unpinned", []):
        notes.append(f"`{md(item['path'])}`: {item['lines']} requirement(s) without a pinned `==` version are not checked")
    for path in inventory.get("unsupported_locks", []):
        notes.append(f"`{md(path)}`: lock file format not scanned by appsec-scan")
    return notes


# ------------------------------------------------------------------ images
def image_findings(data):
    rows = []
    if not data:
        return rows, ""
    image = data.get("ArtifactName", "")
    os_info = (data.get("Metadata", {}) or {}).get("OS", {}) or {}
    os_name = f"{os_info.get('Family', '')} {os_info.get('Name', '')}".strip()
    for res in data.get("Results", []) or []:
        for v in res.get("Vulnerabilities", []) or []:
            rows.append({
                "class": "OS" if res.get("Class") == "os-pkgs" else "library",
                "target": res.get("Target", ""),
                "pkg": v.get("PkgName", ""), "version": v.get("InstalledVersion", ""),
                "fixed": v.get("FixedVersion", "") or "-", "id": v.get("VulnerabilityID", ""),
                "severity": v.get("Severity", ""), "title": (v.get("Title") or "")[:80],
            })
    rows.sort(key=lambda x: (x["class"] != "OS", sev_key(x["severity"]), x["pkg"], x["id"]))
    return rows, f"{image} ({os_name})" if os_name else image


def counts(items):
    c = collections.Counter(str(i["severity"]).upper() for i in items)
    return ", ".join(f"{k} {c[k]}" for k in sorted(c, key=sev_key)) or "0"


def build(run):
    meta = load_meta(run)
    parts = Parts(load_status(run))
    out = []
    w = out.append

    trivy_ver = load_json(os.path.join(run, "trivy-version.json")) or {}
    db = trivy_ver.get("VulnerabilityDB", {}) or {}
    og_path = os.path.join(run, "opengrep.release")
    opengrep_rel = open(og_path, encoding="utf-8").read().strip() if os.path.isfile(og_path) else ""
    inv_head = load_json(os.path.join(run, "inv-head", "inventory.json")) or {}

    w(f"# appsec-scan: {meta.get('NAME', '?')}")
    w("")
    dirty = meta.get("DIRTY", "0")
    w(f"- Branch: `{md(meta.get('BRANCH', '?'))}` @ `{meta.get('HEAD_SHA', '')[:10]}`"
      + (f", **{dirty} uncommitted change(s)**: the working tree is scanned" if dirty not in ("", "0") else ""))
    if meta.get("BASE_SHA"):
        w(f"- Base for new vs existing: `{md(meta.get('BASE_REF'))}` merge-base `{meta.get('BASE_SHA', '')[:10]}` (local ref, no fetch)")
    else:
        w(f"- Base: not compared ({md(parts.get('base')[1])}); findings are marked `?`")
    rules = meta.get("RULES", "registry")
    rules_text = ("Semgrep registry rules (Semgrep Rules License v1.0, internal use only)" if rules == "registry"
                  else f"custom rules `{md(rules[len('custom '):])}`")
    w(f"- Build: {meta.get('BUILD', 'none')}; SAST languages: {meta.get('LANGS') or '-'}; {rules_text}")
    w(f"- Tools: opengrep {opengrep_rel or '?'} (`--taint-intrafile`), trivy {trivy_ver.get('Version', '?')}, "
      f"trivy database from {str(db.get('UpdatedAt', '?'))[:10]}")
    w("")

    problems = [r for r in parts.rows if r[1] == "fail"]
    if problems:
        w("## Parts that failed")
        w("")
        for stage, st, comment in problems:
            w(f"- `{stage}`: **{st}** - {md(comment)}")
        w("")

    external = inv_head.get("external_symlinks", [])
    if external:
        w("## Symlinks to outside the repository (not scanned)")
        w("")
        for s in external:
            effect = f"blocks the {s['critical']} part" if s.get("critical") else "excluded from the scan"
            w(f"- `{md(s['path'])}` -> `{md(s['target'])}`: {effect}")
        w("")

    # SAST
    head_sast = sast_findings(load_json(os.path.join(run, "sast-head.json")), meta.get("REPO", ""))
    base_sast = sast_findings(load_json(os.path.join(run, "sast-base.json")), os.path.join(run, "base-src"))
    sast_why = parts.why_not_comparable("sast")
    fixed_sast = mark(head_sast, base_sast, sast_key, sast_why is None)
    head_sast.sort(key=lambda x: (x["status"] != NEW, sev_key(x["severity"]), x["file"], x["line"] or 0))
    new_sast = [x for x in head_sast if x["status"] == NEW]
    sast_state = parts.get("sast")
    if sast_state[0] == "skip":
        w(f"## SAST: not applicable ({md(sast_state[1])})")
    elif sast_state[0] != "ok" and not head_sast:
        w("## SAST: not run (see \"Parts that failed\")")
    else:
        w(f"## SAST: {len(head_sast)} finding(s), new: {len(new_sast) if sast_why is None else '?'}"
          + ("" if sast_state[0] == "ok" else " - HEAD scan incomplete"))
    w("")
    if sast_why is not None and sast_state[0] != "skip":
        w(f"Comparison unavailable: {md(sast_why)}")
        w("")
    if head_sast:
        w("| Status | Severity | Rule | CWE | File:line | Function | Code |")
        w("|---|---|---|---|---|---|---|")
        for x in head_sast:
            w(f"| {x['status']} | {x['severity']} | `{md(x['rule'])}` | {md(x['cwe'])} | `{md(x['file'])}:{x['line']}` "
              f"| `{md(x['func'])}` | `{md(x['code'])[:110]}` |")
        w("")
    if fixed_sast:
        w(f"Fixed in the branch (in the base, not in HEAD): {len(fixed_sast)}")
        w("")
        for x in fixed_sast:
            w(f"- `{md(x['rule'])}` `{md(x['file'])}` function `{md(x['func'])}` (base line {x['line']}): `{md(x['code'])[:110]}`")
        w("")

    # SCA: the JVM part (build) and the lock file part are compared separately
    deps_head = os.path.join(run, "deps-head")
    origin = load_gradle_paths(deps_head)
    for k, v in load_maven_tree(deps_head).items():
        origin.setdefault(k, v)
    native_head_data = load_json(os.path.join(run, "sca-native-head.json"))
    sca_parts = [
        ("sca", "JVM", sca_findings(load_json(os.path.join(run, "sca-head.json")), origin, jvm=True),
         sca_findings(load_json(os.path.join(run, "sca-base.json")), {}, jvm=True)),
        ("sca-native", "lock files", sca_findings(native_head_data),
         sca_findings(load_json(os.path.join(run, "sca-native-base.json")))),
    ]
    all_sca, fixed_all, sca_new_total, sca_ran, sca_compared = [], [], 0, False, True
    notes = []
    for part, label, head, base in sca_parts:
        state = parts.get(part)
        why = parts.why_not_comparable(part)
        fixed = mark(head, base, sca_key, why is None)
        if state[0] == "ok":
            sca_ran = True
        if state[0] != "skip" and why is not None:
            sca_compared = False
            notes.append(f"{label} ({part}): comparison unavailable: {md(why)}")
        for x in head:
            x["part"] = label
        all_sca += head
        fixed_all += fixed
        sca_new_total += sum(1 for x in head if x["status"] == NEW)
    limits = lock_limitations(inv_head, native_head_data if parts.ok("sca-native") else None)
    sca_states = [parts.get(p)[0] for p, _, _, _ in sca_parts]
    if all(s == "skip" for s in sca_states):
        w("## SCA: not applicable (no Gradle/Maven build and no supported lock file)")
    elif not sca_ran and not all_sca:
        w("## SCA: not run (see \"Parts that failed\")")
    else:
        w(f"## SCA: {len(all_sca)} vulnerabilit(ies) ({counts(all_sca)}), new: {sca_new_total if sca_compared else '?'}"
          + (" - some parts failed" if "fail" in sca_states else ""))
    w("")
    for n in notes:
        w(f"- {n}")
    if notes:
        w("")
    if limits:
        w("Limitations:")
        w("")
        for n in limits:
            w(f"- {n}")
        w("")
    all_sca.sort(key=lambda x: (x["status"] != NEW, sev_key(x["severity"]), x["pkg"], x["id"]))
    if all_sca:
        w("| Status | Severity | Package | Version | Fixed in | Vulnerability | Where | Title |")
        w("|---|---|---|---|---|---|---|---|")
        for x in all_sca:
            where = x["target"] if x["part"] != "JVM" else "JVM " + JVM_TARGET
            w(f"| {x['status']} | {x['severity']} | `{md(x['pkg'])}` | {md(x['version'])} | {md(x['fixed'])} | {md(x['id'])} "
              f"| `{md(where)}` | {md(x['title'])} |")
        w("")
        w("Where the vulnerable packages come from:")
        w("")
        seen = set()
        for x in all_sca:
            key = (x["part"], x["target"], x["pkg"], x["version"])
            if key in seen:
                continue
            seen.add(key)
            mods = f" (modules: {', '.join(sorted(x['modules']))})" if x["modules"] else ""
            w(f"- `{md(x['pkg'])}:{md(x['version'])}`{mods}: {md(x['origin'])}")
        w("")
    if fixed_all:
        w("Fixed in the branch: " + ", ".join(sorted({f"{x['pkg']} {x['id']}" for x in fixed_all})))
        w("")

    # Images: a full snapshot, there is no base image to compare with
    image_files = sorted(glob.glob(os.path.join(run, "docker-*.json")))
    image_total = 0
    for path in image_files:
        rows, title = image_findings(load_json(path))
        image_total += len(rows)
        w(f"## Image {md(title or os.path.basename(path))}: {len(rows)} vulnerabilit(ies) ({counts(rows)})")
        w("")
        w("Full snapshot of the image, not compared with a base.")
        w("")
        if rows:
            w("| Severity | Layer | Package | Version | Fixed in | Vulnerability | Title |")
            w("|---|---|---|---|---|---|---|")
            for x in rows[:DOCKER_ROW_LIMIT]:
                w(f"| {x['severity']} | {x['class']} | `{md(x['pkg'])}` | {md(x['version'])} | {md(x['fixed'])} | {md(x['id'])} | {md(x['title'])} |")
            if len(rows) > DOCKER_ROW_LIMIT:
                w(f"| ... | | | | | | {len(rows) - DOCKER_ROW_LIMIT} more in `{os.path.basename(path)}` |")
            w("")
    docker_state = parts.get("docker")
    if not image_files and docker_state[0] == "skip":
        w(f"## Images: {md(docker_state[1])}")
        w("")

    w("---")
    w(f"Artifacts: `{run}` (sast-*.json, sca-*.json, docker-*.json, status.tsv, scan.log).")
    w("Results depend on the rule set and the CVE database: other scanners may find more or less, and rate severity differently.")

    summary = {
        "repo": meta.get("NAME"), "branch": meta.get("BRANCH"), "dirty": meta.get("DIRTY"),
        "sast_total": len(head_sast), "sast_new": len(new_sast) if sast_why is None else None,
        "sca_total": len(all_sca) if sca_ran else None,
        "sca_new": sca_new_total if (sca_ran and sca_compared) else None,
        "sca_counts": counts(all_sca) if sca_ran else "",
        "images_total": image_total if image_files else None,
        "problems": [f"{stage}: {comment}" for stage, st, comment in problems],
        "findings": {
            "sast": [{"status": x["status"], "rule": x["rule_full"], "file": x["file"], "line": x["line"], "func": x["func"]}
                     for x in head_sast],
            "sast_fixed": [{"rule": x["rule_full"], "file": x["file"], "func": x["func"]} for x in fixed_sast],
            "sca": [{"status": x["status"], "type": x["type"], "target": x["target"], "pkg": x["pkg"], "version": x["version"],
                     "id": x["id"], "origin": x["origin"]} for x in all_sca],
            "sca_fixed": [{"type": x["type"], "target": x["target"], "pkg": x["pkg"], "id": x["id"]} for x in fixed_all],
        },
    }
    return "\n".join(out), summary


def main():
    run = sys.argv[1]
    text, summary = build(run)
    print(text)
    with open(os.path.join(run, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()

"""Helpers for scan.sh. Standard library only, Python 3.9+.

    helpers.py inventory git|tree ROOT OUT    file inventory of ROOT into OUT/inventory.json, lock files staged in OUT/locks
    helpers.py get FILE KEY                   print a JSON value (a list is printed NUL-separated)
    helpers.py check-sast FILE                exit 0 if FILE is an opengrep JSON report without errors, else print the reason
    helpers.py check-trivy FILE               exit 0 if FILE is a trivy JSON report, else print the reason
    helpers.py version-ge A B                 exit 0 if version A >= B
    helpers.py docker-name TEXT               normalize TEXT to [a-z0-9._-], at most 128 characters
    helpers.py meta OUT KEY VALUE...          write the run metadata as JSON
    helpers.py glob-escape TEXT               escape glob metacharacters
"""
import json
import os
import re
import shutil
import subprocess
import sys

LANG_EXT = {
    "java": (".java",),
    "kotlin": (".kt", ".kts"),
    "golang": (".go",),
    "rust": (".rs",),
    "python": (".py", ".pyi"),
    "javascript": (".js", ".jsx", ".mjs", ".cjs"),
    "typescript": (".ts", ".tsx", ".mts", ".cts"),
}
# Lock files scanned by `trivy fs`, and the trivy result type each one gives.
LOCK_FILES = {
    "package-lock.json": "npm", "yarn.lock": "yarn", "pnpm-lock.yaml": "pnpm",
    "poetry.lock": "poetry", "uv.lock": "uv", "Pipfile.lock": "pipenv",
    "go.mod": "gomod", "Cargo.lock": "cargo",
}
REQUIREMENTS = re.compile(r"^requirements[^/]*\.txt$")
# Manifests staged next to lock files: trivy uses them to mark direct dependencies.
MANIFESTS = {"package.json", "go.sum", "Cargo.toml", "pyproject.toml", "Pipfile"}
# Lock files of ecosystems this skill does not scan: reported as a limitation, never as zero findings.
UNSUPPORTED_LOCKS = {
    "bun.lock", "bun.lockb", "deno.lock", "npm-shrinkwrap.json", "composer.lock", "Gemfile.lock",
    "packages.lock.json", "mix.lock", "pubspec.lock", "Package.resolved", "Podfile.lock", "conan.lock",
}
GRADLE_NAMES = {"gradlew", "gradlew.bat", "gradle.properties"}
MAVEN_NAMES = {"mvnw", "mvnw.cmd", "pom.xml", "settings.xml"}
DOCKERFILE = re.compile(r"^(?:Dockerfile[^/]*|[^/]*\.Dockerfile)$", re.IGNORECASE)


def git_files(root):
    out = subprocess.run(["git", "-C", root, "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                         check=True, stdout=subprocess.PIPE).stdout
    seen = set()
    for raw in out.split(b"\0"):
        if raw:
            rel = os.fsdecode(raw)
            if rel not in seen:
                seen.add(rel)
                yield rel


def tree_files(root):
    for top, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if d != ".git" and not os.path.islink(os.path.join(top, d))]
        # Symlinks to directories are listed by os.walk among dirs; take them as files to check where they point.
        for d in os.listdir(top):
            full = os.path.join(top, d)
            if os.path.islink(full) and os.path.isdir(full):
                files.append(d)
        for f in files:
            yield os.path.relpath(os.path.join(top, f), root)


def critical_kind(rel):
    """Which part a symlink to outside the repository breaks, or None if it is only excluded from the scan."""
    name = os.path.basename(rel)
    parts = rel.split("/")
    if name in GRADLE_NAMES or name.endswith((".gradle", ".gradle.kts")) or parts[0] == "gradle":
        return "gradle"
    if name in MAVEN_NAMES or parts[0] == ".mvn":
        return "maven"
    if name in LOCK_FILES or name in MANIFESTS or REQUIREMENTS.match(name):
        return "lockfile"
    if DOCKERFILE.match(name):
        return "dockerfile"
    return None


def inside(path, root):
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def unpinned_lines(path):
    count = 0
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.split("#", 1)[0].strip()
            if not line or line.startswith("-"):
                continue
            if "==" not in line:
                count += 1
    return count


def inventory(mode, root, out):
    root_real = os.path.realpath(root)
    files = git_files(root) if mode == "git" else tree_files(root)
    langs, lockfiles, dockerfiles, external, unsupported, unpinned = set(), [], [], [], [], []
    regular = set()
    for rel in files:
        full = os.path.join(root, rel)
        if not os.path.lexists(full):
            continue  # deleted in the working tree
        # realpath covers the path itself and every parent directory: a tracked file under a directory that was
        # replaced by a symlink to outside the repository is outside too, and is neither read nor scanned
        real = os.path.realpath(full)
        if not inside(real, root_real):
            target = os.readlink(full) if os.path.islink(full) else real
            external.append({"path": rel, "target": target, "critical": critical_kind(rel)})
            continue
        if not os.path.isfile(full):
            continue
        regular.add(rel)
        name = os.path.basename(rel)
        for lang, exts in LANG_EXT.items():
            if name.endswith(exts):
                langs.add(lang)
        if name in LOCK_FILES or REQUIREMENTS.match(name):
            lockfiles.append(rel)
            if REQUIREMENTS.match(name):
                n = unpinned_lines(full)
                if n:
                    unpinned.append({"path": rel, "lines": n})
        elif name in UNSUPPORTED_LOCKS:
            unsupported.append(rel)
        if DOCKERFILE.match(name):
            dockerfiles.append(rel)

    build = "none"
    if regular & {"gradlew", "settings.gradle", "settings.gradle.kts", "build.gradle", "build.gradle.kts"}:
        build = "gradle"
    elif "pom.xml" in regular:
        build = "maven"

    locks_dir = os.path.join(out, "locks")
    os.makedirs(locks_dir, exist_ok=True)
    staged_dirs = {os.path.dirname(p) for p in lockfiles}
    for rel in sorted(regular):
        name = os.path.basename(rel)
        if rel in lockfiles or (name in MANIFESTS and os.path.dirname(rel) in staged_dirs):
            dst = os.path.join(locks_dir, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(os.path.join(root, rel), dst)

    data = {
        "langs": sorted(langs), "build": build, "lockfiles": sorted(lockfiles),
        "lock_types": {p: ("pip" if REQUIREMENTS.match(os.path.basename(p)) else LOCK_FILES[os.path.basename(p)])
                       for p in lockfiles},
        "unsupported_locks": sorted(unsupported), "unpinned": unpinned, "dockerfiles": sorted(dockerfiles),
        "external_symlinks": sorted(external, key=lambda x: x["path"]),
    }
    with open(os.path.join(out, "inventory.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    with open(os.path.join(out, "external.lst"), "wb") as f:
        for item in data["external_symlinks"]:
            f.write(os.fsencode(item["path"]) + b"\0")


def get(path, key):
    with open(path, encoding="utf-8") as f:
        value = json.load(f)
    for part in key.split("."):
        value = value.get(part) if isinstance(value, dict) else None
    if value is None:
        return 1
    if isinstance(value, list):
        sys.stdout.write("".join((json.dumps(v) if isinstance(v, dict) else str(v)) + "\0" for v in value))
    else:
        sys.stdout.write(str(value))
    return 0


def load(path):
    if not os.path.isfile(path):
        print("no output file")
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (ValueError, UnicodeDecodeError) as e:
        print(f"output is not valid JSON ({e.__class__.__name__})")
        return None


def check_sast(path):
    data = load(path)
    if data is None:
        return 1
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        print("output has no results list")
        return 1
    errors = data.get("errors") or []
    if errors:
        first = errors[0] if isinstance(errors[0], dict) else {}
        msg = re.sub(r"\s+", " ", str(first.get("message") or first.get("type") or "")).strip()[:160]
        print(f"opengrep reported {len(errors)} error(s): {msg}")
        return 1
    return 0


def check_trivy(path):
    data = load(path)
    if data is None:
        return 1
    if not isinstance(data, dict) or "SchemaVersion" not in data:
        print("output is not a trivy JSON report")
        return 1
    return 0


def version_tuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


def main(argv):
    cmd, args = argv[1], argv[2:]
    if cmd == "inventory":
        inventory(*args)
        return 0
    if cmd == "get":
        return get(*args)
    if cmd == "check-sast":
        return check_sast(*args)
    if cmd == "check-trivy":
        return check_trivy(*args)
    if cmd == "version-ge":
        return 0 if version_tuple(args[0]) >= version_tuple(args[1]) else 1
    if cmd == "docker-name":
        name = re.sub(r"[^a-z0-9._-]+", "-", args[0].lower()).strip("._-")
        print((name or "image")[:128].rstrip("._-") or "image")
        return 0
    if cmd == "meta":
        # meta OUT KEY VALUE...: run metadata as JSON, so any value (a path with a newline) survives
        with open(args[0], "w", encoding="utf-8") as f:
            json.dump(dict(zip(args[1::2], args[2::2])), f, indent=1)
        return 0
    if cmd == "glob-escape":
        sys.stdout.write(re.sub(r"([\\*?\[\]!])", r"\\\1", args[0]))
        return 0
    print(f"unknown command {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))

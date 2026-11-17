#!/usr/bin/env bash
# Builds a fixture repository for the appsec-scan tests: bash fixtures.sh KIND DIR
# Repositories with history have a base commit on `main` and a HEAD commit on `feature`: the base holds one old
# vulnerable dependency and one SAST finding that stay, plus one of each that HEAD removes; HEAD adds one new of each.
# Package versions are pinned to releases with long-known CVEs (see expect/*.json).
set -euo pipefail
KIND=$1
DIR=$2
mkdir -p "$DIR"
cd "$DIR"

g() { git -c user.name=fixture -c user.email=fixture@example.invalid -c commit.gpgsign=false -c core.hooksPath=/dev/null "$@"; }
init() { g init -q -b main .; }
commit() { g add -A && g commit -q -m "$1"; }
feature() { g checkout -q -b feature; }

# SAST sources: keep() stays, drop() is removed in HEAD, added() is new; HEAD inserts lines above keep() (line shift).
py_base() { printf 'def keep(a):\n    return eval(a)\n\n\ndef drop(b):\n    return eval(b)\n' > "$1"; }
py_head() { printf '"""HEAD shifts lines."""\n\n\ndef keep(a):\n    return eval(a)\n\n\ndef added(c):\n    return eval(c)\n' > "$1"; }
js_base() { printf 'function keep(a) {\n  return eval(a)\n}\n\nfunction drop(b) {\n  return eval(b)\n}\n' > "$1"; }
js_head() { printf '// HEAD shifts lines\n\nfunction keep(a) {\n  return eval(a)\n}\n\nconst added = (c) => {\n  return eval(c)\n}\n' > "$1"; }

npm_lock() {  # npm_lock WITH_MINIMIST WITH_FETCH
    local deps='"lodash": "4.17.15"' pkgs='"node_modules/lodash": {"version": "4.17.15"}'
    if [[ $1 == 1 ]]; then deps="$deps, \"minimist\": \"1.2.0\""; pkgs="$pkgs, \"node_modules/minimist\": {\"version\": \"1.2.0\"}"; fi
    if [[ $2 == 1 ]]; then
        deps="$deps, \"fetch-helper\": \"1.0.0\""
        pkgs="$pkgs, \"node_modules/fetch-helper\": {\"version\": \"1.0.0\", \"dependencies\": {\"node-fetch\": \"2.6.0\"}}"
        pkgs="$pkgs, \"node_modules/node-fetch\": {\"version\": \"2.6.0\"}"
    fi
    printf '{"name": "fixture", "version": "1.0.0", "dependencies": {%s}}\n' "$deps" > package.json
    printf '{"name": "fixture", "version": "1.0.0", "lockfileVersion": 3, "requires": true, "packages": {"": {"name": "fixture", "version": "1.0.0", "dependencies": {%s}}, %s}}\n' \
        "$deps" "$pkgs" > package-lock.json
}

go_mod() {  # go_mod SECOND_REQUIRE
    printf 'module example.com/fixture\n\ngo 1.21\n\nrequire (\n\tgolang.org/x/text v0.3.0\n\t%s\n)\n' "$1" > go.mod
}
go_src() {  # go_src NAMES...
    { printf 'package main\n\nimport "os/exec"\n\n'
      for n in "$@"; do printf 'func %s(c string) {\n\t_ = exec.Command(c)\n}\n\n' "$n"; done
      printf 'func main() {}\n'; } > main.go
}

cargo_lock() {  # cargo_lock CRATE VERSION...
    { printf 'version = 3\n\n[[package]]\nname = "fixture"\nversion = "0.1.0"\ndependencies = [\n'
      local i
      for ((i = 1; i <= $#; i += 2)); do printf ' "%s",\n' "${!i}"; done
      printf ']\n'
      for ((i = 1; i <= $#; i += 2)); do
          local j=$((i + 1))
          printf '\n[[package]]\nname = "%s"\nversion = "%s"\nsource = "registry+https://github.com/rust-lang/crates.io-index"\n' "${!i}" "${!j}"
      done; } > Cargo.lock
    { printf '[package]\nname = "fixture"\nversion = "0.1.0"\nedition = "2021"\n\n[dependencies]\n'
      for ((i = 1; i <= $#; i += 2)); do local j=$((i + 1)); printf '%s = "=%s"\n' "${!i}" "${!j}"; done; } > Cargo.toml
}
rust_src() {
    mkdir -p src
    { printf 'use std::process::Command;\n\n'
      for n in "$@"; do printf 'fn %s(c: &str) {\n    let _ = Command::new(c);\n}\n\n' "$n"; done
      printf 'fn main() {}\n'; } > src/main.rs
}

java_src() {
    mkdir -p src/main/java/fixture
    { printf 'package fixture;\n\npublic class App {\n'
      for n in "$@"; do printf '    public void %s(String c) throws Exception {\n        Runtime.getRuntime().exec(c);\n    }\n\n' "$n"; done
      printf '}\n'; } > src/main/java/fixture/App.java
}
gradle_build() {  # gradle_build DEPENDENCY...
    printf "rootProject.name = 'fixture'\n" > settings.gradle
    { printf "plugins {\n    id 'java'\n}\n\nrepositories {\n    mavenCentral()\n}\n\ndependencies {\n"
      local d
      for d in "$@"; do printf "    implementation '%s'\n" "$d"; done
      printf "}\n"; } > build.gradle
}
maven_pom() {  # maven_pom GROUP:ARTIFACT:VERSION...
    { printf '<project xmlns="http://maven.apache.org/POM/4.0.0">\n  <modelVersion>4.0.0</modelVersion>\n'
      printf '  <groupId>fixture</groupId>\n  <artifactId>fixture</artifactId>\n  <version>1.0.0</version>\n'
      printf '  <properties>\n    <maven.compiler.source>17</maven.compiler.source>\n    <maven.compiler.target>17</maven.compiler.target>\n'
      printf '    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>\n  </properties>\n  <dependencies>\n'
      local d g a v
      for d in "$@"; do
          IFS=: read -r g a v <<< "$d"
          printf '    <dependency><groupId>%s</groupId><artifactId>%s</artifactId><version>%s</version></dependency>\n' "$g" "$a" "$v"
      done
      printf '  </dependencies>\n  <build>\n    <plugins>\n'
      printf '      <plugin><groupId>org.apache.maven.plugins</groupId><artifactId>maven-compiler-plugin</artifactId><version>3.13.0</version></plugin>\n'
      printf '    </plugins>\n  </build>\n</project>\n'; } > pom.xml
}

case "$KIND" in
    npm)
        init; js_base app.js; npm_lock 1 0; commit base
        feature; js_head app.js; npm_lock 0 1; commit head ;;
    python)
        init; py_base app.py; printf 'jinja2==2.10\npyyaml==5.3\n' > requirements.txt; commit base
        feature; py_head app.py; printf 'jinja2==2.10\nrequests==2.19.0\nflask\n' > requirements.txt; commit head ;;
    go)
        init; go_mod 'github.com/dgrijalva/jwt-go v3.2.0+incompatible'; go_src keep drop; commit base
        feature; go_mod 'gopkg.in/yaml.v2 v2.2.2'; go_src keep added; commit head ;;
    cargo)
        init; cargo_lock smallvec 1.6.0 time 0.1.43; rust_src keep drop; commit base
        feature; cargo_lock smallvec 1.6.0 regex 1.5.4; rust_src keep added; commit head ;;
    gradle)
        init; gradle_build commons-collections:commons-collections:3.2.1 org.apache.commons:commons-text:1.9; java_src keep drop; commit base
        feature; gradle_build commons-collections:commons-collections:3.2.1 org.yaml:snakeyaml:1.33; java_src keep added; commit head ;;
    gradle-unresolved)
        init; gradle_build commons-collections:commons-collections:3.2.1; java_src keep; commit base
        feature; gradle_build commons-collections:commons-collections:3.2.1 com.example.appsec.fixture:does-not-exist:1.0; commit head ;;
    maven)
        init; maven_pom commons-collections:commons-collections:3.2.1 org.apache.commons:commons-text:1.9; java_src keep drop; commit base
        feature; maven_pom commons-collections:commons-collections:3.2.1 org.yaml:snakeyaml:1.33; java_src keep added; commit head ;;
    formats)
        # One lock file of every supported format, each pinning a package with a known CVE; one unsupported format.
        init
        mkdir -p npm yarn pnpm pip poetry uv pipenv composer
        (cd npm && npm_lock 0 0)
        printf '# yarn lockfile v1\n\n\nlodash@4.17.15:\n  version "4.17.15"\n  resolved "https://registry.yarnpkg.com/lodash/-/lodash-4.17.15.tgz"\n' > yarn/yarn.lock
        printf '{"name": "fixture", "version": "1.0.0", "dependencies": {"lodash": "4.17.15"}}\n' > yarn/package.json
        printf "lockfileVersion: '6.0'\n\ndependencies:\n  lodash:\n    specifier: 4.17.15\n    version: 4.17.15\n\npackages:\n\n  /lodash@4.17.15:\n    resolution: {integrity: sha512-8xOcRHvCjnocdS5cpwXQXVzmmh5e5+saE2QGoeQmbKmRS6J3VQppPOIt0MnmE+4xlZoumy0GPG0D0MVIQbNA1A==}\n    dev: false\n" > pnpm/pnpm-lock.yaml
        printf 'pyyaml==5.3\n' > pip/requirements.txt
        printf '[[package]]\nname = "pyyaml"\nversion = "5.3"\ndescription = "YAML parser and emitter for Python"\noptional = false\npython-versions = "*"\nfiles = []\n\n[metadata]\nlock-version = "2.0"\npython-versions = "^3.9"\ncontent-hash = "0"\n' > poetry/poetry.lock
        printf '[tool.poetry]\nname = "fixture"\nversion = "0.1.0"\ndescription = ""\nauthors = []\n\n[tool.poetry.dependencies]\npython = "^3.9"\npyyaml = "5.3"\n' > poetry/pyproject.toml
        printf 'version = 1\nrequires-python = ">=3.9"\n\n[[package]]\nname = "fixture"\nversion = "0.1.0"\nsource = { virtual = "." }\ndependencies = [\n    { name = "pyyaml" },\n]\n\n[[package]]\nname = "pyyaml"\nversion = "5.3"\nsource = { registry = "https://pypi.org/simple" }\n' > uv/uv.lock
        printf '[project]\nname = "fixture"\nversion = "0.1.0"\nrequires-python = ">=3.9"\ndependencies = ["pyyaml==5.3"]\n' > uv/pyproject.toml
        printf '{"_meta": {"hash": {"sha256": "0"}, "pipfile-spec": 6, "requires": {}, "sources": []}, "default": {"pyyaml": {"version": "==5.3"}}, "develop": {}}\n' > pipenv/Pipfile.lock
        printf '{"packages": [], "packages-dev": []}\n' > composer/composer.lock
        commit formats ;;
    docker)
        # An old, still supported base image (OS package CVEs) with an installed npm package (library CVEs)
        init; npm_lock 0 0
        mkdir -p node_modules/lodash
        printf '{"name": "lodash", "version": "4.17.15"}\n' > node_modules/lodash/package.json
        printf 'FROM alpine:3.20.0\nCOPY node_modules /app/node_modules\n' > Dockerfile
        commit docker ;;
    r7-names)
        # Hostile file and directory names: the scan must pass and must not create the marker file.
        init
        mkdir -p -- '-rf' '--help' 'dir with space'
        py_base 'dir with space/a b.py'
        py_base "quote'\"q.py"
        py_base '$(touch MARKER-subst).py'
        py_base "$(printf 'new\nline.py')"
        py_base ./-rf/-rf.py
        py_base ./--help/--help.py
        py_base ./-rf.py
        py_base ./--help.py
        commit names ;;
    r7-gradlew)
        # gradlew is a symlink to a script outside the repository that creates a marker: it must never run.
        init
        outside="$(cd .. && pwd -P)/outside-gradlew"
        printf '#!/bin/sh\ntouch "%s/MARKER-gradlew"\n' "$(cd .. && pwd -P)" > "$outside"
        chmod 755 "$outside"
        ln -s "$outside" gradlew
        gradle_build commons-collections:commons-collections:3.2.1; java_src keep
        commit symlink ;;
    r7-lock)
        # package-lock.json is a symlink to an unreadable trap file outside the repository: trivy fs must not run.
        init
        trap_file="$(cd .. && pwd -P)/trap-lock.json"
        printf '{"trap": true}\n' > "$trap_file"
        chmod 000 "$trap_file"
        ln -s "$trap_file" package-lock.json
        printf '{"name": "fixture", "version": "1.0.0"}\n' > package.json
        js_base app.js
        # a source file that is a symlink to outside code: excluded from SAST, listed in the report
        printf 'def evil(x):\n    return eval(x)\n' > "$(cd .. && pwd -P)/outside-evil.py"
        ln -s "$(cd .. && pwd -P)/outside-evil.py" evil.py
        commit symlink ;;
    r7-parent)
        # deps/ is committed with a lock file, then replaced in the working tree by a symlink to outside:
        # the lock file is a regular file under an external directory and must not be read
        init; py_base app.py
        mkdir -p deps; printf 'pyyaml==5.3\n' > deps/requirements.txt
        commit parent
        outside="$(cd .. && pwd -P)/outside-deps"
        mkdir -p "$outside"; printf 'jinja2==2.10\nunpinned-outside\n' > "$outside/requirements.txt"
        rm -rf deps; ln -s "$outside" deps ;;
    r7-dockerfile)
        # the only Dockerfile is a symlink to outside: --docker-build must fail without building
        init; npm_lock 0 0
        printf 'FROM alpine:3.20.0\nRUN touch /MARKER-dockerfile\n' > "$(cd .. && pwd -P)/outside-Dockerfile"
        ln -s "$(cd .. && pwd -P)/outside-Dockerfile" Dockerfile
        commit symlink ;;
    samename-gradle|samename-maven)
        # Two components g1:lib:1.0 and g2:lib:1.0 in a local repository, both files named lib-1.0.jar; each jar
        # carries the pom.properties of a different vulnerable package, so losing one jar loses its CVEs.
        init
        python3 -I - "$PWD/m2" <<'PYJAR'
import os, sys, zipfile
root = sys.argv[1]
for group, (g, a, v) in (("one", ("org.apache.commons", "commons-text", "1.9")), ("two", ("org.yaml", "snakeyaml", "1.33"))):
    d = os.path.join(root, "appsec", "fixture", group, "lib", "1.0")
    os.makedirs(d)
    with zipfile.ZipFile(os.path.join(d, "lib-1.0.jar"), "w") as z:
        z.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\n")
        z.writestr(f"META-INF/maven/{g}/{a}/pom.properties", f"groupId={g}\nartifactId={a}\nversion={v}\n")
    with open(os.path.join(d, "lib-1.0.pom"), "w") as f:
        f.write('<project xmlns="http://maven.apache.org/POM/4.0.0"><modelVersion>4.0.0</modelVersion>'
                f"<groupId>appsec.fixture.{group}</groupId><artifactId>lib</artifactId><version>1.0</version></project>\n")
PYJAR
        if [[ $KIND == samename-gradle ]]; then
            gradle_build appsec.fixture.one:lib:1.0 appsec.fixture.two:lib:1.0
            sed -i.bak 's|^    mavenCentral()$|    maven { url = uri("m2") }|' build.gradle && rm build.gradle.bak
        else
            maven_pom appsec.fixture.one:lib:1.0 appsec.fixture.two:lib:1.0
            sed -i.bak 's|^  <dependencies>$|  <repositories><repository><id>fixture</id><url>file://${project.basedir}/m2</url></repository></repositories>\n  <dependencies>|' pom.xml && rm pom.xml.bak
        fi
        java_src keep
        commit samename ;;
    lang-removed)
        # The base has Python and Java findings; HEAD deletes the Python file and keeps the Java one.
        init; py_base app.py; java_src keep; commit base
        feature; g rm -q app.py; commit head ;;
    *) echo "unknown fixture $KIND" >&2; exit 2 ;;
esac

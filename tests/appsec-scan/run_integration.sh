#!/usr/bin/env bash
# Integration tests of appsec-scan on fixture repositories: bash tests/appsec-scan/run_integration.sh [CASE...]
# Runs from any directory; scans only with the test rules in tests/appsec-scan/rules (never the Semgrep registry).
# Needs git, python3, curl, cosign and trivy; the gradle and maven cases also need a JDK with gradle / mvn on PATH
# (skipped with a SKIP line when missing, or failed when APPSEC_REQUIRE_JVM=1).
set -uo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT="$(cd -- "$HERE/../.." && pwd -P)"
SCAN="${APPSEC_SCAN_SH:-$ROOT/plugins/appsec-scan/skills/appsec-scan/scan.sh}"  # override: mutation checks of the tests
RULES="$ROOT/tests/appsec-scan/rules"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/appsec-it.XXXXXX")"
REAL_CACHE="${XDG_CACHE_HOME:-$HOME/.cache}"
REAL_TRIVY="$(command -v trivy || true)"
trap 'chmod -R u+rwX "$WORK" 2>/dev/null; rm -rf "$WORK"' EXIT

ALL=(npm python go go-nobase cargo formats gradle gradle-nobase gradle-unresolved maven samename-gradle samename-maven
     r2-og-exit r2-og-badjson r2-og-errors r2-trivy-base rules-union rules-missing r7-names r7-gradlew r7-lock r7-parent
     r7-dockerfile docker-default docker-image docker-labels docker-missing docker-build)
CASES=("$@")
[[ ${#CASES[@]} -eq 0 ]] && CASES=("${ALL[@]}")

passed=0
failed=0
skipped=0

# A fake opengrep installed as a verified binary in a separate cache: it fails on HEAD or on the base as asked.
fake_cache() {  # fake_cache MODE WHERE -> prints XDG_CACHE_HOME
    local xdg="$WORK/xdg-$1-$2" bin
    bin="$xdg/appsec-scan/bin/opengrep-v0.0.1"
    mkdir -p "$xdg/appsec-scan/bin"
    ln -s "$REAL_CACHE/appsec-scan/trivy" "$xdg/appsec-scan/trivy"
    cat > "$bin" <<EOF
#!/usr/bin/env bash
out=""; target=""
while [[ \$# -gt 0 ]]; do case "\$1" in --json-output=*) out="\${1#--json-output=}" ;; --) target="\$2"; shift ;; esac; shift; done
where=head; [[ "\$target" == */base-src ]] && where=base
line=4; [[ \$where == base ]] && line=2
result="{\"check_id\": \"fake.rule\", \"path\": \"\$target/app.js\", \"start\": {\"line\": \$line}, \"extra\": {\"lines\": \"  return eval(a)\", \"severity\": \"ERROR\"}}"
if [[ \$where != "$2" ]]; then printf '{"results": [%s], "errors": []}' "\$result" > "\$out"; exit 0; fi
case "$1" in
    exit) printf '{"results": [%s], "errors": []}' "\$result" > "\$out"; exit 2 ;;
    badjson) printf '{"results": [' > "\$out"; exit 0 ;;
    errors) printf '{"results": [], "errors": [{"message": "fake engine error", "level": "error"}]}' > "\$out"; exit 0 ;;
esac
EOF
    chmod 755 "$bin"
    printf 'v0.0.1 %s\n' "$(python3 -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$bin")" \
        > "$xdg/appsec-scan/bin/opengrep.current"
    echo "$xdg"
}

# Registry-style rule packs in a separate cache (one test rule per pack), with the real verified opengrep, and a curl
# that fails: a pack that is not cached cannot be downloaded. PACKS: the packs to put into the cache.
rules_cache() {  # rules_cache NAME PACK... -> prints XDG_CACHE_HOME
    local xdg="$WORK/xdg-rules-$1" pack
    shift
    mkdir -p "$xdg/appsec-scan/rules" "$WORK/shim-nocurl"
    ln -s "$REAL_CACHE/appsec-scan/bin" "$xdg/appsec-scan/bin"
    ln -s "$REAL_CACHE/appsec-scan/trivy" "$xdg/appsec-scan/trivy"
    for pack in "$@"; do
        python3 -I - "$RULES/test-rules.yaml" "$pack" "$xdg/appsec-scan/rules/$pack.yaml" <<'PY2'
import sys
src, pack, out = sys.argv[1:]
lang = {"python": "python", "java": "java"}[pack]
blocks, cur = [], None
for line in open(src, encoding="utf-8"):
    if line.startswith("  - id:"):
        cur = [line]; blocks.append(cur)
    elif cur is not None:
        cur.append(line)
keep = [b for b in blocks if any(l.strip() == f"languages: [{lang}]" for l in b)]
open(out, "w", encoding="utf-8").write("rules:\n" + "".join("".join(b) for b in keep))
PY2
    done
    printf '#!/usr/bin/env bash\nexit 6\n' > "$WORK/shim-nocurl/curl"
    chmod 755 "$WORK/shim-nocurl/curl"
    echo "$xdg"
}

run_case() {
    local name=$1 fixture args=() env=() dir out run rc rules=(--rules "$RULES")
    case "$name" in
        go-nobase) fixture=go; args=(--no-base) ;;
        gradle-nobase) fixture=gradle; args=(--no-base) ;;
        r2-og-*) fixture=npm; args=(--no-update) ;;
        r2-trivy-base) fixture=npm ;;
        docker-default) fixture=docker ;;
        docker-image) fixture=docker; args=(--image alpine:3.20.0) ;;
        docker-missing) fixture=docker; args=(--image appsec-scan-fixture/does-not-exist:0) ;;
        docker-build) fixture=docker; args=(--docker-build) ;;
        docker-labels) fixture=docker; args=(--image alpine:3.20.0 --image alpine-3.20.0) ;;
        r7-dockerfile) fixture=r7-dockerfile; args=(--docker-build) ;;
        rules-union|rules-missing) fixture=lang-removed; args=(--no-update); rules=() ;;
        *) fixture=$name ;;
    esac
    case "$fixture" in
        gradle|gradle-unresolved|r7-gradlew|samename-gradle)
            if ! command -v gradle >/dev/null 2>&1 && [[ $fixture != r7-gradlew ]]; then
                [[ "${APPSEC_REQUIRE_JVM:-0}" == 1 ]] && { echo "FAIL $name: gradle not on PATH"; failed=$((failed + 1)); return; }
                echo "SKIP $name: gradle not on PATH"; skipped=$((skipped + 1)); return
            fi ;;
        maven|samename-maven)
            if ! command -v mvn >/dev/null 2>&1; then
                [[ "${APPSEC_REQUIRE_JVM:-0}" == 1 ]] && { echo "FAIL $name: mvn not on PATH"; failed=$((failed + 1)); return; }
                echo "SKIP $name: mvn not on PATH"; skipped=$((skipped + 1)); return
            fi ;;
    esac
    if [[ $name == docker-build ]] && ! docker info >/dev/null 2>&1; then
        [[ "${APPSEC_REQUIRE_DOCKER:-0}" == 1 ]] && { echo "FAIL $name: docker daemon unavailable"; failed=$((failed + 1)); return; }
        echo "SKIP $name: docker daemon unavailable"; skipped=$((skipped + 1)); return
    fi
    dir="$WORK/$name/repo"
    mkdir -p "$WORK/$name"
    if ! bash "$HERE/fixtures.sh" "$fixture" "$dir" > "$WORK/$name/fixture.log" 2>&1; then
        echo "FAIL $name: fixture: $(tail -3 "$WORK/$name/fixture.log")"; failed=$((failed + 1)); return
    fi
    case "$name" in
        r2-og-exit) env=(XDG_CACHE_HOME="$(fake_cache exit head)") ;;
        r2-og-badjson) env=(XDG_CACHE_HOME="$(fake_cache badjson base)") ;;
        r2-og-errors) env=(XDG_CACHE_HOME="$(fake_cache errors head)") ;;
        r2-trivy-base)
            mkdir -p "$WORK/shim"
            printf '#!/usr/bin/env bash\nfor a in "$@"; do case "$a" in */base-src*|*/inv-base/*) echo "FATAL fake base failure" >&2; exit 1 ;; esac; done\nexec "%s" "$@"\n' \
                "$REAL_TRIVY" > "$WORK/shim/trivy"
            chmod 755 "$WORK/shim/trivy"
            env=(PATH="$WORK/shim:$PATH") ;;
        rules-union) env=(XDG_CACHE_HOME="$(rules_cache union python java)" PATH="$WORK/shim-nocurl:$PATH") ;;
        rules-missing) env=(XDG_CACHE_HOME="$(rules_cache missing java)" PATH="$WORK/shim-nocurl:$PATH") ;;
    esac
    out="$WORK/$name/scan.out"
    (cd -- "$dir" && env ${env[@]+"${env[@]}"} bash "$SCAN" . ${rules[@]+"${rules[@]}"} ${args[@]+"${args[@]}"}) > "$out" 2>&1
    rc=$?
    run="$(sed -n 's/^REPORT=\(.*\)\/report\.md$/\1/p' "$out" | tail -1)"
    if [[ $rc -ne 0 || -z "$run" ]]; then
        echo "FAIL $name: scan.sh exited with $rc: $(tail -3 "$out")"; failed=$((failed + 1)); return
    fi
    echo "CASE $name ($run)"
    if python3 "$HERE/check_expect.py" "$run" "$HERE/expect/$name.json" "$WORK/$name"; then
        passed=$((passed + 1))
    else
        failed=$((failed + 1))
        diagnose "$run"
    fi
}

diagnosed=0
diagnose() {  # the tool statuses and network steps of the first failed case, so a CI log shows why
    [[ $diagnosed -eq 1 ]] && return
    diagnosed=1
    echo "  -- tool statuses:"
    grep -E '^(tools|rules)-' "$1/status.tsv" | sed 's/^/     /'
    echo "  -- network steps (scan.log):"
    grep -E '^fetch |^curl: ' "$1/scan.log" | sed 's/^/     /'
}

for c in "${CASES[@]}"; do run_case "$c"; done
echo "passed $passed, failed $failed, skipped $skipped"
[[ $failed -eq 0 && $passed -gt 0 ]]

#!/usr/bin/env bash
# Linux only. Network and file side effects of appsec-scan (R14, R8): bash tests/appsec-scan/run_isolation.sh
#  1. Warm-up with the network: installs opengrep and the trivy database into the cache.
#  2. --no-update --rules <test rules> inside `unshare -rn` (no network at all) under `strace -f -e trace=connect`:
#     no network attempt, no request to semgrep.dev (curl shim), no rules-* status line, the scan succeeds.
#  3. Control: the same without --no-update and without --rules: network attempts and semgrep.dev requests are
#     visible, rules-* fail. The test therefore tells a quiet run from a noisy one.
#  4. Files: after a run, new files exist only under the cache and the project's build/ or target/.
# A network attempt is a connect() to a non-loopback address, or to port 53 on any address (DNS: inside the
# namespace the resolver may be a loopback address, so a lookup would otherwise go unseen).
# Needs unshare (util-linux) with unprivileged user namespaces, strace, git, python3, curl, cosign, trivy.
set -uo pipefail
[[ "$(uname -s)" == Linux ]] || { echo "Linux only"; exit 2; }
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT="$(cd -- "$HERE/../.." && pwd -P)"
SCAN="${APPSEC_SCAN_SH:-$ROOT/plugins/appsec-scan/skills/appsec-scan/scan.sh}"
RULES="$ROOT/tests/appsec-scan/rules"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/appsec-iso.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/appsec-scan"
REAL_CURL="$(command -v curl)"
unshare -rn true 2>/dev/null || { echo "FAIL unshare -rn is not permitted (user namespaces disabled)"; exit 1; }

passed=0
failed=0
ok() { echo "  ok   $1"; passed=$((passed + 1)); }
bad() { echo "  FAIL $1"; failed=$((failed + 1)); }

mkdir -p "$WORK/shim"
printf '#!/usr/bin/env bash\nfor a in "$@"; do case "$a" in http*) printf "%%s\\n" "$a" >> "%s/curl.log" ;; esac; done\nexec "%s" "$@"\n' \
    "$WORK" "$REAL_CURL" > "$WORK/shim/curl"
chmod 755 "$WORK/shim/curl"

attempts() {  # attempts STRACE_LOG: network attempts in the trace
    python3 - "$1" <<'PY'
import re, sys
n = 0
for line in open(sys.argv[1], errors="replace"):
    if "connect(" not in line or "AF_INET" not in line:
        continue
    port = re.search(r"htons\((\d+)\)", line)
    addr = re.search(r'inet_(?:addr|pton)\((?:AF_INET6, )?"([^"]+)"', line)
    a = addr.group(1) if addr else ""
    loopback = a.startswith("127.") or a in ("::1", "::ffff:127.0.0.1")
    if not loopback or (port and port.group(1) == "53"):
        n += 1
print(n)
PY
}
scan_in() {  # scan_in NAME DIR ARGS...: scan inside a network namespace under strace, prints the run directory
    local name=$1 dir=$2
    shift 2
    : > "$WORK/curl.log"
    (cd "$dir" && PATH="$WORK/shim:$PATH" unshare -rn strace -f -qq -e trace=connect -o "$WORK/$name.strace" \
        bash "$SCAN" . "$@") > "$WORK/$name.out" 2>&1
    sed -n 's/^REPORT=\(.*\)\/report\.md$/\1/p' "$WORK/$name.out" | tail -1
}
rules_lines() { grep -c '^rules-' "$1/status.tsv"; }

for fixture in go npm; do
    echo "CASE $fixture"
    bash "$HERE/fixtures.sh" "$fixture" "$WORK/$fixture/repo" > /dev/null
    (cd "$WORK/$fixture/repo" && bash "$SCAN" . --rules "$RULES") > "$WORK/$fixture-warm.out" 2>&1 \
        || { bad "warm-up scan failed: $(tail -3 "$WORK/$fixture-warm.out")"; continue; }

    run="$(scan_in "$fixture-quiet" "$WORK/$fixture/repo" --no-update --rules "$RULES")"
    if [[ -z "$run" ]]; then bad "quiet scan failed: $(tail -3 "$WORK/$fixture-quiet.out")"; continue; fi
    n="$(attempts "$WORK/$fixture-quiet.strace")"
    [[ "$n" == 0 ]] && ok "--no-update --rules: 0 network attempts" || bad "--no-update --rules: $n network attempts: $(grep AF_INET "$WORK/$fixture-quiet.strace" | head -3)"
    [[ ! -s "$WORK/curl.log" ]] && ok "no curl calls" || bad "curl calls: $(head -3 "$WORK/curl.log")"
    [[ "$(rules_lines "$run")" == 0 ]] && ok "no rules-* lines in status.tsv" || bad "rules lines: $(grep '^rules-' "$run/status.tsv")"
    for part in sast sca-native; do
        [[ "$(awk -F'\t' -v p=$part '$1 == p {print $2}' "$run/status.tsv")" == ok ]] && ok "$part ok offline" \
            || bad "$part: $(grep "^$part	" "$run/status.tsv")"
    done

    run="$(scan_in "$fixture-noisy" "$WORK/$fixture/repo")"
    n="$(attempts "$WORK/$fixture-noisy.strace")"
    [[ "$n" -gt 0 ]] && ok "control without --no-update: $n network attempts are visible" || bad "control shows no network attempts: the check cannot tell"
    grep -q 'semgrep.dev' "$WORK/curl.log" && ok "control requests semgrep.dev" || bad "control made no semgrep.dev request"
    [[ -n "$run" && "$(grep -c $'^rules-[a-z]*\tfail' "$run/status.tsv")" -gt 0 ]] && ok "control: rules-* fail without network" \
        || bad "control rules: $(grep '^rules-' "$run/status.tsv" 2>/dev/null)"
done

echo "CASE files written by a run (go fixture)"
mark="$WORK/mark"
touch "$mark"
sleep 1
(cd "$WORK/go/repo" && bash "$SCAN" . --no-update --rules "$RULES") > "$WORK/files.out" 2>&1
new="$( { find "$HOME" -newer "$mark" -type f 2>/dev/null | grep -v -e "^$CACHE/" -e "^$WORK/"
          find "$WORK/go/repo" -newer "$mark" -type f | grep -v -e '/build/' -e '/target/' -e '/\.git/'; } || true)"
[[ -z "$new" ]] && ok "new files only in the cache" || bad "files outside the cache: $(printf '%s\n' "$new" | head -5)"
# opengrep's own defaults (log in ~/.opengrep, unpacked runtime in ~/.cache/opengrep) must be redirected into the cache
[[ ! -e "$HOME/.opengrep" && ! -e "${XDG_CACHE_HOME:-$HOME/.cache}/opengrep" ]] && ok "no ~/.opengrep or ~/.cache/opengrep" \
    || bad "opengrep wrote to the home directory: $(ls -d "$HOME/.opengrep" "${XDG_CACHE_HOME:-$HOME/.cache}/opengrep" 2>/dev/null)"
changed="$(git -C "$WORK/go/repo" status --porcelain --untracked-files=all)"
[[ -z "$changed" ]] && ok "the repository is unchanged" || bad "repository changed: $changed"

echo "passed $passed, failed $failed"
[[ $failed -eq 0 && $passed -gt 0 ]]

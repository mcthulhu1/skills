#!/usr/bin/env bash
# Tests of the verified opengrep install (R1): bash tests/appsec-scan/run_opengrep_install.sh
# Downloads three real opengrep releases (two 1.x signed on release-<tag> branches, one 2.x signed on main) and the
# commits of their tags once, then serves them through curl and git shims to simulate a wrong signing identity, a
# signature from another commit, an unresolved commit, an annotated tag, an unexpected latest-release redirect, a
# tampered signature, a corrupted cache, an interrupted download and two parallel updates.
# Needs git, python3, curl, cosign (and network to github.com and Sigstore for the real downloads and cosign).
set -uo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT="$(cd -- "$HERE/../.." && pwd -P)"
SCAN="${APPSEC_SCAN_SH:-$ROOT/plugins/appsec-scan/skills/appsec-scan/scan.sh}"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/appsec-og.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
NEW=v1.33.1
OLD=v1.33.0
V2=v2.0.0  # signed by the workflow on main, not on a release branch
REAL_CURL="$(command -v curl)"
REAL_GIT="$(command -v git)"

case "$(uname -s)/$(uname -m)" in
    Darwin/arm64) ASSET=opengrep_osx_arm64; OTHER=opengrep_osx_x86 ;;
    Darwin/x86_64) ASSET=opengrep_osx_x86; OTHER=opengrep_osx_arm64 ;;
    Linux/x86_64) ASSET=opengrep_manylinux_x86; OTHER=opengrep_manylinux_aarch64 ;;
    Linux/aarch64|Linux/arm64) ASSET=opengrep_manylinux_aarch64; OTHER=opengrep_manylinux_x86 ;;
    *) echo "unsupported platform"; exit 2 ;;
esac
if ldd --version 2>&1 | grep -qi musl; then ASSET=${ASSET/manylinux/musllinux}; OTHER=${OTHER/manylinux/musllinux}; fi
ASSET2=${ASSET/manylinux/linux}; ASSET2=${ASSET2/musllinux/linux}  # 2.x: one static Linux binary

DL="$WORK/dl"
mkdir -p "$DL/$NEW" "$DL/$OLD" "$DL/$V2"
for f in "$ASSET" "$ASSET.cert" "$ASSET.sig" "$OTHER.sig"; do
    "$REAL_CURL" -fsSL -o "$DL/$NEW/$f" "https://github.com/opengrep/opengrep/releases/download/$NEW/$f" || { echo "download $NEW/$f failed"; exit 2; }
done
for f in "$ASSET" "$ASSET.cert" "$ASSET.sig"; do
    "$REAL_CURL" -fsSL -o "$DL/$OLD/$f" "https://github.com/opengrep/opengrep/releases/download/$OLD/$f" || { echo "download $OLD/$f failed"; exit 2; }
done
for f in "$ASSET2" "$ASSET2.cert" "$ASSET2.sig"; do
    "$REAL_CURL" -fsSL -o "$DL/$V2/$f" "https://github.com/opengrep/opengrep/releases/download/$V2/$f" || { echo "download $V2/$f failed"; exit 2; }
done
for t in "$NEW" "$OLD" "$V2"; do
    "$REAL_GIT" ls-remote https://github.com/opengrep/opengrep "refs/tags/$t" | cut -f1 > "$DL/$t/commit"
    [[ -s "$DL/$t/commit" ]] || { echo "commit of $t failed"; exit 2; }
done

# curl shim: serves $SERVE/<tag>/<file> for release downloads and the redirect of the latest-release page to $TAG
# (SHIM_REDIRECT=<url> replaces it). SHIM_FAIL=<file>: writes half of that file, then fails (interrupted download).
# SHIM_SLOW=<seconds> per file. Any other URL fails, the REST API included.
mkdir -p "$WORK/shim"
cat > "$WORK/shim/curl" <<'EOF'
#!/usr/bin/env bash
out=""; url=""; fmt=""
while [[ $# -gt 0 ]]; do case "$1" in -o) out="$2"; shift ;; -w) fmt="$2"; shift ;; -m|--proto) shift ;; -*) ;; *) url="$1" ;; esac; shift; done
printf '%s\n' "$url" >> "$SHIM_LOG"
case "$url" in
    https://github.com/opengrep/opengrep/releases/latest)
        [[ "$fmt" == '%{redirect_url}' ]] || exit 6
        printf '%s' "${SHIM_REDIRECT:-https://github.com/opengrep/opengrep/releases/tag/$TAG}" ;;
    https://github.com/opengrep/opengrep/releases/download/*)
        rest=${url#https://github.com/opengrep/opengrep/releases/download/}
        file=${rest#*/}
        src="$SERVE/${rest%%/*}/$file"
        [[ -f "$src" ]] || exit 22
        [[ -n "${SHIM_SLOW:-}" ]] && sleep "$SHIM_SLOW"
        if [[ "$file" == "${SHIM_FAIL:-}" ]]; then head -c $(( $(wc -c < "$src") / 2 )) "$src" > "$out"; exit 18; fi
        cp "$src" "$out" ;;
    *) exit 6 ;;
esac
EOF
chmod 755 "$WORK/shim/curl"
# git shim: `ls-remote` of the opengrep repository prints $SERVE/<tag>/commit for refs/tags/<tag>; with
# $SERVE/<tag>/tagobject it prints that as the tag and the commit as the peeled refs/tags/<tag>^{} (an annotated tag).
cat > "$WORK/shim/git" <<'EOF'
#!/usr/bin/env bash
if [[ " $* " == *" ls-remote https://github.com/opengrep/opengrep "* ]]; then
    printf 'ls-remote %s\n' "${*: -2:1}" >> "$SHIM_LOG"
    tag="${*: -2:1}"; tag="${tag#refs/tags/}"
    [[ -f "$SERVE/$tag/commit" ]] || exit 0
    if [[ -f "$SERVE/$tag/tagobject" ]]; then
        printf '%s\trefs/tags/%s\n%s\trefs/tags/%s^{}\n' "$(cat "$SERVE/$tag/tagobject")" "$tag" "$(cat "$SERVE/$tag/commit")" "$tag"
    else
        printf '%s\trefs/tags/%s\n' "$(cat "$SERVE/$tag/commit")" "$tag"
    fi
    exit 0
fi
exec "$REAL_GIT" "$@"
EOF
chmod 755 "$WORK/shim/git"

REPO="$WORK/repo"
mkdir -p "$REPO"
(cd "$REPO" && git init -q -b main . && printf 'def f(a):\n    return eval(a)\n' > app.py \
    && git -c user.name=fixture -c user.email=fixture@example.invalid -c commit.gpgsign=false -c core.hooksPath=/dev/null add -A \
    && git -c user.name=fixture -c user.email=fixture@example.invalid -c commit.gpgsign=false -c core.hooksPath=/dev/null commit -q -m one)

passed=0
failed=0
ok() { echo "  ok   $1"; passed=$((passed + 1)); }
bad() { echo "  FAIL $1"; failed=$((failed + 1)); }

scan() {  # scan XDG SERVE_DIR TAG [args...]: runs scan.sh with the shim, prints the run directory
    local xdg=$1 serve=$2 tag=$3 out
    shift 3
    out="$WORK/scan.$RANDOM.out"
    (cd "$REPO" && XDG_CACHE_HOME="$xdg" SERVE="$serve" TAG="$tag" SHIM_LOG="$xdg/shim.log" REAL_GIT="$REAL_GIT" PATH="$WORK/shim:$PATH" \
        bash "$SCAN" . --no-base --rules "$ROOT/tests/appsec-scan/rules" "$@") > "$out" 2>&1
    sed -n 's/^REPORT=\(.*\)\/report\.md$/\1/p' "$out" | tail -1
}
state() { awk -F'\t' -v p="$2" '$1 == p {print $2 "\t" $3}' "$1/status.tsv"; }
sha() { python3 -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$1"; }
consistent() {  # the recorded tag and sha256 match the installed binary
    local xdg=$1 tag s
    read -r tag s < "$xdg/appsec-scan/bin/opengrep.current" || return 1
    [[ "$tag" == "$2" && "$(sha "$xdg/appsec-scan/bin/opengrep-$tag")" == "$s" ]]
}

echo "CASE good install"
X="$WORK/x-good"; run="$(scan "$X" "$DL" "$NEW")"
[[ "$(state "$run" tools-opengrep)" == ok*"installed, cosign signature verified"* ]] && ok "installed" || bad "install: $(state "$run" tools-opengrep)"
consistent "$X" "$NEW" && ok "tag and sha256 recorded" || bad "record does not match the binary"
[[ "$(state "$run" sast)" == ok* ]] && ok "sast ran" || bad "sast: $(state "$run" sast)"

echo "CASE wrong signing identity (the $OLD release served as $NEW)"
X="$WORK/x-identity"; mkdir -p "$WORK/serve-identity/$NEW"; cp "$DL/$OLD/"* "$WORK/serve-identity/$NEW/"
cp "$DL/$NEW/commit" "$WORK/serve-identity/$NEW/"
run="$(scan "$X" "$WORK/serve-identity" "$NEW")"
[[ "$(state "$run" tools-opengrep)" == fail*"did not verify"* ]] && ok "rejected" || bad "identity: $(state "$run" tools-opengrep)"
[[ ! -e "$X/appsec-scan/bin/opengrep-$NEW" && ! -e "$X/appsec-scan/bin/opengrep.current" ]] && ok "nothing installed" || bad "a binary was installed"
[[ "$(state "$run" sast)" == fail*"not installed"* ]] && ok "sast not run" || bad "sast: $(state "$run" sast)"

echo "CASE release signed on main ($V2)"
X="$WORK/x-v2"; run="$(scan "$X" "$DL" "$V2")"
[[ "$(state "$run" tools-opengrep)" == ok*"installed, cosign signature verified"* ]] && ok "installed" || bad "install: $(state "$run" tools-opengrep)"
consistent "$X" "$V2" && ok "tag and sha256 recorded" || bad "record does not match the binary"
[[ "$(state "$run" sast)" == ok* ]] && ok "sast ran" || bad "sast: $(state "$run" sast)"

echo "CASE signature from another commit (the commit of $OLD given for $NEW)"
X="$WORK/x-commit"; mkdir -p "$WORK/serve-commit/$NEW"; cp "$DL/$NEW/"* "$WORK/serve-commit/$NEW/"
cp "$DL/$OLD/commit" "$WORK/serve-commit/$NEW/"
run="$(scan "$X" "$WORK/serve-commit" "$NEW")"
[[ "$(state "$run" tools-opengrep)" == fail*"did not verify"* ]] && ok "rejected" || bad "commit: $(state "$run" tools-opengrep)"
[[ ! -e "$X/appsec-scan/bin/opengrep-$NEW" && ! -e "$X/appsec-scan/bin/opengrep.current" ]] && ok "nothing installed" || bad "a binary was installed"

echo "CASE commit of the tag not resolved"
X="$WORK/x-nocommit"; mkdir -p "$WORK/serve-nocommit/$NEW"; cp "$DL/$NEW/$ASSET"* "$WORK/serve-nocommit/$NEW/"
run="$(scan "$X" "$WORK/serve-nocommit" "$NEW")"
[[ "$(state "$run" tools-opengrep)" == fail*"cannot resolve the commit of $NEW"* ]] && ok "fails" || bad "no commit: $(state "$run" tools-opengrep)"
[[ ! -e "$X/appsec-scan/bin/opengrep-$NEW" ]] && ok "nothing installed" || bad "a binary was installed"

echo "CASE annotated tag: the peeled commit is checked, not the tag object"
X="$WORK/x-annotated"; mkdir -p "$WORK/serve-annotated/$NEW"; cp "$DL/$NEW/"* "$WORK/serve-annotated/$NEW/"
cp "$DL/$OLD/commit" "$WORK/serve-annotated/$NEW/tagobject"
run="$(scan "$X" "$WORK/serve-annotated" "$NEW")"
[[ "$(state "$run" tools-opengrep)" == ok*"installed, cosign signature verified"* ]] && ok "installed" || bad "annotated: $(state "$run" tools-opengrep)"

echo "CASE unexpected redirect of the latest-release page"
X="$WORK/x-redirect"
run="$(SHIM_REDIRECT=https://github.com/opengrep/opengrep/releases scan "$X" "$DL" "$NEW")"
[[ "$(state "$run" tools-opengrep)" == fail*"cannot get the latest opengrep release"* ]] && ok "fails" || bad "redirect: $(state "$run" tools-opengrep)"
[[ ! -e "$X/appsec-scan/bin/opengrep.current" ]] && ok "nothing installed" || bad "a binary was installed"
! grep -q 'api\.github\.com' "$WORK/x-good/shim.log" && ok "no REST API request" || bad "REST API used: $(grep api.github.com "$WORK/x-good/shim.log")"

echo "CASE tampered signature (the signature of another asset)"
X="$WORK/x-sig"; mkdir -p "$WORK/serve-sig/$NEW"; cp "$DL/$NEW/$ASSET" "$DL/$NEW/$ASSET.cert" "$DL/$NEW/commit" "$WORK/serve-sig/$NEW/"
cp "$DL/$NEW/$OTHER.sig" "$WORK/serve-sig/$NEW/$ASSET.sig"
run="$(scan "$X" "$WORK/serve-sig" "$NEW")"
[[ "$(state "$run" tools-opengrep)" == fail*"did not verify"* ]] && ok "rejected" || bad "signature: $(state "$run" tools-opengrep)"
[[ ! -e "$X/appsec-scan/bin/opengrep-$NEW" ]] && ok "nothing installed" || bad "a binary was installed"

echo "CASE corrupted cache (the binary no longer matches its sha256)"
X="$WORK/x-corrupt"; cp -R "$WORK/x-good" "$X"
printf '#!/bin/sh\ntouch "%s/MARKER-corrupt"\n' "$WORK" > "$X/appsec-scan/bin/opengrep-$NEW"
run="$(scan "$X" "$DL" "$NEW" --no-update)"
[[ "$(state "$run" sast)" == fail*"corrupted"* ]] && ok "sast fails: cache corrupted" || bad "sast: $(state "$run" sast)"
[[ ! -e "$WORK/MARKER-corrupt" ]] && ok "the corrupted binary did not run" || bad "the corrupted binary ran"

echo "CASE interrupted download keeps the installed binary"
X="$WORK/x-interrupt"; cp -R "$WORK/x-good" "$X"; mkdir -p "$WORK/serve-int/v1.99.9"; cp "$DL/$NEW/"* "$WORK/serve-int/v1.99.9/"
before="$(sha "$X/appsec-scan/bin/opengrep-$NEW")"
run="$(SHIM_FAIL="$ASSET" scan "$X" "$WORK/serve-int" v1.99.9)"
[[ "$(state "$run" tools-opengrep)" == fail*"download of $ASSET failed"*"using the verified cached $NEW"* ]] && ok "update failed, cached binary kept" \
    || bad "interrupt: $(state "$run" tools-opengrep)"
consistent "$X" "$NEW" && [[ "$(sha "$X/appsec-scan/bin/opengrep-$NEW")" == "$before" ]] && ok "installed binary unchanged" || bad "installed binary changed"
[[ ! -e "$X/appsec-scan/bin/opengrep-v1.99.9" ]] && ok "no partial binary" || bad "partial binary installed"
[[ "$(state "$run" sast)" == ok* ]] && ok "sast ran with the cached binary" || bad "sast: $(state "$run" sast)"

echo "CASE two parallel updates"
X="$WORK/x-parallel"
(SHIM_SLOW=2 scan "$X" "$DL" "$NEW" > "$WORK/p1") &
(sleep 1; SHIM_SLOW=2 scan "$X" "$DL" "$NEW" > "$WORK/p2") &
wait
r1="$(cat "$WORK/p1")"; r2="$(cat "$WORK/p2")"
[[ -n "$r1" && -n "$r2" ]] && ok "both runs finished" || bad "a run did not finish"
[[ "$(state "$r1" tools-opengrep)" == ok* && "$(state "$r2" tools-opengrep)" == ok* ]] && ok "both ok" \
    || bad "parallel: $(state "$r1" tools-opengrep) / $(state "$r2" tools-opengrep)"
grep -qh "waiting for .*opengrep.lock" "$r1/scan.log" "$r2/scan.log" && ok "the second run waited for the lock" || bad "no run waited for the lock"
bins=("$X"/appsec-scan/bin/opengrep-*)
[[ ${#bins[@]} == 1 ]] && consistent "$X" "$NEW" && ok "one binary, record consistent" || bad "bin: $(ls -a "$X/appsec-scan/bin")"
[[ ! -e "$X/appsec-scan/opengrep.lock" ]] && ok "lock released" || bad "lock left behind"

echo "passed $passed, failed $failed"
[[ $failed -eq 0 && $passed -gt 0 ]]

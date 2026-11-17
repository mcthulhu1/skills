#!/usr/bin/env bash
# appsec-scan: local pre-PR security scan of one git repository - SAST (opengrep), SCA (trivy) and, on request,
# container images (trivy image). Findings are compared with the merge-base of the base branch: new vs existing.
# Never edits the repository's source, build or lock files. Report: <cache>/runs/<repo>-<time>/report.md
#
# Usage: scan.sh [REPO] [--base REF] [--no-base] [--no-update] [--rules PATH] [--image REF]... [--docker-build]
#   REPO            repository to scan (default: current directory)
#   --base REF      base for "new vs existing" (default: origin/main, origin/master, main, master; local refs, no fetch)
#   --no-base       do not compare with a base
#   --no-update     do not update opengrep, rules or the trivy database; use what is cached
#   --rules PATH    use these opengrep rules (file or directory) instead of the Semgrep registry; no requests to semgrep.dev
#   --image REF     scan an existing container image (repeatable); nothing is built
#   --docker-build  build every Dockerfile of the repository (runs its RUN steps) and scan the images
set -uo pipefail
umask 022

SKILL_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
LIB="$SKILL_DIR/lib"
CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/appsec-scan"
MIN_TRIVY="0.63.0"  # first release with --disable-telemetry and --skip-version-check
OPENGREP_ISSUER="https://token.actions.githubusercontent.com"

usage() { sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'; }

REPO_ARG="."
BASE_REF=""
DO_BASE=1
DO_UPDATE=1
RULES=""
IMAGES=()
DOCKER_BUILD=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --base) [[ $# -ge 2 ]] || { echo "--base needs a value" >&2; exit 2; }; BASE_REF="$2"; shift 2 ;;
        --no-base) DO_BASE=0; shift ;;
        --no-update) DO_UPDATE=0; shift ;;
        --rules) [[ $# -ge 2 ]] || { echo "--rules needs a path" >&2; exit 2; }; RULES="$2"; shift 2 ;;
        --image) [[ $# -ge 2 ]] || { echo "--image needs a reference" >&2; exit 2; }; IMAGES+=("$2"); shift 2 ;;
        --docker-build) DOCKER_BUILD=1; shift ;;
        -h|--help) usage; exit 0 ;;
        --) shift; [[ $# -gt 0 ]] && { REPO_ARG="$1"; shift; } ;;
        -*) echo "Unknown option: $1 (see --help)" >&2; exit 2 ;;
        *) REPO_ARG="$1"; shift ;;
    esac
done

for tool in git python3; do
    command -v "$tool" >/dev/null 2>&1 || { echo "$tool is required" >&2; exit 2; }
done
python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))' || { echo "python3 >= 3.9 is required" >&2; exit 2; }
REPO="$(git -C "$REPO_ARG" rev-parse --show-toplevel 2>/dev/null)" || { echo "Not a git repository: $REPO_ARG" >&2; exit 2; }
REPO="$(cd -- "$REPO" && pwd -P)"
if [[ -n "$RULES" ]]; then
    [[ -e "$RULES" ]] || { echo "Rules not found: $RULES" >&2; exit 2; }
    RULES="$(cd -- "$(dirname -- "$RULES")" && pwd -P)/$(basename -- "$RULES")"
fi

helper() { python3 -I "$LIB/helpers.py" "$@"; }
NAME="$(helper docker-name "$(basename -- "$REPO")")"
RUN="$CACHE/runs/$NAME-$(date +%Y%m%d-%H%M%S)-$$"
mkdir -p "$RUN" "$CACHE/bin" "$CACHE/rules" "$CACHE/opengrep-runtime" "$CACHE/opengrep-config" || exit 2
LOG="$RUN/scan.log"
STATUS="$RUN/status.tsv"   # part <TAB> ok|fail|skip <TAB> comment
: > "$STATUS"

HOLD_LOCK=0
TMP_DIRS=()
cleanup() {
    [[ $HOLD_LOCK -eq 1 ]] && rm -rf "$CACHE/opengrep.lock"
    local d
    for d in ${TMP_DIRS[@]+"${TMP_DIRS[@]}"}; do rm -rf "$d"; done
}
trap cleanup EXIT
trap 'exit 130' INT TERM

log()    { printf '%s\n' "$*" >> "$LOG"; }
step()   { printf '==> %s\n' "$*"; log "==> $*"; }
status() { printf '%s\t%s\t%s\n' "$1" "$2" "$(printf '%s' "$3" | tr '\t\n' '  ')" >> "$STATUS"; }
logcmd() { { printf '$'; printf ' %q' "$@"; printf '\n'; } >> "$LOG"; }
run()    { logcmd "$@"; "$@" >> "$LOG" 2>&1; }
run_to() {  # run_to FILE CMD...: output to FILE (for reason) and to the log
    local out=$1 rc
    shift
    logcmd "$@"
    "$@" > "$out" 2>&1
    rc=$?
    cat "$out" >> "$LOG"
    return $rc
}
# Every download of the skill itself goes through this function.
fetch()  { log "fetch $1"; curl -fsSL --proto '=https' --tlsv1.2 -m "$3" -o "$2" "$1" 2>> "$LOG"; }
sha256() { if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d' ' -f1; else shasum -a 256 "$1" | cut -d' ' -f1; fi; }
is_darwin() { [[ "$(uname -s)" == "Darwin" ]]; }
hint() {
    case "$1" in
        trivy) echo "macOS: brew install trivy; Linux: https://trivy.dev/latest/getting-started/installation/" ;;
        cosign) echo "macOS: brew install cosign; Linux: https://docs.sigstore.dev/cosign/system_config/installation/" ;;
        curl) echo "macOS: preinstalled; Linux: install the curl package" ;;
        docker) echo "https://docs.docker.com/get-started/get-docker/" ;;
    esac
}
# Reason of a failed build from its log: network first, then compiler/docker errors, then Gradle's "What went wrong".
reason() {
    { grep -m1 -E "Could not (get|resolve|GET|HEAD) |Connect(ion)? (timed out|refused)|UnknownHost|nodename nor servname|Temporary failure in name resolution" "$1"
      grep -m1 -E 'error: |^ERROR: |^\[ERROR\] ' "$1"; grep -A3 'What went wrong' "$1" | grep -m1 -E '^ *> '; } 2>/dev/null \
        | head -1 | sed 's/^ *> *//' | cut -c1-220
}
read_list() {  # read_list ARRAY FILE: NUL-separated FILE into ARRAY (bash 3.2: no mapfile -d)
    local __item __name=$1
    eval "$__name=()"
    [[ -e "$2" ]] || return 0
    while IFS= read -r -d '' __item; do eval "$__name+=(\"\$__item\")"; done < "$2"
}

# ------------------------------------------------------------------ 1. Repository and base
step "Repository $REPO"
HEAD_SHA="$(git -C "$REPO" rev-parse HEAD 2>/dev/null)" || { echo "The repository has no commits" >&2; exit 2; }
BRANCH="$(git -C "$REPO" rev-parse --abbrev-ref HEAD)"
DIRTY="$(git -C "$REPO" status --porcelain --untracked-files=no | wc -l | tr -d ' ')"

BASE_SHA=""
if [[ $DO_BASE -eq 0 ]]; then
    status base skip "disabled (--no-base)"
else
    if [[ -z "$BASE_REF" ]]; then
        for r in origin/main origin/master main master; do
            git -C "$REPO" rev-parse --verify -q "$r^{commit}" >/dev/null && { BASE_REF="$r"; break; }
        done
    fi
    if [[ -z "$BASE_REF" ]]; then
        status base skip "no base branch found (origin/main, origin/master, main, master); pass --base REF"
    elif ! BASE_SHA="$(git -C "$REPO" merge-base HEAD "$BASE_REF" 2>/dev/null)"; then
        status base fail "no merge-base between HEAD and $BASE_REF"
        BASE_SHA=""
    fi
fi
# HEAD == merge-base: a comparison only makes sense when the working tree has changes (then the base is the HEAD commit)
CHANGES="$(git -C "$REPO" status --porcelain --untracked-files=all | wc -l | tr -d ' ')"
if [[ -n "$BASE_SHA" && "$BASE_SHA" == "$HEAD_SHA" && "$CHANGES" == "0" ]]; then
    status base skip "HEAD is the merge-base with $BASE_REF and the working tree is clean: nothing to compare"
    BASE_SHA=""
fi
if [[ -n "$BASE_SHA" ]]; then
    mkdir -p "$RUN/base-src"
    if git -C "$REPO" archive --format=tar "$BASE_SHA" 2>> "$LOG" | tar -x -C "$RUN/base-src" 2>> "$LOG"; then
        status base ok "$BASE_REF merge-base ${BASE_SHA:0:10}"
    else
        status base fail "git archive of $BASE_SHA failed"
        BASE_SHA=""
    fi
fi

mkdir -p "$RUN/inv-head"
helper inventory git "$REPO" "$RUN/inv-head" 2>> "$LOG" || { echo "File inventory failed, see $LOG" >&2; exit 2; }
if [[ -n "$BASE_SHA" ]]; then
    mkdir -p "$RUN/inv-base"
    helper inventory tree "$RUN/base-src" "$RUN/inv-base" 2>> "$LOG" || { status base fail "file inventory of the base failed"; BASE_SHA=""; }
fi
read_list LANGS <(helper get "$RUN/inv-head/inventory.json" langs)
BUILD="$(helper get "$RUN/inv-head/inventory.json" build)"

# Parts blocked by a symlink that points outside the repository: nothing is run or read through it.
blocked() {  # blocked INV KIND: print the first external symlink of KIND, exit 0 if there is one
    python3 -I -c 'import json,sys
for s in json.load(open(sys.argv[1]))["external_symlinks"]:
    if s["critical"] == sys.argv[2]:
        sys.stdout.write(s["path"]); sys.exit(0)
sys.exit(1)' "$1" "$2"
}

helper meta "$RUN/meta.json" REPO "$REPO" NAME "$NAME" BRANCH "$BRANCH" HEAD_SHA "$HEAD_SHA" DIRTY "$DIRTY" \
    BASE_REF "$BASE_REF" BASE_SHA "$BASE_SHA" LANGS "${LANGS[*]:-}" BUILD "$BUILD" \
    RULES "$(if [[ -n "$RULES" ]]; then printf 'custom %s' "$RULES"; else echo registry; fi)" UPDATE "$DO_UPDATE" \
    || { echo "writing meta.json failed" >&2; exit 2; }

# ------------------------------------------------------------------ 2. Tools and rules
platform_asset() {
    local libc="many"
    case "$(uname -s)/$(uname -m)" in
        Darwin/arm64) echo opengrep_osx_arm64 ;;
        Darwin/x86_64) echo opengrep_osx_x86 ;;
        Linux/x86_64|Linux/amd64|Linux/aarch64|Linux/arm64)
            if ldd --version 2>&1 | grep -qi musl || ls /lib/ld-musl-* >/dev/null 2>&1; then libc="musl"; fi
            case "$(uname -m)" in x86_64|amd64) echo "opengrep_${libc}linux_x86" ;; *) echo "opengrep_${libc}linux_aarch64" ;; esac ;;
        *) return 1 ;;
    esac
}

OG_BIN=""
OG_TAG=""
# The verified binary is <cache>/bin/opengrep-<tag>; <cache>/bin/opengrep.current holds "<tag> <sha256>".
# Returns 1 if nothing is installed, 2 if the record or the binary does not match (corrupted cache).
opengrep_current() {
    local tag sha f
    OG_BIN=""; OG_TAG=""
    [[ -f "$CACHE/bin/opengrep.current" ]] || return 1
    read -r tag sha < "$CACHE/bin/opengrep.current" || return 2
    [[ "$tag" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ && "$sha" =~ ^[0-9a-f]{64}$ ]] || return 2
    f="$CACHE/bin/opengrep-$tag"
    [[ -f "$f" && "$(sha256 "$f")" == "$sha" ]] || return 2
    OG_BIN="$f"; OG_TAG="$tag"
}
cached_note() {
    opengrep_current
    case $? in
        0) echo "; using the verified cached $OG_TAG" ;;
        2) echo "; the cached binary is corrupted (sha256 mismatch)" ;;
        *) echo "; no cached binary" ;;
    esac
}
acquire_lock() {
    local waited=0
    while ! mkdir "$CACHE/opengrep.lock" 2>/dev/null; do
        if [[ -n "$(find "$CACHE/opengrep.lock" -maxdepth 0 -mmin +10 2>/dev/null)" ]]; then
            log "removing a stale lock $CACHE/opengrep.lock (older than 10 minutes)"
            rm -rf "$CACHE/opengrep.lock"
            continue
        fi
        [[ $waited -ge 900 ]] && return 1
        [[ $waited -eq 0 ]] && log "waiting for $CACHE/opengrep.lock"
        sleep 2
        waited=$((waited + 2))
    done
    HOLD_LOCK=1
}
release_lock() { [[ $HOLD_LOCK -eq 1 ]] && rm -rf "$CACHE/opengrep.lock"; HOLD_LOCK=0; }

update_opengrep() {
    local asset tag tmp base f identity sha
    if ! asset="$(platform_asset)"; then
        status tools-opengrep fail "unsupported platform $(uname -s)/$(uname -m)"
        return
    fi
    if ! command -v cosign >/dev/null 2>&1; then
        status tools-opengrep fail "cosign not found, the opengrep signature cannot be verified; install: $(hint cosign)$(cached_note)"
        return
    fi
    tmp="$(mktemp -d "$CACHE/dl.XXXXXX")" || { status tools-opengrep fail "cannot create a download directory"; return; }
    TMP_DIRS+=("$tmp")
    if ! fetch https://api.github.com/repos/opengrep/opengrep/releases/latest "$tmp/latest.json" 30 \
            || ! tag="$(helper get "$tmp/latest.json" tag_name)"; then
        status tools-opengrep fail "cannot get the latest opengrep release$(cached_note)"
        return
    fi
    if [[ ! "$tag" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        status tools-opengrep fail "unexpected release tag$(cached_note)"
        return
    fi
    if ! acquire_lock; then
        status tools-opengrep fail "another update holds $CACHE/opengrep.lock$(cached_note)"
        return
    fi
    if opengrep_current && [[ "$OG_TAG" == "$tag" ]]; then
        release_lock
        status tools-opengrep ok "release $tag (cached, sha256 matches)"
        return
    fi
    base="https://github.com/opengrep/opengrep/releases/download/$tag"
    for f in "$asset" "$asset.cert" "$asset.sig"; do
        if ! fetch "$base/$f" "$tmp/$f" 300; then
            release_lock
            status tools-opengrep fail "download of $f failed$(cached_note)"
            return
        fi
    done
    sha="$(sha256 "$tmp/$asset")"
    identity="^https://github\\.com/opengrep/opengrep/\\.github/workflows/rolling-release\\.yml@refs/heads/release-${tag//./\\.}\$"
    if ! run cosign verify-blob --certificate "$tmp/$asset.cert" --signature "$tmp/$asset.sig" \
            --certificate-identity-regexp "$identity" --certificate-oidc-issuer "$OPENGREP_ISSUER" "$tmp/$asset"; then
        release_lock
        status tools-opengrep fail "signature of $tag did not verify (expected identity $identity, issuer $OPENGREP_ISSUER); not installed$(cached_note)"
        return
    fi
    chmod 755 "$tmp/$asset"
    is_darwin && xattr -d com.apple.quarantine "$tmp/$asset" 2>/dev/null
    if [[ "$(sha256 "$tmp/$asset")" != "$sha" ]] \
            || ! mv -f "$tmp/$asset" "$CACHE/bin/.opengrep-$tag.$$" \
            || ! mv -f "$CACHE/bin/.opengrep-$tag.$$" "$CACHE/bin/opengrep-$tag" \
            || ! printf '%s %s\n' "$tag" "$sha" > "$CACHE/bin/.opengrep.current.$$" \
            || ! mv -f "$CACHE/bin/.opengrep.current.$$" "$CACHE/bin/opengrep.current"; then
        release_lock
        status tools-opengrep fail "installing $tag failed$(cached_note)"
        return
    fi
    release_lock
    status tools-opengrep ok "release $tag installed, cosign signature verified"
}

PACKS=()
MISSING_PACKS=()
update_rules() {
    local pack tmp
    for pack in "$@"; do
        tmp="$CACHE/rules/.$pack.yaml.$$"
        if fetch "https://semgrep.dev/c/p/$pack" "$tmp" 60 && head -1 "$tmp" | grep -q '^rules:'; then
            mv -f "$tmp" "$CACHE/rules/$pack.yaml"
            status "rules-$pack" ok "registry p/$pack, $(grep -c '^- id:' "$CACHE/rules/$pack.yaml") rules"
        else
            rm -f "$tmp"
            if [[ -f "$CACHE/rules/$pack.yaml" ]]; then
                status "rules-$pack" fail "registry unavailable, using the cached p/$pack"
            else
                status "rules-$pack" fail "registry unavailable and no cached p/$pack"
            fi
        fi
    done
}

step "Tools"
command -v curl >/dev/null 2>&1 || status tools-curl fail "curl not found; install: $(hint curl)"
if [[ $DO_UPDATE -eq 1 ]] && command -v curl >/dev/null 2>&1; then
    update_opengrep
else
    status tools-opengrep skip "update disabled (--no-update)"
fi
opengrep_current
OG_STATE=$?
[[ -n "$OG_TAG" ]] && printf '%s\n' "$OG_TAG" > "$RUN/opengrep.release"

TRIVY_OK=0
if ! command -v trivy >/dev/null 2>&1; then
    status tools-trivy fail "trivy not found; install: $(hint trivy)"
elif ! trivy version --format json > "$RUN/trivy-version.json" 2>> "$LOG"; then
    status tools-trivy fail "trivy version failed, see scan.log"
else
    tv="$(helper get "$RUN/trivy-version.json" Version)"
    if helper version-ge "$tv" "$MIN_TRIVY"; then
        TRIVY_OK=1
        status tools-trivy ok "trivy $tv"
    else
        status tools-trivy fail "trivy $tv is older than $MIN_TRIVY; update: $(hint trivy)"
    fi
fi
TRIVY_ARGS=(--quiet --scanners vuln --format json --list-all-pkgs --disable-telemetry --skip-version-check
            --offline-scan --cache-dir "$CACHE/trivy")
[[ $DO_UPDATE -eq 0 ]] && TRIVY_ARGS+=(--skip-db-update --skip-java-db-update)

RULE_FILES=()
if [[ -n "$RULES" ]]; then
    RULE_FILES=("$RULES")
else
    # Packs for the languages of HEAD and of the base: a finding in a language the branch removed is still
    # found in the base and reported as fixed
    read_list PACKS <( { helper get "$RUN/inv-head/inventory.json" langs
                         [[ -n "$BASE_SHA" ]] && helper get "$RUN/inv-base/inventory.json" langs; } | sort -zu)
fi
if [[ -z "$RULES" && ${#PACKS[@]} -gt 0 ]]; then
    if [[ $DO_UPDATE -eq 1 ]]; then
        command -v curl >/dev/null 2>&1 && update_rules "${PACKS[@]}"
    else
        # SAST cannot run without rules: packs that are not cached yet are downloaded even with --no-update
        missing=()
        for pack in "${PACKS[@]}"; do [[ -f "$CACHE/rules/$pack.yaml" ]] || missing+=("$pack"); done
        [[ ${#missing[@]} -gt 0 ]] && command -v curl >/dev/null 2>&1 && update_rules "${missing[@]}"
    fi
    MISSING_PACKS=()
    for pack in "${PACKS[@]}"; do
        if [[ -f "$CACHE/rules/$pack.yaml" ]]; then RULE_FILES+=("$CACHE/rules/$pack.yaml"); else MISSING_PACKS+=("p/$pack"); fi
    done
    echo "Note: the Semgrep registry rules are licensed under the Semgrep Rules License v1.0 (internal business use only);"
    echo "      see https://semgrep.dev/legal/rules-license. Use --rules PATH to scan with your own rules."
fi

# ------------------------------------------------------------------ 3. SAST
SAST_REASON=""
sast() {  # sast DIR OUT EXCLUDE_LIST
    local args=(scan --quiet --disable-version-check --taint-intrafile --json-output="$2") f p rc excl
    for f in "${RULE_FILES[@]}"; do args+=(--config "$f"); done
    read_list excl "$3"
    for p in ${excl[@]+"${excl[@]}"}; do args+=(--exclude "$(helper glob-escape "$p")"); done
    rm -f "$2"
    # opengrep unpacks itself into $XDG_CACHE_HOME/opengrep and logs to $XDG_CONFIG_HOME/.opengrep (else $HOME):
    # both go into the skill cache, so a scan writes nothing else to the home directory
    run env XDG_CACHE_HOME="$CACHE/opengrep-runtime" XDG_CONFIG_HOME="$CACHE/opengrep-config" "$OG_BIN" "${args[@]}" -- "$1"
    rc=$?
    if [[ $rc -ne 0 ]]; then
        SAST_REASON="opengrep exited with $rc; $(helper check-sast "$2")"
        return 1
    fi
    SAST_REASON="$(helper check-sast "$2")" || return 1
    return 0
}
if [[ ${#PACKS[@]} -eq 0 && -z "$RULES" ]]; then
    status sast skip "no Java, Kotlin, Go, Rust, Python, JavaScript or TypeScript files"
    status sast-base skip "no SAST languages"
elif [[ $OG_STATE -eq 2 ]]; then
    status sast fail "opengrep cache is corrupted (sha256 mismatch); remove $CACHE/bin and run without --no-update"
    status sast-base fail "opengrep cache is corrupted"
elif [[ -z "$OG_BIN" ]]; then
    status sast fail "opengrep is not installed; run without --no-update (needs curl and cosign)"
    status sast-base fail "opengrep is not installed"
elif [[ ${#RULE_FILES[@]} -eq 0 ]]; then
    status sast fail "no rules for ${PACKS[*]} (registry unavailable and nothing cached)"
    status sast-base fail "no rules"
else
    step "SAST (opengrep $OG_TAG, $(if [[ -n "$RULES" ]]; then echo "custom rules"; else echo "rules: ${PACKS[*]}"; fi))"
    # A pack that could not be loaded leaves its language unscanned: the part is incomplete, not ok
    incomplete=""
    [[ ${#MISSING_PACKS[@]} -gt 0 ]] && incomplete="rules missing for ${MISSING_PACKS[*]} (registry unavailable and not cached): those languages are not scanned"
    if ! sast "$REPO" "$RUN/sast-head.json" "$RUN/inv-head/external.lst"; then
        status sast fail "$SAST_REASON"
    elif [[ -n "$incomplete" ]]; then
        status sast fail "$incomplete"
    else
        status sast ok "HEAD scanned"
    fi
    if [[ -n "$BASE_SHA" ]]; then
        if ! sast "$RUN/base-src" "$RUN/sast-base.json" "$RUN/inv-base/external.lst"; then
            status sast-base fail "$SAST_REASON"
        elif [[ -n "$incomplete" ]]; then
            status sast-base fail "$incomplete"
        else
            status sast-base ok "base scanned"
        fi
    else
        status sast-base skip "no base"
    fi
fi

# ------------------------------------------------------------------ 4. SCA
JVM_REASON=""
build_tool() {  # build_tool DIR KIND: sets TOOL to the command for the wrapper or the tool on PATH
    TOOL=()
    case "$2" in
        gradle)
            if [[ -f "$1/gradlew" ]]; then TOOL=(sh ./gradlew); elif command -v gradle >/dev/null 2>&1; then TOOL=(gradle); else return 1; fi ;;
        maven)
            if [[ -f "$1/mvnw" ]]; then TOOL=(sh ./mvnw); elif command -v mvn >/dev/null 2>&1; then TOOL=(mvn); else return 1; fi ;;
    esac
}
gradle_deps() {  # gradle_deps SRC DEPS
    rm -rf "$2"
    build_tool "$1" gradle || { JVM_REASON="no gradlew and no gradle on PATH"; return 1; }
    local out="$2.log"
    mkdir -p "$2"
    if ! (cd -- "$1" && run_to "$out" "${TOOL[@]}" -q --no-daemon --no-configuration-cache --project-cache-dir "$2.gradle-cache" \
            -I "$LIB/init-appsec.gradle" appsecCopyDeps "-PappsecDepsDir=$2"); then
        JVM_REASON="gradle failed: $(reason "$out")"
        return 1
    fi
    if [[ -n "$(cat "$2"/unresolved/*.txt 2>/dev/null)" ]]; then
        JVM_REASON="unresolved dependencies: $(cat "$2"/unresolved/*.txt | sort -u | head -3 | tr '\n' ';' | cut -c1-220)"
        return 1
    fi
    [[ -d "$2/jars" ]] || { JVM_REASON="no Java project with a runtimeClasspath"; return 1; }
}
maven_deps() {  # maven_deps SRC DEPS
    rm -rf "$2"
    build_tool "$1" maven || { JVM_REASON="no mvnw and no mvn on PATH"; return 1; }
    local out="$2.log"
    mkdir -p "$2/jars/root" "$2/tree"
    if ! (cd -- "$1" && run_to "$out" "${TOOL[@]}" -B -q -DskipTests package \
            dependency:copy-dependencies -DincludeScope=runtime -Dmdep.useRepositoryLayout=true "-DoutputDirectory=$2/jars/root" \
            dependency:tree "-DoutputFile=$2/tree/tree.txt" -DappendOutput=true -Dscope=runtime); then
        JVM_REASON="maven failed: $(reason "$out")"
        return 1
    fi
}
trivy_scan() {  # trivy_scan SUBCOMMAND TARGET OUT: sets TRIVY_REASON on failure
    rm -f "$3"
    if ! run_to "$3.log" trivy "$1" "${TRIVY_ARGS[@]}" -o "$3" -- "$2"; then
        TRIVY_REASON="trivy $1 failed: $(grep -m1 -E 'FATAL|ERROR' "$3.log" | cut -c1-200)"
        return 1
    fi
    TRIVY_REASON="$(helper check-trivy "$3")" || return 1
}
jvm_part() {  # jvm_part SRC DEPS OUT INV PART
    local link
    if link="$(blocked "$4" "$BUILD")"; then
        status "$5" fail "external symlink $link: $BUILD is not run"
    elif [[ $TRIVY_OK -eq 0 ]]; then
        status "$5" fail "trivy unavailable"
    elif "${BUILD}_deps" "$1" "$2"; then
        if trivy_scan rootfs "$2/jars" "$3"; then
            status "$5" ok "$BUILD runtime classpath"
        else
            status "$5" fail "$TRIVY_REASON"
        fi
    else
        status "$5" fail "$JVM_REASON"
    fi
}
native_part() {  # native_part INV-DIR OUT PART
    local link
    if link="$(blocked "$1/inventory.json" lockfile)"; then
        status "$3" fail "external symlink $link: trivy fs is not run"
    elif [[ -z "$(helper get "$1/inventory.json" lockfiles | tr -d '\0')" ]]; then
        status "$3" skip "no supported lock files"
    elif [[ $TRIVY_OK -eq 0 ]]; then
        status "$3" fail "trivy unavailable"
    elif trivy_scan fs "$1/locks" "$2"; then
        status "$3" ok "lock files"
    else
        status "$3" fail "$TRIVY_REASON"
    fi
}

step "SCA"
case "$BUILD" in
    gradle|maven)
        jvm_part "$REPO" "$RUN/deps-head" "$RUN/sca-head.json" "$RUN/inv-head/inventory.json" sca
        if [[ -n "$BASE_SHA" ]]; then
            jvm_part "$RUN/base-src" "$RUN/deps-base" "$RUN/sca-base.json" "$RUN/inv-base/inventory.json" sca-base
        else
            status sca-base skip "no base"
        fi ;;
    *)
        status sca skip "no Gradle or Maven build"
        status sca-base skip "no Gradle or Maven build" ;;
esac
native_part "$RUN/inv-head" "$RUN/sca-native-head.json" sca-native
if [[ -n "$BASE_SHA" ]]; then
    native_part "$RUN/inv-base" "$RUN/sca-native-base.json" sca-native-base
else
    status sca-native-base skip "no base"
fi

# ------------------------------------------------------------------ 5. Container images (full snapshot, no base)
image_scan() {  # image_scan REF LABEL
    if [[ $TRIVY_OK -eq 0 ]]; then
        status "docker-$2" fail "trivy unavailable"
    elif trivy_scan image "$1" "$RUN/docker-$2.json"; then
        status "docker-$2" ok "$1"
    else
        status "docker-$2" fail "$1: $TRIVY_REASON"
    fi
}
USED_LABELS=" "
unique_label() {  # unique_label TEXT: sets LABEL to the normalized TEXT, with -2, -3... if it is already taken
    local base n=1
    base="$(helper docker-name "$1")"
    LABEL="$base"
    while [[ "$USED_LABELS" == *" $LABEL "* ]]; do n=$((n + 1)); LABEL="$base-$n"; done
    USED_LABELS+="$LABEL "
}
step "Container images"
for img in ${IMAGES[@]+"${IMAGES[@]}"}; do
    unique_label "$img"
    label="$LABEL"
    if [[ ! "$img" =~ ^[A-Za-z0-9][A-Za-z0-9._/:@+-]*$ || ${#img} -gt 255 ]]; then
        status "docker-$label" fail "not a valid image reference"
    else
        image_scan "$img" "$label"
    fi
done
if [[ $DOCKER_BUILD -eq 1 ]]; then
    read_list DOCKERFILES <(helper get "$RUN/inv-head/inventory.json" dockerfiles)
    if link="$(blocked "$RUN/inv-head/inventory.json" dockerfile)"; then
        status docker-build fail "external symlink $link: docker build is not run"
    elif ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
        status docker-build fail "docker daemon unavailable; install: $(hint docker)"
    elif [[ ${#DOCKERFILES[@]} -eq 0 ]]; then
        status docker-build skip "no Dockerfile in the repository"
    elif link="$(blocked "$RUN/inv-head/inventory.json" "$BUILD")"; then
        status docker-build fail "external symlink $link: $BUILD is not run"
    else
        # Dockerfiles usually copy build outputs: build them first, as a developer would before docker build
        case "$BUILD" in
            gradle) build_tool "$REPO" gradle && (cd -- "$REPO" && run "${TOOL[@]}" -q --no-daemon assemble -x test) ;;
            maven) build_tool "$REPO" maven && (cd -- "$REPO" && run "${TOOL[@]}" -B -q -DskipTests package) ;;
        esac
        for df in "${DOCKERFILES[@]}"; do
            unique_label "$df"
            label="$LABEL"
            tag="appsec-scan/$NAME:$(helper docker-name "$label-${HEAD_SHA:0:8}")"
            blog="$RUN/docker-build-$label.log"
            if (cd -- "$REPO" && run docker build -f "$df" -t "$tag" -- "$(dirname -- "$df")") ; then
                image_scan "$tag" "$label"
                run docker rmi "$tag"
            else
                tail -n 50 "$LOG" > "$blog"
                status "docker-$label" fail "docker build of $df failed: $(reason "$blog")"
            fi
        done
    fi
fi
if [[ ${#IMAGES[@]} -eq 0 && $DOCKER_BUILD -eq 0 ]]; then
    status docker skip "not requested: pass --image REF to scan an image, or --docker-build to build the Dockerfiles"
fi

# ------------------------------------------------------------------ 6. Report
step "Report"
if ! python3 -I "$LIB/report.py" "$RUN" > "$RUN/report.md" 2>> "$LOG"; then
    echo "report.py failed, see $LOG" >&2
    exit 1
fi
# Large intermediate files are not kept: jar copies, staged lock files and the base sources
rm -rf "$RUN/base-src" "$RUN/deps-head/jars" "$RUN/deps-base/jars" "$RUN/inv-head/locks" "$RUN/inv-base/locks" \
    "$RUN/deps-head.gradle-cache" "$RUN/deps-base.gradle-cache"
echo "REPORT=$RUN/report.md"

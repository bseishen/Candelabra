#!/usr/bin/env bash
# Sync firmware source changes from Elmue's upstream CANable 2.5 repo into Candelabra.
#
#   sync.sh status [TARGET]         fetch upstream, report what changed since the last sync
#   sync.sh apply  [TARGET]         stage upstream firmware changes into firmware/ (no commit)
#   sync.sh build                   build all targets (local toolchain, else devcontainer image)
#
# TARGET defaults to upstream/main. The last synced upstream commit is read from
# the file "last-sync" next to this script; override with FROM=<sha>.
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(git -C "$SKILL_DIR" rev-parse --show-toplevel)"
cd "$ROOT"

UPSTREAM_URL="https://github.com/elmue/CANable-2.5-firmware-Slcan-and-Candlelight.git"
STATE_FILE="$SKILL_DIR/last-sync"

ensure_remote() {
    if ! git remote get-url upstream >/dev/null 2>&1; then
        git remote add upstream "$UPSTREAM_URL"
    fi
    git fetch -q upstream
}

resolve_range() {
    FROM="${FROM:-$(tr -d '[:space:]' < "$STATE_FILE")}"
    TARGET="$(git rev-parse "${1:-upstream/main}")"
    git cat-file -e "$FROM^{commit}"
}

# Firmware/Candlelight/buffer.c -> firmware/candlelight/buffer.c (directories lowercased, file name kept)
map_path() {
    local dir base
    dir="$(dirname "$1")"; base="$(basename "$1")"
    echo "$(echo "$dir" | tr '[:upper:]' '[:lower:]')/$base"
}

# blob id of a path at a commit, empty if it does not exist
blob_at() { git rev-parse -q --verify "$1:$2" 2>/dev/null || true; }

# echo "board mcu quartz firmware" for an upstream makefile
parse_makefile() {
    git show "$1:$2" | tr -d '\r' | awk -F= '
        /^TARGET_FIRMWARE/ {gsub(/ /,"",$2); fw=$2}
        /^TARGET_BOARD/    {gsub(/ /,"",$2); b=$2}
        /^TARGET_MCU/      {gsub(/ /,"",$2); m=$2}
        /^QUARTZ_FREQU/    {gsub(/ /,"",$2); q=$2}
        END {print b, m, q, fw}'
}

# "firmware board mcu quartz" for every upstream board makefile at a commit, sorted
boards_at() {
    git ls-tree -r --name-only "$1" | grep -E '(^|/)Make_[^/]+$' | while read -r f; do
        read -r b m q fw < <(parse_makefile "$1" "$f")
        echo "$fw $b $m $q"
    done | sort -u
}

cmd_status() {
    local tmpd; tmpd="$(mktemp -d)"
    ensure_remote
    resolve_range "${1:-}"
    echo "Last sync : $(git log -1 --format='%h %ad %s' --date=short "$FROM")"
    echo "Target    : $(git log -1 --format='%h %ad %s' --date=short "$TARGET")"
    if [ "$FROM" = "$TARGET" ]; then
        echo; echo "UP TO DATE: nothing to sync."; return 0
    fi

    echo; echo "== Upstream commits"
    git log --format='%h %ad %s' --date=short "$FROM..$TARGET"

    echo; echo "== Firmware changes (will be applied)"
    git diff --no-renames --name-status "$FROM" "$TARGET" -- Firmware | while read -r st f; do
        local l note=""
        l="$(map_path "$f")"
        if [ "$st" != "A" ] && [ -n "$(blob_at HEAD "$l")" ] && [ "$(blob_at HEAD "$l")" != "$(blob_at "$FROM" "$f")" ]; then
            note="  <-- LOCALLY CUSTOMIZED, will 3-way merge"
        fi
        echo "$st  $f -> $l$note"
    done
    git diff --shortstat "$FROM" "$TARGET" -- Firmware

    echo; echo "== Boards (from upstream makefiles; renames/moves ignored)"
    boards_at "$FROM"   > "$tmpd/from"
    boards_at "$TARGET" > "$tmpd/target"
    comm -13 "$tmpd/from" "$tmpd/target" | sed 's/^/NEW upstream:     /'
    comm -23 "$tmpd/from" "$tmpd/target" | sed 's/^/REMOVED upstream: /'
    while read -r fw b m q; do
        grep -Eq "add_firmware_target\(\s*$fw\s+$b\s+$m\s+$q\s*\)" CMakeLists.txt \
            || echo "MISSING in CMakeLists.txt: $fw $b $m quartz=$q"
    done < "$tmpd/target"
    rm -rf "$tmpd"

    echo; echo "== Firmware version in upstream GCC_Rules.mk"
    for r in "$FROM" "$TARGET"; do
        for p in Build/GCC_Rules.mk GCC_Rules.mk; do
            if git cat-file -e "$r:$p" 2>/dev/null; then
                echo "$(git rev-parse --short "$r"): $(git show "$r:$p" | tr -d '\r' | grep -E '^FIRMWARE_VERSION' || true)"
                break
            fi
        done
    done

    echo; echo "== Other upstream changes (NOT applied; review for follow-up work)"
    git diff --stat=120 "$FROM" "$TARGET" -- . ':(exclude)Firmware' | tail -n 40
}

cmd_apply() {
    ensure_remote
    resolve_range "${1:-}"
    if [ "$FROM" = "$TARGET" ]; then echo "Up to date; nothing to apply."; return 0; fi
    if [ -n "$(git status --porcelain -- firmware)" ]; then
        echo "firmware/ has uncommitted changes; commit or stash them first." >&2; exit 1
    fi

    local tmp conflicts=()
    tmp="$(mktemp -d)"
    while read -r st f; do
        local l base theirs ours
        l="$(map_path "$f")"
        base="$(blob_at "$FROM" "$f")"; theirs="$(blob_at "$TARGET" "$f")"; ours="$(blob_at HEAD "$l")"
        case "$st" in
            D)
                if [ -n "$ours" ]; then
                    if [ "$ours" = "$base" ]; then git rm -q "$l"; echo "deleted  $l"
                    else conflicts+=("$l (deleted upstream but locally customized)"); fi
                fi ;;
            A|M)
                if [ -z "$ours" ] || [ "$ours" = "$base" ]; then
                    # untouched locally: take upstream's exact bytes (keeps CRLF, avoids autocrlf churn)
                    mkdir -p "$(dirname "$l")"
                    git update-index --add --cacheinfo "100644,$theirs,$l"
                    git checkout -- "$l"
                    echo "updated  $l"
                else
                    # locally customized: 3-way merge ours/base/theirs
                    git cat-file blob "$ours" > "$tmp/ours"; git cat-file blob "$theirs" > "$tmp/theirs"
                    if [ -n "$base" ]; then git cat-file blob "$base" > "$tmp/base"; else : > "$tmp/base"; fi
                    if git merge-file -L local -L "upstream-base" -L upstream "$tmp/ours" "$tmp/base" "$tmp/theirs"; then
                        git update-index --add --cacheinfo "100644,$(git hash-object -w --no-filters "$tmp/ours"),$l"
                        git checkout -- "$l"
                        echo "merged   $l (local customizations kept)"
                    else
                        cp "$tmp/ours" "$l"
                        conflicts+=("$l")
                    fi
                fi ;;
        esac
    done < <(git diff --no-renames --name-status "$FROM" "$TARGET" -- Firmware)
    rm -rf "$tmp"

    echo "$TARGET" > "$STATE_FILE"
    git add "$STATE_FILE"
    echo; echo "last-sync -> $(git rev-parse --short "$TARGET")"

    if [ ${#conflicts[@]} -gt 0 ]; then
        echo; echo "CONFLICTS (resolve, then git add):"; printf '  %s\n' "${conflicts[@]}"; exit 2
    fi
    echo; git diff --cached --stat
}

cmd_build() {
    if command -v arm-none-eabi-gcc >/dev/null && command -v cmake >/dev/null; then
        log="$(mktemp)"
        rm -rf build && ./build_all.sh > "$log" 2>&1 || { tail -40 "$log"; exit 1; }
    else
        command -v docker >/dev/null || { echo "Need arm-none-eabi-gcc+cmake or docker." >&2; exit 1; }
        docker build -q -t candelabra-sync-build .devcontainer >/dev/null
        log="$(mktemp)"
        MSYS_NO_PATHCONV=1 docker run --rm -u vscode -v "$(pwd -W 2>/dev/null || pwd):/src:ro" candelabra-sync-build \
            bash -c 'cp -r /src /tmp/w && cd /tmp/w && rm -rf build && ./build_all.sh 2>&1' > "$log" \
            || { tail -40 "$log"; exit 1; }
    fi
    echo "Build OK. warnings/errors: $(grep -ciE 'warning:|error:' "$log" || true)"
    grep -iE 'warning:|error:' "$log" | sort | uniq -c | head -20 || true
    grep -E '^/.*\.bin$' "$log" | sed 's#.*/##' | sort
}

case "${1:-status}" in
    status) shift || true; cmd_status "${1:-}" ;;
    apply)  shift; cmd_apply  "${1:-}" ;;
    build)  cmd_build ;;
    *) sed -n '2,9p' "$0"; exit 1 ;;
esac

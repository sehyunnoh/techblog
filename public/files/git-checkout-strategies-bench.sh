#!/usr/bin/env bash
# What each stock-git checkout strategy downloads and stores for one big repository.
# Usage:  bash git-checkout-strategies-bench.sh [workdir] [repo-url] [subdir]
# Defaults: ./gitbench, https://github.com/rust-lang/rust.git, library/core
# Needs about 6 GB of free disk and downloads several GB in total.
# Tested with git 2.55.0 on Windows 11 (Git for Windows, bash); other versions untested.
set -u
export GIT_TERMINAL_PROMPT=0
# Windows: this repository has paths longer than 260 characters, and without this the checkout
# stops partway ("Filename too long") while the clone still reports success.
GIT="git -c core.longpaths=true"
W="${1:-./gitbench}"
URL="${2:-https://github.com/rust-lang/rust.git}"
SUB="${3:-library/core}"
OLD_TAG="${OLD_TAG:-1.85.0}"      # an older tag used for the "stay up to date" test
mkdir -p "$W" && cd "$W" || exit 1

# Size of the object store in MiB. Git keeps received packs as they arrive, so this is close to
# the bytes downloaded. (Progress lines are not used: lazy blob fetches during checkout do not print any.)
objects_mib() { du -sk "$1/.git/objects" 2>/dev/null | awk '{printf "%.1f", $1/1024}'; }

printf "%-46s %8s %12s %9s %7s\n" "strategy" "seconds" "objects MiB" "tree MiB" "files"

run() { # label dir -- git-args...
  local label="$1" dir="$2"; shift 3
  rm -rf "$dir"
  local t0 t1; t0=$(date +%s)
  "$@" > "$dir.log" 2>&1
  t1=$(date +%s)
  local files; files=$(find "$dir" -path "$dir/.git" -prune -o -type f -print | wc -l)
  local tree; tree=$(( $(du -sk "$dir" | awk '{print $1}') - $(du -sk "$dir/.git" | awk '{print $1}') ))
  printf "%-46s %8d %12s %9s %7d\n" "$label" $((t1-t0)) "$(objects_mib "$dir")" "$(awk -v k="$tree" 'BEGIN{printf "%.1f", k/1024}')" "$files"
  if grep -q -E "checkout failed|Filename too long" "$dir.log"; then echo "  !! checkout failed for '$label', this row is not valid (see $dir.log)"; fi
}

run "full clone"                                   full    -- $GIT clone "$URL" full
run "shallow (--depth 1)"                          shallow -- $GIT clone --depth 1 "$URL" shallow
run "blobless (--filter=blob:none)"                blobless -- $GIT clone --filter=blob:none "$URL" blobless
run "treeless (--filter=tree:0)"                   treeless -- $GIT clone --filter=tree:0 "$URL" treeless
run "shallow + sparse ($SUB)"                      shsparse -- bash -c "$GIT clone --depth 1 --sparse '$URL' shsparse && $GIT -C shsparse sparse-checkout set '$SUB'"
run "shallow + blobless + sparse ($SUB)"           minimal -- bash -c "$GIT clone --depth 1 --filter=blob:none --sparse '$URL' minimal && $GIT -C minimal sparse-checkout set '$SUB'"
run "blobless + sparse, full history ($SUB)"       blsparse -- bash -c "$GIT clone --filter=blob:none --sparse '$URL' blsparse && $GIT -C blsparse sparse-checkout set '$SUB'"

echo
echo "commits reachable: full=$($GIT -C full rev-list --count HEAD) shallow=$($GIT -C shallow rev-list --count HEAD) blobless=$($GIT -C blobless rev-list --count HEAD) treeless=$($GIT -C treeless rev-list --count HEAD)"
echo "HEAD: $($GIT -C full rev-parse --short HEAD)"

echo
echo "Staying up to date: start from tag $OLD_TAG, then update to the default branch tip"
printf "%-46s %8s %12s %12s\n" "strategy" "seconds" "added MiB" "objects MiB"
upd() { # label dir clone-cmd
  local label="$1" dir="$2" cmd="$3"
  rm -rf "$dir"; bash -c "$cmd" > "$dir.log0" 2>&1
  local before; before=$(du -sk "$dir/.git/objects" | awk '{print $1}')
  local t0 t1; t0=$(date +%s)
  bash -c "cd '$dir' && $GIT fetch --depth 1 origin HEAD && $GIT checkout --quiet FETCH_HEAD" > "$dir.log" 2>&1
  t1=$(date +%s)
  local after; after=$(du -sk "$dir/.git/objects" | awk '{print $1}')
  printf "%-46s %8d %12s %12s\n" "$label" $((t1-t0)) "$(awk -v a="$after" -v b="$before" 'BEGIN{printf "%.1f", (a-b)/1024}')" "$(objects_mib "$dir")"
  if grep -q -E "checkout failed|Filename too long" "$dir.log" "$dir.log0"; then echo "  !! checkout failed for '$label', this row is not valid"; fi
}
upd "shallow, then fetch --depth 1"                 upd1 "$GIT clone --depth 1 --branch $OLD_TAG '$URL' upd1"
upd "shallow+blobless+sparse, then fetch --depth 1" upd2 "$GIT clone --depth 1 --branch $OLD_TAG --filter=blob:none --sparse '$URL' upd2 && $GIT -C upd2 sparse-checkout set '$SUB'"

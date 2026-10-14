#!/usr/bin/env bash
# The hands-on steps from the guide "Git Partial Clone and Sparse Checkout, Step by Step",
# each with its wall time and the growth of .git/objects.
# Usage:  bash git-partial-sparse-guide-steps.sh [workdir] [repo-url] [subdir] [other-subdir]
# Defaults: ./gitguide, https://github.com/rust-lang/rust.git, library/core, library/alloc
# Needs about 3 GB of free disk. Tested with git 2.55.0 on Windows 11; other versions untested.
set -u
export GIT_TERMINAL_PROMPT=0
GIT="git -c core.longpaths=true"   # needed on Windows for repositories with very long paths
W="${1:-./gitguide}"
URL="${2:-https://github.com/rust-lang/rust.git}"
SUB="${3:-library/core}"
SUB2="${4:-library/alloc}"
FILE_OUT="${FILE_OUT:-compiler/rustc_borrowck/src/lib.rs}"   # a file outside the sparse set
FILE_HIST="${FILE_HIST:-library/core/src/option.rs}"          # a file with a long history
mkdir -p "$W" && cd "$W" || exit 1

objs() { du -sk "$1/.git/objects" | awk '{printf "%.1f", $1/1024}'; }
now() { date +%s.%N; }
secs() { awk -v a="$1" -v b="$(now)" 'BEGIN{printf "%.1f", b-a}'; }
files_on_disk() { find "$1" -path "$1/.git" -prune -o -type f -print | wc -l; }
rm -rf min min2 bl tr

echo "### 1. clone: shallow + blobless + sparse"
t=$(now); $GIT clone --depth 1 --filter=blob:none --sparse "$URL" min >/dev/null 2>&1; $GIT -C min sparse-checkout set "$SUB" >/dev/null 2>&1
echo "   $(secs $t) s, objects $(objs min) MiB, files on disk $(files_on_disk min), tracked $($GIT -C min ls-files | wc -l)"

echo "### 2. what the repository records about itself"
$GIT -C min config --get-regexp '^(remote\.origin\.(promisor|partialclonefilter)|core\.sparsecheckout|core\.sparsecheckoutcone)' | sed 's/^/   /'
echo "   shallow: $($GIT -C min rev-parse --is-shallow-repository), sparse list: $($GIT -C min sparse-checkout list | tr '\n' ' ')"

echo "### 3. objects it knows about but does not have"
t=$(now); n=$($GIT -C min rev-list --objects --missing=print HEAD | grep -c '^?'); echo "   $n missing blobs, $(secs $t) s"

echo "### 4. read one file outside the sparse set (lazy fetch of a single blob)"
b=$(objs min); t=$(now); $GIT -C min show "HEAD:$FILE_OUT" | wc -l | sed 's/^/   lines: /'
echo "   $(secs $t) s, objects $b -> $(objs min) MiB"

echo "### 5. add a second directory to the sparse set"
b=$(objs min); t=$(now); $GIT -C min sparse-checkout add "$SUB2" >/dev/null 2>&1
echo "   $(secs $t) s, objects $b -> $(objs min) MiB, files on disk $(files_on_disk min)"

echo "### 6. deepen history"
cp -r min min2
for d in 1 5; do
  b=$(objs min); t=$(now); $GIT -C min fetch --deepen=$d -q >/dev/null 2>&1
  echo "   --deepen=$d: $(secs $t) s, objects $b -> $(objs min) MiB, commits now $($GIT -C min rev-list --count HEAD)"
done
SINCE=$(date -u -d '3 days ago' +%Y-%m-%d 2>/dev/null || date -u +%Y-%m-%d)
b=$(objs min2); t=$(now); $GIT -C min2 fetch --shallow-since="$SINCE" -q >/dev/null 2>&1
echo "   --shallow-since=$SINCE: $(secs $t) s, objects $b -> $(objs min2) MiB, commits now $($GIT -C min2 rev-list --count HEAD)"

echo "### 7. history commands: blobless clone, no checkout"
t=$(now); $GIT clone --filter=blob:none --no-checkout "$URL" bl >/dev/null 2>&1
echo "   clone $(secs $t) s, objects $(objs bl) MiB"
b=$(objs bl); t=$(now); n=$($GIT -C bl log -n 20 --oneline -- "$FILE_HIST" | wc -l)
echo "   log -n 20 -- $FILE_HIST: $n commits, $(secs $t) s, objects $b -> $(objs bl) MiB"
b=$(objs bl); t=$(now); n=$(timeout 900 $GIT -C bl blame "HEAD" -- "$FILE_HIST" 2>/dev/null | wc -l); rc=$?
echo "   blame $FILE_HIST: $n lines, $(secs $t) s, objects $b -> $(objs bl) MiB"

echo "### 8. the same log in a treeless clone, no checkout"
t=$(now); $GIT clone --filter=tree:0 --no-checkout "$URL" tr >/dev/null 2>&1
echo "   clone $(secs $t) s, objects $(objs tr) MiB"
b=$(objs tr); t=$(now); n=$(timeout 900 $GIT -C tr log -n 20 --oneline -- "$FILE_HIST" | wc -l)
echo "   log -n 20 -- $FILE_HIST: $n commits, $(secs $t) s, objects $b -> $(objs tr) MiB"

echo "### 9. change your mind: turn sparse checkout off (needs the whole tree)"
b=$(objs min); t=$(now); $GIT -C min sparse-checkout disable >/dev/null 2>&1
echo "   $(secs $t) s, objects $b -> $(objs min) MiB, files on disk $(files_on_disk min)"

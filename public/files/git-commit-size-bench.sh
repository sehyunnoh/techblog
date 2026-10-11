#!/bin/bash
# Measures what a Git commit costs: loose objects (file bytes and disk blocks) vs packed,
# for tiny commits and for large files. Run on a Linux filesystem, not tmpfs.
# usage: ./git-commit-size-bench.sh tiny | large
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t
work=$(mktemp -d -p "$HOME")
trap 'rm -rf "$work"' EXIT
cd "$work" || exit 1

newrepo() { # name [object-format]
  git init -q --object-format="${2:-sha1}" "$1" && cd "$1" || exit 1
  git config core.autocrlf false
  git config gc.auto 0
  git config maintenance.auto false   # otherwise git may pack objects behind your back mid-run
}
loose_bytes() { find .git/objects -type f -not -path '*/pack/*' -printf '%s\n' | awk '{s+=$1} END{print s+0}'; }
pack_bytes()  { find .git/objects/pack -type f \( -name '*.pack' -o -name '*.idx' \) -printf '%s\n' | awk '{s+=$1} END{print s+0}'; }

tiny() {
  for fmt in sha1 sha256; do
    newrepo "r_$fmt" "$fmt"
    seq 1 50 | sed 's/^/line /' > f.txt; git add f.txt; git commit -qm init
    for i in $(seq 1 200); do
      sed -i "$(( (i % 50) + 1 ))s/.*/edited at commit $i/" f.txt
      git commit -qam "change $i"
    done
    n=$(git rev-list --count HEAD)
    lb=$(loose_bytes); kb=$(du -sk .git/objects | cut -f1)
    git gc -q --prune=now
    pb=$(pack_bytes)
    echo "$fmt commits=$n loose-file-bytes/commit=$((lb / n)) loose-on-disk/commit=$((kb * 1024 / n)) packed/commit=$((pb / n))"
    cd ..
  done
}

large() {
  python3 - <<'PY'
import os, subprocess, gzip
n = 16415223
src = b''.join(open(os.path.join(r, f), 'rb').read()
               for r, _, fs in os.walk('/usr/lib/python3.12') for f in sorted(fs) if f.endswith('.py'))[:n]
open('text.in', 'wb').write(src)
open('gz.in', 'wb').write(gzip.compress(src))
open('rand.in', 'wb').write(os.urandom(n))
open('rep.in', 'wb').write((b'the same line over and over\n' * n)[:n])
PY
  cat /usr/bin/* 2>/dev/null | head -c 16415223 > bin.in
  base=$PWD
  for c in text bin rand gz rep; do
    newrepo "r_$c"
    cp "$base/$c.in" data; raw=$(stat -c %s data)
    git add data; git commit -qm init; one=$(loose_bytes)
    printf 'one more line\n' >> data; git commit -qam edit; two=$(loose_bytes)
    git gc -q --aggressive --prune=now; pk=$(pack_bytes)
    echo "$c raw=$raw loose-1-commit=$one loose-2-commits=$two packed-2-commits=$pk"
    cd "$base"
  done
}

"${1:-tiny}"

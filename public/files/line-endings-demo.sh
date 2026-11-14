#!/usr/bin/env bash
# Shows what `git checkout` writes to the working tree for different
# core.autocrlf values, with and without a .gitattributes `eol=lf` rule.
# Needs only git and bash. Works in a throwaway directory.
set -eu
d=$(mktemp -d); cd "$d"
git init -q .; git config user.email demo@example.com; git config user.name demo
git config core.autocrlf false        # commit the file exactly as written
printf 'echo hi\n' > a.sh
git add a.sh; git commit -qm base
echo "git $(git --version | awk '{print $3}'); system core.autocrlf='$(git config --system core.autocrlf || true)'"
show() { # label
  printf '%-44s %s\n' "$1" "$(git ls-files --eol a.sh | awk '{print "index=" $1 " worktree=" $2}')"
}
echo "--- no .gitattributes"
for cfg in true input false; do
  rm -f a.sh; git -c core.autocrlf=$cfg checkout -- a.sh; show "core.autocrlf=$cfg"
done
echo "--- .gitattributes: * text=auto eol=lf"
printf '* text=auto eol=lf\n' > .gitattributes; git add .gitattributes; git commit -qm attrs
for cfg in true input false; do
  rm -f a.sh; git -c core.autocrlf=$cfg checkout -- a.sh; show "core.autocrlf=$cfg"
done
echo "--- .gitattributes: * text=auto eol=crlf"
printf '* text=auto eol=crlf\n' > .gitattributes; git add .gitattributes; git commit -qm attrs2
for cfg in true input false; do
  rm -f a.sh; git -c core.autocrlf=$cfg checkout -- a.sh; show "core.autocrlf=$cfg"
done
cd /; rm -rf "$d"

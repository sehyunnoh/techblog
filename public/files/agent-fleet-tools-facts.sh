#!/usr/bin/env bash
# Prints repo facts and latest-release asset sizes for three coding-agent
# fleet tools. Read-only: it only calls the GitHub API through the `gh` CLI
# (you must be logged in with `gh auth login`). It runs nothing from the repos.
#
# Usage: bash agent-fleet-tools-facts.sh
# The numbers in the guide come from a run on 2026-11-04.

set -u
repos="stablyai/orca getpaseo/paseo herdrdev/herdr"
since="${SINCE:-2026-10-04}"   # 30 days before the run date

for r in $repos; do
  echo "=== $r"
  gh api "repos/$r" --jq '"stars \(.stargazers_count)  forks \(.forks_count)  license \(.license.spdx_id)  created \(.created_at[0:10])  default branch pushed \(.pushed_at[0:10])"'
  gh api "repos/$r/releases/latest" --jq '"latest release \(.tag_name) on \(.published_at[0:10])"'
  # Counts every published release since $since (pre-releases included, if any)
  n=$(gh api "repos/$r/releases?per_page=100" --jq "[.[] | select(.published_at > \"$since\")] | length")
  echo "releases published since $since: $n"
  echo "latest release assets, size in MB (installers and binaries only):"
  gh api "repos/$r/releases/latest" --jq '.assets[] | select(.name | test("yml$|blockmap$|sourcemaps") | not) | "  \(.name)\t\((.size/1048576*10|floor)/10)"'
done

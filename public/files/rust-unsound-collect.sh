#!/usr/bin/env bash
# Download every issue labelled I-unsound in rust-lang/rust (open and closed).
# Needs the GitHub CLI (gh), logged in. Output: rust-unsound-issues.json
set -euo pipefail
gh issue list -R rust-lang/rust --label I-unsound --state all --limit 2000 \
  --json number,title,state,createdAt,closedAt,labels,stateReason \
  > rust-unsound-issues.json
python3 -c "import json;d=json.load(open('rust-unsound-issues.json',encoding='utf-8'));print(len(d),'issues')"

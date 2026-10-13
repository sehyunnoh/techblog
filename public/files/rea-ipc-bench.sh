#!/usr/bin/env bash
# Reproduces the measurements in "REA analysis of a 1.4 KB Electron app".
# Usage:  REA="npx -y rea-agents@6.4.0" bash rea-ipc-bench.sh [workdir]
# Needs Node.js >= 22.19 and network access for the first npx download.
# The script only reads four tiny apps it creates itself. Nothing is installed
# into your agent configuration (it never runs `rea setup`).
set -u
REA="${REA:-npx -y rea-agents@6.4.0}"
W="${1:-./rea-bench}"
mkdir -p "$W" && cd "$W" || exit 1

mkapp() { # $1 = dir
  mkdir -p "$1"
  cat > "$1/package.json" <<'EOF'
{ "name": "notes-demo", "version": "1.0.0", "main": "main.js", "dependencies": { "electron": "30.0.0" } }
EOF
  cat > "$1/main.js" <<'EOF'
const { app, BrowserWindow, ipcMain, shell } = require('electron');
const fs = require('fs');
const path = require('path');
const https = require('https');
const API_BASE = 'https://api.notes-demo.example/v2';
// old endpoint https://legacy.notes-demo.example/v1 (unused)
function createWindow() {
  const win = new BrowserWindow({ width: 800, height: 600, webPreferences: { nodeIntegration: true, contextIsolation: false } });
  win.loadFile('index.html');
}
ipcMain.handle('notes:save', async (_e, name, text) => {
  fs.writeFileSync(path.join(app.getPath('userData'), name + '.txt'), text);
  return true;
});
ipcMain.handle('notes:sync', async (_e, token) => {
  return new Promise((res) => {
    const req = https.request(API_BASE + '/sync', { method: 'POST', headers: { Authorization: 'Bearer ' + token } }, (r) => res(r.statusCode));
    req.end();
  });
});
ipcMain.on('open-external', (_e, url) => shell.openExternal(url));
function neverCalled() { require('child_process').exec('rm -rf /tmp/cache'); }
app.whenReady().then(createWindow);
EOF
}

# The same renderer code, placed four different ways.
mkapp inline-script
cat > inline-script/index.html <<'EOF'
<html><body><textarea id="t"></textarea><button id="s">Save</button>
<script>const { ipcRenderer } = require('electron');
document.getElementById('s').onclick = () => ipcRenderer.invoke('notes:save', 'note1', document.getElementById('t').value);</script></body></html>
EOF

mkapp external-file
cat > external-file/index.html <<'EOF'
<html><body><textarea id="t"></textarea><button id="s">Save</button>
<script src="renderer.js"></script></body></html>
EOF
cat > external-file/renderer.js <<'EOF'
const { ipcRenderer } = require('electron');
document.getElementById('s').onclick = () => ipcRenderer.invoke('notes:save', 'note1', document.getElementById('t').value);
EOF

mkapp inline-module
cat > inline-module/index.html <<'EOF'
<html><body><textarea id="t"></textarea><button id="s">Save</button>
<script type="module">import { ipcRenderer } from 'electron';
document.getElementById('s').onclick = () => ipcRenderer.invoke('notes:save', 'note1', document.getElementById('t').value);</script></body></html>
EOF

mkapp onclick-attr
cat > onclick-attr/index.html <<'EOF'
<html><body><textarea id="t"></textarea><button id="s" onclick="require('electron').ipcRenderer.invoke('notes:save', 'note1', document.getElementById('t').value)">Save</button></body></html>
EOF

RANGE='normalized_result.graph.nodes[0,40].observations[0,1].properties.web_preferences'

echo "app            bytes  ipc: renderer_tx paired main_handlers  parsedJS  full_tokens  range_tokens"
for a in inline-script external-file inline-module onclick-attr; do
  bytes=$(cat "$a"/* | wc -c)
  $REA analyze-javascript-application "$a" --format json > "out_$a.json" 2>/dev/null
  read -r tx pr mh pj <<<"$(node -e '
    const j = JSON.parse(require("fs").readFileSync(process.argv[1], "utf8"));
    const n = j.normalized_result, i = n.summary.ipc;
    console.log(i.renderer_transmissions, i.paired_renderer_transmissions, i.main_handlers, n.statistics.parsed_javascript_files);
  ' "out_$a.json")"
  ft=$($REA analyze-javascript-application "$a" --format json --token-count 2>/dev/null | tail -1)
  rt=$($REA analyze-javascript-application "$a" --format json --filter-output "$RANGE" --token-count 2>/dev/null | tail -1)
  printf "%-14s %5s  %12s %6s %13s %9s %12s %13s\n" "$a" "$bytes" "$tx" "$pr" "$mh" "$pj" "$ft" "$rt"
done

echo
echo "summary-only tokens (external-file): $($REA analyze-javascript-application external-file --format json --filter-output normalized_result.summary --token-count 2>/dev/null | tail -1)"

echo
echo "determinism (external-file, 5 runs, evidence_id and size):"
for i in 1 2 3 4 5; do
  $REA analyze-javascript-application external-file --format json --full-output > "run_$i.json" 2>/dev/null
  echo "  run$i $(wc -c < "run_$i.json") $(grep -o '"evidence_id":"[^"]*"' "run_$i.json" | head -1)"
done

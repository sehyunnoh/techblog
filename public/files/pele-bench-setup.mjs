// Setup for pele-bench.html. Run from an empty directory that has this file and pele-bench.html:
//   npm i pele@1.6.0 mermaid@11.17.2 esbuild
//   node pele-bench-setup.mjs /path/to/TechBlog/src/content/blog
// It extracts every <Mermaid code={`...`}> block, bundles both libraries with esbuild,
// then serves the folder on :8765 with gzip so transferSize reflects what a browser would download.
import fs from 'fs'; import path from 'path'; import zlib from 'zlib'; import http from 'http';
import { build } from 'esbuild';

const blogDir = process.argv[2];
const out = [];
for (const f of fs.readdirSync(blogDir).filter((f) => /\.mdx?$/.test(f) && !f.startsWith('_'))) {
  const t = fs.readFileSync(path.join(blogDir, f), 'utf8');
  const re = /<Mermaid[\s\S]*?code=\{`([\s\S]*?)`\}/g; let m, i = 0;
  while ((m = re.exec(t))) out.push({ id: f.replace(/\.mdx?$/, '') + '#' + i++, code: m[1].replace(/\`/g, '`').replace(/\\/g, '\').trim() });
}
fs.writeFileSync('diagrams.json', JSON.stringify(out, null, 1));
console.log(out.length, 'diagrams');

fs.writeFileSync('e-pele.js', "import {render} from 'pele'; window.r = render;");
fs.writeFileSync('e-mmd.js', "import m from 'mermaid'; window.m = m;");
fs.writeFileSync('e-core.js', "import {register, render} from 'pele/core'; import flowchart from 'pele/diagrams/flowchart'; import sequence from 'pele/diagrams/sequence'; register(flowchart); register(sequence); window.r = render;");
await build({ entryPoints: ['e-pele.js'], bundle: true, minify: true, format: 'esm', outfile: 'b/pele.js' });
await build({ entryPoints: ['e-core.js'], bundle: true, minify: true, format: 'esm', outfile: 'b/pele-core.js' });
await build({ entryPoints: ['e-mmd.js'], bundle: true, minify: true, splitting: true, format: 'esm', outdir: 'b/mmd' });

const types = { '.js': 'text/javascript', '.html': 'text/html', '.json': 'application/json' };
http.createServer((q, r) => {
  const p = path.join(process.cwd(), decodeURIComponent(q.url.split('?')[0]));
  if (!fs.existsSync(p) || fs.statSync(p).isDirectory()) { r.writeHead(404); return r.end(); }
  r.writeHead(200, { 'content-type': types[path.extname(p)] || 'application/octet-stream', 'content-encoding': 'gzip', 'cache-control': 'no-store' });
  r.end(zlib.gzipSync(fs.readFileSync(p), { level: 9 }));
}).listen(8765, () => console.log('open http://localhost:8765/pele-bench.html?lib=pele  or  ?lib=mmd  (add &only=flowchart to filter)'));

const urls = ['https://example.com/', 'https://lleg.dev/', 'https://en.wikipedia.org/wiki/Web_browser'];
const out = [];
for (const url of urls) {
  for (let i = 0; i < 5; i++) {
    const t0 = Date.now();
    const p = await openTab(url);
    const t1 = Date.now();
    const s = await snapshot(p, {});
    const t2 = Date.now();
    const si = await snapshot(p, { interactive: true });
    const t3 = Date.now();
    out.push({ url, i, openMs: t1 - t0, snapMs: t2 - t1, snapChars: s.tree.length, interMs: t3 - t2, interChars: si.tree.length });
    await closeTab(p);
  }
}
console.log(JSON.stringify(out));

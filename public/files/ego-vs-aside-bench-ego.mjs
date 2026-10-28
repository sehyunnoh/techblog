const task = await taskSpace("bench ego vs aside 20261028");
const page = task.page("p1");
const urls = ['https://example.com/', 'https://lleg.dev/', 'https://en.wikipedia.org/wiki/Web_browser'];
const out = [];
for (const url of urls) {
  for (let i = 0; i < 5; i++) {
    const t0 = Date.now();
    await page.goto(url);
    const t1 = Date.now();
    const s = await page.snapshot({ scope: "full_page" });
    const t2 = Date.now();
    const v = await page.snapshot();
    const t3 = Date.now();
    out.push({ url, i, openMs: t1 - t0, snapMs: t2 - t1, snapChars: s.length, viewMs: t3 - t2, viewChars: v.length });
  }
}
console.log("RESULT" + JSON.stringify(out));
await task.finish({ keep: [] });

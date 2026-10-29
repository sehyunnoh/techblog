// Sum claude_code.api_request events by query_source from the OTel console output.
// Usage: node agent-summary-aggregate.mjs <out_dir> <label> [<label> ...]
import fs from 'node:fs';

const [dir, ...labels] = process.argv.slice(2);
for (const label of labels) {
  const text = fs.readFileSync(`${dir}/${label}.out.txt`, 'utf8');
  const blocks = text.split('body: "claude_code.api_request"').slice(1);
  const agg = {};
  for (const block of blocks) {
    const body = block.split('\n  },\n}')[0];
    const kv = {};
    for (const line of body.split('\n')) {
      const i = line.indexOf(': ');
      if (i < 0) continue;
      kv[line.slice(0, i).trim().replace(/"/g, '')] = line.slice(i + 2).replace(/,$/, '').replace(/"/g, '');
    }
    const a = (agg[kv.query_source] ??= { n: 0, input: 0, output: 0, cacheRead: 0, cacheCreate: 0, cost: 0 });
    a.n++;
    a.input += +kv.input_tokens;
    a.output += +kv.output_tokens;
    a.cacheRead += +kv.cache_read_tokens;
    a.cacheCreate += +kv.cache_creation_tokens;
    a.cost += +kv.cost_usd;
  }
  const total = Object.values(agg).reduce((s, a) => ({
    n: s.n + a.n,
    cost: s.cost + a.cost,
    tokens: s.tokens + a.input + a.output + a.cacheRead + a.cacheCreate,
  }), { n: 0, cost: 0, tokens: 0 });
  console.log(`== ${label}: ${total.n} requests, $${total.cost.toFixed(5)}, ${total.tokens} tokens`);
  for (const [source, a] of Object.entries(agg)) {
    const tokens = a.input + a.output + a.cacheRead + a.cacheCreate;
    console.log(
      source.padEnd(32),
      `n=${a.n} cacheRead=${a.cacheRead} cacheCreate=${a.cacheCreate} cost=$${a.cost.toFixed(5)}`,
      `(${(100 * a.cost / total.cost).toFixed(1)}% cost, ${(100 * a.n / total.n).toFixed(1)}% requests, ${(100 * tokens / total.tokens).toFixed(1)}% tokens)`,
    );
  }
}

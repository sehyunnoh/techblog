"""A tiny GPT-style transformer in NumPy, used to measure how prefill, the KV cache
and decoding behave. Random weights: the text it produces is noise, but the work per
token is the same shape as in a real model. Usage: python llm-inference-toy.py"""
import time, statistics, sys
import numpy as np

L, D, H, FFN, V, MAXT = 12, 768, 12, 3072, 32000, 1100   # GPT-2-small-sized
DH = D // H
rng = np.random.default_rng(0)
f32 = np.float32
W = dict(
    tok=(rng.standard_normal((V, D)) * .02).astype(f32), pos=(rng.standard_normal((MAXT, D)) * .02).astype(f32),
    qkv=[(rng.standard_normal((D, 3 * D)) * .02).astype(f32) for _ in range(L)],
    o=[(rng.standard_normal((D, D)) * .02).astype(f32) for _ in range(L)],
    w1=[(rng.standard_normal((D, FFN)) * .02).astype(f32) for _ in range(L)],
    w2=[(rng.standard_normal((FFN, D)) * .02).astype(f32) for _ in range(L)],
    head=(rng.standard_normal((D, V)) * .02).astype(f32))
PARAMS = sum(a.size for a in [W['tok'], W['pos'], W['head']] + W['qkv'] + W['o'] + W['w1'] + W['w2'])

def norm(x): return x / np.sqrt((x * x).mean(-1, keepdims=True) + 1e-5)
def gelu(x): return .5 * x * (1 + np.tanh(.79788456 * (x + .044715 * x ** 3)))

class Cache:
    def __init__(s): s.k = np.zeros((L, H, MAXT, DH), f32); s.v = np.zeros((L, H, MAXT, DH), f32); s.n = 0

def forward(ids, cache):
    """Run `ids` (new tokens only) through the model, appending their keys/values to the cache."""
    n, p0 = len(ids), cache.n
    x = W['tok'][ids] + W['pos'][p0:p0 + n]
    for l in range(L):
        qkv = norm(x) @ W['qkv'][l]
        q, k, v = (t.reshape(n, H, DH).transpose(1, 0, 2) for t in np.split(qkv, 3, axis=1))
        cache.k[l, :, p0:p0 + n] = k; cache.v[l, :, p0:p0 + n] = v
        T = p0 + n
        s = q @ cache.k[l, :, :T].transpose(0, 2, 1) / f32(DH ** .5)  # a float64 scalar here would upcast the whole model
        if n > 1:  # causal mask only matters when several new tokens are processed at once
            s += np.triu(np.full((n, T), -1e9, f32), k=T - n + 1)
        s = np.exp(s - s.max(-1, keepdims=True)); s /= s.sum(-1, keepdims=True)
        a = (s @ cache.v[l, :, :T]).transpose(1, 0, 2).reshape(n, D)
        x = x + a @ W['o'][l]
        x = x + gelu(norm(x) @ W['w1'][l]) @ W['w2'][l]
    cache.n += n
    return norm(x[-1:]) @ W['head']   # logits for the last position only

def gen_cached(prompt, steps):
    c = Cache(); out = []; times = []
    t = time.perf_counter(); lg = forward(prompt, c); pre = time.perf_counter() - t
    for _ in range(steps):
        nxt = int(lg.argmax()); out.append(nxt)
        t = time.perf_counter(); lg = forward([nxt], c); times.append(time.perf_counter() - t)
    return out, pre, times

def gen_nocache(prompt, steps):
    seq = list(prompt); out = []; times = []
    for _ in range(steps):
        t = time.perf_counter(); lg = forward(seq, Cache()); times.append(time.perf_counter() - t)
        nxt = int(lg.argmax()); out.append(nxt); seq.append(nxt)
    return out, times

if __name__ == '__main__':
    print(f'params {PARAMS/1e6:.1f}M, float32 weights {PARAMS*4/1e6:.0f} MB, numpy {np.__version__}')
    prompt = list(rng.integers(0, V, 512))
    forward(prompt[:8], Cache())  # warm-up
    a, pre, tc = gen_cached(prompt, 40); b, tn = gen_nocache(prompt, 40)
    print('same tokens with and without cache:', a == b)
    print(f'prefill 512 tokens: {pre*1e3:.0f} ms = {512/pre:.0f} tok/s')
    print(f'decode with cache: first 10 median {statistics.median(tc[:10])*1e3:.1f} ms, last 10 median {statistics.median(tc[-10:])*1e3:.1f} ms')
    print(f'decode no cache:   first 10 median {statistics.median(tn[:10])*1e3:.1f} ms, last 10 median {statistics.median(tn[-10:])*1e3:.1f} ms')
    # decode cost versus context length, with the cache
    print('context  ms/token (median of 15, cached)')
    for ctx in (64, 256, 512, 1024):
        c = Cache(); forward(list(rng.integers(0, V, ctx)), c); ts = []
        for _ in range(15):
            t = time.perf_counter(); forward([1], c); ts.append(time.perf_counter() - t)
        print(f'{ctx:6d}  {statistics.median(ts)*1e3:.2f}')
    # batch size: cost of decoding one token vs a prefill chunk of the same weights
    print('tokens per forward call -> ms per call, ms per token')
    c = Cache(); forward(list(rng.integers(0, V, 16)), c)
    for n in (1, 2, 4, 8, 16, 64, 256):
        ts = []
        for _ in range(7):
            cc = Cache(); t = time.perf_counter(); forward(list(rng.integers(0, V, n)), cc); ts.append(time.perf_counter() - t)
        m = statistics.median(ts); print(f'{n:6d}  {m*1e3:8.2f}  {m*1e3/n:7.3f}')

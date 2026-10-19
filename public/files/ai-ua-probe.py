import urllib.request, urllib.error, json, time, random, sys

random.seed(20261019)
LIGHT = {"chase.com","schwab.com","delta.com","amtrak.com","united.com","aa.com","southwest.com",
         "bankofamerica.com","wellsfargo.com","fidelity.com","paypal.com"}
SITES = """amazon.com yelp.com cars.com walmart.com bestbuy.com sephora.com gap.com shopify.com ticketmaster.com
opentable.com nytimes.com wikipedia.org github.com reddit.com stackoverflow.com cloudflare.com bbc.com theverge.com
etsy.com ebay.com target.com homedepot.com lowes.com costco.com wayfair.com macys.com nike.com zillow.com airbnb.com
booking.com expedia.com tripadvisor.com hilton.com marriott.com doordash.com instacart.com linkedin.com medium.com
quora.com imdb.com cnn.com washingtonpost.com theguardian.com forbes.com bloomberg.com techcrunch.com wired.com
npmjs.com pypi.org developer.mozilla.org stripe.com vercel.com netlify.com openai.com anthropic.com""".split() + sorted(LIGHT)
BROWSER = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36"
UAS = {
 "browser": BROWSER,
 "browser_ctl": BROWSER,
 "ChatGPT-User": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; ChatGPT-User/1.0; +https://openai.com/bot",
 "ClaudeBot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; ClaudeBot/1.0; +claudebot@anthropic.com)",
 "GPTBot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; GPTBot/1.1; +https://openai.com/gptbot)",
}
HDRS = ("server","cf-mitigated","x-datadome","x-datadome-response","x-px-block","x-akamai-edgescape","retry-after")

def get(url, ua):
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "text/html,*/*;q=0.8", "Accept-Language": "en-US,en;q=0.9"})
    t = time.time()
    try:
        r = urllib.request.urlopen(req, timeout=20)
        body = r.read(300000); st = r.status; h = r.headers
    except urllib.error.HTTPError as e:
        body = e.read(300000); st = e.code; h = e.headers
    except Exception as e:
        return {"status": "ERR", "err": f"{type(e).__name__}: {str(e)[:80]}", "bytes": 0, "sec": round(time.time()-t,2), "hdr": {}}
    return {"status": st, "bytes": len(body), "sec": round(time.time()-t,2),
            "hdr": {k: h.get(k) for k in HDRS if h.get(k)}, "body": body.decode("utf8","ignore") if st==200 and b"user-agent" in body.lower() and url.endswith("robots.txt") else None}

out = open("full.jsonl","a",encoding="utf8")
def log(rec): out.write(json.dumps(rec)+"\n"); out.flush()

# 1) robots.txt (one browser-UA fetch per site, retry once on error)
hosts = {}
for s in SITES:
    for host in (f"www.{s}", s):
        r = get(f"https://{host}/robots.txt", BROWSER)
        if r["status"] == "ERR": time.sleep(5); r = get(f"https://{host}/robots.txt", BROWSER)
        if r["status"] == 200: break
        time.sleep(1)
    hosts[s] = host
    log({"kind":"robots","site":s,"host":host,**r}); time.sleep(2)
print("robots done", flush=True)

# 2) HTTP probes: 3 rounds (1 for LIGHT sites), UA order shuffled per site per round, sites interleaved
for rnd in range(3):
    order = [s for s in SITES if rnd == 0 or s not in LIGHT]
    random.shuffle(order)
    for s in order:
        names = list(UAS); random.shuffle(names)
        for pos, n in enumerate(names):
            r = get(f"https://{hosts[s]}/", UAS[n]); retried = False
            if r["status"] == "ERR": time.sleep(5); r = get(f"https://{hosts[s]}/", UAS[n]); retried = True
            r.pop("body", None)
            log({"kind":"probe","site":s,"host":hosts[s],"round":rnd,"pos":pos,"ua":n,"retried":retried,**r})
            time.sleep(2)
    print("round", rnd, "done", flush=True)
print("ALL DONE", flush=True)

import json, collections, statistics as st, urllib.robotparser
rows=[json.loads(l) for l in open("full.jsonl",encoding="utf8")]
rob={r["site"]:r for r in rows if r["kind"]=="robots"}
pr=[r for r in rows if r["kind"]=="probe"]
AI=["GPTBot","ChatGPT-User","ClaudeBot"]
by=collections.defaultdict(lambda:collections.defaultdict(list))
for r in pr: by[r["site"]][r["ua"]].append(r)
def base(s):
    ok=[r["bytes"] for u in ("browser","browser_ctl") for r in by[s][u] if r["status"]==200]
    return st.median(ok) if ok else None
def cls(r,b):
    if r["status"]=="ERR": return "ERR"
    if r["status"]>=400: return "BLK"
    if b is None: return "?"
    if b>=300000:  # browser page hit my 300 KB read cap: only tiny responses count as stubs
        return "SHORT" if r["bytes"]<10000 else "SAME"
    ratio=r["bytes"]/b
    if ratio<0.5: return "SHORT"      # 2xx but far smaller than browser page (stub/challenge)
    if abs(ratio-1)>0.1: return "DIFF" # 2xx, size differs >10%
    return "SAME"
def agg(l):
    c=collections.Counter(l)
    ne=[k for k in c if k!="ERR"]
    if not ne: return "ERR"
    if set(ne)=={"SAME"}: return "SAME"
    if set(ne)<= {"BLK"}: return "BLK"
    if set(ne)<= {"BLK","SHORT"}: return "BLK" if "BLK" in ne and "SHORT" not in ne else "SHORT"
    return "MIX:"+"/".join(sorted(ne))
res={}; lowcontent=[]
for s in by:
    b=base(s)
    if b is not None and b<10000: lowcontent.append((s,int(b)))
    res[s]={u:agg([cls(r,b) for r in by[s][u]]) for u in by[s]}
usable=[s for s,d in res.items() if d["browser"]=="SAME" or d["browser"]=="?" or (base(s) is not None and d["browser"] in("SAME",))]
usable=[s for s in res if base(s) is not None and base(s)>=10000 and all(r["status"]==200 for r in by[s]["browser"] if r["status"]!="ERR") and any(r["status"]==200 for r in by[s]["browser"])]
print("browser-OK with >=10KB baseline:",len(usable))
print("low-content baselines (<10KB, inconclusive):",sorted(lowcontent))
print("\nsite | robots GPT,CGU,Claude | GPTBot ChatGPT-User ClaudeBot")
def ra(s,t):
    r=rob.get(s)
    if not r or r["status"]!=200 or not r.get("body"): return None
    rp=urllib.robotparser.RobotFileParser(); rp.parse(r["body"].splitlines()); return rp.can_fetch(t,"https://%s/"%r["host"])
f=lambda v:"-" if v is None else "A" if v else "D"
cnt=collections.Counter(); anyblock=0; allblock=0; claude_only=[]; diffs=[]
for s in sorted(usable):
    d=res[s]; rr=[ra(s,t) for t in AI]
    print(f"{s:22} {''.join(f(x) for x in rr)}  {d['GPTBot']:10} {d['ChatGPT-User']:10} {d['ClaudeBot']:10}")
    vals=[d[t] for t in AI]
    if any(v in("BLK","SHORT") for v in vals): anyblock+=1
    if all(v in("BLK","SHORT") for v in vals): allblock+=1
    if d["ClaudeBot"] in("BLK","SHORT") and d["GPTBot"]=="SAME" and d["ChatGPT-User"]=="SAME": claude_only.append(s)
    for t,v in zip(AI,rr):
        h=d[t]
        if h=="ERR": continue
        blocked=h in("BLK","SHORT")
        cnt[(f(v),"blocked" if blocked else ("diff" if h.startswith(("DIFF","MIX")) else "same"))]+=1
print("\ncounts (robots, outcome):",dict(cnt))
print("any AI-UA blocked:",anyblock,"/",len(usable),"| all 3 blocked:",allblock,"| ClaudeBot-only:",claude_only)
print("\nsites with DIFF/MIX (not clean):",[(s,{t:res[s][t] for t in AI}) for s in usable if any(res[s][t].startswith(("DIFF","MIX")) for t in AI)])
print("\nnotable (not usable) sites:")
for s in ["amazon.com","amtrak.com","bestbuy.com","united.com","linkedin.com","delta.com"]:
    print(" ",s,"base",base(s),{u:v for u,v in res[s].items()})

import html, json, re, sys, random, statistics as st

path = sys.argv[1]
h = open(path, encoding="utf-8").read()

# Astro island props: props="{...}" HTML-escaped; values wrapped as [0, v] (scalar) or [1, [..]] (array)
m = re.search(r'props="([^"]*tasks[^"]*)"', h)
raw = html.unescape(m.group(1))
props = json.loads(raw)


def dec(x):
    if isinstance(x, list) and len(x) == 2 and x[0] in (0, 1):
        return dec(x[1]) if x[0] == 0 else [dec(i) for i in x[1]]
    if isinstance(x, dict):
        return {k: dec(v) for k, v in x.items()}
    return x


d = dec(props)
print("props keys:", list(d.keys()))
models = d["models"] if "models" in d else d.get("configs")
tasks = d["tasks"]
print("models:", len(models), "tasks:", len(tasks))
for mo in models:
    print(" ", mo)
json.dump({"models": models, "tasks": tasks}, open(path.replace("data.html", "grid.json"), "w"))

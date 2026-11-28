"""List every network call site in the Convex Claude Code plugin (convex/convex-backend-skill).

Usage:  python -I convex-plugin-egress.py <unpacked-plugin-dir>
Get a snapshot with e.g.
  curl -sL https://codeload.github.com/convex/convex-backend-skill/tar.gz/51b4e65 | tar xz
Counts literal https://basic-anteater-667.convex.site/... URLs, $BASE/$B/${BASE} paths, and PostHog hosts,
skipping *.test.mjs. Each line is: occurrences, file, path, kind (GET / POST / pipe-to-shell).
This is a regex scan, not a parser; it was checked by hand against each SKILL.md.
Snapshots used in the post: 6ca54f6 (marketplace pin), a28c1f4 (before fix), 51b4e65 (after fix).
"""
import re,sys,os,collections
root=sys.argv[1]
host=re.compile(r'(https://basic-anteater-667\.convex\.site|\$\{?BASE\}?|\$\{?B\}?)(/[A-Za-z0-9_./<>?=-]*)')
ph=re.compile(r'posthog\.com')
rows=collections.Counter()
for d,_,fs in os.walk(root):
  for f in fs:
    p=os.path.join(d,f); rel=os.path.relpath(p,root).replace(os.sep,'/')
    if rel.endswith('.test.mjs'): continue
    try: t=open(p,encoding='utf8').read()
    except: continue
    for line in t.splitlines():
      for m in host.finditer(line):
        path=m.group(2).rstrip('.`)')
        if path in ('/',''): continue
        kind='pipe-to-shell' if re.search(r'\|\s*(\w+=\S+\s+)?bash',line) else ('POST' if 'POST' in line else 'GET')
        rows[(rel,path,kind)]+=1
      if ph.search(line) and 'http' in line: rows[(rel,'posthog /capture/','POST')]+=1
for k,v in sorted(rows.items()): print(v,*k,sep='\t')

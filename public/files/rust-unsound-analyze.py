"""Summarise rust-lang/rust issues labelled I-unsound (from rust-unsound-issues.json).
Standard library only. Run: python3 rust-unsound-analyze.py"""
import json, statistics as st
from datetime import datetime
from collections import Counter

d = json.load(open('rust-unsound-issues.json', encoding='utf-8'))
ts = lambda s: datetime.strptime(s, '%Y-%m-%dT%H:%M:%SZ')
NOW = max(ts(i['createdAt']) for i in d)  # newest issue as the "as of" moment
for i in d:
    i['L'] = {l['name'] for l in i['labels']}
    i['c'] = ts(i['createdAt'])
    i['x'] = ts(i['closedAt']) if i['closedAt'] else None
    i['open'] = i['state'] == 'OPEN'
op = [i for i in d if i['open']]
cl = [i for i in d if not i['open']]
print('total', len(d), 'open', len(op), 'closed', len(cl), 'newest created', NOW)

def share(sub, name, cond):
    n = sum(1 for i in sub if cond(i))
    return f'{name}: {n} of {len(sub)} ({100*n/len(sub):.0f}%)'
print('\n-- open issues by team label --')
for t in ['T-libs','T-libs-api','T-compiler','T-lang','T-types','T-opsem','T-rustdoc','T-cargo']:
    print(share(op, t, lambda i, t=t: t in i['L']))
print(share(op, 'no T- label', lambda i: not any(l.startswith('T-') for l in i['L'])))
print(share(op, 'requires-nightly', lambda i: 'requires-nightly' in i['L']))
print(share(op, 'A-stdlib-ish (T-libs or T-libs-api)', lambda i: 'T-libs' in i['L'] or 'T-libs-api' in i['L']))
libs_open = [i for i in op if 'T-libs' in i['L'] or 'T-libs-api' in i['L']]
print(share(libs_open, 'T-libs open and requires-nightly', lambda i: 'requires-nightly' in i['L']))
print('\n-- priority labels on open --')
for p in ['P-critical','P-high','P-medium','P-low']:
    print(share(op, p, lambda i, p=p: p in i['L']))
print(share(op, 'no P- label', lambda i: not any(l.startswith('P-') for l in i['L'])))

print('\n-- created per year (all, then still open) --')
cy = Counter(i['c'].year for i in d); oy = Counter(i['c'].year for i in op)
for y in sorted(cy): print(y, cy[y], oy.get(y, 0))

print('\n-- age of open issues (years) --')
ages = sorted((NOW - i['c']).days / 365.25 for i in op)
print('median %.1f, p75 %.1f, max %.1f' % (st.median(ages), ages[int(.75*len(ages))], ages[-1]))
for k in [1, 3, 5]:
    n = sum(1 for a in ages if a >= k); print(f'open >= {k} years old: {n} ({100*n/len(ages):.0f}%)')

print('\n-- days to close (closed issues) --')
days = sorted((i['x'] - i['c']).days for i in cl)
print('median', st.median(days), 'p75', days[int(.75*len(days))], 'p90', days[int(.9*len(days))])
for k in [7, 30, 365]:
    n = sum(1 for x in days if x <= k); print(f'closed within {k} days: {n} of {len(cl)} ({100*n/len(cl):.0f}%)')
print(Counter(i['stateReason'] for i in cl))

print('\n-- the five FORGE issues --')
for n in [156501, 156490, 156491, 161018, 156951]:
    i = next((x for x in d if x['number'] == n), None)
    if i:
        dd = (i['x'] - i['c']).days if i['x'] else (NOW - i['c']).days
        print(n, i['state'], f"{dd}d", 'nightly' if 'requires-nightly' in i['L'] else 'stable', [l for l in i['L'] if l.startswith('P-')])
print('\n-- std/core-area labels (open) --')
areas = Counter(l for i in op for l in i['L'] if l.startswith('A-'))
print(areas.most_common(12))

print('\n-- created per year, T-libs only (all, still open) --')
lib = [i for i in d if 'T-libs' in i['L'] or 'T-libs-api' in i['L']]
ly = Counter(i['c'].year for i in lib); lo = Counter(i['c'].year for i in lib if i['open'])
print('T-libs total', len(lib), 'open', sum(1 for i in lib if i['open']))
for y in range(2019, 2027): print(y, ly.get(y, 0), lo.get(y, 0))

print('\n-- created per month, 2025-07 to 2026-11 (all, T-libs) --')
cm = Counter(i['c'].strftime('%Y-%m') for i in d); lm = Counter(i['c'].strftime('%Y-%m') for i in lib)
for m in sorted(k for k in cm if k >= '2025-07'): print(m, cm[m], lm.get(m, 0))

print('\n-- the five FORGE issues, titles --')
for n in [156501, 156490, 156491, 161018, 156951]:
    i = next((x for x in d if x['number'] == n), None)
    if i: print(n, i['title'][:90])

"""A small robots.txt matcher that follows RFC 9309, plus a comparison against
Python's urllib.robotparser. Run it: python robots-rfc9309-match.py

Rules implemented from the RFC: groups end at the next user-agent line after
rules, groups naming the same product token are merged, "*" is the fallback
group, the longest matching pattern wins, Allow wins a tie, "*" and "$" are
wildcards, paths are case sensitive, /robots.txt is always allowed.
"""
import re
import sys
import urllib.robotparser


def parse(text):
    groups, agents, rules, in_rules = [], [], [], False
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key, value = key.strip().lower(), value.strip()
        if key == "user-agent":
            if in_rules:
                groups.append((agents, rules))
                agents, rules, in_rules = [], [], False
            agents.append(value.lower())
        elif key in ("allow", "disallow") and agents:
            in_rules = True
            rules.append((key == "allow", value))
    if agents:
        groups.append((agents, rules))
    return groups


def pattern_to_regex(pattern):
    anchored = pattern.endswith("$")
    if anchored:
        pattern = pattern[:-1]
    body = "".join(".*" if ch == "*" else re.escape(ch) for ch in pattern)
    return re.compile("^" + body + ("$" if anchored else ""))


def can_fetch(groups, token, path):
    """token is the crawler's product token, e.g. "GPTBot" (case-insensitive)."""
    if path == "/robots.txt":
        return True
    token = token.lower()
    selected = [r for agents, r in groups if token in agents]
    if not selected:
        selected = [r for agents, r in groups if "*" in agents]
    if not selected:
        return True
    best = None  # (pattern length, is_allow)
    for rules in selected:
        for allow, pattern in rules:
            if pattern and pattern_to_regex(pattern).match(path):
                cand = (len(pattern), allow)
                if best is None or cand[0] > best[0] or (cand[0] == best[0] and allow):
                    best = cand
    return True if best is None else best[1]


CASES = [
    ("Disallow /a/ then Allow /a/b, fetch /a/b", "User-agent: *\nDisallow: /a/\nAllow: /a/b\n", "/a/b"),
    ("Allow /a/b then Disallow /a/, fetch /a/b", "User-agent: *\nAllow: /a/b\nDisallow: /a/\n", "/a/b"),
    ("Disallow /p and Allow /p (tie), fetch /p", "User-agent: *\nDisallow: /p\nAllow: /p\n", "/p"),
    ("Disallow /*.gif$, fetch /x/y.gif", "User-agent: *\nDisallow: /*.gif$\n", "/x/y.gif"),
    ("Disallow /private*/x, fetch /private123/x", "User-agent: *\nDisallow: /private*/x\n", "/private123/x"),
    ("Disallow /fish$, fetch /fish/x", "User-agent: *\nDisallow: /fish$\n", "/fish/x"),
    ("Two groups for Bot, second has /baz", "User-agent: Bot\nDisallow: /foo\n\nUser-agent: Bot\nDisallow: /baz\n", "/baz"),
    ("Specific group overrides *", "User-agent: *\nDisallow: /\n\nUser-agent: Bot\nAllow: /\n", "/x"),
    ("Empty Disallow allows everything", "User-agent: *\nDisallow:\n", "/x"),
    ("Disallow /admin also blocks /administrator", "User-agent: *\nDisallow: /admin\n", "/administrator"),
]


def python_can_fetch(text, path):
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(text.splitlines())
    return rp.can_fetch("Bot", "https://example.test" + path)


if __name__ == "__main__":
    print(sys.version.split()[0])
    differ = 0
    for name, text, path in CASES:
        py, rfc = python_can_fetch(text, path), can_fetch(parse(text), "Bot", path)
        differ += py != rfc
        print(f"{name:46} python={py!s:5} rfc={rfc!s:5} {'DIFFERS' if py != rfc else ''}")
    print(f"{differ} of {len(CASES)} differ")

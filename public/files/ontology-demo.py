"""A tiny ontology, standard library only: subclass inference, domain/range as inference,
disjointness, and the open-world answer "unknown". Run: python ontology-demo.py"""

# Facts about individuals: (subject, predicate, object). "a" means "is an instance of".
facts = {
    ("Rex", "a", "Dog"), ("Tom", "a", "Cat"), ("Mia", "a", "Person"),
    ("Mia", "owns", "Rex"),
    ("Rex", "owns", "Tom"),  # a data-entry mistake: a dog owns a cat
}

# The ontology: statements about classes and properties, not about Rex or Mia.
subclass = {("Dog", "Mammal"), ("Cat", "Mammal"), ("Person", "Mammal"), ("Mammal", "Animal")}
domain = {"owns": "Person"}   # whoever owns something is a Person
range_ = {"owns": "Animal"}   # whatever is owned is an Animal
disjoint = {frozenset(p) for p in [("Person", "Dog"), ("Person", "Cat"), ("Dog", "Cat")]}


def infer(kb):
    """Apply the three rules until nothing new appears."""
    kb = set(kb)
    while True:
        new = set()
        for s, p, o in kb:
            if p == "a":
                new |= {(s, "a", sup) for sub, sup in subclass if sub == o}
            if p in domain:
                new.add((s, "a", domain[p]))
            if p in range_:
                new.add((o, "a", range_[p]))
        if new <= kb:
            return kb
        kb |= new


def types(kb, who):
    return {o for s, p, o in kb if s == who and p == "a"}


def ask(kb, who, cls):
    if cls in types(kb, who):
        return "yes"
    if any(frozenset((cls, t)) in disjoint for t in types(kb, who)):
        return "no"
    return "unknown"


def mammals(kb):
    return sorted(s for s, p, o in kb if p == "a" and o == "Mammal")


closed = facts          # what a plain table knows
open_ = infer(facts)    # what the ontology adds

print("Mammals in the raw facts:     ", mammals(closed))
print("Mammals after subclass rules: ", mammals(open_))
print("Rex is a Person (never stated):", ("Rex", "a", "Person") in open_, "<- inferred from 'Rex owns Tom'")
print("Conflicts:", [(w, sorted(c)) for w in ("Rex", "Tom", "Mia")
                     for c in disjoint if c <= types(open_, w)])
print()
for who, cls in [("Rex", "Cat"), ("Rex", "Reptile"), ("Mia", "Dog")]:
    table = "yes" if (who, "a", cls) in closed else "no"
    print(f"Is {who} a {cls:8s}  table: {table:3s}  ontology: {ask(open_, who, cls)}")

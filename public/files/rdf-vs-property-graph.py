"""Same data as RDF triples (rdflib, SPARQL, OWL RL) and as a property graph (Kuzu, Cypher).

    pip install rdflib owlrl kuzu
    python rdf-vs-property-graph.py

Prints four things: (1) one fact modelled three ways and the statements each needs,
(2) what reasoning does to the size of an RDF graph, (3) how a property graph answers the same
"is it a kind of X" question, (4) 2-hop and 3-hop query timing on a random graph.
Timing compares two different engines (pure-Python rdflib vs embedded C++ Kuzu), so it says
nothing about RDF versus property graphs as models. It is here to show the order of magnitude.
"""
import random, shutil, statistics, tempfile, time
import kuzu
import owlrl
from rdflib import RDF, RDFS, BNode, Graph, Literal, Namespace, URIRef, XSD

EX = Namespace("http://example.org/")

def tmpdb():
    d = tempfile.mkdtemp()
    return kuzu.Database(d + "/db"), d

def rows(res):
    out = []
    while res.has_next():
        out.append(res.get_next())
    return out

# ---------------------------------------------------------------- 1. one fact, three models
def part1():
    print("== 1. 'Caroline attended the support group on 2023-05-07 (source turn D1:3)'")
    # a) plain triples: the relation is a predicate, so it cannot carry a date
    g = Graph(); g.add((EX.Caroline, EX.attended, EX.SupportGroup))
    print(f"plain triple: {len(g)} statement, no place for the date")
    # b) n-ary pattern: promote the relation to a node
    g = Graph(); ev = EX.attendance1
    for t in [(ev, RDF.type, EX.Attendance), (ev, EX.who, EX.Caroline), (ev, EX.what, EX.SupportGroup),
              (ev, EX.date, Literal("2023-05-07", datatype=XSD.date)), (ev, EX.source, Literal("D1:3"))]:
        g.add(t)
    print(f"n-ary event node: {len(g)} statements")
    q = """SELECT ?d WHERE { ?e ex:who ex:Caroline ; ex:what ex:SupportGroup ; ex:date ?d }"""
    print("  SPARQL ->", [str(r[0]) for r in g.query(q, initNs={"ex": EX})])
    # c) RDF reification: keep the plain triple and describe it with more triples
    g = Graph(); g.add((EX.Caroline, EX.attended, EX.SupportGroup)); st = BNode()
    for t in [(st, RDF.type, RDF.Statement), (st, RDF.subject, EX.Caroline), (st, RDF.predicate, EX.attended),
              (st, RDF.object, EX.SupportGroup), (st, EX.date, Literal("2023-05-07", datatype=XSD.date)),
              (st, EX.source, Literal("D1:3"))]:
        g.add(t)
    print(f"reification: {len(g)} statements (1 original + 6 describing it)")
    # d) property graph: the edge has properties
    db, d = tmpdb(); con = kuzu.Connection(db)
    con.execute("CREATE NODE TABLE P(name STRING PRIMARY KEY)")
    con.execute("CREATE REL TABLE ATTENDED(FROM P TO P, date DATE, source STRING)")
    con.execute("CREATE (:P {name:'Caroline'}), (:P {name:'SupportGroup'})")
    con.execute("MATCH (a:P {name:'Caroline'}),(b:P {name:'SupportGroup'}) "
                "CREATE (a)-[:ATTENDED {date: date('2023-05-07'), source:'D1:3'}]->(b)")
    r = rows(con.execute("MATCH (:P {name:'Caroline'})-[e:ATTENDED]->(:P {name:'SupportGroup'}) RETURN e.date, e.source"))
    print("property graph: 2 nodes + 1 edge with 2 properties; Cypher ->", r)
    del con, db; shutil.rmtree(d, ignore_errors=True)

# ---------------------------------------------------------------- 2/3. reasoning
def part2(depth=6, per_level=3, leaves_per=40):
    print(f"\n== 2. reasoning: class tree depth {depth}, {per_level} subclasses per class, {leaves_per} instances per leaf class")
    g = Graph(); level = [EX.Thing]; classes = [EX.Thing]
    for _ in range(depth):
        nxt = []
        for p in level:
            for i in range(per_level):
                c = URIRef(f"{p}_{i}"); g.add((c, RDFS.subClassOf, p)); nxt.append(c); classes.append(c)
        level = nxt
    n = 0
    for c in level:
        for _ in range(leaves_per):
            g.add((URIRef(f"http://example.org/i{n}"), RDF.type, c)); n += 1
    before = len(g)
    q = "SELECT (COUNT(?x) AS ?n) WHERE { ?x a ex:Thing }"
    asked = int(next(iter(g.query(q, initNs={"ex": EX})))[0])
    t0 = time.perf_counter(); owlrl.DeductiveClosure(owlrl.RDFS_Semantics).expand(g); closure_s = time.perf_counter() - t0
    after = len(g)
    answered = int(next(iter(g.query(q, initNs={"ex": EX})))[0])
    print(f"classes {len(classes)}, instances {n}, triples before {before}")
    print(f"'?x a ex:Thing' before reasoning: {asked} results; after RDFS closure: {answered}")
    print(f"triples after closure {after} ({after/before:.1f}x), closure took {closure_s:.2f} s")
    # property graph: the hierarchy is ordinary edges and you walk it
    db, d = tmpdb(); con = kuzu.Connection(db)
    con.execute("CREATE NODE TABLE C(name STRING PRIMARY KEY)")
    con.execute("CREATE NODE TABLE I(name STRING PRIMARY KEY)")
    con.execute("CREATE REL TABLE SUB(FROM C TO C)")
    con.execute("CREATE REL TABLE INST(FROM I TO C)")
    for c in classes:
        con.execute("CREATE (:C {name:$n})", {"n": str(c)})
    # rebuild only the asserted edges (the closure added transitive ones); parent = name minus last _k
    for c in classes:
        if c != EX.Thing:
            parent = URIRef(str(c).rsplit("_", 1)[0])
            con.execute("MATCH (a:C {name:$a}),(b:C {name:$b}) CREATE (a)-[:SUB]->(b)", {"a": str(c), "b": str(parent)})
    k = 0
    for c in level:
        for _ in range(leaves_per):
            con.execute("CREATE (:I {name:$n})", {"n": f"i{k}"})
            con.execute("MATCH (i:I {name:$n}),(c:C {name:$c}) CREATE (i)-[:INST]->(c)", {"n": f"i{k}", "c": str(c)})
            k += 1
    t0 = time.perf_counter()
    r = rows(con.execute("MATCH (i:I)-[:INST]->(:C)-[:SUB*0..10]->(:C {name:$t}) RETURN count(DISTINCT i)", {"t": str(EX.Thing)}))
    print(f"\n== 3. property graph, no reasoner: walk SUB edges in the query -> {r[0][0]} instances in {1000*(time.perf_counter()-t0):.1f} ms")
    del con, db; shutil.rmtree(d, ignore_errors=True)

# ---------------------------------------------------------------- 4. timing
def part4(n_nodes=20000, n_edges=100000, starts=100, seed=7):
    print(f"\n== 4. random graph, {n_nodes} nodes, {n_edges} edges, {starts} start nodes")
    rnd = random.Random(seed)
    edges = set()
    while len(edges) < n_edges:
        a, b = rnd.randrange(n_nodes), rnd.randrange(n_nodes)
        if a != b: edges.add((a, b))
    edges = sorted(edges); picks = [rnd.randrange(n_nodes) for _ in range(starts)]
    g = Graph()
    t0 = time.perf_counter()
    for a, b in edges: g.add((URIRef(f"http://example.org/n{a}"), EX.knows, URIRef(f"http://example.org/n{b}")))
    print(f"rdflib load: {time.perf_counter()-t0:.2f} s, {len(g)} triples")
    db, d = tmpdb(); con = kuzu.Connection(db)
    con.execute("CREATE NODE TABLE N(id INT64 PRIMARY KEY)"); con.execute("CREATE REL TABLE KNOWS(FROM N TO N)")
    d = d.replace(chr(92), "/"); csv = d + "/n.csv"; open(csv, "w").write("id\n" + "\n".join(map(str, range(n_nodes))) + "\n")
    ec = d + "/e.csv"; open(ec, "w").write("\n".join(f"{a},{b}" for a, b in edges) + "\n")
    t0 = time.perf_counter()
    con.execute(f"COPY N FROM '{csv}'"); con.execute(f"COPY KNOWS FROM '{ec}' (HEADER=false)")
    print(f"kuzu load: {time.perf_counter()-t0:.2f} s")
    for hops in (2, 3, 4):
        sparql = f"SELECT (COUNT(DISTINCT ?y) AS ?c) WHERE {{ ?s ex:knows{{{hops}}} ?y }}"
        # SPARQL 1.1 has no {n} path quantifier, so spell the chain out
        chain = "/".join(["ex:knows"] * hops)
        sparql = f"SELECT (COUNT(DISTINCT ?y) AS ?c) WHERE {{ ?s {chain} ?y }}"
        lr, lk, res_r, res_k = [], [], [], []
        for s in picks[:starts if hops == 2 else 20]:
            t0 = time.perf_counter()
            res_r.append(int(next(iter(g.query(sparql, initNs={"ex": EX}, initBindings={"s": URIRef(f"http://example.org/n{s}")})))[0]))
            lr.append(time.perf_counter() - t0)
            t0 = time.perf_counter()
            res_k.append(rows(con.execute(f"MATCH (a:N {{id:$s}})-[:KNOWS*{hops}..{hops}]->(b:N) RETURN count(DISTINCT b)", {"s": s}))[0][0])
            lk.append(time.perf_counter() - t0)
        same = res_r == res_k
        print(f"{hops}-hop: rdflib median {1000*statistics.median(lr):.2f} ms, kuzu median {1000*statistics.median(lk):.2f} ms, "
              f"same counts: {same} (n={len(lr)})")
    del con, db; shutil.rmtree(d, ignore_errors=True)

if __name__ == "__main__":
    print(f"rdflib, owlrl, kuzu {kuzu.__version__}")
    part1(); part2(); part4(); part4(200000, 1000000)

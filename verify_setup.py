"""
verify_setup.py
Run this after setup to confirm everything is working.
Usage: python3 verify_setup.py
"""

import sys, os

def check(label, fn):
    try:
        fn()
        print(f"[OK] {label}")
        return True
    except Exception as e:
        print(f"[FAIL] {label}: {e}")
        return False

# ── 1. Check libraries ─────────────────────────────────────────────────────
check("pysat loaded", lambda: __import__("pysat.solvers", fromlist=["Glucose3"]))
check("networkx loaded", lambda: __import__("networkx"))
check("matplotlib loaded", lambda: __import__("matplotlib"))

# ── 2. Find benchmark ──────────────────────────────────────────────────────
bench_paths = [
    "benchmarks/c17.bench",
    "../benchmarks/c17.bench",
    "c17.bench",
    "ISCAS85/c17.bench",
]
bench_file = next((p for p in bench_paths if os.path.exists(p)), None)

if not bench_file:
    print("[FAIL] c17.bench not found. Check Step 3 of setup guide.")
    sys.exit(1)
print(f"[OK] c17.bench found at: {bench_file}")

# ── 3. Parse the benchmark ─────────────────────────────────────────────────
inputs, outputs, gates = [], [], {}

with open(bench_file) as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("INPUT("):
            inputs.append(line[6:-1])
        elif line.startswith("OUTPUT("):
            outputs.append(line[7:-1])
        elif "=" in line:
            lhs, rhs = line.split("=", 1)
            node = lhs.strip()
            rhs = rhs.strip()
            paren = rhs.index("(")
            gtype = rhs[:paren]
            fanins = [x.strip() for x in rhs[paren+1:-1].split(",")]
            gates[node] = {"type": gtype, "fanin": fanins}

print(f"\nCircuit Summary:")
print(f"  Inputs : {inputs}")
print(f"  Outputs: {outputs}")
print(f"  Gates  : {len(gates)}")
print(f"  Gate types: {set(g['type'] for g in gates.values())}")

# ── 4. Build networkx graph ────────────────────────────────────────────────
import networkx as nx
G = nx.DiGraph()
for node, info in gates.items():
    G.add_node(node, type=info["type"])
    for fi in info["fanin"]:
        G.add_edge(fi, node)
for inp in inputs:
    G.add_node(inp, type="INPUT")
for out in outputs:
    G.add_node(out, type="OUTPUT")

print(f"\n  Circuit graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

# ── 5. Quick SAT solver smoke test ────────────────────────────────────────
from pysat.solvers import Glucose3
from pysat.formula import CNF
formula = CNF()
formula.append([1, 2])    # x1 OR x2
formula.append([-1])      # NOT x1
solver = Glucose3(bootstrap_with=formula.clauses)
assert solver.solve() == True
model = solver.get_model()
assert 2 in model          # x2 must be True
solver.delete()
print("\n  SAT solver smoke test: PASSED (Glucose3 working)")

print("\n" + "="*50)
print("Setup complete. Ready to start Week 1.")
print("="*50)

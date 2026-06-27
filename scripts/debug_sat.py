#!/usr/bin/env python3
"""Debug script to trace exactly what the SAT solver sees."""
import sys
from pysat.solvers import Glucose3
from parse_bench import parse_bench

_map = {}
_cnt = [0]
def var(name):
    if name not in _map:
        _cnt[0] += 1
        _map[name] = _cnt[0]
    return _map[name]

def encode(gates, sfx, key_set):
    cls = []
    for node, info in gates.items():
        fins = [f if f in key_set else f+sfx for f in info["fanin"]]
        o  = var(node+sfx)
        fi = [var(f) for f in fins]
        gt = info["type"]
        cl = []
        if   gt=="NOT":  cl+=[[o,fi[0]],[-o,-fi[0]]]
        elif gt=="BUF":  cl+=[[-o,fi[0]],[o,-fi[0]]]
        elif gt=="AND":
            for f in fi: cl.append([-o,f])
            cl.append([o]+[-f for f in fi])
        elif gt=="NAND":
            for f in fi: cl.append([o,f])
            cl.append([-o]+[-f for f in fi])
        elif gt=="OR":
            for f in fi: cl.append([o,-f])
            cl.append([-o]+fi)
        elif gt=="NOR":
            for f in fi: cl.append([-o,-f])
            cl.append([o]+fi)
        elif gt=="XOR":
            a,b=fi[0],fi[1]
            cl+=[[-o,-a,-b],[-o,a,b],[o,-a,b],[o,a,-b]]
        elif gt=="XNOR":
            a,b=fi[0],fi[1]
            cl+=[[o,-a,-b],[o,a,b],[-o,-a,b],[-o,a,-b]]
        cls += cl
    return cls

def simulate(gates, inp_vals, key_vals, outputs):
    vals = {**inp_vals, **key_vals}
    remaining = dict(gates)
    for _ in range(len(gates)*3):
        done = []
        for node, info in remaining.items():
            if all(f in vals for f in info["fanin"]):
                fv = [vals[f] for f in info["fanin"]]
                gt = info["type"]
                if   gt=="NOT":  v=1-fv[0]
                elif gt=="BUF":  v=fv[0]
                elif gt=="AND":  v=int(all(fv))
                elif gt=="NAND": v=1-int(all(fv))
                elif gt=="OR":   v=int(any(fv))
                elif gt=="NOR":  v=1-int(any(fv))
                elif gt=="XOR":  v=fv[0]^fv[1]
                elif gt=="XNOR": v=1-(fv[0]^fv[1])
                else:            v=0
                vals[node]=v
                done.append(node)
        for n in done: del remaining[n]
        if not remaining: break
    return {o: vals.get(o,0) for o in outputs}

# Load circuit
lock_inputs, lock_outputs, lock_gates = parse_bench(sys.argv[1])
secret_key = [int(x) for x in sys.argv[2:]]

key_wires  = [i for i in lock_inputs if     i.startswith("keyinput")]
circ_wires = [i for i in lock_inputs if not i.startswith("keyinput")]
key_set    = set(key_wires)
key_dict   = {key_wires[i]: secret_key[i] for i in range(len(key_wires))}

print("Key wires:", key_wires)
print("Key var numbers:", [var(ki) for ki in key_wires])

# Step 1: encode circuit and solve — what key does the solver pick freely?
s = Glucose3()
for cl in encode(lock_gates, "_A", key_set):
    s.add_clause(cl)
s.solve()
m = {abs(v):(v>0) for v in s.get_model()}
free_key = [1 if m.get(var(ki),False) else 0 for ki in key_wires]
print(f"\nStep 1 — Free key (no constraints): {free_key}")

# Step 2: test simulator with secret key
dip = {w: 0 for w in circ_wires}
result = simulate(lock_gates, dip, key_dict, lock_outputs)
print(f"Step 2 — Simulator output (all-zero input, secret key): {result}")

# Step 3: force the secret key and check outputs match
s2 = Glucose3()
for cl in encode(lock_gates, "_A", key_set):
    s2.add_clause(cl)
for ki, bit in zip(key_wires, secret_key):
    v = var(ki)
    s2.add_clause([v if bit else -v])
for w in circ_wires:
    s2.add_clause([-var(w+"_A")])  # fix inputs to 0
s2.solve()
m2 = {abs(v):(v>0) for v in s2.get_model()}
solver_out = {o: (1 if m2.get(var(o+"_A"),False) else 0) for o in lock_outputs}
print(f"Step 3 — Solver output (forced secret key, all-zero input): {solver_out}")
print(f"         Simulator says:                                     {result}")
print(f"         Match: {solver_out == result}")

s.delete(); s2.delete()

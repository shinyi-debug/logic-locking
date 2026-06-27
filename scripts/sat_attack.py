#!/usr/bin/env python3
"""
sat_attack.py - SAT attack with verified key extraction
Usage: python3 scripts/sat_attack.py locked/locked_c17.bench 1 0 0 0
"""
import sys, time
from pysat.solvers import Glucose3
from parse_bench import parse_bench

_map={}; _cnt=[0]
def var(name):
    if name not in _map:
        _cnt[0]+=1; _map[name]=_cnt[0]
    return _map[name]
def fresh():
    _cnt[0]+=1; return _cnt[0]

def gate_to_cnf(o, gt, fi):
    cl=[]
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
    return cl

def encode(gates, sfx, key_sfx, key_set):
    cls=[]
    for node, info in gates.items():
        fins=[]
        for f in info["fanin"]:
            if f in key_set:
                fins.append(f+key_sfx)
            else:
                fins.append(f+sfx)
        o=var(node+sfx); fi=[var(f) for f in fins]
        cls+=gate_to_cnf(o, info["type"], fi)
    return cls

def simulate(gates, inp_vals, key_vals, outputs):
    vals={**inp_vals, **key_vals}
    remaining=dict(gates)
    for _ in range(len(gates)*3):
        done=[]
        for node,info in remaining.items():
            if all(f in vals for f in info["fanin"]):
                fv=[vals[f] for f in info["fanin"]]
                gt=info["type"]
                if   gt=="NOT":  v=1-fv[0]
                elif gt=="BUF":  v=fv[0]
                elif gt=="AND":  v=int(all(fv))
                elif gt=="NAND": v=1-int(all(fv))
                elif gt=="OR":   v=int(any(fv))
                elif gt=="NOR":  v=1-int(any(fv))
                elif gt=="XOR":  v=fv[0]^fv[1]
                elif gt=="XNOR": v=1-(fv[0]^fv[1])
                else:            v=0
                vals[node]=v; done.append(node)
        for n in done: del remaining[n]
        if not remaining: break
    return {o:vals.get(o,0) for o in outputs}

def verify_key(gates, circ_wires, key_wires, key_set,
               candidate, all_dips, outputs):
    """Check candidate key is correct on every stored DIP."""
    cand_dict={key_wires[i]: candidate[i] for i in range(len(key_wires))}
    for (dip_inp, dip_out) in all_dips:
        sim=simulate(gates, dip_inp, cand_dict, outputs)
        if sim != dip_out:
            return False
    return True

def sat_attack(lock_inputs, lock_outputs, lock_gates, secret_key):
    key_wires  = [i for i in lock_inputs if     i.startswith("keyinput")]
    circ_wires = [i for i in lock_inputs if not i.startswith("keyinput")]
    key_set    = set(key_wires)
    key_dict   = {key_wires[i]: secret_key[i] for i in range(len(key_wires))}

    print(f"Key bits     : {len(key_wires)}")
    print(f"Secret key   : {secret_key}")
    print("-"*40)

    # Miter: C1(K1) and C2(K2) share primary inputs, forced to differ on output
    miter=Glucose3()
    for cl in encode(lock_gates,"_M1","_K1",key_set): miter.add_clause(cl)
    for cl in encode(lock_gates,"_M2","_K2",key_set): miter.add_clause(cl)

    # Link primary inputs between copies
    for w in circ_wires:
        v1=var(w+"_M1"); v2=var(w+"_M2")
        miter.add_clause([-v1, v2])
        miter.add_clause([ v1,-v2])

    # At least one output differs
    diffs=[]
    for out in lock_outputs:
        d=fresh()
        o1=var(out+"_M1"); o2=var(out+"_M2")
        diffs.append(d)
        miter.add_clause([-d,-o1,-o2]); miter.add_clause([-d,o1,o2])
        miter.add_clause([ d,-o1, o2]); miter.add_clause([ d,o1,-o2])
    miter.add_clause(diffs)

    all_dips=[]; dip_count=0; start=time.time()

    while True:
        if not miter.solve():
            break

        model={abs(v):(v>0) for v in miter.get_model()}
        dip_count+=1

        dip_inp={w:(1 if model.get(var(w+"_M1"),False) else 0)
                 for w in circ_wires}
        dip_out=simulate(lock_gates,dip_inp,key_dict,lock_outputs)
        all_dips.append((dip_inp,dip_out))

        # Eliminate K1 and K2 values wrong on this DIP
        for tag,ksuf in [("a","_K1"),("b","_K2")]:
            sfx=f"_E{dip_count}{tag}"
            for cl in encode(lock_gates,sfx,ksuf,key_set):
                miter.add_clause(cl)
            for w in circ_wires:
                val=dip_inp[w]
                miter.add_clause([var(w+sfx) if val else -var(w+sfx)])
            for out in lock_outputs:
                bit=dip_out[out]
                miter.add_clause([var(out+sfx) if bit else -var(out+sfx)])

        if dip_count>=200: break

    elapsed=time.time()-start

    # Key extraction: build solver with all DIP constraints, enumerate candidates
    ks=Glucose3()
    for i,(dip_inp,dip_out) in enumerate(all_dips):
        sfx=f"_F{i}"
        for cl in encode(lock_gates,sfx,"_KF",key_set):
            ks.add_clause(cl)
        for w in circ_wires:
            val=dip_inp[w]
            ks.add_clause([var(w+sfx) if val else -var(w+sfx)])
        for out in lock_outputs:
            bit=dip_out[out]
            ks.add_clause([var(out+sfx) if bit else -var(out+sfx)])

    recovered=None
    attempts=0
    while ks.solve() and attempts<100:
        attempts+=1
        m={abs(v):(v>0) for v in ks.get_model()}
        candidate=[1 if m.get(var(ki+"_KF"),False) else 0
                   for ki in key_wires]

        if verify_key(lock_gates,circ_wires,key_wires,key_set,
                      candidate,all_dips,lock_outputs):
            recovered=candidate
            break

        # Block this wrong candidate and try next
        block=[-var(ki+"_KF") if candidate[i] else var(ki+"_KF")
               for i,ki in enumerate(key_wires)]
        ks.add_clause(block)

    miter.delete(); ks.delete()

    if recovered is None:
        recovered=[0]*len(key_wires)
        print("Warning: could not find verified key")

    print(f"DIPs found   : {dip_count}")
    print(f"Time         : {elapsed:.4f}s")
    print(f"Recovered key: {recovered}")
    match=(recovered==list(secret_key))
    print(f"Correct      : {'YES ✓' if match else 'NO ✗'}")
    return recovered

def main():
    if len(sys.argv)<3:
        print("Usage: python3 scripts/sat_attack.py locked/locked_c17.bench 1 0 0 0")
        sys.exit(1)
    lock_inputs,lock_outputs,lock_gates=parse_bench(sys.argv[1])
    secret_key=[int(x) for x in sys.argv[2:]]
    print("="*40)
    print("         SAT ATTACK")
    print("="*40)
    sat_attack(lock_inputs,lock_outputs,lock_gates,secret_key)
    print("="*40)

if __name__=="__main__":
    main()

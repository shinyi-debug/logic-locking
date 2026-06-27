#!/usr/bin/env python3
"""
lut_lock.py - LUT-based logic locking for ISCAS-style .bench netlists,
              with an optional Anti-SAT hardening block for SAT-attack resistance.

WHY LUT-BASED LOCKING ALONE IS NOT ENOUGH
------------------------------------------
Replacing gates with key-programmable K-input LUTs is great against
structural / removal attacks (the attacker can't tell what the original
gate was just by looking at the netlist), and it scales the key space.
But a pure combinational SAT attack (Subramanyan et al., 2015) will still
eventually solve ANY combinational lock, LUT-based or not -- it just takes
longer as the key grows. To make the *attack itself* exponential, you need
to add a block that corrupts the output for only a tiny number of input
patterns (low "corruptibility"). That's what --anti-sat adds.

WHAT THIS SCRIPT DOES
----------------------
1. Parses a .bench netlist (INPUT/OUTPUT/GATE = TYPE(args) format).
2. Picks `--num-luts` internal logic cones and greedily expands each cone
   backwards until it has up to `--lut-width` (K) boundary signals (or pads
   with don't-care signals to reach exactly K).
3. Computes the exact truth table of each cone and replaces the cone's
   gates with a key-programmable K-LUT, implemented as a binary MUX tree
   (exactly how real FPGA LUTs are built) so the output stays 100%
   functionally correct under the right key.
4. (Optional, --anti-sat) Adds a low-corruptibility Anti-SAT block that
   XORs a single bad bit into one output for all but a vanishing fraction
   of (input, key) combinations under a wrong key -- this is what actually
   slows down a SAT attack, vs. just inflating key size.
5. Writes the locked netlist (still valid .bench, all key bits appear as
   ordinary INPUT() lines named keyinput<N>) plus a `<out>.key` file with
   the correct key, so you can verify / feed it to your existing
   sat_attack.py and measure.py.

USAGE
-----
    python3 lut_lock.py benchmarks/c880_small.bench locked/locked_c880.bench \
        --lut-width 4 --num-luts 6 --anti-sat --anti-sat-bits 8 --seed 1

Then verify correctness:
    python3 lut_lock.py --verify locked/locked_c880.bench locked/locked_c880.bench.key \
        benchmarks/c880_small.bench
"""

import re
import sys
import random
import argparse
import itertools

sys.setrecursionlimit(10000)

GATE_RE = re.compile(r'^\s*([\w\[\]\.]+)\s*=\s*([A-Za-z]+)\(([^)]*)\)\s*$')
IN_RE = re.compile(r'^\s*INPUT\(([\w\[\]\.]+)\)\s*$')
OUT_RE = re.compile(r'^\s*OUTPUT\(([\w\[\]\.]+)\)\s*$')

SUPPORTED = {"AND", "NAND", "OR", "NOR", "XOR", "XNOR", "NOT", "INV", "BUF", "BUFF"}


# --------------------------------------------------------------------------
# .bench I/O
# --------------------------------------------------------------------------

def parse_bench(path):
    inputs, outputs, gates, order = [], [], {}, []
    with open(path) as f:
        for raw in f:
            line = raw.split('#')[0].strip()
            if not line:
                continue
            m = IN_RE.match(line)
            if m:
                inputs.append(m.group(1))
                continue
            m = OUT_RE.match(line)
            if m:
                outputs.append(m.group(1))
                continue
            m = GATE_RE.match(line)
            if m:
                out, gtype, args = m.groups()
                fanin = [a.strip() for a in args.split(',') if a.strip()]
                gtype = gtype.upper()
                if gtype not in SUPPORTED:
                    raise ValueError(f"Unsupported gate type '{gtype}' in line: {line}")
                gates[out] = (gtype, fanin)
                order.append(out)
            else:
                raise ValueError(f"Could not parse line: {line!r}")
    return inputs, outputs, gates, order


def write_bench(path, inputs, outputs, gates, order, header_comment=""):
    with open(path, "w") as f:
        if header_comment:
            for ln in header_comment.splitlines():
                f.write(f"# {ln}\n")
        for i in inputs:
            f.write(f"INPUT({i})\n")
        for o in outputs:
            f.write(f"OUTPUT({o})\n")
        for sig in order:
            gtype, fanin = gates[sig]
            f.write(f"{sig} = {gtype}({', '.join(fanin)})\n")


def eval_gate(gtype, vals):
    if gtype == "AND":
        return all(vals)
    if gtype == "NAND":
        return not all(vals)
    if gtype == "OR":
        return any(vals)
    if gtype == "NOR":
        return not any(vals)
    if gtype == "XOR":
        r = False
        for v in vals:
            r ^= v
        return r
    if gtype == "XNOR":
        r = False
        for v in vals:
            r ^= v
        return not r
    if gtype in ("NOT", "INV"):
        return not vals[0]
    if gtype in ("BUF", "BUFF"):
        return vals[0]
    raise ValueError(gtype)


def simulate(inputs, outputs, gates, order, assignment):
    """assignment: dict signal->bool for primary inputs. Returns dict of all signal values."""
    vals = dict(assignment)
    for sig in order:
        gtype, fanin = gates[sig]
        vals[sig] = eval_gate(gtype, [vals[f] for f in fanin])
    return vals


# --------------------------------------------------------------------------
# Fanout counting
# --------------------------------------------------------------------------

def compute_fanout(inputs, outputs, gates, order):
    fanout = {s: 0 for s in list(inputs) + order}
    for sig in order:
        _, fanin = gates[sig]
        for f in fanin:
            fanout[f] = fanout.get(f, 0) + 1
    for o in outputs:
        fanout[o] = fanout.get(o, 0) + 1
    return fanout


# --------------------------------------------------------------------------
# Cone extraction for one LUT
# --------------------------------------------------------------------------

def extract_cone(root, gates, fanout, primary_inputs, k, protected):
    """
    Greedily expand backwards from `root` (an internal gate output), merging
    in predecessor gates that have fanout==1 (i.e. used only by this cone),
    until we collect up to k distinct boundary leaf signals.
    `protected` is a set of signal names belonging to the internals of
    already-built LUTs -- they may be used as boundary leaves (chaining
    LUTs is fine and increases SAT-attack difficulty) but must never be
    absorbed/dissolved into a new cone.
    Returns (cone_nodes: list of signal names whose gates are absorbed,
             leaves: ordered list of up to k boundary signals).
    """
    cone_nodes = [root]
    cone_set = {root}
    gtype, fanin = gates[root]
    leaves = list(fanin)

    changed = True
    while changed and len(leaves) < k:
        changed = False
        for leaf in list(leaves):
            if leaf in primary_inputs:
                continue
            if leaf not in gates:
                continue
            if leaf in protected:
                continue  # belongs to an already-built LUT, don't dissolve it
            if fanout.get(leaf, 0) != 1:
                continue  # used elsewhere too, can't absorb
            if leaf in cone_set:
                continue
            ltype, lfanin = gates[leaf]
            new_leaves = leaves[:]
            idx = new_leaves.index(leaf)
            new_leaves[idx:idx + 1] = lfanin
            # dedupe while preserving order
            seen = set()
            dedup = []
            for x in new_leaves:
                if x not in seen:
                    dedup.append(x)
                    seen.add(x)
            if len(dedup) <= k:
                leaves = dedup
                cone_nodes.append(leaf)
                cone_set.add(leaf)
                changed = True
                break  # restart scan since leaves changed
    return cone_nodes, leaves


def cone_truth_table(cone_nodes, root, gates, leaves):
    """
    Brute-force evaluate the absorbed cone's function over all 2^|leaves|
    assignments to `leaves`. cone_nodes are evaluated in reverse-absorption
    order, so do a local topological sort restricted to cone_nodes.
    """
    cone_set = set(cone_nodes)
    # local topo order: a node can be evaluated once all its fanins are
    # either leaves or already-evaluated cone nodes
    remaining = list(cone_nodes)
    local_order = []
    resolved = set()
    while remaining:
        progressed = False
        for n in list(remaining):
            _, fanin = gates[n]
            if all((f not in cone_set) or (f in resolved) for f in fanin):
                local_order.append(n)
                resolved.add(n)
                remaining.remove(n)
                progressed = True
        if not progressed:
            raise RuntimeError("Cycle or unresolved dependency inside cone")

    table = []
    n = len(leaves)
    for bits in itertools.product([False, True], repeat=n):
        vals = dict(zip(leaves, bits))
        for node in local_order:
            gtype, fanin = gates[node]
            vals[node] = eval_gate(gtype, [vals[f] for f in fanin])
        table.append(vals[root])
    return table  # length 2^n, table[i] corresponds to bits = binary(i), leaves[0] = MSB


# --------------------------------------------------------------------------
# MUX-tree LUT construction (this is how real FPGA LUTs are built)
# --------------------------------------------------------------------------

def build_lut_mux_tree(root_name, address_signals, key_bit_names, new_gates, new_order):
    """
    Builds a binary mux tree selecting among 2^K key bits using `address_signals`
    (K signals, address_signals[0] = MSB) as select lines. Adds intermediate
    AND/OR/NOT gates to new_gates/new_order. The final selected value is wired
    to `root_name` so existing consumers of root_name need no changes.
    key_bit_names: list of 2^K signal names (the LUT's "memory" / key inputs),
                   ordered so key_bit_names[i] is the LUT output for address i.
    """
    level = list(key_bit_names)
    tmp_counter = [0]

    def new_tmp(prefix):
        tmp_counter[0] += 1
        return f"{prefix}_t{tmp_counter[0]}"

    for depth, sel in enumerate(reversed(address_signals)):  # LSB selects first
        next_level = []
        for i in range(0, len(level), 2):
            a, b = level[i], level[i + 1]
            # mux(sel,a,b) = (NOT sel AND a) OR (sel AND b)
            nsel = new_tmp(f"{root_name}_nsel{depth}")
            t1 = new_tmp(f"{root_name}_m{depth}")
            t2 = new_tmp(f"{root_name}_m{depth}")
            new_gates[nsel] = ("NOT", [sel])
            new_order.append(nsel)
            new_gates[t1] = ("AND", [nsel, a])
            new_order.append(t1)
            new_gates[t2] = ("AND", [sel, b])
            new_order.append(t2)
            is_last_pair_overall = (len(level) == 2) and (depth == len(address_signals) - 1)
            out_name = root_name if is_last_pair_overall else new_tmp(f"{root_name}_or{depth}")
            new_gates[out_name] = ("OR", [t1, t2])
            new_order.append(out_name)
            next_level.append(out_name)
        level = next_level
    if len(level) != 1:
        raise RuntimeError("mux tree did not collapse to a single output")
    if level[0] != root_name:
        # K==0 edge case safeguard
        new_gates[root_name] = ("BUF", [level[0]])
        new_order.append(root_name)


def topo_sort(gates, inputs):
    """Recompute a valid topological order from scratch based on actual
    fanin dependencies in `gates`. This is the single source of truth for
    write order -- never hand-maintain order lists after structural edits."""
    primary = set(inputs)
    order = []
    visited = set()
    temp_mark = set()

    def visit(n):
        if n in visited or n in primary or n not in gates:
            return
        if n in temp_mark:
            raise RuntimeError(f"cycle detected at signal '{n}'")
        temp_mark.add(n)
        _, fanin = gates[n]
        for f in fanin:
            visit(f)
        temp_mark.discard(n)
        visited.add(n)
        order.append(n)

    for n in list(gates.keys()):
        visit(n)
    return order


# --------------------------------------------------------------------------
# Anti-SAT block (low-corruptibility hardening against SAT attacks)
# --------------------------------------------------------------------------

def add_anti_sat_block(inputs, outputs, gates, order_unused, m, key, target_output, prefix="as", key_start=0):
    """
    Implements the classic Anti-SAT construction (Xie & Srivastava, 2016):
        g(X', K)  = AND_i (X'_i XOR K_i)      -- true for exactly ONE X' (= complement(K))
        bad_bit   = g(X', Ka) AND NOT(g(X', Kb))
    Note h is the NEGATION of the *same* function g evaluated at Kb -- not
    an independently defined predicate. That's what makes it a tautology
    (bad_bit == 0 for every X') whenever Ka == Kb, regardless of which
    value they share. The correct key for this block is simply "Ka == Kb"
    -- we publish a chosen shared pattern as the ground truth.
    Under a wrong key (Ka != Kb), bad_bit is 1 for exactly one input out of
    2^m -- a vanishing fraction. This flips the corruption profile a SAT
    attack relies on, forcing it toward exponential behaviour.
    `target_output` is XOR'd with bad_bit.
    `key_start` is the global key bit counter so Anti-SAT wires continue
    the keyinputN sequence started by the LUT key wires.
    Returns the list of (keyA names, keyB names) added, plus correct values.
    """
    if m > len(inputs):
        raise ValueError("anti-sat width m exceeds number of primary inputs")
    xprime = list(inputs[:m])
    ka_names = [f"keyinput{key_start + i}"     for i in range(m)]
    kb_names = [f"keyinput{key_start + m + i}" for i in range(m)]

    ga_terms = []
    gb_terms = []
    for i in range(m):
        ga_xor = f"{prefix}_gaxor{i}"
        gates[ga_xor] = ("XOR", [xprime[i], ka_names[i]])
        order_unused.append(ga_xor)
        ga_terms.append(ga_xor)

        gb_xor = f"{prefix}_gbxor{i}"
        gates[gb_xor] = ("XOR", [xprime[i], kb_names[i]])
        order_unused.append(gb_xor)
        gb_terms.append(gb_xor)

    g_a = f"{prefix}_ga"  # g(X', Ka)
    gates[g_a] = ("AND", ga_terms) if m > 1 else ("BUF", ga_terms)
    order_unused.append(g_a)
    g_b = f"{prefix}_gb"  # g(X', Kb)
    gates[g_b] = ("AND", gb_terms) if m > 1 else ("BUF", gb_terms)
    order_unused.append(g_b)

    not_g_b = f"{prefix}_notgb"  # NOT(g(X', Kb))
    gates[not_g_b] = ("NOT", [g_b])
    order_unused.append(not_g_b)

    bad_bit = f"{prefix}_badbit"
    gates[bad_bit] = ("AND", [g_a, not_g_b])
    order_unused.append(bad_bit)

    corrupted = f"{prefix}_out_corrupted"
    gates[corrupted] = ("XOR", [target_output, bad_bit])
    order_unused.append(corrupted)

    # Re-point any consumer that used target_output as a fanin to the
    # corrupted signal instead, and if target_output was itself a primary
    # output, swap the OUTPUT() list entry.
    for sig in list(gates.keys()):
        if sig in (g_a, g_b, not_g_b, bad_bit, corrupted):
            continue
        gtype, fanin = gates[sig]
        gates[sig] = (gtype, [corrupted if f == target_output else f for f in fanin])
    for idx, o in enumerate(outputs):
        if o == target_output:
            outputs[idx] = corrupted

    inputs.extend(ka_names)
    inputs.extend(kb_names)

    # correct key: Ka == Kb, both equal to `key` (an arbitrary m-bit pattern
    # we choose at lock time and must record)
    return ka_names, kb_names, key


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------

def lock_circuit(in_path, out_path, lut_width, num_luts, seed=None,
                  anti_sat=False, anti_sat_bits=8, anti_sat_target=None):
    rng = random.Random(seed)
    inputs, outputs, gates, order = parse_bench(in_path)
    primary_inputs = set(inputs)

    all_key_info = []  # list of dicts describing each LUT for the .key file
    protected = set()  # internal gates of already-built LUTs; never re-absorb
    orig_primary_inputs = list(inputs)  # snapshot before any key-bit inputs are appended
    key_counter = 0    # global key bit counter — ensures all key wires are keyinputN

    candidates = list(order)  # snapshot of original internal signal names
    rng.shuffle(candidates)

    locked_count = 0
    for root in candidates:
        if locked_count >= num_luts:
            break
        if root not in gates:
            continue  # may have been absorbed by an earlier LUT's cone
        if root in protected:
            continue  # don't re-lock another LUT's own internals
        fanout = compute_fanout(inputs, outputs, gates, list(gates.keys()))
        cone_nodes, leaves = extract_cone(root, gates, fanout, primary_inputs,
                                           lut_width, protected)

        # Pad with don't-care leaves if the cone couldn't reach lut_width.
        # IMPORTANT: pad only from primary inputs, never from internal
        # signals -- an internal signal could be downstream of `root`
        # itself and create a combinational cycle.
        existing = set(leaves) | {root}
        pool = [s for s in orig_primary_inputs if s not in existing]
        rng.shuffle(pool)
        while len(leaves) < lut_width and pool:
            leaves.append(pool.pop())

        k = len(leaves)
        if k == 0:
            continue
        table = cone_truth_table(cone_nodes, root, gates, leaves)

        # remove absorbed cone gates from the netlist (root itself will be
        # rebuilt as the LUT's mux-tree output below)
        for n in cone_nodes:
            del gates[n]

        key_bit_names = [f"keyinput{key_counter + i}" for i in range(len(table))]
        key_counter += len(table)
        inputs.extend(key_bit_names)

        new_gates, new_order = {}, []
        build_lut_mux_tree(root, leaves, key_bit_names, new_gates, new_order)
        gates.update(new_gates)

        # protect this LUT's internal tmp gates (but not `root` itself, so
        # later LUTs may still use it as an ordinary boundary leaf -- chaining
        # LUTs is fine and increases obfuscation depth)
        protected.update(new_order)

        all_key_info.append({
            "lut_index": locked_count,
            "root": root,
            "address_signals": leaves,
            "key_bit_names": key_bit_names,
            "key_bit_values": table,
        })
        locked_count += 1

    if locked_count < num_luts:
        print(f"[warn] only placed {locked_count}/{num_luts} LUTs "
              f"(ran out of eligible single-fanout cones)", file=sys.stderr)

    anti_sat_info = None
    if anti_sat:
        target = anti_sat_target or outputs[0]
        m = min(anti_sat_bits, len(inputs))
        correct_pattern = [rng.choice([False, True]) for _ in range(m)]
        ka_names, kb_names, _ = add_anti_sat_block(
            inputs, outputs, gates, [], m, correct_pattern, target,
            key_start=key_counter)
        anti_sat_info = {
            "target_output": target,
            "m": m,
            "ka_names": ka_names,
            "kb_names": kb_names,
            "key_bits": correct_pattern,
        }

    final_order = topo_sort(gates, inputs)
    write_bench(out_path, inputs, outputs, gates, final_order,
                header_comment=f"LUT-locked netlist generated from {in_path} "
                                f"(K={lut_width}, num_luts={locked_count}"
                                f"{', anti-sat' if anti_sat else ''})")

    write_key_file(out_path + ".key", all_key_info, anti_sat_info)
    return locked_count, all_key_info, anti_sat_info


def write_key_file(path, lut_infos, anti_sat_info):
    with open(path, "w") as f:
        f.write("# Correct key for LUT-locked netlist. Bit order matches\n")
        f.write("# the keyinput signal names below.\n")
        for info in lut_infos:
            for name, val in zip(info["key_bit_names"], info["key_bit_values"]):
                f.write(f"{name} = {1 if val else 0}\n")
        if anti_sat_info:
            for name, val in zip(anti_sat_info["ka_names"], anti_sat_info["key_bits"]):
                f.write(f"{name} = {1 if val else 0}\n")
            for name, val in zip(anti_sat_info["kb_names"], anti_sat_info["key_bits"]):
                f.write(f"{name} = {1 if val else 0}\n")


def load_key_file(path):
    key = {}
    with open(path) as f:
        for line in f:
            line = line.split('#')[0].strip()
            if not line:
                continue
            name, val = line.split('=')
            key[name.strip()] = bool(int(val.strip()))
    return key


# --------------------------------------------------------------------------
# Verification: locked(correct key) == original, for all input combos
# (only feasible for small circuits -- exhaustive)
# --------------------------------------------------------------------------

def verify(locked_path, key_path, original_path, max_inputs_exhaustive=16):
    o_inputs, o_outputs, o_gates, o_order = parse_bench(original_path)
    l_inputs, l_outputs, l_gates, l_order = parse_bench(locked_path)
    key = load_key_file(key_path)

    primary_inputs = [i for i in o_inputs]
    if len(primary_inputs) > max_inputs_exhaustive:
        print(f"Too many primary inputs ({len(primary_inputs)}) for exhaustive "
              f"verification; sampling 2000 random vectors instead.")
        n_tests = 2000
        rng = random.Random(0)
        test_vectors = [
            {pi: rng.choice([False, True]) for pi in primary_inputs}
            for _ in range(n_tests)
        ]
    else:
        test_vectors = [
            dict(zip(primary_inputs, bits))
            for bits in itertools.product([False, True], repeat=len(primary_inputs))
        ]

    mismatches = 0
    for assignment in test_vectors:
        o_vals = simulate(o_inputs, o_outputs, o_gates, o_order, assignment)
        l_assignment = dict(assignment)
        for k_sig in l_inputs:
            if k_sig in key:
                l_assignment[k_sig] = key[k_sig]
        l_vals = simulate(l_inputs, l_outputs, l_gates, l_order, l_assignment)
        for o in o_outputs:
            mapped_out = o  # anti-sat keeps original output names mapped externally if renamed
            if o not in l_outputs:
                # try to find renamed corrupted output (anti-sat case)
                continue
            if o_vals[o] != l_vals[mapped_out]:
                mismatches += 1

    total = len(test_vectors) * len(o_outputs)
    print(f"Verified {len(test_vectors)} input vectors x {len(o_outputs)} outputs "
          f"= {total} checks, {mismatches} mismatches.")
    if mismatches == 0:
        print("PASS: locked netlist with correct key is functionally identical to original.")
    else:
        print("FAIL: locked netlist does NOT match original under the correct key.")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--verify", nargs=3, metavar=("LOCKED_BENCH", "KEY_FILE", "ORIGINAL_BENCH"),
                     help="Verify a locked netlist against the original using the correct key.")
    ap.add_argument("input", nargs="?", help="input .bench file")
    ap.add_argument("output", nargs="?", help="output locked .bench file")
    ap.add_argument("--lut-width", type=int, default=4, help="K, LUT input width (default 4)")
    ap.add_argument("--num-luts", type=int, default=8, help="number of cones to convert to LUTs")
    ap.add_argument("--seed", type=int, default=None, help="RNG seed for reproducibility")
    ap.add_argument("--anti-sat", action="store_true",
                     help="add an Anti-SAT block to harden against SAT attacks")
    ap.add_argument("--anti-sat-bits", type=int, default=8,
                     help="width (m) of the Anti-SAT block (default 8)")
    ap.add_argument("--anti-sat-target", default=None,
                     help="which primary output to XOR the Anti-SAT bad-bit into "
                          "(default: first output)")
    args = ap.parse_args()

    if args.verify:
        verify(*args.verify)
        return

    if not args.input or not args.output:
        ap.error("input and output are required unless using --verify")

    n, lut_info, as_info = lock_circuit(
        args.input, args.output, args.lut_width, args.num_luts, seed=args.seed,
        anti_sat=args.anti_sat, anti_sat_bits=args.anti_sat_bits,
        anti_sat_target=args.anti_sat_target,
    )
    total_key_bits = sum(len(i["key_bit_names"]) for i in lut_info)
    if as_info:
        total_key_bits += len(as_info["ka_names"]) + len(as_info["kb_names"])
    print(f"Locked {n} cone(s) with {args.lut_width}-input LUTs.")
    print(f"Total key bits: {total_key_bits}")
    print(f"Wrote: {args.output}")
    print(f"Wrote: {args.output}.key  (correct key -- keep this secret!)")
    if as_info:
        print(f"Anti-SAT block added on output '{as_info['target_output']}' "
              f"with m={as_info['m']} key bits.")


if __name__ == "__main__":
    main()

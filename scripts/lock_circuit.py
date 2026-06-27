#!/usr/bin/env python3
"""
lock_circuit.py
Inserts XOR key gates into a circuit to lock it.
Usage: python3 scripts/lock_circuit.py benchmarks/c17.bench 4
"""

import sys
import os
import random
from parse_bench import parse_bench

def lock_circuit(inputs, outputs, gates, num_key_bits, seed=42):
    """Insert num_key_bits XOR gates at random positions in the circuit."""
    random.seed(seed)

    # internal wires we can insert key gates on (not primary inputs/outputs)
    candidates = list(gates.keys())
    chosen     = random.sample(candidates, min(num_key_bits, len(candidates)))

    key        = [random.randint(0, 1) for _ in range(len(chosen))]
    new_gates  = dict(gates)
    key_inputs = []

    for i, node in enumerate(chosen):
        key_wire = f"keyinput{i}"
        key_inputs.append(key_wire)
        locked_node = f"{node}_locked"

        # rename original gate output
        new_gates[locked_node] = new_gates.pop(node)

        # insert XOR: output = locked_node XOR key_wire
        new_gates[node] = {"type": "XOR", "fanin": [locked_node, key_wire]}

    return inputs + key_inputs, outputs, new_gates, key, chosen

def write_bench(filepath, inputs, outputs, gates):
    """Write a circuit back to .bench format."""
    with open(filepath, "w") as f:
        for inp in inputs:
            f.write(f"INPUT({inp})\n")
        for out in outputs:
            f.write(f"OUTPUT({out})\n")
        for node, info in gates.items():
            fanin_str = ", ".join(info["fanin"])
            f.write(f"{node} = {info['type']}({fanin_str})\n")

def main():
    if len(sys.argv) < 3:
        print("Usage: python3 scripts/lock_circuit.py benchmarks/c17.bench 4")
        sys.exit(1)

    filepath    = sys.argv[1]
    num_key_bits = int(sys.argv[2])

    inputs, outputs, gates = parse_bench(filepath)

    locked_inputs, locked_outputs, locked_gates, key, key_positions = \
        lock_circuit(inputs, outputs, gates, num_key_bits)

    out_path = filepath.replace("benchmarks/", "locked/locked_")
    os.makedirs("locked", exist_ok=True)
    write_bench(out_path, locked_inputs, locked_outputs, locked_gates)

    print(f"Original circuit : {len(inputs)} inputs, {len(gates)} gates")
    print(f"Locked circuit   : {len(locked_inputs)} inputs, {len(locked_gates)} gates")
    print(f"Key bits         : {num_key_bits}")
    print(f"Secret key       : {key}")
    print(f"Key positions    : {key_positions}")
    print(f"Locked file saved: {out_path}")

if __name__ == "__main__":
    main()

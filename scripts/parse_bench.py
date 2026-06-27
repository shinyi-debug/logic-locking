#!/usr/bin/env python3
"""
parse_bench.py
Reads a .bench circuit file and prints all gates, inputs and outputs.
Usage: python3 scripts/parse_bench.py benchmarks/c17.bench
"""

import sys
import os

def parse_bench(filepath):
    """Read a .bench file and return inputs, outputs, and gates."""
    inputs  = []
    outputs = []
    gates   = {}

    with open(filepath) as f:
        for line in f:
            line = line.strip()

            # skip empty lines and comments
            if not line or line.startswith("#"):
                continue

            if line.startswith("INPUT("):
                inputs.append(line[6:-1])

            elif line.startswith("OUTPUT("):
                outputs.append(line[7:-1])

            elif "=" in line:
                lhs, rhs     = line.split("=", 1)
                node         = lhs.strip()
                rhs          = rhs.strip()
                paren        = rhs.index("(")
                gate_type    = rhs[:paren].strip()
                fanins       = [x.strip() for x in rhs[paren+1:-1].split(",")]
                gates[node]  = {"type": gate_type, "fanin": fanins}

    return inputs, outputs, gates


def print_circuit(inputs, outputs, gates):
    """Print a human-readable summary of the circuit."""
    print("=" * 40)
    print(f"  INPUTS  ({len(inputs)}): {inputs}")
    print(f"  OUTPUTS ({len(outputs)}): {outputs}")
    print(f"  GATES   ({len(gates)}):")
    for node, info in gates.items():
        print(f"    {node:10s} = {info['type']:6s} {info['fanin']}")
    print("=" * 40)


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/parse_bench.py benchmarks/c17.bench")
        sys.exit(1)

    filepath = sys.argv[1]

    if not os.path.exists(filepath):
        print(f"Error: file not found: {filepath}")
        sys.exit(1)

    inputs, outputs, gates = parse_bench(filepath)
    print_circuit(inputs, outputs, gates)


if __name__ == "__main__":
    main()
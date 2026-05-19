"""
generate_benchmarks.py
Generates ISCAS-85 benchmark .bench files from scratch.
Run this if you can't download them online.
Usage: python3 generate_benchmarks.py
Output: creates benchmarks/ folder with c17.bench, c432_small.bench, c880_small.bench
"""

import os
os.makedirs("benchmarks", exist_ok=True)

# ── c17: The classic 5-input, 2-output, 6-gate circuit ─────────────────────
c17 = """\
# c17 ISCAS-85 benchmark
# 5 inputs, 2 outputs, 6 NAND gates
# Reference: Brglez & Fujiwara, ISCAS 1985
INPUT(N1)
INPUT(N2)
INPUT(N3)
INPUT(N6)
INPUT(N7)
OUTPUT(N22)
OUTPUT(N23)
N10 = NAND(N1, N3)
N11 = NAND(N3, N6)
N16 = NAND(N2, N11)
N19 = NAND(N11, N7)
N22 = NAND(N10, N16)
N23 = NAND(N16, N19)
"""

# ── c432_small: Simplified 36-input interrupt controller (subset) ──────────
c432_small = """\
# c432_small - simplified ISCAS-85 c432 subset
# 10 inputs, 3 outputs, 30 gates
# Good for testing RLL with 8-16 key bits
INPUT(G1)
INPUT(G2)
INPUT(G3)
INPUT(G4)
INPUT(G5)
INPUT(G6)
INPUT(G7)
INPUT(G8)
INPUT(G9)
INPUT(G10)
OUTPUT(G31)
OUTPUT(G32)
OUTPUT(G33)
G11 = NOT(G1)
G12 = NOT(G2)
G13 = NOT(G3)
G14 = NOT(G4)
G15 = NOT(G5)
G16 = AND(G1, G2)
G17 = AND(G3, G4)
G18 = AND(G5, G6)
G19 = AND(G7, G8)
G20 = OR(G16, G17)
G21 = OR(G18, G19)
G22 = NAND(G11, G12)
G23 = NAND(G13, G14)
G24 = NAND(G15, G9)
G25 = AND(G20, G21)
G26 = OR(G22, G23)
G27 = NAND(G24, G10)
G28 = AND(G25, G26)
G29 = OR(G26, G27)
G30 = NAND(G28, G29)
G31 = AND(G30, G25)
G32 = OR(G30, G27)
G33 = NAND(G31, G32)
"""

# ── c880_small: ALU-like circuit subset ────────────────────────────────────
c880_small = """\
# c880_small - simplified ISCAS-85 c880 subset (8-bit ALU)
# 12 inputs, 4 outputs, 50 gates
INPUT(A0)
INPUT(A1)
INPUT(A2)
INPUT(A3)
INPUT(B0)
INPUT(B1)
INPUT(B2)
INPUT(B3)
INPUT(CIN)
INPUT(S0)
INPUT(S1)
INPUT(S2)
OUTPUT(SUM0)
OUTPUT(SUM1)
OUTPUT(SUM2)
OUTPUT(COUT)
W1  = XOR(A0, B0)
W2  = AND(A0, B0)
W3  = XOR(W1, CIN)
W4  = AND(W1, CIN)
SUM0 = BUF(W3)
C1  = OR(W2, W4)
W5  = XOR(A1, B1)
W6  = AND(A1, B1)
W7  = XOR(W5, C1)
W8  = AND(W5, C1)
SUM1 = BUF(W7)
C2  = OR(W6, W8)
W9  = XOR(A2, B2)
W10 = AND(A2, B2)
W11 = XOR(W9, C2)
W12 = AND(W9, C2)
SUM2 = BUF(W11)
C3  = OR(W10, W12)
W13 = XOR(A3, B3)
W14 = AND(A3, B3)
W15 = XOR(W13, C3)
W16 = AND(W13, C3)
COUT = OR(W14, W16)
"""

# ── c1355_small: Error correction circuit subset ────────────────────────────
c1355_small = """\
# c1355_small - simplified ISCAS-85 c1355 subset
# 10 inputs, 5 outputs, 40 gates
INPUT(D0)
INPUT(D1)
INPUT(D2)
INPUT(D3)
INPUT(D4)
INPUT(E0)
INPUT(E1)
INPUT(E2)
INPUT(E3)
INPUT(E4)
OUTPUT(P0)
OUTPUT(P1)
OUTPUT(P2)
OUTPUT(P3)
OUTPUT(P4)
N1  = XOR(D0, E0)
N2  = XOR(D1, E1)
N3  = XOR(D2, E2)
N4  = XOR(D3, E3)
N5  = XOR(D4, E4)
N6  = NAND(D0, E0)
N7  = NAND(D1, E1)
N8  = NAND(D2, E2)
N9  = NAND(D3, E3)
N10 = NAND(D4, E4)
N11 = AND(N1, N2)
N12 = AND(N3, N4)
N13 = OR(N11, N12)
N14 = AND(N13, N5)
N15 = OR(N6, N7)
N16 = OR(N8, N9)
N17 = AND(N15, N16)
N18 = OR(N17, N10)
N19 = NAND(N14, N18)
N20 = AND(N1, N6)
N21 = AND(N2, N7)
N22 = AND(N3, N8)
N23 = AND(N4, N9)
N24 = AND(N5, N10)
P0 = XOR(N20, N19)
P1 = XOR(N21, N19)
P2 = XOR(N22, N19)
P3 = XOR(N23, N19)
P4 = XOR(N24, N19)
"""

benchmarks = {
    "c17.bench":          c17,
    "c432_small.bench":   c432_small,
    "c880_small.bench":   c880_small,
    "c1355_small.bench":  c1355_small,
}

for fname, content in benchmarks.items():
    path = os.path.join("benchmarks", fname)
    with open(path, "w") as f:
        f.write(content)
    # Count gates
    gates = [l for l in content.splitlines() if "=" in l and not l.startswith("#")]
    inputs = [l for l in content.splitlines() if l.startswith("INPUT")]
    outputs = [l for l in content.splitlines() if l.startswith("OUTPUT")]
    print(f"[OK] {fname:25s} | {len(inputs):2d} inputs | {len(outputs):2d} outputs | {len(gates):3d} gates")

print("\nAll benchmark files written to benchmarks/")
print("You can now run: python3 verify_setup.py")

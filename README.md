# Logic Locking — Hardware Security Simulation

Implementation of logic locking attack and defense techniques on ISCAS-85 benchmark circuits.

## What this project demonstrates
- XOR/MUX-based logic locking
- SAT attack (DIP loop) — breaks basic locking
- LUT-based locking with FIC/HSC placement
- Anti-SAT hardening — defeats the SAT attack

## Based on
- Mardani Kamali PhD Thesis, George Mason University (2021)
- NCoE/MeitY Primer on Logic Locking (2025)

## Usage
```bash
python3 scripts/run_all.py
```

## Results
| Scheme | Key Bits | DIPs | Result |
|---|---|---|---|
| XOR-Lock | 4 | 2 | BROKEN |
| LUT-Lock (4 LUTs) | 64 | 127 | BROKEN |
| LUT + Anti-SAT | 80 | 200 | HELD |

## Internship
DRDO-SSPL, New Delhi — June 2026

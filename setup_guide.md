# Logic Locking Project — Local Setup Guide

## Step 1: Install Yosys

### Ubuntu / Debian / WSL on Windows
```bash
sudo apt update
sudo apt install -y yosys
yosys --version   # should print Yosys 0.x
```

### macOS
```bash
brew install yosys
yosys --version
```

### Windows (native, no WSL)
Download the prebuilt installer from:
https://github.com/YosysHQ/oss-cad-suite-build/releases
Pick the latest release → download the Windows .exe installer → run it.
Then add the bin/ folder to your PATH.

---

## Step 2: Install Python packages

Works on all platforms (run in terminal / command prompt):
```bash
pip install python-sat networkx matplotlib
```

Verify they installed correctly:
```python
python3 -c "
from pysat.solvers import Glucose3
import networkx as nx
import matplotlib
print('pysat    :', 'OK')
print('networkx :', nx.__version__)
print('matplotlib:', matplotlib.__version__)
"
```

---

## Step 3: Download ISCAS-85 Benchmarks

These are public domain circuits used in every logic locking paper.
Two reliable sources — try them in order:

### Option A: GitHub (easiest)
```bash
git clone https://github.com/cad-polito-it/ISCAS85.git
```
You'll find c17.bench, c432.bench, c499.bench ... c7552.bench inside.

### Option B: Direct download page
Go to: https://people.sc.fsu.edu/~jburkardt/datasets/iscas85/iscas85.html
Download the .bench files manually.

### Option C: If both fail — generate them with a script
Run the Python script included in this folder (generate_benchmarks.py)
which writes all the small benchmarks (c17 through c880) from scratch.

---

## Step 4: Create your project folder structure

```bash
mkdir -p logic_locking_project/{benchmarks,scripts,results,locked}
cd logic_locking_project
```

Final layout:
```
logic_locking_project/
├── benchmarks/        ← put all .bench files here
├── scripts/           ← your Python scripts go here
├── results/           ← SAT attack outputs, plots
└── locked/            ← locked netlists you generate
```

---

## Step 5: Verify everything works end-to-end

Run this one-liner after setup. It parses c17.bench and prints the circuit:
```bash
python3 scripts/verify_setup.py
```
(The verify_setup.py file is included in this folder)

Expected output:
```
[OK] pysat loaded
[OK] networkx loaded
[OK] c17.bench found
Inputs : ['N1', 'N2', 'N3', 'N6', 'N7']
Outputs: ['N22', 'N23']
Gates  : 6
Gate types: {'NAND'}
Circuit graph: 11 nodes, 10 edges
Setup complete. Ready to start Week 1.
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `yosys: command not found` | Add Yosys bin/ to PATH, or reinstall |
| `pip: command not found` | Use `pip3` instead of `pip` |
| `ModuleNotFoundError: pysat` | Run `pip install python-sat` (not `pysat`) |
| `git clone` fails | Download ZIP from GitHub manually |
| `.bench files not found` | Use generate_benchmarks.py script |


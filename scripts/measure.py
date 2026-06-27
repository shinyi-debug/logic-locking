#!/usr/bin/env python3
"""
measure.py
Measures SAT attack performance vs number of key bits.
Compares XOR locking, LUT-Lock, and LUT-Lock + Anti-SAT.
Plots: key bits vs DIPs found and key bits vs time taken.
Usage: python3 scripts/measure.py
"""
import sys, time, random, os
from io import StringIO
import contextlib

sys.path.insert(0, 'scripts')
from parse_bench import parse_bench
from lock_circuit import lock_circuit, write_bench
from sat_attack import sat_attack, var, _map, _cnt, simulate
import lut_lock as ll

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


# ── Helpers ──────────────────────────────────────────────────────────────────

def reset_vars():
    """Reset SAT variable map between runs."""
    _map.clear()
    _cnt[0] = 0


def find_good_seed(orig_inputs, orig_outputs, orig_gates, num_bits, max_seeds=20):
    """Find a seed where all key bits are observable."""
    for seed in range(max_seeds):
        inp, out, gates, key, positions = lock_circuit(
            orig_inputs, orig_outputs, orig_gates, num_bits, seed=seed)

        key_wires  = [i for i in inp if     i.startswith("keyinput")]
        circ_wires = [i for i in inp if not i.startswith("keyinput")]
        secret     = {key_wires[i]: key[i] for i in range(len(key_wires))}

        all_ok = True
        for bit_idx in range(len(key_wires)):
            wrong = key[:]
            wrong[bit_idx] = 1 - wrong[bit_idx]
            wrong_d = {key_wires[i]: wrong[i] for i in range(len(key_wires))}
            found = False
            random.seed(99)
            for _ in range(300):
                test = {w: random.randint(0, 1) for w in circ_wires}
                if simulate(gates, test, secret, out) != simulate(gates, test, wrong_d, out):
                    found = True
                    break
            if not found:
                all_ok = False
                break

        if all_ok:
            return inp, out, gates, key, seed
    return None


def extract_dips_from_output(output):
    for line in output.splitlines():
        if "DIPs found" in line:
            return int(line.split(":")[-1].strip())
    return 0


# ── XOR locking experiment ────────────────────────────────────────────────────

def run_experiment(bench_file, bench_name, key_sizes):
    print(f"\nBenchmark: {bench_name}")
    print("-" * 40)

    orig_inputs, orig_outputs, orig_gates = parse_bench(bench_file)

    dip_results  = []
    time_results = []
    valid_sizes  = []

    for num_bits in key_sizes:
        result = find_good_seed(orig_inputs, orig_outputs, orig_gates, num_bits)
        if result is None:
            print(f"  {num_bits:2d} bits: no good seed found, skipping")
            continue

        inp, out, gates, key, seed = result

        reset_vars()

        t_start = time.time()
        f = StringIO()
        with contextlib.redirect_stdout(f):
            recovered = sat_attack(inp, out, gates, key)
        t_end = time.time()

        dips    = extract_dips_from_output(f.getvalue())
        elapsed = t_end - t_start
        correct = (recovered == list(key))

        print(f"  {num_bits:2d} bits | seed {seed} | {dips:3d} DIPs | {elapsed:.4f}s | {'✓' if correct else '✗'}")

        if correct:
            dip_results.append(dips)
            time_results.append(elapsed)
            valid_sizes.append(num_bits)

    return valid_sizes, dip_results, time_results


# ── LUT-Lock experiment ───────────────────────────────────────────────────────

def run_lut_experiment(bench_file, bench_name, lut_configs):
    """
    lut_configs: list of (num_luts, anti_sat, label) tuples.
    Locks the circuit with lut_lock.py, then attacks with sat_attack.py.
    Returns list of (label, key_bits, dips, elapsed).
    """
    print(f"\nLUT-Lock Benchmark: {bench_name}")
    print("-" * 40)

    os.makedirs("locked", exist_ok=True)
    results = []

    for num_luts, anti_sat, label in lut_configs:
        locked_path = f"locked/lut_measure_{bench_name}_{num_luts}{'_as' if anti_sat else ''}.bench"
        key_path    = locked_path + ".key"

        # Lock the circuit
        try:
            n_placed, lut_info, as_info = ll.lock_circuit(
                in_path       = bench_file,
                out_path      = locked_path,
                lut_width     = 4,
                num_luts      = num_luts,
                seed          = 42,
                anti_sat      = anti_sat,
                anti_sat_bits = 8,
            )
        except Exception as e:
            print(f"  {label}: locking failed — {e}")
            continue

        # Count total key bits
        total_key_bits = sum(len(info["key_bit_names"]) for info in lut_info)
        if as_info:
            total_key_bits += len(as_info["ka_names"]) + len(as_info["kb_names"])

        # Load locked circuit and key
        lock_inputs, lock_outputs, lock_gates = parse_bench(locked_path)
        key_dict = ll.load_key_file(key_path)
        secret   = [key_dict[w] for w in lock_inputs if w.startswith("keyinput")]

        reset_vars()

        t_start = time.time()
        f = StringIO()
        with contextlib.redirect_stdout(f):
            recovered = sat_attack(lock_inputs, lock_outputs, lock_gates, secret)
        t_end = time.time()

        dips    = extract_dips_from_output(f.getvalue())
        elapsed = t_end - t_start
        broken  = (dips < 200)  # hit limit = not broken

        print(f"  {label:<25} | {total_key_bits:3d} key bits | {dips:3d} DIPs | {elapsed:.4f}s | {'BROKEN ✗' if broken else 'HELD ✓'}")

        results.append((label, total_key_bits, dips, elapsed))

    return results


# ── Plotting ──────────────────────────────────────────────────────────────────

def plot_results(xor_results, lut_results):
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    fig.suptitle("Logic Locking — SAT Attack Resistance Comparison", fontsize=14, fontweight='bold')

    ax1, ax2, ax3 = axes

    # ── Plot 1: XOR locking — key bits vs DIPs ──
    colors = ['#2E86C1', '#E74C3C', '#27AE60', '#F39C12']
    for i, (name, sizes, dips, times) in enumerate(xor_results):
        c = colors[i % len(colors)]
        ax1.plot(sizes, dips, marker='o', label=name, color=c, linewidth=2)

    ax1.set_xlabel("Key Bits")
    ax1.set_ylabel("DIPs Required")
    ax1.set_title("XOR Locking: Key Bits vs DIPs")
    ax1.legend(fontsize=8)
    ax1.grid(True, alpha=0.3)

    # ── Plot 2: XOR locking — key bits vs time ──
    for i, (name, sizes, dips, times) in enumerate(xor_results):
        c = colors[i % len(colors)]
        ax2.plot(sizes, times, marker='s', label=name, color=c, linewidth=2)

    ax2.set_xlabel("Key Bits")
    ax2.set_ylabel("Time (seconds)")
    ax2.set_title("XOR Locking: Key Bits vs Time")
    ax2.legend(fontsize=8)
    ax2.grid(True, alpha=0.3)

    # ── Plot 3: Scheme comparison bar chart ──
    if lut_results:
        scheme_labels = [r[0] for r in lut_results]
        scheme_dips   = [r[2] for r in lut_results]
        scheme_colors = []
        for r in lut_results:
            if r[2] >= 200:
                scheme_colors.append('#27AE60')   # green = held
            else:
                scheme_colors.append('#E74C3C')   # red = broken

        bars = ax3.bar(range(len(scheme_labels)), scheme_dips,
                       color=scheme_colors, edgecolor='white', linewidth=1.2)

        # Add value labels on bars
        for bar, dips in zip(bars, scheme_dips):
            label = f"{dips}" if dips < 200 else "200\n(limit)"
            ax3.text(bar.get_x() + bar.get_width() / 2,
                     bar.get_height() + 2,
                     label, ha='center', va='bottom', fontsize=9, fontweight='bold')

        ax3.set_xticks(range(len(scheme_labels)))
        ax3.set_xticklabels(scheme_labels, rotation=15, ha='right', fontsize=8)
        ax3.set_ylabel("DIPs Required")
        ax3.set_title("Scheme Comparison (c432)\nGreen = attack failed, Red = broken")
        ax3.axhline(y=200, color='black', linestyle='--', alpha=0.5, label='DIP limit (200)')
        ax3.legend(fontsize=8)
        ax3.grid(True, alpha=0.3, axis='y')

    plt.tight_layout()
    os.makedirs("results", exist_ok=True)
    out_path = "results/sat_attack_performance.png"
    plt.savefig(out_path, dpi=150, bbox_inches='tight')
    print(f"\nPlot saved: {out_path}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    # ── XOR locking experiments ──
    benchmarks = [
        ("benchmarks/c17.bench",        "c17",        [2, 3, 4]),
        ("benchmarks/c432_small.bench", "c432_small", [4, 6, 8, 10, 12]),
        ("benchmarks/c880_small.bench", "c880_small", [4, 6, 8, 10, 12]),
        ("benchmarks/c1355_small.bench","c1355_small",[4, 6, 8, 10, 12]),
    ]

    print("=" * 55)
    print("  SAT ATTACK PERFORMANCE MEASUREMENT")
    print("=" * 55)
    print("\n── XOR LOCKING ──────────────────────────────────────")

    xor_results = []
    for bench_file, bench_name, key_sizes in benchmarks:
        sizes, dips, times = run_experiment(bench_file, bench_name, key_sizes)
        if sizes:
            xor_results.append((bench_name, sizes, dips, times))

    # ── LUT-Lock experiments ──
    print("\n── LUT-LOCK + ANTI-SAT ──────────────────────────────")
    lut_configs = [
        # (num_luts, anti_sat, label)
        (2,  False, "LUT-Lock (2 LUTs)"),
        (4,  False, "LUT-Lock (4 LUTs)"),
        (6,  False, "LUT-Lock (6 LUTs)"),
        (4,  True,  "LUT-Lock + Anti-SAT (4 LUTs)"),
        (6,  True,  "LUT-Lock + Anti-SAT (6 LUTs)"),
    ]
    lut_results = run_lut_experiment(
        "benchmarks/c432_small.bench", "c432_small", lut_configs)

    # ── Plot everything ──
    plot_results(xor_results, lut_results)

    # ── Summary tables ──
    print("\n" + "=" * 55)
    print("  XOR LOCKING SUMMARY")
    print("=" * 55)
    print(f"{'Benchmark':<15} {'Key Bits':<10} {'DIPs':<8} {'Time(s)':<10}")
    print("-" * 45)
    for name, sizes, dips, times in xor_results:
        for s, d, t in zip(sizes, dips, times):
            print(f"{name:<15} {s:<10} {d:<8} {t:<10.4f}")

    print("\n" + "=" * 55)
    print("  LUT-LOCK COMPARISON SUMMARY (c432_small)")
    print("=" * 55)
    print(f"{'Scheme':<30} {'Key Bits':<10} {'DIPs':<8} {'Time(s)':<10} {'Result'}")
    print("-" * 70)
    for label, key_bits, dips, elapsed in lut_results:
        result = "HELD ✓" if dips >= 200 else "BROKEN ✗"
        print(f"{label:<30} {key_bits:<10} {dips:<8} {elapsed:<10.4f} {result}")

    print()


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
Reproducible analysis pipeline for the eVTOL vertiport CTMC models.

For each model / parameter point it
  1. generates the CTMC with BigraphER  (.tra / .csl / .rews),
  2. model-checks it with PRISM (steady-state throughput, utilisation, safety),
  3. writes tidy CSV files into  analysis/.

Outputs
  analysis/capacity_oph.csv       fig1 — V1/V2/V3 (one-way) capacity vs N
  analysis/open_v1_v2.csv         fig2 — open V1/V2 vs lambda
  analysis/v3_mix.csv             fig3 — V3 one-way traffic mix at N=5
  analysis/resilience_oph.csv     fig4 — V1 isolated fault / turnaround throughput
  analysis/v3_oneway.csv          fig3 — abstract vs one-way comparison

Run
  python3 scripts/run_analysis.py              # all modules
  python3 scripts/run_analysis.py mix          # one module
  python3 scripts/run_analysis.py mix open     # several modules
  python3 scripts/run_analysis.py --list       # show module names
"""

import argparse
import csv
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PRISM_DIR = os.path.join(ROOT, "prism_files")
ANALYSIS_DIR = os.path.join(ROOT, "analysis")
os.makedirs(PRISM_DIR, exist_ok=True)
os.makedirs(ANALYSIS_DIR, exist_ok=True)

BIGRAPHER = os.environ.get("BIGRAPHER", "bigrapher")
PRISM = os.environ.get("PRISM", "prism")
MAX_STATES = "20000000"
RESULT_RE = re.compile(r"Result:\s*([-+0-9.eE]+)")


def generate(model_file, consts, tag):
    """Run BigraphER -> .tra/.csl/.rews; return (tra, csl, rews, n_states)."""
    base = os.path.join(PRISM_DIR, tag)
    tra, csl, rews = base + ".tra", base + ".csl", base + ".rews"
    cmd = [BIGRAPHER, "full", "--solver=MCARD", "-c", consts,
           "-M", MAX_STATES, "-q", "-p", tra, "-l", csl, "-r", rews,
           os.path.join(ROOT, model_file)]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0 or not os.path.exists(tra):
        sys.stderr.write(f"[bigrapher FAILED] {tag}\n{res.stderr}\n")
        return None
    with open(tra) as f:
        n_states = int(f.readline().split()[0])
    return tra, csl, rews, n_states


def prism(tra, csl, rews, queries, consts=None, maxiters=2_000_000):
    """Model-check; return list of float results (one per query, in order)."""
    props = tra + ".props"
    as_csl_query(props, csl, queries)
    cmd = [PRISM, "-javastack", "64m",
           "-importtrans", tra, "-importstaterewards", rews,
           "-ctmc", props, "-gs", "-maxiters", str(maxiters)]
    if consts:
        cmd += ["-const", consts]
    res = subprocess.run(cmd, capture_output=True, text=True)
    out = [float(m) for m in RESULT_RE.findall(res.stdout)]
    if len(out) != len(queries):
        sys.stderr.write(f"[prism WARN] expected {len(queries)} results, "
                         f"got {len(out)}\n{res.stdout}\n{res.stderr}\n")
    return out


def as_csl_query(props, csl, queries):
    with open(csl) as f:
        labels = f.read()
    const_decl = "const double t;\n" if any("<=t" in q or "=t" in q for q in queries) else ""
    with open(props, "w") as f:
        f.write(labels + "\n" + const_decl + "\n".join(queries) + "\n")


def write_csv(name, header, rows):
    path = os.path.join(ANALYSIS_DIR, name)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"  wrote {path}  ({len(rows)} rows)")


def first_result(tra, csl, rews, query, consts=None):
    values = prism(tra, csl, rews, [query], consts=consts)
    return values[0] if values else 0.0


# ---------------------------------------------------------------------
# 1. Capacity: throughput(N) for V1, V2, V3  (N = 4, 5, 6, 7, 8, 9)
# ---------------------------------------------------------------------
def v3_split(n):
    """Balanced small/large split that sums to n (extra goes to small)."""
    s = (n + 1) // 2
    return s, n - s


V3_ONEWAY = "Vertiport_V3_2FATO_4Stand_OneWay_SBrs.big"
V3_ABSTRACT = "Vertiport_V3_2FATO_4Stand_SBrs.big"
PRISM_MAXITERS_V3 = {
    3: 2_000_000,
    4: 2_000_000,
    5: 8_000_000,
    6: 8_000_000,
    7: 8_000_000,
    8: 8_000_000,
    9: 8_000_000,
}
V3_ESTIMATE_RATIO_FROM_N = 5


def prism_v3_oneway(tra, csl, rews, n, *, with_transit_blocking=False):
    """Steady-state queries shared by capacity sweep and abstract comparison."""
    qs = [
        'R=? [ S ]',
        'S=? [ "small_pad_landing" ]',
        'S=? [ "small_pad_departing" ]',
        'S=? [ "large_pad_landing" ]',
        'S=? [ "large_pad_departing" ]',
        'S=? [ "large_pad_landing_small" ]',
        'S=? [ "large_pad_departing_small" ]',
        'S=? [ !"some_stand_free" ]',
    ]
    if with_transit_blocking:
        qs += [
            'S=? [ "small_transit_blocked_1" ]',
            'S=? [ "large_transit_blocked_1" ]',
        ]
    return prism(tra, csl, rews, qs, maxiters=PRISM_MAXITERS_V3.get(n, 2_000_000))


def v3_oneway_scale_from_fig5():
    """Use the highest validated Fig. 5 point as the abstract->one-way scale."""
    n = V3_ESTIMATE_RATIO_FROM_N
    ns_small, ns_large = v3_split(n)
    vals = {}
    for model, mfile in [("abstract", V3_ABSTRACT), ("oneway", V3_ONEWAY)]:
        tag = f"V3_scale_{model}_N{n}"
        g = generate(mfile, f"n_small={ns_small},n_large={ns_large}", tag)
        if not g:
            return 1.0
        tra, csl, rews, _states = g
        vals[model] = 60 * prism_v3_oneway(tra, csl, rews, n)[0]
    ratio = vals["oneway"] / vals["abstract"]
    print(f"   V3 estimate scale from Fig.5 N={n}: "
          f"oneway/abstract={ratio:.4f}")
    return ratio


def run_capacity():
    print("[1/5] Capacity throughput(N) for V1/V2/V3 ...")
    rows = []
    fleet = [4, 5, 6, 7, 8, 9]
    single = [
        ("V1", "Vertiport_V1_1FATO_3Stand_SBrs.big", "1 FATO / 3 stands"),
        ("V2", "Vertiport_V2_1FATO_4Stand_SBrs.big", "1 FATO / 4 stands"),
    ]
    for key, mfile, desc in single:
        for n in fleet:
            tag = f"{key}_N{n}"
            g = generate(mfile, f"n_evtol={n}", tag)
            if not g:
                continue
            tra, csl, rews, ns = g
            r = prism(tra, csl, rews, [
                'R=? [ S ]',
                'S=? [ "fato_landing" ]',
                'S=? [ "fato_departing" ]',
                'S=? [ !"some_stand_free" ]',   # all stands busy = no free stand
            ])
            throughput = 60 * r[0]
            pad_util = r[1] + r[2]
            rows.append([key, desc, n, ns, round(throughput, 3),
                         round(pad_util, 4), round(r[3], 4), "false"])
            print(f"   {key} N={n}: states={ns} throughput={throughput:.2f} "
                  f"pad_util={pad_util:.3f} stands_busy={r[3]:.3f}")

    v3_scale = v3_oneway_scale_from_fig5()
    for n in fleet:
        ns_small, ns_large = v3_split(n)
        if n <= 5:
            mfile = V3_ONEWAY
            tag = f"V3_oneway_N{n}"
            layout = f"2 FATO / 4 stands one-way ({ns_small}S+{ns_large}L)"
            estimated = "false"
        else:
            mfile = V3_ABSTRACT
            tag = f"V3_abstract_capacity_N{n}"
            layout = (
                "2 FATO / 4 stands one-way predicted "
                f"({ns_small}S+{ns_large}L; abstract x Fig.5 N=5 ratio)"
            )
            estimated = "true"
        g = generate(mfile, f"n_small={ns_small},n_large={ns_large}", tag)
        if not g:
            continue
        tra, csl, rews, ns = g
        r = prism_v3_oneway(tra, csl, rews, n)
        throughput = 60 * r[0]
        large_pad_util = r[3] + r[4] + r[5] + r[6]
        pad_util = (r[1] + r[2] + large_pad_util) / 2.0   # avg of the two pads
        if estimated == "true":
            throughput *= v3_scale
            pad_util *= v3_scale
            print(f"   V3 abstract N={n}: states={ns} "
                  f"estimated throughput={throughput:.2f}")
        else:
            print(f"   V3 one-way N={n}: states={ns} throughput={throughput:.2f} "
                  f"pad_util={pad_util:.3f} stands_busy={r[7]:.3f}")
        rows.append(["V3", layout, n, ns, round(throughput, 3), round(pad_util, 4),
                     round(r[7], 4), estimated])

    write_csv("capacity_oph.csv",
              ["model", "layout", "N", "states", "throughput",
               "pad_utilisation", "all_stands_busy_prob", "estimated"],
              rows)


# ---------------------------------------------------------------------
# 2. V3 traffic mix sensitivity (fig3: N = 5 only)
# ---------------------------------------------------------------------
def run_mix(fleet=None):
    fleet = fleet or [5]
    print(f"[mix] V3 one-way traffic-mix sensitivity at N={fleet} ...")
    rows = []
    for total in fleet:
        for ns_small in range(0, total + 1):
            ns_large = total - ns_small
            tag = f"V3_oneway_mix_N{total}_{ns_small}S{ns_large}L"
            g = generate(V3_ONEWAY, f"n_small={ns_small},n_large={ns_large}", tag)
            if not g:
                print(f"   N={total} skip {ns_small}S+{ns_large}L (generation failed)")
                continue
            tra, csl, rews, ns = g
            r = prism_v3_oneway(tra, csl, rews, total)
            throughput = 60 * r[0]
            large_pad_util = r[3] + r[4] + r[5] + r[6]
            rows.append([ns_small, ns_large, total, ns, round(throughput, 3),
                         round(r[1] + r[2], 4), round(large_pad_util, 4)])
            print(f"   N={total} {ns_small}S+{ns_large}L: states={ns} throughput={throughput:.2f}")
    write_csv("v3_mix.csv",
              ["n_small", "n_large", "N", "states", "throughput",
               "small_pad_util", "large_pad_util"],
              rows)


# ---------------------------------------------------------------------
# 3. V3 one-way realism: abstracted vs de-abstracted taxiways (fig3 panels 2-3)
# ---------------------------------------------------------------------
def run_v3_oneway():
    print("[3/5] V3 abstract vs one-way taxiways (fig3) ...")
    rows = []
    cases = [(3, 2, 1), (4, 2, 2), (5, 3, 2)]
    for n, ns_small, ns_large in cases:
        for model, mfile in [
            ("abstract", V3_ABSTRACT),
            ("oneway", V3_ONEWAY),
        ]:
            tag = f"V3_{model}_N{n}"
            g = generate(mfile, f"n_small={ns_small},n_large={ns_large}", tag)
            if not g:
                continue
            tra, csl, rews, states = g
            if model == "abstract":
                r = prism_v3_oneway(tra, csl, rews, n)
                small_block, large_block = 0.0, 0.0
            else:
                r = prism_v3_oneway(tra, csl, rews, n, with_transit_blocking=True)
                small_block, large_block = r[8], r[9]
            throughput = 60 * r[0]
            large_pad_util = r[3] + r[4] + r[5] + r[6]
            pad_util = (r[1] + r[2] + large_pad_util) / 2.0
            rows.append([model, n, ns_small, ns_large, states, round(throughput, 3),
                         round(pad_util, 4), round(r[7], 4),
                         round(small_block, 5), round(large_block, 5)])
            print(f"   V3 {model} N={n}: states={states} throughput={throughput:.2f}")
    write_csv("v3_oneway.csv",
              ["model", "N", "n_small", "n_large", "states", "throughput",
               "pad_utilisation", "all_stands_busy_prob",
               "small_transit_blocked", "large_transit_blocked"],
              rows)


def expected_from_cumulative(at_least_probs, max_k):
    """E[X] from P(X>=k) labels; E[X] = sum_k P(X >= k)."""
    return sum(at_least_probs[:max_k])


def open_count_queries(k_app, k_taxi, max_stands):
    labels = []
    weights = []
    for prefix, max_value in [
        ("app_count", k_app),
        ("taxi_in_count", k_taxi),
        ("taxi_out_count", k_taxi),
    ]:
        for i in range(max_value + 1):
            labels.append(f'{prefix}_{i}')
            weights.append(i)
    svc_labels = [f'svc_at_least_{k}' for k in range(1, max_stands + 1)]
    rdy_labels = [f'rdy_at_least_{k}' for k in range(1, max_stands + 1)]
    labels += svc_labels + rdy_labels + ["pad_in_system", "pad_out_system"]
    weights += [1, 1]
    return [f'S=? [ "{label}" ]' for label in labels], weights, max_stands


def mean_in_system_from_counts(count_probs, weights, max_stands):
    """Little's-law mean L from exact-count and cumulative stand labels."""
    idx = 0
    l_system = 0.0
    for w in weights[:-2]:
        l_system += w * count_probs[idx]
        idx += 1
    svc_cum = count_probs[idx:idx + max_stands]
    idx += max_stands
    rdy_cum = count_probs[idx:idx + max_stands]
    idx += max_stands
    l_system += expected_from_cumulative(svc_cum, max_stands)
    l_system += expected_from_cumulative(rdy_cum, max_stands)
    l_system += count_probs[idx] + count_probs[idx + 1]
    return l_system


# ---------------------------------------------------------------------
# 5. Open-arrival V1/V2 (M/M/c/K with blocking)
# ---------------------------------------------------------------------
def run_open_v1_v2(k_app=6, k_taxi=3):
    print("[4/5] Open V1/V2 M/M/c/K lambda sweep ...")
    rows = []
    lambdas = [0.2, 0.5, 1.0, 2.0]
    for model, mfile, layout, max_stands in [
        ("V1", "Vertiport_V1_Open_SBrs.big", "1 FATO / 3 stands", 3),
        ("V2", "Vertiport_V2_Open_SBrs.big", "1 FATO / 4 stands", 4),
    ]:
        for lam in lambdas:
            tag = f"{model}_open_kapp{k_app}_ktaxi{k_taxi}_lam{lam}"
            g = generate(mfile, f"arr_rate={lam},k_app={k_app},k_taxi={k_taxi}", tag)
            if not g:
                continue
            tra, csl, rews, states = g
            r = prism(tra, csl, rews, [
                'R=? [ S ]',
                'S=? [ "approach_full" ]',
            ])
            throughput = 60 * r[0]
            p_block = r[1]
            count_qs, weights, n_stands = open_count_queries(k_app, k_taxi, max_stands)
            count_probs = prism(tra, csl, rews, count_qs)
            l_system = mean_in_system_from_counts(count_probs, weights, n_stands)
            lambda_eff = max(lam * (1.0 - p_block), 1e-9)
            delay = l_system / lambda_eff
            rows.append([model, layout, lam, k_app, k_taxi, states,
                         round(throughput, 3), round(p_block, 5),
                         round(l_system, 4), round(delay, 4)])
            print(f"   {model} lambda={lam}: throughput={throughput:.2f} block={p_block:.3f}")
    write_csv("open_v1_v2.csv",
              ["model", "layout", "lambda", "k_app", "k_taxi", "states",
               "throughput", "P_block", "mean_in_system", "mean_delay_min"],
              rows)


# ---------------------------------------------------------------------
# 6. V1 saturated resilience (isolated fault models + turnaround sweep)
# ---------------------------------------------------------------------
RESILIENCE_MODELS = {
    "pad": "Vertiport_V1_Resilience_Pad_SBrs.big",
    "stand": "Vertiport_V1_Resilience_Stand_SBrs.big",
    "weather": "Vertiport_V1_Resilience_Weather_SBrs.big",
}
RESILIENCE_REPAIR = {
    "pad": {"repair_rate": 0.1},              # mean repair 10 min
    "stand": {"stand_repair_rate": 0.1},      # mean repair 10 min
    "weather": {"weather_repair_rate": 0.05}, # mean recovery 20 min
}
RESILIENCE_RATE_KEY = {
    "pad": "fault_rate",
    "stand": "stand_fault_rate",
    "weather": "weather_fault_rate",
}
TURNAROUND_MINUTES = [10, 15, 20, 30]


def run_resilience_depth(n=6):
    print(f"[5/5] V1 isolated resilience + turnaround (N={n}) ...")
    rows = []
    g0 = generate("Vertiport_V1_1FATO_3Stand_SBrs.big", f"n_evtol={n}",
                  f"V1_nominal_N{n}")
    if not g0:
        return
    tra0, csl0, rews0, _states0 = g0
    nominal_throughput = 60 * first_result(tra0, csl0, rews0, 'R=? [ S ]')
    print(f"   nominal N={n}: throughput={nominal_throughput:.2f}")

    fault_rates = [0.01, 0.05, 0.1]
    for panel in ("pad", "stand", "weather"):
        rows.append([panel, "baseline", "", round(nominal_throughput, 3), "baseline"])
        rate_key = RESILIENCE_RATE_KEY[panel]
        repair = RESILIENCE_REPAIR[panel]
        mfile = RESILIENCE_MODELS[panel]
        for fr in fault_rates:
            consts = ",".join(
                [f"n_evtol={n}", f"{rate_key}={fr}"]
                + [f"{k}={v}" for k, v in repair.items()]
            )
            tag = f"V1_res_{panel}_N{n}_fr{fr}"
            g = generate(mfile, consts, tag)
            if not g:
                continue
            tra, csl, rews, states = g
            throughput = 60 * first_result(tra, csl, rews, 'R=? [ S ]')
            rows.append([panel, rate_key, fr, round(throughput, 3), "degraded"])
            print(f"   {panel} {rate_key}={fr}: states={states} throughput={throughput:.2f}")

    rows.append(["turnaround", "baseline", "", round(nominal_throughput, 3), "baseline"])
    for minutes in TURNAROUND_MINUTES:
        rate_service = 1.0 / minutes
        consts = f"n_evtol={n},rate_service={rate_service}"
        tag = f"V1_turnaround_N{n}_t{minutes}"
        g = generate("Vertiport_V1_Resilience_Turnaround_SBrs.big", consts, tag)
        if not g:
            continue
        tra, csl, rews, states = g
        throughput = 60 * first_result(tra, csl, rews, 'R=? [ S ]')
        curve = "baseline" if minutes == 10 else "degraded"
        rows.append(["turnaround", "minutes", minutes, round(throughput, 3), curve])
        print(f"   turnaround {minutes} min: states={states} throughput={throughput:.2f}")

    write_csv("resilience_oph.csv",
              ["panel", "param_name", "param_value", "throughput", "curve"],
              rows)


MODULES = {
    "capacity": run_capacity,
    "mix": run_mix,
    "v3_oneway": run_v3_oneway,
    "open": run_open_v1_v2,
    "resilience": lambda: run_resilience_depth(n=6),
}


def main():
    order = ["capacity", "mix", "v3_oneway", "open", "resilience"]
    parser = argparse.ArgumentParser(
        description="BigraphER → PRISM pipeline for eVTOL vertiport analysis.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Modules: "
            + ", ".join(MODULES)
            + ".  With no module names, all modules run in order."
        ),
    )
    parser.add_argument(
        "modules",
        nargs="*",
        metavar="MODULE",
        help="one or more of: "
        + ", ".join(MODULES)
        + " (default: all, in pipeline order)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="list module names and exit",
    )
    args = parser.parse_args()
    if args.list:
        for name in order:
            print(name)
        return
    selected = args.modules or order
    unknown = [m for m in selected if m not in MODULES]
    if unknown:
        parser.error(
            "unknown module(s): "
            + ", ".join(unknown)
            + ".  Choose from: "
            + ", ".join(order)
        )
    selected = [m for m in order if m in selected]
    for name in selected:
        MODULES[name]()
    print("\nDone. CSV results are in analysis/.")


if __name__ == "__main__":
    main()

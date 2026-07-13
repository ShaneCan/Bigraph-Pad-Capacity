#!/usr/bin/env python3
"""
Reproducible analysis pipeline for the eVTOL vertiport CTMC models.

For each model / parameter point it
  1. generates the CTMC with BigraphER  (.tra / .csl / .rews),
  2. model-checks it with PRISM (steady-state throughput, utilisation, safety),
  3. writes tidy CSV files into  analysis/.

Outputs
  analysis/fig1_capacity_oph.csv        fig1 — V1/V2/V3 capacity vs N (N = 4..8)
  analysis/fig2_open_v1_v2.csv          fig2 — open V1/V2 vs lambda
  analysis/fig3_sensitivity_oph.csv     fig3 — V1 steady-state fault / turnaround sensitivity
  analysis/fig4_recovery_throughput.csv fig4 — pad-closed transient throughput R=?[I=t]
  analysis/fig5_compound_recovery.csv   fig5 — pad-closed + k stands out recovery erosion
  analysis/fig6_compound_capacity.csv   fig6 — sustained capacity (weather × stands out)

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
# 1. Capacity: throughput(N) for V1, V2, V3  (N = 4, 5, 6, 7, 8)
# ---------------------------------------------------------------------
V3_BIDIR = "Vertiport_V3_2FATO_4Stand_BiDir_SBrs.big"
V3_OPEN = "Vertiport_V3_Open_SBrs.big"
M_MOVE_V3 = 8   # in-vertiport admission cap (matches m_move in the .big models)
PRISM_MAXITERS_V3 = {
    4: 2_000_000,
    5: 8_000_000,
    6: 8_000_000,
    7: 8_000_000,
    8: 8_000_000,
}


def prism_v3(tra, csl, rews, n, *, with_stand_util=False):
    """Steady-state queries for the V3 bidirectional U-taxiway model."""
    qs = [
        'R=? [ S ]',
        'S=? [ "pad1_free" ]',
        'S=? [ "pad2_free" ]',
        'S=? [ !"some_stand_free" ]',
    ]
    if with_stand_util:
        qs += stand_util_queries(M_STAND["V3"])
    return prism(tra, csl, rews, qs, maxiters=PRISM_MAXITERS_V3.get(n, 2_000_000))


def v3_pad_util(r):
    """Mean pad utilisation (fraction of the 2 pads busy) from prism_v3."""
    e_free = r[1] + r[2]
    return (2.0 - e_free) / 2.0


def v3_open_interior_queries(k_taxi, max_stands=4):
    """PRISM labels for the V3 open (taxi-abstract, 2-pad) interior count.

    Interior = inbound taxi + outbound taxi + stands + both pads.  Returns
    (queries, taxi_weights, max_stands): the two pads are counted with four
    per-pad occupancy labels (each 0/1) so E[pads busy] = sum of their
    probabilities."""
    labels = []
    weights = []
    for prefix in ("taxi_in_count", "taxi_out_count"):
        for i in range(k_taxi + 1):
            labels.append(f"{prefix}_{i}")
            weights.append(i)
    labels += [f"svc_at_least_{k}" for k in range(1, max_stands + 1)]
    labels += [f"rdy_at_least_{k}" for k in range(1, max_stands + 1)]
    labels += ["pad1_landing", "pad1_departing", "pad2_landing", "pad2_departing"]
    return [f'S=? [ "{lbl}" ]' for lbl in labels], weights, max_stands


def mean_in_vertiport_v3(probs, taxi_weights, max_stands):
    """Mean aircraft inside the V3 vertiport (taxi + stands + 2 pads)."""
    idx = 0
    total = 0.0
    for w in taxi_weights:
        total += w * probs[idx]
        idx += 1
    total += expected_from_cumulative(probs[idx:idx + max_stands], max_stands)
    idx += max_stands
    total += expected_from_cumulative(probs[idx:idx + max_stands], max_stands)
    idx += max_stands
    total += sum(probs[idx:idx + 4])   # four per-pad occupancy probabilities
    return total


def run_capacity():
    print("[1/4] Capacity throughput(N) for V1/V2/V3 ...")
    rows = []
    fleet = [4, 5, 6, 7, 8]
    single = [
        ("V1", "Vertiport_V1_1FATO_3Stand_SBrs.big", "1 FATO / 3 stands"),
        ("V2", "Vertiport_V2_1FATO_4Stand_SBrs.big", "1 FATO / 4 stands"),
    ]
    for key, mfile, desc in single:
        max_stands = M_STAND[key]
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
            ] + stand_util_queries(max_stands))
            throughput = 60 * r[0]
            pad_util = r[1] + r[2]
            stand_util = mean_stand_utilisation(r[4:], max_stands)
            rows.append([key, desc, n, ns, round(throughput, 3),
                         round(pad_util, 4), round(stand_util, 4),
                         round(r[3], 4), "false"])
            print(f"   {key} N={n}: states={ns} throughput={throughput:.2f} "
                  f"pad_util={pad_util:.3f} stand_util={stand_util:.3f} "
                  f"stands_busy={r[3]:.3f}")

    for n in fleet:
        tag = f"V3_bidir_N{n}"
        layout = "2 FATO / 4 stands bidirectional U-taxiway"
        g = generate(V3_BIDIR, f"n={n}", tag)
        if not g:
            continue
        tra, csl, rews, ns = g
        r = prism_v3(tra, csl, rews, n, with_stand_util=True)
        throughput = 60 * r[0]
        pad_util = v3_pad_util(r)
        stand_util = mean_stand_utilisation(r[4:], M_STAND["V3"])
        print(f"   V3 bidir N={n}: states={ns} throughput={throughput:.2f} "
              f"pad_util={pad_util:.3f} stand_util={stand_util:.3f} "
              f"stands_busy={r[3]:.3f}")
        rows.append(["V3", layout, n, ns, round(throughput, 3), round(pad_util, 4),
                     round(stand_util, 4), round(r[3], 4), "false"])

    write_csv("fig1_capacity_oph.csv",
              ["model", "layout", "N", "states", "throughput",
               "pad_utilisation", "stand_utilisation",
               "all_stands_busy_prob", "estimated"],
              rows)


def expected_from_cumulative(at_least_probs, max_k):
    """E[X] from P(X>=k) labels; E[X] = sum_k P(X >= k)."""
    return sum(at_least_probs[:max_k])


M_STAND = {"V1": 3, "V2": 4, "V3": 4}


def stand_util_queries(max_stands):
    """PRISM steady-state labels for mean stand occupancy."""
    labels = []
    for prefix in ("svc_at_least_", "rdy_at_least_"):
        for k in range(1, max_stands + 1):
            labels.append(f"{prefix}{k}")
    return [f'S=? [ "{label}" ]' for label in labels]


def mean_stand_utilisation(at_least_probs, max_stands):
    """Average fraction of stands occupied (Svc or Rdy)."""
    idx = 0
    occupied = 0.0
    for _ in range(2):
        occupied += expected_from_cumulative(
            at_least_probs[idx:idx + max_stands], max_stands,
        )
        idx += max_stands
    return occupied / max_stands


def vertiport_count_queries(k_taxi, max_stands):
    """PRISM steady-state labels for mean vertiport-interior occupancy."""
    labels = []
    count_weights = []
    for prefix, max_value in [
        ("taxi_in_count", k_taxi),
        ("taxi_out_count", k_taxi),
    ]:
        for i in range(max_value + 1):
            labels.append(f"{prefix}_{i}")
            count_weights.append(i)
    labels += [f"svc_at_least_{k}" for k in range(1, max_stands + 1)]
    labels += [f"rdy_at_least_{k}" for k in range(1, max_stands + 1)]
    labels += ["pad_in_system", "pad_out_system"]
    return [f'S=? [ "{label}" ]' for label in labels], count_weights, max_stands


def mean_in_vertiport_from_counts(count_probs, count_weights, max_stands):
    """Mean aircraft inside the vertiport (taxi, stands, pads only)."""
    idx = 0
    l_vertiport = 0.0
    for w in count_weights:
        l_vertiport += w * count_probs[idx]
        idx += 1
    svc_cum = count_probs[idx:idx + max_stands]
    idx += max_stands
    rdy_cum = count_probs[idx:idx + max_stands]
    idx += max_stands
    l_vertiport += expected_from_cumulative(svc_cum, max_stands)
    l_vertiport += expected_from_cumulative(rdy_cum, max_stands)
    l_vertiport += count_probs[idx] + count_probs[idx + 1]
    return l_vertiport


# ---------------------------------------------------------------------
# 5. Open-arrival V1/V2 (M/M/c/K with blocking)
# ---------------------------------------------------------------------
def run_open(k_app=20, k_taxi=3):
    print("[2/4] Open V1/V2/V3 M/M/c/K lambda sweep ...")
    rows = []
    # Arrival-rate sweep spanning below-capacity to overload (V1 cap ~0.26,
    # V2 ~0.32, V3 ~0.37 min^-1).  Buffer k_app=20 (~20-aircraft holding
    # stack) is large enough that the mean approach-queue length is set by
    # queueing dynamics in the stable regime; past capacity the queue
    # saturates the holding stack (overload).
    lambdas = [0.10, 0.20, 0.50, 1.00]

    # --- V1 / V2: counter-based taxi interior --------------------------
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
            count_qs, count_weights, n_stands = vertiport_count_queries(
                k_taxi, max_stands,
            )
            count_probs = prism(tra, csl, rews, count_qs)
            l_vertiport = mean_in_vertiport_from_counts(
                count_probs, count_weights, n_stands,
            )
            lambda_eff = max(lam * (1.0 - p_block), 1e-9)
            delay_vertiport = l_vertiport / lambda_eff
            rows.append([model, layout, lam, k_app, k_taxi, states,
                         round(throughput, 3), round(p_block, 5),
                         round(l_vertiport, 4), round(delay_vertiport, 4)])
            print(f"   {model} lambda={lam}: throughput={throughput:.2f} "
                  f"block={p_block:.3f} L_vp={l_vertiport:.2f} "
                  f"W_vp={delay_vertiport:.2f}min")

    # --- V3: taxi-abstract 2-pad open model (same abstraction as V1/V2),
    # so the lambda-sweep compares all three layouts at one modelling level.
    # (The explicit bidirectional open model is state-space intractable and
    # its taxiway detail does not change the M/M/c/K queueing metrics.)
    for lam in lambdas:
        tag = f"V3_open_kapp{k_app}_ktaxi{k_taxi}_lam{lam}"
        g = generate(V3_OPEN, f"arr_rate={lam},k_app={k_app},k_taxi={k_taxi}", tag)
        if not g:
            continue
        tra, csl, rews, states = g
        r = prism(tra, csl, rews, [
            'R=? [ S ]',
            'S=? [ "approach_full" ]',
        ])
        throughput = 60 * r[0]
        p_block = r[1]
        count_qs, taxi_weights, n_stands = v3_open_interior_queries(k_taxi)
        count_probs = prism(tra, csl, rews, count_qs)
        l_vertiport = mean_in_vertiport_v3(count_probs, taxi_weights, n_stands)
        lambda_eff = max(lam * (1.0 - p_block), 1e-9)
        delay_vertiport = l_vertiport / lambda_eff
        rows.append(["V3", "2 FATO / 4 stands", lam, k_app, k_taxi,
                     states, round(throughput, 3), round(p_block, 5),
                     round(l_vertiport, 4), round(delay_vertiport, 4)])
        print(f"   V3 lambda={lam}: throughput={throughput:.2f} "
              f"block={p_block:.3f} L_vp={l_vertiport:.2f} "
              f"W_vp={delay_vertiport:.2f}min")

    write_csv("fig2_open_v1_v2.csv",
              ["model", "layout", "lambda", "k_app", "k_taxi", "states",
               "throughput", "P_block",
               "mean_in_vertiport", "mean_delay_vertiport"],
              rows)


# ---------------------------------------------------------------------
# 6. V1 saturated resilience (isolated fault models + turnaround sweep)
# ---------------------------------------------------------------------
RESILIENCE_MODELS = {
    "pad": "Vertiport_V1_Sensitivity_Pad_SBrs.big",
    "stand": "Vertiport_V1_Sensitivity_Stand_SBrs.big",
    "weather": "Vertiport_V1_Sensitivity_Weather_SBrs.big",
}
RESILIENCE_REPAIR = {
    "pad": {"repair_rate": 0.1},               # mean repair 10 min
    "stand": {"stand_repair_rate": 0.03333},  # mean repair 30 min
    "weather": {"weather_repair_rate": 0.05}, # mean recovery 20 min
}
RESILIENCE_RATE_KEY = {
    "pad": "fault_rate",
    "stand": "stand_fault_rate",
    "weather": "weather_fault_rate",
}
TURNAROUND_MINUTES = [10, 15, 20, 30]

RECOVERY_MODEL = "Vertiport_V1_Recovery_PadClosed_SBrs.big"
RECOVERY_REPAIR_RATES = [0.05, 0.1, 0.2, 0.5]
RECOVERY_T_STEP = 5
RECOVERY_T_MAX = 120
REF_TIME_MIN = 30


def recovery_time_grid():
    return list(range(0, RECOVERY_T_MAX + 1, RECOVERY_T_STEP))


def run_pad_recovery(n=6):
    print(f"[recovery] Pad-closed transient throughput R=?[I=t] (N={n}, fig4) ...")
    rows = []
    t_values = recovery_time_grid()
    for rr in RECOVERY_REPAIR_RATES:
        tag = f"V1_recovery_padclosed_N{n}_rr{rr}"
        g = generate(RECOVERY_MODEL, f"n_evtol={n},repair_rate={rr}", tag)
        if not g:
            continue
        tra, csl, rews, states = g
        print(f"   repair_rate={rr}: states={states}")
        for t in t_values:
            instant = first_result(
                tra, csl, rews, 'R=? [ I=t ]',
                consts=f"t={t},repair_rate={rr},n_evtol={n}",
            )
            throughput = 60 * instant
            rows.append([
                rr, t, round(instant, 6), round(throughput, 3), n,
            ])
            if t in (0, REF_TIME_MIN, RECOVERY_T_MAX):
                print(f"      t={t}: throughput={throughput:.2f} oph")
    write_csv(
        "fig4_recovery_throughput.csv",
        ["repair_rate", "t_min", "instant_rate", "throughput_oph", "n_evtol"],
        rows,
    )


def run_resilience_depth(n=6):
    print(f"[3/4] V1 isolated resilience + turnaround (N={n}) ...")
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
        g = generate("Vertiport_V1_Sensitivity_Turnaround_SBrs.big", consts, tag)
        if not g:
            continue
        tra, csl, rews, states = g
        throughput = 60 * first_result(tra, csl, rews, 'R=? [ S ]')
        curve = "baseline" if minutes == 10 else "degraded"
        rows.append(["turnaround", "minutes", minutes, round(throughput, 3), curve])
        print(f"   turnaround {minutes} min: states={states} throughput={throughput:.2f}")

    write_csv("fig3_sensitivity_oph.csv",
              ["panel", "param_name", "param_value", "throughput", "curve"],
              rows)


# ---------------------------------------------------------------------
# 7. Compound-fault recovery erosion (fig5): pad closed + k stands out
# ---------------------------------------------------------------------
COMPOUND_RECOVERY_MODELS = {
    0: "Vertiport_V1_Recovery_PadClosed_SBrs.big",     # pad closed, 0 stands out
    1: "Vertiport_V1_Recovery_Compound_k1_SBrs.big",   # pad closed + 1 stand out
    2: "Vertiport_V1_Recovery_Compound_k2_SBrs.big",   # pad closed + 2 stands out
}
COMPOUND_REPAIR_RATE = 0.1           # pad mean repair 10 min
COMPOUND_STAND_REPAIR_RATE = 0.03333 # stand mean repair 30 min


def run_compound_recovery(n=6):
    """fig5 — throughput recovery after pad closure, eroded by k co-failed stands."""
    print(f"[compound-recovery] pad-closed + k stands out, R=?[I=t] (N={n}, fig5) ...")
    rows = []
    t_values = recovery_time_grid()
    for k in (0, 1, 2):
        model = COMPOUND_RECOVERY_MODELS[k]
        gen_consts = f"n_evtol={n},repair_rate={COMPOUND_REPAIR_RATE}"
        if k > 0:
            gen_consts += f",stand_repair_rate={COMPOUND_STAND_REPAIR_RATE}"
        g = generate(model, gen_consts, f"V1_comprec_k{k}_N{n}")
        if not g:
            continue
        tra, csl, rews, states = g
        print(f"   k={k}: states={states}")
        for t in t_values:
            instant = first_result(tra, csl, rews, 'R=? [ I=t ]', consts=f"t={t}")
            throughput = 60 * instant
            rows.append([k, t, round(instant, 6), round(throughput, 3), n])
            if t in (0, REF_TIME_MIN, RECOVERY_T_MAX):
                print(f"      t={t}: throughput={throughput:.2f} oph")
    write_csv("fig5_compound_recovery.csv",
              ["k_out", "t_min", "instant_rate", "throughput_oph", "n_evtol"],
              rows)


# ---------------------------------------------------------------------
# 8. Stand-outage cost under weather (fig6): capacity envelope + recovery
# ---------------------------------------------------------------------
COMPOUNDSW_CAP_MODELS = {
    0: "Vertiport_V1_Sensitivity_Weather_SBrs.big",       # 0 stands out (weather only)
    1: "Vertiport_V1_Weather_StandOut_k1_SBrs.big",   # 1 stand out of service
    2: "Vertiport_V1_Weather_StandOut_k2_SBrs.big",   # 2 stands out of service
    3: "Vertiport_V1_Weather_StandOut_k3_SBrs.big",   # 3 stands out -> capacity 0
}
# Weather severity axis: bad-weather onset rate (mean bad-spell = 1/repair).
# 0.001 ~ "always clear" (BigraphER rejects an exact 0.0 rate).
COMPOUNDSW_WEATHER_FF = [0.001, 0.02, 0.05, 0.1, 0.2]
COMPOUNDSW_WEATHER_REPAIR = 0.05    # mean bad-weather spell 20 min

def run_compound_standweather(n=6):
    """fig6 — sustained capacity heat-map: weather severity × stands out (R=?[S])."""
    print(f"[compound-SW] stand-outage cost under weather (N={n}, fig6) ...")
    cap_rows = []
    for k in (0, 1, 2, 3):
        model = COMPOUNDSW_CAP_MODELS[k]
        for wff in COMPOUNDSW_WEATHER_FF:
            consts = (f"n_evtol={n},weather_fault_rate={wff},"
                      f"weather_repair_rate={COMPOUNDSW_WEATHER_REPAIR}")
            g = generate(model, consts, f"V1_swcap_k{k}_wff{wff}_N{n}")
            if not g:
                continue
            tra, csl, rews, states = g
            thr = 60 * first_result(tra, csl, rews, 'R=? [ S ]')
            cap_rows.append([k, wff, round(thr, 3), n])
            print(f"   k={k} weather_ff={wff}: states={states} throughput={thr:.2f}")
    write_csv("fig6_compound_capacity.csv",
              ["stands_out", "weather_fault_rate", "throughput_oph", "n_evtol"],
              cap_rows)


MODULES = {
    "capacity": run_capacity,
    "open": run_open,
    "resilience": lambda: run_resilience_depth(n=6),
    "recovery": lambda: run_pad_recovery(n=6),
    "compound_recovery": lambda: run_compound_recovery(n=6),
    "compound_sw": lambda: run_compound_standweather(n=6),
}


def main():
    order = ["capacity", "open", "resilience", "recovery",
             "compound_recovery", "compound_sw"]
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

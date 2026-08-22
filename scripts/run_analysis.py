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
  analysis/fig3_sensitivity_oph.csv     fig3 — V1 sensitivity vs unavailability P (pad/stand/weather) + turnaround
  analysis/fig4_recovery_throughput.csv fig4 — V1 pad-closed transient throughput R=?[I=t]
  analysis/fig4_recovery_v3.csv         fig4 — V3 dual-FATO pad-closed recovery (mu=0.1)
  analysis/fig5_compound_recovery.csv   fig5 — V1 pad-closed + k stands out recovery erosion
  analysis/fig5_compound_recovery_v2.csv fig5 — V2 compound recovery (pad + 1/2 stands out)
  analysis/fig4b_recovery_prob.csv      fig4 — V1 P[F<=t recovered], pad-closure severity sweep
  analysis/fig5b_restoration_prob.csv   fig5 — V1 P[F<=t restored], k = 0/1/2 stands out
  analysis/fig6_compound_capacity.csv   fig6 — V1 sustained capacity (weather × stands out)
  analysis/fig6_compound_capacity_v2.csv fig6 — V2 sustained capacity (weather × stands out)
  analysis/fig_envelope.csv             envelope — compound k=2 contract: p*(t), C_d(t), rho(t) for V1 and V2
  analysis/fig_sla_survival.csv         availability — SLA survival P[G<=t op(d)] vs t for V1/V2 (d=10,15)
  analysis/fig_sla_envelope.csv         availability — demand-horizon envelope: t*(d), S_avail, MTTB for V1/V2

Run
  python3 scripts/run_analysis.py              # all modules
  python3 scripts/run_analysis.py mix          # one module
  python3 scripts/run_analysis.py mix open     # several modules
  python3 scripts/run_analysis.py --list       # show module names

One-click rerun of the NEW figure comparisons (existing V1 data untouched):
  fig4 (+V3):  python3 scripts/run_analysis.py recovery_v3          && python3 scripts/plot_results.py fig4
  fig5 (+V2):  python3 scripts/run_analysis.py compound_recovery_v2 && python3 scripts/plot_results.py fig5
  fig6 (+V2):  python3 scripts/run_analysis.py compound_sw_v2       && python3 scripts/plot_results.py fig6
"""

import argparse
import csv
import math
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
    "stand": {"stand_repair_rate": 0.05},     # mean repair 20 min
    "weather": {"weather_repair_rate": 0.05}, # mean recovery 20 min
}
RESILIENCE_RATE_KEY = {
    "pad": "fault_rate",
    "stand": "stand_fault_rate",
    "weather": "weather_fault_rate",
}
TURNAROUND_MINUTES = [10, 15, 20, 30]

# fig3/fig6 share one physically comparable severity axis: steady-state
# unavailability P (the fraction of time the resource is closed / degraded).
# Each stressor is a 2-state up<->down CTMC with onset rate lambda and recovery
# rate mu; in steady state P = lambda / (lambda + mu), so the BigraphER onset
# rate is back-computed from the target P and the panel's own repair time.
UNAVAIL_GRID = [0.05, 0.10, 0.15, 0.20, 0.30]   # P=0 is handled separately


def lambda_from_unavailability(p, mu):
    """Onset rate giving steady-state unavailability p for a 2-state up<->down
    CTMC with recovery rate mu:  p = lambda / (lambda + mu)."""
    return p * mu / (1.0 - p)

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


# --- fig4 extension: V3 (dual-FATO) pad-closure recovery at a single mu ---
# Only the NEW V3 curve is (re)computed here; the V1 curves already live in
# fig4_recovery_throughput.csv and are not regenerated.  One representative
# repair rate (mu = 0.1, "typical closure") is enough to show that the second
# FATO buys resilience.
#
# Unlike V1 (whose single closed pad is a full stop: with the only pad shut,
# nothing lands or departs, so the closed vertiport just sits in its cold
# start s0 with zero throughput), V3 keeps the OTHER FATO running while FATO1
# is closed, so the closed vertiport settles into a *degraded operating
# equilibrium* (single-FATO throughput) rather than 0.  The recovery transient
# must therefore start from that degraded equilibrium, not from the empty
# cold-start state, or the curve would spuriously begin at 0 and imply that
# BOTH pads are down.  We build the degraded stationary distribution on the
# recovery model's own state space (drop the pad1_repair edges, identified via
# the pad1_closed label, and take the resulting closed class's stationary
# distribution) and evolve it under the full recovery generator by
# uniformisation (scipy expm_multiply).
RECOVERY_MODEL_V3 = "Vertiport_V3_Recovery_PadClosed_SBrs.big"
RECOVERY_V3_REPAIR_RATE = 0.1
RECOVERY_V3_CLOSED_LABEL = "pad1_closed"


def _parse_tra_edges(tra):
    """Return (n_states, [(src, dst, rate), ...]) from a PRISM .tra file."""
    with open(tra) as f:
        header = f.readline().split()
        n_states = int(header[0])
        edges = []
        for line in f:
            if line.strip():
                s, d, r = line.split()
                edges.append((int(s), int(d), float(r)))
    return n_states, edges


def _parse_label_states(csl, label):
    """State indices satisfying `label` in a PRISM labels (.csl) file."""
    import re
    text = open(csl).read()
    m = re.search(r'label "%s" =([^\n]*)' % re.escape(label), text)
    if not m:
        return set()
    return {int(x) for x in re.findall(r"x = (\d+)", m.group(1))}


def _parse_state_rewards(rews, n_states):
    import numpy as np
    rew = np.zeros(n_states)
    with open(rews) as f:
        f.readline()  # header: "<n_states> <n_reward_entries>"
        for line in f:
            if line.strip():
                st, rv = line.split()
                rew[int(st)] = float(rv)
    return rew


def _degraded_init_distribution(n_states, edges, closed):
    """Stationary distribution of the closed-pad (degraded) sub-chain.

    Drops the closure-repair edges (closed -> open) so the closed states form
    a terminal class, then solves pi Q = 0 on the states reachable from s0.
    Returns a length-n_states probability vector (0 on open/unreachable
    states).  This is the "operating on one FATO in equilibrium" condition.
    """
    import numpy as np
    from collections import deque
    degraded = [(s, d, r) for (s, d, r) in edges
                if not (s in closed and d not in closed)]
    adj = {}
    for s, d, _ in degraded:
        adj.setdefault(s, []).append(d)
    reach = {0}
    q = deque([0])
    while q:
        u = q.popleft()
        for v in adj.get(u, ()):
            if v not in reach:
                reach.add(v)
                q.append(v)
    reach = sorted(reach)
    idx = {s: i for i, s in enumerate(reach)}
    m = len(reach)
    Q = np.zeros((m, m))
    for s, d, r in degraded:
        if s in idx and d in idx:
            Q[idx[s], idx[d]] += r
            Q[idx[s], idx[s]] -= r
    # pi Q = 0, sum pi = 1  ->  replace one balance eq. with normalisation.
    A = Q.T.copy()
    b = np.zeros(m)
    A[0, :] = 1.0
    b[0] = 1.0
    pi, *_ = np.linalg.lstsq(A, b, rcond=None)
    pi = np.clip(pi, 0.0, None)
    pi /= pi.sum()
    full = np.zeros(n_states)
    for i, s in enumerate(reach):
        full[s] = pi[i]
    return full


def run_pad_recovery_v3(n=6):
    import numpy as np
    import scipy.sparse as sp
    from scipy.sparse.linalg import expm_multiply

    rr = RECOVERY_V3_REPAIR_RATE
    print(f"[recovery-v3] V3 dual-FATO pad-closed recovery (N={n}, mu={rr}, "
          f"fig4) ...")
    tag = f"V3_recovery_padclosed_N{n}_rr{rr}"
    g = generate(RECOVERY_MODEL_V3, f"n={n},repair_rate={rr}", tag)
    if not g:
        return
    tra, csl, rews, states = g

    n_states, edges = _parse_tra_edges(tra)
    closed = _parse_label_states(csl, RECOVERY_V3_CLOSED_LABEL)
    rew = _parse_state_rewards(rews, n_states)
    p0 = _degraded_init_distribution(n_states, edges, closed)
    floor = float(p0 @ rew) * 60.0
    print(f"   V3 states={states}, closed(degraded) states={len(closed)}, "
          f"single-FATO degraded floor={floor:.2f} oph")

    # Full recovery generator Q (all edges, incl. pad1_repair).
    r_idx, c_idx, vals = [], [], []
    diag = np.zeros(n_states)
    for s, d, r in edges:
        r_idx.append(s)
        c_idx.append(d)
        vals.append(r)
        diag[s] -= r
    for i in range(n_states):
        r_idx.append(i)
        c_idx.append(i)
        vals.append(diag[i])
    Q = sp.csr_matrix((vals, (r_idx, c_idx)), shape=(n_states, n_states))

    # Evolve the degraded distribution under Q by uniformisation:
    #   p(t) = exp(Q^T t) p0 ;  instantaneous throughput = 60 * p(t) . reward.
    t_values = recovery_time_grid()
    seq = expm_multiply(Q.T, p0, start=0, stop=RECOVERY_T_MAX,
                        num=len(t_values), endpoint=True)
    rows = []
    for t, pt in zip(t_values, seq):
        instant = float(pt @ rew)
        throughput = 60 * instant
        rows.append([rr, t, round(instant, 6), round(throughput, 3), n])
        if t in (0, REF_TIME_MIN, RECOVERY_T_MAX):
            print(f"      t={t}: throughput={throughput:.2f} oph")
    write_csv(
        "fig4_recovery_v3.csv",
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

    # Panels a/b/c share one severity axis: steady-state unavailability P.  The
    # onset rate lambda is back-computed from P and the panel's own repair rate
    # mu (P = lambda / (lambda + mu)).  P=0 is the nominal baseline itself (no
    # model run; BigraphER would reject an exact 0.0 rate anyway).
    for panel in ("pad", "stand", "weather"):
        rate_key = RESILIENCE_RATE_KEY[panel]
        repair = RESILIENCE_REPAIR[panel]
        mfile = RESILIENCE_MODELS[panel]
        mu = next(iter(repair.values()))    # this panel's recovery rate
        rows.append([panel, "baseline", "", round(nominal_throughput, 3),
                     "baseline", ""])
        # P=0 curve point == nominal, so each curve starts at the nominal line.
        rows.append([panel, "unavailability", 0.0, round(nominal_throughput, 3),
                     "degraded", 0.0])
        for p in UNAVAIL_GRID:
            lam = lambda_from_unavailability(p, mu)
            consts = ",".join(
                [f"n_evtol={n}", f"{rate_key}={lam}"]
                + [f"{k}={v}" for k, v in repair.items()]
            )
            tag = f"V1_res_{panel}_N{n}_p{p}"
            g = generate(mfile, consts, tag)
            if not g:
                continue
            tra, csl, rews, states = g
            throughput = 60 * first_result(tra, csl, rews, 'R=? [ S ]')
            rows.append([panel, "unavailability", p, round(throughput, 3),
                         "degraded", round(lam, 6)])
            print(f"   {panel} P={p} ({rate_key}={lam:.6f}): "
                  f"states={states} throughput={throughput:.2f}")

    rows.append(["turnaround", "baseline", "", round(nominal_throughput, 3),
                 "baseline", ""])
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
        rows.append(["turnaround", "minutes", minutes, round(throughput, 3),
                     curve, ""])
        print(f"   turnaround {minutes} min: states={states} throughput={throughput:.2f}")

    write_csv("fig3_sensitivity_oph.csv",
              ["panel", "param_name", "param_value", "throughput", "curve",
               "lambda_rate"],
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
COMPOUND_STAND_REPAIR_RATE = 0.05    # stand mean repair 20 min


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
# Weather severity axis: steady-state bad-weather fraction P(bad) on the shared
# UNAVAIL_GRID {0, 5, 10, 15, 20, 30}%.  The stored onset rate is back-computed
# from P (lambda = P*mu/(1-P)); the plot recovers P = lambda/(lambda+mu) for the
# tick labels.  EPS ~ "always clear" (BigraphER rejects an exact 0.0 rate);
# 1e-4 recovers P ~ 0.2%, which rounds to the 0% tick.
COMPOUNDSW_WEATHER_REPAIR = 0.05    # mean bad-weather spell 20 min
COMPOUNDSW_EPS_LAMBDA = 1e-4        # P~0 stand-in
COMPOUNDSW_WEATHER_FF = [COMPOUNDSW_EPS_LAMBDA] + [
    lambda_from_unavailability(p, COMPOUNDSW_WEATHER_REPAIR) for p in UNAVAIL_GRID
]

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


# --- fig5 extension: V2 (extra stand) compound recovery -------------------
# V2 rerun ONLY at the same compound scenarios as V1's fig5 overlay
# (pad closed + 1 stand out, pad closed + 2 stands out).  The V1 curves are
# already in fig5_compound_recovery.csv and are not regenerated.  Shows that
# the "stands before pads" ordering also holds for resilience: the extra
# stand keeps the recovering throughput floor higher under compound failure.
COMPOUND_RECOVERY_MODELS_V2 = {
    1: "Vertiport_V2_Recovery_Compound_k1_SBrs.big",   # pad closed + 1 stand out
    2: "Vertiport_V2_Recovery_Compound_k2_SBrs.big",   # pad closed + 2 stands out
}


def run_compound_recovery_v2(n=6):
    """fig5 (V2 overlay) — V2 throughput recovery, pad-closed + k stands out."""
    print(f"[compound-recovery-v2] V2 pad-closed + k stands out, R=?[I=t] "
          f"(N={n}, fig5) ...")
    rows = []
    t_values = recovery_time_grid()
    for k in (1, 2):
        model = COMPOUND_RECOVERY_MODELS_V2[k]
        gen_consts = (f"n_evtol={n},repair_rate={COMPOUND_REPAIR_RATE},"
                      f"stand_repair_rate={COMPOUND_STAND_REPAIR_RATE}")
        g = generate(model, gen_consts, f"V2_comprec_k{k}_N{n}")
        if not g:
            continue
        tra, csl, rews, states = g
        print(f"   V2 k={k}: states={states}")
        for t in t_values:
            instant = first_result(tra, csl, rews, 'R=? [ I=t ]', consts=f"t={t}")
            throughput = 60 * instant
            rows.append([k, t, round(instant, 6), round(throughput, 3), n])
            if t in (0, REF_TIME_MIN, RECOVERY_T_MAX):
                print(f"      t={t}: throughput={throughput:.2f} oph")
    write_csv("fig5_compound_recovery_v2.csv",
              ["k_out", "t_min", "instant_rate", "throughput_oph", "n_evtol"],
              rows)


# --- fig6 extension: V2 (extra stand) compound capacity -------------------
# V2 weather x stands-out capacity envelope, computed for the same axes as
# V1's fig6 (stands_out 0..3 x weather severity).  The V1 rows are already in
# fig6_compound_capacity.csv and are not regenerated.  Shows V2's higher
# capacity floor: with 4 stands, k stands out leaves one more working stand
# than V1, so the worst-case (bad weather + stands out) stays above demand
# where V1 has already dropped below it.
COMPOUNDSW_CAP_MODELS_V2 = {
    0: "Vertiport_V2_Sensitivity_Weather_SBrs.big",   # 0 stands out (weather only)
    1: "Vertiport_V2_Weather_StandOut_k1_SBrs.big",   # 1 stand out of service
    2: "Vertiport_V2_Weather_StandOut_k2_SBrs.big",   # 2 stands out of service
    3: "Vertiport_V2_Weather_StandOut_k3_SBrs.big",   # 3 stands out (1 stand left)
}


def run_compound_standweather_v2(n=6):
    """fig6 (V2 overlay) — V2 sustained capacity: weather severity x stands out."""
    print(f"[compound-SW-v2] V2 stand-outage cost under weather (N={n}, fig6) ...")
    cap_rows = []
    for k in (0, 1, 2, 3):
        model = COMPOUNDSW_CAP_MODELS_V2[k]
        for wff in COMPOUNDSW_WEATHER_FF:
            consts = (f"n_evtol={n},weather_fault_rate={wff},"
                      f"weather_repair_rate={COMPOUNDSW_WEATHER_REPAIR}")
            g = generate(model, consts, f"V2_swcap_k{k}_wff{wff}_N{n}")
            if not g:
                continue
            tra, csl, rews, states = g
            thr = 60 * first_result(tra, csl, rews, 'R=? [ S ]')
            cap_rows.append([k, wff, round(thr, 3), n])
            print(f"   V2 k={k} weather_ff={wff}: states={states} throughput={thr:.2f}")
    write_csv("fig6_compound_capacity_v2.csv",
              ["stands_out", "weather_fault_rate", "throughput_oph", "n_evtol"],
              cap_rows)


# ---------------------------------------------------------------------
# 9. Recovery probability (fig4b/fig5b): CSL time-bounded reachability
# ---------------------------------------------------------------------
RECOVERY_PROB_TARGET = 2               # app <= 2 (90% nominal operating envelope)
RECOVERY_PROB_MU = [0.05, 0.1, 0.2, 0.5]


def _recovery_reach_prob(tra, csl, not_labels, target=RECOVERY_PROB_TARGET):
    """P[F<=t (no not_label holds and approach queue <= target)] from the fault
    state, with the target set made absorbing.  Returns [(t, prob), ...]."""
    import numpy as np
    import scipy.sparse as sp
    from scipy.sparse.linalg import expm_multiply
    n_states, edges = _parse_tra_edges(tra)
    forbidden = set().union(*(_parse_label_states(csl, l) for l in not_labels))
    drained = set().union(*(_parse_label_states(csl, f"app_at_{a}")
                            for a in range(target + 1)))
    target_states = sorted(s for s in range(n_states)
                           if s not in forbidden and s in drained)
    absorbing = set(target_states)
    r_idx, c_idx, vals = [], [], []
    diag = np.zeros(n_states)
    for s, d, r in edges:
        if s in absorbing:                 # make the target set absorbing
            continue
        r_idx.append(s); c_idx.append(d); vals.append(r); diag[s] -= r
    for i in range(n_states):
        r_idx.append(i); c_idx.append(i); vals.append(diag[i])
    Q = sp.csr_matrix((vals, (r_idx, c_idx)), shape=(n_states, n_states))
    p0 = np.zeros(n_states); p0[0] = 1.0
    grid = recovery_time_grid()
    seq = expm_multiply(Q.T, p0, start=0, stop=grid[-1], num=len(grid),
                        endpoint=True)
    idx = np.array(target_states)
    return [(t, float(pt[idx].sum())) for t, pt in zip(grid, seq)]


def run_recovery_prob(n=6):
    """fig4b/fig5b - V1 CSL recovery-probability curves.

    fig4b: P[F<=t recovered] across the pad-closure severity sweep.
    fig5b: P[F<=t restored] across concurrent stand outages k = 0, 1, 2.
    'recovered' is the pad reopened with the approach queue drained to at most
    RECOVERY_PROB_TARGET aircraft (the 90% nominal envelope); 'restored' also
    requires the failed stands back in service.  Threshold robustness (app<=1,3)
    is a one-line change to RECOVERY_PROB_TARGET.
    """
    print(f"[recovery-prob] V1 recovery/restoration probability "
          f"(N={n}, fig4b/fig5b) ...")
    rows4 = []
    for mu in RECOVERY_PROB_MU:
        g = generate(RECOVERY_MODEL, f"n_evtol={n},repair_rate={mu}",
                     f"recprob_pad_N{n}_mu{mu}")
        if not g:
            continue
        tra, csl, _, _ = g
        curve = _recovery_reach_prob(tra, csl, ["pad_closed"])
        rows4 += [[mu, t, round(p, 5)] for t, p in curve]
        print(f"   mu={mu}: P(recovered@{REF_TIME_MIN})={dict(curve)[REF_TIME_MIN]:.3f}")
    write_csv("fig4b_recovery_prob.csv",
              ["repair_rate", "t_min", "p_recovered"], rows4)

    rows5 = []
    for k in (0, 1, 2):
        consts = f"n_evtol={n},repair_rate={COMPOUND_REPAIR_RATE}"
        not_labels = ["pad_closed"]
        if k > 0:
            consts += f",stand_repair_rate={COMPOUND_STAND_REPAIR_RATE}"
            not_labels = ["pad_closed", "stand_out"]
        g = generate(COMPOUND_RECOVERY_MODELS[k], consts, f"recprob_cmp_k{k}_N{n}")
        if not g:
            continue
        tra, csl, _, _ = g
        curve = _recovery_reach_prob(tra, csl, not_labels)
        rows5 += [[k, t, round(p, 5)] for t, p in curve]
        print(f"   k={k}: P(restored@{REF_TIME_MIN})={dict(curve)[REF_TIME_MIN]:.3f}")
    write_csv("fig5b_restoration_prob.csv",
              ["k_out", "t_min", "p_restored"], rows5)


# ---------------------------------------------------------------------
# Resilience contract envelope: retained service + contract
# ---------------------------------------------------------------------
# For the headline compound disruption (pad closed + 2 stands out) this
# reports, over a deadline grid t, the first-passage probability of full
# recovery p*(t) (the feasibility gate) and the retained-service ratio
#     rho(t) = C_d(t) / ((T_nom/60) * t),
# where C_d(t) = E[cumulative take-offs in [0,t]] from R{takeoffs}=?[C<=t].
# The recovered state is structurally durable here, so stable recovery
# coincides with first-passage; the layout comparison therefore lives on
# the retained-service axis, where the extra stand of V2 delivers more
# service through the recovery.
ENVELOPE_K = 2
ENVELOPE_MODELS = {
    "V1": COMPOUND_RECOVERY_MODELS[ENVELOPE_K],
    "V2": COMPOUND_RECOVERY_MODELS_V2[ENVELOPE_K],
}
ENVELOPE_TNOM = {"V1": 15.447, "V2": 18.19}     # N=6 saturated nominal (fig1)
ENVELOPE_REC = ('((!"pad_closed") & ("app_at_0"|"app_at_1"|"app_at_2") '
                '& !"stand_out")')


def run_resilience_envelope(n=6):
    print(f"[envelope] Resilience contract envelope (compound k={ENVELOPE_K}, "
          f"N={n}, fig_envelope) ...")
    rows = []
    ts = [t for t in recovery_time_grid() if t > 0]
    for layout, model in ENVELOPE_MODELS.items():
        g = generate(model, f"n_evtol={n},repair_rate={COMPOUND_REPAIR_RATE},"
                            f"stand_repair_rate={COMPOUND_STAND_REPAIR_RATE}",
                     f"envelope_{layout}_k{ENVELOPE_K}")
        if not g:
            continue
        tra, csl, rews, ns = g
        tnom = ENVELOPE_TNOM[layout]
        for t in ts:
            pstar = first_result(tra, csl, rews,
                                 f"P=? [ F<=t {ENVELOPE_REC} ]", consts=f"t={t}")
            cd = first_result(tra, csl, rews, "R=? [ C<=t ]", consts=f"t={t}")
            rho = cd / ((tnom / 60.0) * t)
            rows.append([layout, ENVELOPE_K, t, round(pstar, 4),
                         round(cd, 3), round(rho, 4)])
        r30 = next(r for r in rows if r[0] == layout and r[2] == 30)
        print(f"   {layout}: states={ns}  p*(30)={r30[3]}  rho(30)={r30[5]}")
    write_csv("fig_envelope.csv",
              ["layout", "k_out", "t_min", "p_star", "C_d", "rho"], rows)


# =====================================================================
# Long-run service-level (SLA) resilience under RECURRENT disruption.
# A healthy repairable model injects and repairs pad + stand faults; the
# service contract op(d) = "the current configuration can sustain >= d
# fph" is read off the fig6 capacity ladder (demand d -> max tolerable
# stand outages).  fig_sla_resilience: (a) survival P=?[G<=t op(d)] (the
# advisor's F[t,t_end]!op, complemented) and (b) demand-horizon envelope.
# =====================================================================
AVAILABILITY_MODELS = {
    "V1": "Vertiport_V1_Availability_SBrs.big",
    "V2": "Vertiport_V2_Availability_SBrs.big",
}
AVAIL_M_STAND = {"V1": 3, "V2": 4}
AVAIL_LADDER_CSV = {"V1": "fig6_compound_capacity.csv",
                    "V2": "fig6_compound_capacity_v2.csv"}
# Fault severity is parameterised by steady-state unavailability P (as in the
# sensitivity sweep, Fig.~fig3): a 2-state up<->down channel with recovery
# rate mu reaches unavailability P at onset rate lambda = P*mu/(1-P).  Repair
# times match the rest of the paper (pad 10 min, stand 20 min).  The pad is
# more reliable than a stand, so the two channels sit at different points of
# the Fig.~fig3 range: pad 1% and per-stand 3% steady-state unavailability.
AVAIL_PAD_UNAVAIL   = 0.01       # pad steady-state unavailability
AVAIL_STAND_UNAVAIL = 0.03       # per-stand steady-state unavailability
AVAIL_PAD_REPAIR    = 0.1        # pad mean repair 10 min
AVAIL_STAND_REPAIR  = 0.05       # stand mean repair 20 min (matches fig3/fig5)
AVAIL_PAD_FAIL      = lambda_from_unavailability(AVAIL_PAD_UNAVAIL, AVAIL_PAD_REPAIR)
AVAIL_STAND_FAIL    = lambda_from_unavailability(AVAIL_STAND_UNAVAIL, AVAIL_STAND_REPAIR)
AVAIL_DEMANDS_REPR  = [10, 15]           # nominal target and near-capacity (Panel a)
AVAIL_CONF          = 0.9                # confidence for the horizon t*
AVAIL_DEMAND_LO, AVAIL_DEMAND_HI, AVAIL_DEMAND_STEP = 4.0, 15.0, 0.5
AVAIL_T_MAX, AVAIL_T_STEP = 720, 30      # horizon spans an operating day (min)


def capacity_ladder(csv_name, m_stand):
    """cap[k] = sustainable throughput (fph) with k stands out, pad open.

    Read from the fig6 compound-capacity CSV at its lowest weather rate
    (~no weather, matching the weather-free availability model)."""
    best = {}
    with open(os.path.join(ANALYSIS_DIR, csv_name)) as f:
        for r in csv.DictReader(f):
            k = int(r["stands_out"])
            wr = float(r["weather_fault_rate"])
            thr = float(r["throughput_oph"])
            if k not in best or wr < best[k][0]:
                best[k] = (wr, thr)
    ladder = [best[k][1] for k in sorted(best)]
    while len(ladder) <= m_stand:          # all stands out -> zero capacity
        ladder.append(0.0)
    return ladder[:m_stand + 1]


def demand_threshold(ladder, d):
    """Max number of stands out at which capacity still meets demand d
    (-1 if demand is infeasible even when healthy)."""
    thr = -1
    for k, cap in enumerate(ladder):
        if cap >= d:
            thr = k
    return thr


def op_label(k, m_stand):
    """CSL predicate for op = pad open AND at most k stands out."""
    if k + 1 > m_stand:
        return '(!"pad_closed")'
    return f'(!"pad_closed") & (!"out_at_least_{k + 1}")'


def horizon_at_confidence(curve, p):
    """Largest t with survival P[G<=t op] >= p (linear interpolation)."""
    prev_t, prev_p = curve[0]
    if prev_p < p:
        return 0.0
    for t, pr in curve[1:]:
        if pr < p:
            if prev_p == pr:
                return prev_t
            frac = (prev_p - p) / (prev_p - pr)
            return prev_t + frac * (t - prev_t)
        prev_t, prev_p = t, pr
    return curve[-1][0]


def mean_time_to_breach(curve):
    """MTTB = integral of the survival curve + an exponential tail beyond
    the grid (dominant mode from the last two points)."""
    area = 0.0
    for i in range(1, len(curve)):
        area += 0.5 * (curve[i - 1][1] + curve[i][1]) * (curve[i][0] - curve[i - 1][0])
    (t1, p1), (t2, p2) = curve[-2], curve[-1]
    if p2 > 1e-6 and p1 > p2 > 0:
        tau = (t2 - t1) / math.log(p1 / p2)
        area += p2 * tau
    return area


def run_availability(n=6):
    print(f"[availability] Long-run SLA resilience under recurrent pad+stand "
          f"faults (N={n}, fig_sla_resilience) ...")
    consts = (f"n_evtol={n},pad_fail_rate={AVAIL_PAD_FAIL},"
              f"pad_repair_rate={AVAIL_PAD_REPAIR},"
              f"stand_fail_rate={AVAIL_STAND_FAIL},"
              f"stand_repair_rate={AVAIL_STAND_REPAIR}")
    # Rare, realistic faults act over hours, so the horizon spans an operating
    # day rather than the minute-scale recovery grid.
    ts = list(range(0, AVAIL_T_MAX + 1, AVAIL_T_STEP))
    demands_grid = []
    d = AVAIL_DEMAND_LO
    while d <= AVAIL_DEMAND_HI + 1e-9:
        demands_grid.append(round(d, 2))
        d += AVAIL_DEMAND_STEP

    survival_rows, envelope_rows = [], []
    for layout, model in AVAILABILITY_MODELS.items():
        m = AVAIL_M_STAND[layout]
        ladder = capacity_ladder(AVAIL_LADDER_CSV[layout], m)
        g = generate(model, consts, f"availability_{layout}_N{n}")
        if not g:
            continue
        tra, csl, rews, ns = g

        # steady-state throughput (single scalar) and per-threshold survival
        thr_ss = 60.0 * first_result(tra, csl, rews, "R=? [ S ]")
        survival = {}   # k -> [(t, P[G<=t op_k])]
        for k in range(m):
            survival[k] = []
        for t in ts:
            qs = [f"P=? [ G<=t {op_label(k, m)} ]" for k in range(m)]
            vals = prism(tra, csl, rews, qs, consts=f"t={t}")
            for k in range(m):
                survival[k].append((t, vals[k] if k < len(vals) else 0.0))
        steady = {}     # k -> S=?[op_k]
        svals = prism(tra, csl, rews,
                      [f"S=? [ {op_label(k, m)} ]" for k in range(m)])
        for k in range(m):
            steady[k] = svals[k] if k < len(svals) else 0.0

        print(f"   {layout}: states={ns}  steady throughput={thr_ss:.2f} fph  "
              f"ladder={[round(c, 1) for c in ladder]}")

        # Panel (a): survival at the representative demands
        for dd in AVAIL_DEMANDS_REPR:
            k = demand_threshold(ladder, dd)
            for (t, pr) in (survival[k] if k >= 0 else [(t, 0.0) for t in ts]):
                survival_rows.append([layout, dd, k, t, round(pr, 4)])

        # Panel (b): demand-horizon envelope over the fine demand grid
        for dd in demands_grid:
            k = demand_threshold(ladder, dd)
            if k >= 0:
                tstar = horizon_at_confidence(survival[k], AVAIL_CONF)
                savail = steady[k]
                mttb = mean_time_to_breach(survival[k])
            else:
                tstar, savail, mttb = 0.0, 0.0, 0.0
            envelope_rows.append([layout, dd, k, round(tstar, 2),
                                  round(savail, 4), round(mttb, 2),
                                  round(thr_ss, 2)])
        d10 = demand_threshold(ladder, 10)
        print(f"     d=10 -> tolerate <= {d10} stands out, "
              f"S_avail={steady.get(d10, 0):.3f}, "
              f"MTTB={mean_time_to_breach(survival[d10]):.1f} min"
              if d10 >= 0 else f"     d=10 infeasible")

    write_csv("fig_sla_survival.csv",
              ["layout", "demand", "threshold", "t_min", "P_hold"],
              survival_rows)
    write_csv("fig_sla_envelope.csv",
              ["layout", "demand", "threshold", "t_star", "S_avail",
               "mttb", "throughput_ss"], envelope_rows)


MODULES = {
    "capacity": run_capacity,
    "open": run_open,
    "resilience": lambda: run_resilience_depth(n=6),
    "recovery": lambda: run_pad_recovery(n=6),
    "recovery_v3": lambda: run_pad_recovery_v3(n=6),
    "compound_recovery": lambda: run_compound_recovery(n=6),
    "compound_recovery_v2": lambda: run_compound_recovery_v2(n=6),
    "recovery_prob": lambda: run_recovery_prob(n=6),
    "compound_sw": lambda: run_compound_standweather(n=6),
    "compound_sw_v2": lambda: run_compound_standweather_v2(n=6),
    "envelope": lambda: run_resilience_envelope(n=6),
    "availability": lambda: run_availability(n=6),
}


def main():
    order = ["capacity", "open", "resilience", "recovery", "recovery_v3",
             "compound_recovery", "compound_recovery_v2", "recovery_prob",
             "compound_sw", "compound_sw_v2", "envelope", "availability"]
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

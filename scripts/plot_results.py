#!/usr/bin/env python3
"""
Produce paper figures from the CSVs in analysis/.

Figures (figures/):
  fig1_oph_vs_n.png          Saturated capacity, pad/stand util, P(all stands busy) vs N
  fig2_open_v1_v2.png        Open V1/V2: throughput, mean number/time in vertiport vs lambda
  fig3_resilience_depth.png  V1 steady-state fault / turnaround sensitivity (N=6)
  fig4_pad_recovery.png      Pad-closed recovery: capacity loss + throughput (N=6)
  fig5_compound_recovery.png Compound-fault recovery erosion: pad + 0/1/2 stands (N=6)
  fig6_standweather_compound.png  Stand × weather compound capacity: line chart + heat-map (N=6)

Run (after run_analysis.py):  python3 scripts/plot_results.py
"""

import csv
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ANALYSIS = os.path.join(ROOT, "analysis")
FIGURES = os.path.join(ROOT, "figures")
os.makedirs(FIGURES, exist_ok=True)

SAVE_DPI = 300
THROUGHPUT_LABEL = "Throughput (flights/hour)"
CAPACITY_FLEET_NS = [4, 5, 6, 7, 8]
RESILIENCE_FLEET_N = 6
RECOVERY_FLEET_N = 6

# Paul Tol bright — colourblind-safe, common in Nature/Science-style figures.
COLOURS = {"V1": "#4477AA", "V2": "#EE6677", "V3": "#228833"}
MARKERS = {"V1": "o", "V2": "s", "V3": "D"}
FAULT_COLOURS = {
    "pad": "#4477AA", "stand": "#EE6677", "weather": "#228833",
    "turnaround": "#CCBB44",
}
FAULT_MARKERS = {"pad": "o", "stand": "s", "weather": "D", "turnaround": "s"}
RECOVERY_COLOURS = ["#4477AA", "#EE6677", "#228833", "#CCBB44"]
REF_TIME_MIN = 30
THROUGHPUT_REF_OPH = 10.0


def read_csv(name):
    with open(os.path.join(ANALYSIS, name)) as f:
        return list(csv.DictReader(f))


def apply_nature_style():
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
        "mathtext.fontset": "dejavusans",
        "font.size": 8,
        "axes.labelsize": 8,
        "axes.titlesize": 9,
        "xtick.labelsize": 7,
        "ytick.labelsize": 7,
        "legend.fontsize": 7,
        "legend.frameon": False,
        "axes.grid": True,
        "grid.color": "#CCCCCC",
        "grid.linestyle": "-",
        "grid.linewidth": 0.4,
        "grid.alpha": 0.55,
        "axes.linewidth": 0.6,
        "axes.edgecolor": "black",
        "axes.facecolor": "white",
        "figure.facecolor": "white",
        "xtick.major.width": 0.6,
        "ytick.major.width": 0.6,
        "xtick.major.size": 3.5,
        "ytick.major.size": 3.5,
        "xtick.direction": "out",
        "ytick.direction": "out",
        "lines.linewidth": 1.25,
        "lines.markersize": 4.5,
        "savefig.dpi": SAVE_DPI,
        "savefig.bbox": "tight",
        "savefig.facecolor": "white",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })


def adaptive_ylim(values):
    lo, hi = min(values), max(values)
    if hi == lo:
        margin = max(abs(hi) * 0.1, 0.5)
    else:
        margin = (hi - lo) * 0.12
    return lo - margin, hi + margin


def style_axis(ax, y_values, x_ticks=None, x_lim=None):
    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_color("black")
        spine.set_linewidth(0.6)
    ax.tick_params(top=False, right=False, which="both")
    if x_ticks is not None:
        ax.set_xticks(x_ticks)
    if x_lim is not None:
        ax.set_xlim(*x_lim)
    ax.set_ylim(*adaptive_ylim(y_values))
    ax.set_box_aspect(1)
    ax.grid(True, which="major", axis="both", zorder=0)
    ax.set_axisbelow(True)


def plot_trace(ax, xs, ys, colour, marker, label, linestyle="-", fill=True):
    markerfacecolor = colour if fill else "white"
    ax.plot(
        xs, ys,
        marker=marker,
        linestyle=linestyle,
        color=colour,
        label=label,
        markerfacecolor=markerfacecolor,
        markeredgecolor=colour if not fill else "white",
        markeredgewidth=0.5,
        clip_on=False,
        zorder=3,
    )


def add_legend(ax, title=None):
    ax.legend(
        title=title,
        loc="best",
        handlelength=1.6,
        handletextpad=0.5,
        borderaxespad=0.4,
    )


def save_figure(fig, name):
    out = os.path.join(FIGURES, name)
    fig.savefig(out)
    plt.close(fig)
    print("  wrote", out)


def capacity_points(rows, model, field):
    pts = [
        (int(r["N"]), float(r[field]))
        for r in rows
        if r["model"] == model and int(r["N"]) in CAPACITY_FLEET_NS
    ]
    pts.sort()
    return pts


def is_estimated(row):
    return row.get("estimated", "false").lower() == "true"


def open_points(rows, model, field):
    pts = [(float(r["lambda"]), float(r[field])) for r in rows if r["model"] == model]
    pts.sort()
    return pts


def plot_capacity_panel(ax, rows, field, ylabel, xlabel, show_legend=False):
    all_y = []
    for model in ("V1", "V2"):
        pts = capacity_points(rows, model, field)
        xs, ys = zip(*pts)
        all_y.extend(ys)
        plot_trace(ax, xs, ys, COLOURS[model], MARKERS[model], model)

    v3_rows = sorted(
        [r for r in rows
         if r["model"] == "V3" and int(r["N"]) in CAPACITY_FLEET_NS],
        key=lambda r: int(r["N"]),
    )
    actual = [(int(r["N"]), float(r[field])) for r in v3_rows if not is_estimated(r)]
    predicted = [(int(r["N"]), float(r[field])) for r in v3_rows if is_estimated(r)]
    if actual:
        xs, ys = zip(*actual)
        all_y.extend(ys)
        plot_trace(ax, xs, ys, COLOURS["V3"], MARKERS["V3"], "V3")
    if actual and predicted:
        ax.plot(
            [actual[-1][0], predicted[0][0]],
            [actual[-1][1], predicted[0][1]],
            linestyle="--", color=COLOURS["V3"], linewidth=1.25, zorder=2,
        )
    if predicted:
        xs, ys = zip(*predicted)
        all_y.extend(ys)
        plot_trace(
            ax, xs, ys, COLOURS["V3"], MARKERS["V3"],
            "V3 estimated", linestyle="--", fill=False,
        )

    style_axis(ax, all_y, x_ticks=CAPACITY_FLEET_NS, x_lim=(3.7, 8.3))
    ax.set_ylabel(ylabel)
    ax.set_xlabel(xlabel)
    if show_legend:
        add_legend(ax, title="Layout")


def plot_open_panel(ax, rows, field, ylabel, xlabel, x_ticks, x_lim,
                    show_legend=False):
    all_y = []
    for model in ("V1", "V2", "V3"):
        pts = open_points(rows, model, field)
        if not pts:
            continue
        xs, ys = zip(*pts)
        all_y.extend(ys)
        plot_trace(ax, xs, ys, COLOURS[model], MARKERS[model], model)
    style_axis(ax, all_y, x_ticks=x_ticks, x_lim=x_lim)
    ax.set_ylabel(ylabel)
    ax.set_xlabel(xlabel)
    if show_legend:
        add_legend(ax, title="Layout")


# ---------------------------------------------------------------------
def fig1_oph_vs_n():
    apply_nature_style()
    rows = read_csv("fig1_capacity_oph.csv")
    xlabel = "Operating aircraft $N$"
    fig, axes = plt.subplots(1, 4, figsize=(9.6, 2.55))
    plot_capacity_panel(
        axes[0], rows, "throughput", THROUGHPUT_LABEL, xlabel, show_legend=True,
    )
    plot_capacity_panel(
        axes[1], rows, "pad_utilisation", "Pad utilisation", xlabel,
    )
    plot_capacity_panel(
        axes[2], rows, "stand_utilisation", "Stand utilisation", xlabel,
    )
    plot_capacity_panel(
        axes[3], rows, "all_stands_busy_prob",
        r"$P(\mathrm{all\ stands\ busy})$", xlabel,
    )
    fig.subplots_adjust(wspace=0.42)
    save_figure(fig, "fig1_oph_vs_n.png")


def fig2_open_v1_v2():
    apply_nature_style()
    rows = read_csv("fig2_open_v1_v2.csv")
    lambdas = sorted({float(r["lambda"]) for r in rows})
    xlabel = r"Arrival rate $\lambda$ (min$^{-1}$)"
    span = max(lambdas) - min(lambdas)
    margin = 0.12 * span if span else 0.05
    x_lim = (min(lambdas) - margin, max(lambdas) + margin)
    fig, axes = plt.subplots(1, 3, figsize=(7.2, 2.55))
    panels = [
        ("throughput", THROUGHPUT_LABEL, True),
        ("mean_in_vertiport", "Mean number in vertiport (aircraft)", False),
        ("mean_delay_vertiport", "Mean time in vertiport (min)", False),
    ]
    for ax, (field, ylabel, show_legend) in zip(axes, panels):
        plot_open_panel(
            ax, rows, field, ylabel, xlabel, lambdas, x_lim,
            show_legend=show_legend,
        )
    fig.subplots_adjust(wspace=0.42)
    save_figure(fig, "fig2_open_v1_v2.png")


def plot_resilience_panel(ax, rows, panel, xlabel, title, x_ticks, x_lim,
                          colour, show_legend=False):
    panel_rows = [r for r in rows if r["panel"] == panel]
    baseline = [float(r["throughput"]) for r in panel_rows if r["curve"] == "baseline"]
    baseline_throughput = baseline[0] if baseline else 0.0
    degraded = [
        (float(r["param_value"]), float(r["throughput"]))
        for r in panel_rows if r["curve"] == "degraded"
    ]
    degraded.sort()
    all_y = [baseline_throughput]
    if degraded:
        xs, ys = zip(*degraded)
        all_y.extend(ys)
        plot_trace(ax, xs, ys, colour, FAULT_MARKERS[panel], "With disruption")
    ax.axhline(
        baseline_throughput, color="#BBBBBB", linestyle="--", linewidth=1.0,
        label="Nominal", zorder=2,
    )
    style_axis(ax, all_y, x_ticks=x_ticks, x_lim=x_lim)
    ax.set_ylabel(THROUGHPUT_LABEL)
    ax.set_xlabel(xlabel)
    ax.set_title(title)
    if show_legend:
        add_legend(ax)


def fleet_n_from_csv(name, col="n_evtol", default=6):
    try:
        rows = read_csv(name)
    except FileNotFoundError:
        return default
    if rows and col in rows[0]:
        return int(rows[0][col])
    return default


def fig3_resilience_depth():
    apply_nature_style()
    rows = read_csv("fig3_sensitivity_oph.csv")
    n = RESILIENCE_FLEET_N
    fault_rates = [0.01, 0.05, 0.1]
    fr_xlim = (min(fault_rates) - 0.015, max(fault_rates) + 0.015)
    turn_minutes = [15, 20, 30]
    turn_xlim = (13, 32)

    fig, axes = plt.subplots(1, 4, figsize=(9.6, 2.75))
    panels = [
        ("pad",        r"Fault rate (min$^{-1}$)", "Pad fault\n(repair: 10 min)",    fault_rates,  fr_xlim),
        ("stand",      r"Fault rate (min$^{-1}$)", "Stand fault\n(repair: 30 min)",   fault_rates,  fr_xlim),
        ("weather",    r"Fault rate (min$^{-1}$)", "Weather fault\n(recovery: 20 min)", fault_rates, fr_xlim),
        ("turnaround", "Turnaround (min)",          "Turnaround time",                turn_minutes, turn_xlim),
    ]
    for ax, (panel, xlabel, title, x_ticks, x_lim) in zip(axes, panels):
        plot_resilience_panel(
            ax, rows, panel, xlabel, title, x_ticks, x_lim,
            FAULT_COLOURS[panel], show_legend=(panel == "pad"),
        )
    fig.suptitle(f"V1 steady-state sensitivity ($N={n}$)", fontsize=10, y=1.02)
    fig.subplots_adjust(wspace=0.42, top=0.82)
    save_figure(fig, "fig3_sensitivity.png")


def nominal_throughput_from_resilience():
    try:
        rows = read_csv("fig3_sensitivity_oph.csv")
    except FileNotFoundError:
        return 15.447
    for r in rows:
        if r["panel"] == "pad" and r["curve"] == "baseline":
            return float(r["throughput"])
    return 15.447


def fig4_pad_recovery():
    apply_nature_style()
    recovery_rows = read_csv("fig4_recovery_throughput.csv")
    n = fleet_n_from_csv("fig4_recovery_throughput.csv", default=RECOVERY_FLEET_N)
    nominal = nominal_throughput_from_resilience()

    fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.8))
    repair_rates = sorted({float(r["repair_rate"]) for r in recovery_rows})

    ax = axes[0]
    all_y = [0.0]
    for i, rr in enumerate(repair_rates):
        pts = sorted(
            [(float(r["t_min"]), float(r["throughput_oph"]))
             for r in recovery_rows if float(r["repair_rate"]) == rr],
            key=lambda p: p[0],
        )
        xs, ys = zip(*pts)
        # Trapezoidal integration of (nominal - throughput) over time [flights]
        cum_loss = [0.0]
        for j in range(1, len(xs)):
            dt_hours = (xs[j] - xs[j - 1]) / 60.0
            avg_deficit = ((nominal - ys[j - 1]) + (nominal - ys[j])) / 2.0
            cum_loss.append(cum_loss[-1] + max(avg_deficit, 0.0) * dt_hours)
        all_y.extend(cum_loss)
        mean_repair = round(1.0 / rr)
        plot_trace(
            ax, xs, cum_loss, RECOVERY_COLOURS[i % len(RECOVERY_COLOURS)], "o",
            rf"repair {mean_repair} min ($\mu$={rr})",
        )
    ax.axvline(REF_TIME_MIN, color="#666666", linestyle="-.", linewidth=0.8,
               label=f"$t={REF_TIME_MIN}$ min")
    style_axis(ax, all_y, x_ticks=list(range(0, 121, 30)), x_lim=(-2, 122))
    ax.set_xlabel("Time since pad closure (min)")
    ax.set_ylabel("Cumulative flights lost")
    ax.set_title("Capacity loss")

    ax = axes[1]
    all_y = [0.0, nominal, THROUGHPUT_REF_OPH]
    for i, rr in enumerate(repair_rates):
        pts = sorted(
            [(float(r["t_min"]), float(r["throughput_oph"]))
             for r in recovery_rows if float(r["repair_rate"]) == rr],
            key=lambda p: p[0],
        )
        xs, ys = zip(*pts)
        all_y.extend(ys)
        mean_repair = round(1.0 / rr)
        plot_trace(
            ax, xs, ys, RECOVERY_COLOURS[i % len(RECOVERY_COLOURS)], "o",
            rf"repair {mean_repair} min ($\mu$={rr})",
        )
    ax.axhline(nominal, color="#BBBBBB", linestyle="--", linewidth=1.0, label="Nominal")
    ax.axhline(THROUGHPUT_REF_OPH, color="#AA3377", linestyle=":", linewidth=1.0,
               label="Throughput = 10")
    ax.axvline(REF_TIME_MIN, color="#666666", linestyle="-.", linewidth=0.8,
               label=f"$t={REF_TIME_MIN}$ min")
    style_axis(ax, all_y, x_ticks=list(range(0, 121, 30)), x_lim=(-2, 122))
    ax.set_xlabel("Time since pad closure (min)")
    ax.set_ylabel(THROUGHPUT_LABEL)
    ax.set_title("Operational throughput recovery")
    add_legend(ax)

    fig.suptitle(f"Pad-closed recovery ($N={n}$)", fontsize=10, y=1.02)
    fig.subplots_adjust(wspace=0.38, top=0.82)
    save_figure(fig, "fig4_pad_recovery.png")


COMPOUND_K_LABELS = {0: "pad only", 1: "pad + 1 stand", 2: "pad + 2 stands"}
WEATHER_REPAIR_RATE = 0.05          # matches COMPOUNDSW_WEATHER_REPAIR
DEMAND_OPH = 10.0                   # representative scheduled demand (flights/hour)


def cumulative_loss(xs, ys, nominal):
    """Trapezoidal integral of (nominal - throughput) over time, in flights."""
    cum = [0.0]
    for j in range(1, len(xs)):
        dt_hours = (xs[j] - xs[j - 1]) / 60.0
        avg_deficit = ((nominal - ys[j - 1]) + (nominal - ys[j])) / 2.0
        cum.append(cum[-1] + max(avg_deficit, 0.0) * dt_hours)
    return cum


def fig5_compound_recovery():
    """Compound-fault recovery erosion: pad closure with 0/1/2 co-failed stands.

    Panel layout mirrors fig4: left = capacity loss (cumulative flights lost),
    right = operational throughput recovery.
    Pad repair: 10 min  |  Stand repair: 30 min
    """
    apply_nature_style()
    rows = read_csv("fig5_compound_recovery.csv")
    n = int(rows[0]["n_evtol"]) if rows else RECOVERY_FLEET_N
    nominal = nominal_throughput_from_resilience()
    ks = sorted({int(r["k_out"]) for r in rows})
    x_ticks = list(range(0, 121, 30))
    x_lim = (-2, 122)

    fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.8))

    ax = axes[0]
    all_y = [0.0]
    for i, k in enumerate(ks):
        pts = sorted(
            [(float(r["t_min"]), float(r["throughput_oph"]))
             for r in rows if int(r["k_out"]) == k and float(r["t_min"]) <= 120],
            key=lambda p: p[0],
        )
        xs, ys = zip(*pts)
        cum = cumulative_loss(xs, ys, nominal)
        all_y.extend(cum)
        plot_trace(
            ax, xs, cum, RECOVERY_COLOURS[i % len(RECOVERY_COLOURS)], "o",
            COMPOUND_K_LABELS.get(k, f"pad + {k} stands"),
        )
    ax.axvline(REF_TIME_MIN, color="#666666", linestyle="-.", linewidth=0.8,
               label=f"$t={REF_TIME_MIN}$ min")
    style_axis(ax, all_y, x_ticks=x_ticks, x_lim=x_lim)
    ax.set_xlabel("Time since compound failure (min)")
    ax.set_ylabel("Cumulative flights lost")
    ax.set_title("Capacity loss")

    ax = axes[1]
    all_y = [0.0, nominal, THROUGHPUT_REF_OPH]
    for i, k in enumerate(ks):
        pts = sorted(
            [(float(r["t_min"]), float(r["throughput_oph"]))
             for r in rows if int(r["k_out"]) == k and float(r["t_min"]) <= 120],
            key=lambda p: p[0],
        )
        xs, ys = zip(*pts)
        all_y.extend(ys)
        plot_trace(
            ax, xs, ys, RECOVERY_COLOURS[i % len(RECOVERY_COLOURS)], "o",
            COMPOUND_K_LABELS.get(k, f"pad + {k} stands"),
        )
    ax.axhline(nominal, color="#BBBBBB", linestyle="--", linewidth=1.0, label="Nominal")
    ax.axhline(THROUGHPUT_REF_OPH, color="#AA3377", linestyle=":", linewidth=1.0,
               label="Throughput = 10")
    ax.axvline(REF_TIME_MIN, color="#666666", linestyle="-.", linewidth=0.8,
               label=f"$t={REF_TIME_MIN}$ min")
    style_axis(ax, all_y, x_ticks=x_ticks, x_lim=x_lim)
    ax.set_xlabel("Time since compound failure (min)")
    ax.set_ylabel(THROUGHPUT_LABEL)
    ax.set_title("Operational throughput recovery")
    add_legend(ax)

    fig.suptitle(
        f"Compound-fault recovery erosion ($N={n}$)  "
        r"[Pad repair: 10 min $\cdot$ Stand repair: 30 min]",
        fontsize=10, y=1.02,
    )
    fig.subplots_adjust(wspace=0.38, top=0.82)
    save_figure(fig, "fig5_compound_recovery.png")


# Colours and markers for stands-out levels (k=0..3)
STAND_COLOURS = {0: "#4477AA", 1: "#228833", 2: "#CCBB44", 3: "#EE6677"}
STAND_MARKERS = {0: "o", 1: "s", 2: "D", 3: "^"}
STAND_LABELS  = {
    0: "All stands operational",
    1: "$k=1$ stand out",
    2: "$k=2$ stands out",
    3: "$k=3$ stands out (blockage)",
}


def fig6_standweather_compound():
    """Compound stand × weather steady-state capacity line chart.

    Uses compound_capacity.csv (R=?[S] steady-state — no cold-start artifact).
    Sustained throughput vs P(bad) for k=0..3 stands out, with demand threshold.
    """
    apply_nature_style()
    cap_rows = read_csv("fig6_compound_capacity.csv")
    n = int(cap_rows[0]["n_evtol"]) if cap_rows else RECOVERY_FLEET_N

    ks   = sorted({int(r["stands_out"])          for r in cap_rows})
    wffs = sorted({float(r["weather_fault_rate"]) for r in cap_rows})
    lut  = {(int(r["stands_out"]), float(r["weather_fault_rate"])): float(r["throughput_oph"])
            for r in cap_rows}

    p_bads_pct = [wff / (wff + WEATHER_REPAIR_RATE) * 100 for wff in wffs]
    x_idx = list(range(len(wffs)))

    fig, ax = plt.subplots(figsize=(5.2, 3.4))

    all_y = []
    for k in ks:
        ys = [lut.get((k, w), np.nan) for w in wffs]
        all_y.extend([v for v in ys if not np.isnan(v)])
        colour = STAND_COLOURS.get(k, "#999999")
        marker = STAND_MARKERS.get(k, "o")
        ls = "--" if k == max(ks) else "-"
        plot_trace(ax, x_idx, ys, colour, marker, STAND_LABELS.get(k, f"k={k}"),
                   linestyle=ls, fill=(k != max(ks)))

    ax.axhline(DEMAND_OPH, color="#888888", linestyle=":", linewidth=1.1,
               label=f"Demand ({DEMAND_OPH:.0f} fph)")
    ax.fill_between([-0.3, len(wffs) - 0.7], 0, DEMAND_OPH,
                    color="#EE6677", alpha=0.07, zorder=0)

    ax.set_xticks(x_idx)
    ax.set_xticklabels([f"{p:.0f}%" for p in p_bads_pct], fontsize=7)
    ax.set_xlabel("Bad-weather fraction  P(bad)", fontsize=7)
    ax.set_ylabel(THROUGHPUT_LABEL, fontsize=7)
    ax.set_xlim(-0.3, len(wffs) - 0.7)
    all_y.append(DEMAND_OPH)
    style_axis(ax, all_y + [0.0])
    add_legend(ax)

    fig.suptitle(f"Stand-outage × weather compound capacity ($N={n}$)", fontsize=10)
    fig.tight_layout()
    save_figure(fig, "fig6_standweather_compound.png")


if __name__ == "__main__":
    print("Generating figures ...")
    fig1_oph_vs_n()
    fig2_open_v1_v2()
    fig3_resilience_depth()
    fig4_pad_recovery()
    fig5_compound_recovery()
    fig6_standweather_compound()
    print("Done. Figures in figures/.")

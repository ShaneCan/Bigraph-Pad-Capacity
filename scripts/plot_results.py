#!/usr/bin/env python3
"""
Produce paper figures from the CSVs in analysis/.

Figures (figures/):
  fig1_oph_vs_n.png         Saturated capacity, pad utilisation, stand congestion vs N
  fig2_open_v1_v2.png       Open V1/V2: throughput, blocking, mean number/time in system vs lambda
  fig3_v3_mix.png           V3 mix (N=5), abstract vs one-way, transit blocking
  fig4_resilience_depth.png V1 isolated fault / turnaround throughput (N=6)

Run (after run_analysis.py):  python3 scripts/plot_results.py
"""

import csv
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ANALYSIS = os.path.join(ROOT, "analysis")
FIGURES = os.path.join(ROOT, "figures")
os.makedirs(FIGURES, exist_ok=True)

SAVE_DPI = 300
THROUGHPUT_LABEL = "Throughput (flights/hour)"
CAPACITY_FLEET_NS = [4, 5, 6, 7, 8, 9]

# Paul Tol bright — colourblind-safe, common in Nature/Science-style figures.
COLOURS = {"V1": "#4477AA", "V2": "#EE6677", "V3": "#228833"}
MARKERS = {"V1": "o", "V2": "s", "V3": "D"}
FAULT_COLOURS = {
    "pad": "#4477AA", "stand": "#EE6677", "weather": "#228833",
    "turnaround": "#CCBB44",
}
FAULT_MARKERS = {"pad": "o", "stand": "s", "weather": "D", "turnaround": "s"}
COMPARE_COLOURS = {"abstract": "#BBBBBB", "oneway": "#228833"}
COMPARE_MARKERS = {"abstract": "o", "oneway": "D"}


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
    pts = [(int(r["N"]), float(r[field])) for r in rows if r["model"] == model]
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
        [r for r in rows if r["model"] == "V3"],
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

    style_axis(ax, all_y, x_ticks=CAPACITY_FLEET_NS, x_lim=(3.7, 9.3))
    ax.set_ylabel(ylabel)
    ax.set_xlabel(xlabel)
    if show_legend:
        add_legend(ax, title="Layout")


def plot_open_panel(ax, rows, field, ylabel, xlabel, x_ticks, x_lim,
                    show_legend=False):
    all_y = []
    for model in ("V1", "V2"):
        pts = open_points(rows, model, field)
        xs, ys = zip(*pts)
        all_y.extend(ys)
        plot_trace(ax, xs, ys, COLOURS[model], MARKERS[model], model)
    style_axis(ax, all_y, x_ticks=x_ticks, x_lim=x_lim)
    ax.set_ylabel(ylabel)
    ax.set_xlabel(xlabel)
    if show_legend:
        add_legend(ax, title="Layout")


def plot_line_panel(ax, series, ylabel, xlabel, x_ticks, x_lim,
                    show_legend=False, legend_title=None):
    all_y = []
    for label, xs, ys, colour, marker in series:
        all_y.extend(ys)
        plot_trace(ax, xs, ys, colour, marker, label)
    style_axis(ax, all_y, x_ticks=x_ticks, x_lim=x_lim)
    ax.set_ylabel(ylabel)
    ax.set_xlabel(xlabel)
    if show_legend:
        add_legend(ax, title=legend_title)


# ---------------------------------------------------------------------
def fig1_oph_vs_n():
    apply_nature_style()
    rows = read_csv("capacity_oph.csv")
    xlabel = "Fleet size $N$"
    fig, axes = plt.subplots(1, 3, figsize=(7.4, 2.55))
    plot_capacity_panel(
        axes[0], rows, "throughput", THROUGHPUT_LABEL, xlabel, show_legend=True,
    )
    plot_capacity_panel(
        axes[1], rows, "pad_utilisation", "Pad utilisation", xlabel,
    )
    plot_capacity_panel(
        axes[2], rows, "all_stands_busy_prob",
        r"$P(\mathrm{all\ stands\ busy})$", xlabel,
    )
    fig.subplots_adjust(wspace=0.42)
    save_figure(fig, "fig1_oph_vs_n.png")


def fig2_open_v1_v2():
    apply_nature_style()
    rows = read_csv("open_v1_v2.csv")
    lambdas = sorted({float(r["lambda"]) for r in rows})
    xlabel = r"Arrival rate $\lambda$ (min$^{-1}$)"
    x_lim = (min(lambdas) - 0.15, max(lambdas) + 0.15)
    fig, axes = plt.subplots(1, 4, figsize=(9.6, 2.55))
    panels = [
        ("throughput", THROUGHPUT_LABEL, True),
        ("P_block", r"$P_{\mathrm{block}}$", False),
        ("mean_in_system", "Mean number in system (aircraft)", False),
        ("mean_delay_min", "Mean time in system (min)", False),
    ]
    for ax, (field, ylabel, show_legend) in zip(axes, panels):
        plot_open_panel(
            ax, rows, field, ylabel, xlabel, lambdas, x_lim,
            show_legend=show_legend,
        )
    fig.subplots_adjust(wspace=0.42)
    save_figure(fig, "fig2_open_v1_v2.png")


def fig3_v3_mix():
    apply_nature_style()
    mix_rows = read_csv("v3_mix.csv")
    oneway_rows = read_csv("v3_oneway.csv")
    ns = sorted({int(r["N"]) for r in oneway_rows})
    x_lim = (min(ns) - 0.3, max(ns) + 0.3)
    xlabel_n = "Fleet size $N$"

    fig, axes = plt.subplots(1, 3, figsize=(9.6, 2.55))

    subset = sorted(
        [r for r in mix_rows if int(r["N"]) == 5],
        key=lambda r: int(r["n_small"]),
    )
    xs = [int(r["n_small"]) for r in subset]
    ys = [float(r["throughput"]) for r in subset]
    labels = [f"{r['n_small']}S/{r['n_large']}L" for r in subset]
    plot_trace(axes[0], xs, ys, COLOURS["V3"], MARKERS["V3"], "$N=5$")
    style_axis(axes[0], ys, x_ticks=xs, x_lim=(min(xs) - 0.35, max(xs) + 0.35))
    axes[0].set_xticklabels(labels)
    axes[0].set_xlabel("Traffic mix (small / large),  $N=5$")
    axes[0].set_ylabel(THROUGHPUT_LABEL)

    throughput_series = []
    for model in ("abstract", "oneway"):
        pts = [(int(r["N"]), float(r["throughput"])) for r in oneway_rows if r["model"] == model]
        pts.sort()
        xs, ys = zip(*pts)
        throughput_series.append((
            model.capitalize(),
            xs, ys,
            COMPARE_COLOURS[model],
            COMPARE_MARKERS[model],
        ))
    plot_line_panel(
        axes[1], throughput_series, THROUGHPUT_LABEL, xlabel_n, ns, x_lim,
        show_legend=True, legend_title="Model",
    )

    ow = [r for r in oneway_rows if r["model"] == "oneway"]
    block_series = [
        (
            "Small at LargeFATO",
            [int(r["N"]) for r in ow],
            [float(r["small_transit_blocked"]) for r in ow],
            "#4477AA", "o",
        ),
        (
            "Large at SmallFATO",
            [int(r["N"]) for r in ow],
            [float(r["large_transit_blocked"]) for r in ow],
            "#EE6677", "s",
        ),
    ]
    plot_line_panel(
        axes[2], block_series,
        r"$P(\mathrm{transit\ blocked})$", xlabel_n, ns, x_lim,
        show_legend=True, legend_title="Gate",
    )

    fig.subplots_adjust(wspace=0.42)
    save_figure(fig, "fig3_v3_mix.png")


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


def fig4_resilience_depth():
    apply_nature_style()
    rows = read_csv("resilience_oph.csv")
    fault_rates = [0.01, 0.05, 0.1]
    fr_xlim = (min(fault_rates) - 0.015, max(fault_rates) + 0.015)
    turn_minutes = [15, 20, 30]
    turn_xlim = (13, 32)

    fig, axes = plt.subplots(1, 4, figsize=(9.6, 2.55))
    panels = [
        ("pad", r"Fault rate (min$^{-1}$)", "Pad fault", fault_rates, fr_xlim),
        ("stand", r"Fault rate (min$^{-1}$)", "Stand fault", fault_rates, fr_xlim),
        ("weather", r"Fault rate (min$^{-1}$)", "Weather fault", fault_rates, fr_xlim),
        ("turnaround", "Turnaround (min)", "Turnaround time", turn_minutes, turn_xlim),
    ]
    for ax, (panel, xlabel, title, x_ticks, x_lim) in zip(axes, panels):
        plot_resilience_panel(
            ax, rows, panel, xlabel, title, x_ticks, x_lim,
            FAULT_COLOURS[panel], show_legend=(panel == "pad"),
        )
    fig.subplots_adjust(wspace=0.42)
    save_figure(fig, "fig4_resilience_depth.png")


if __name__ == "__main__":
    print("Generating figures ...")
    fig1_oph_vs_n()
    fig2_open_v1_v2()
    fig3_v3_mix()
    fig4_resilience_depth()
    print("Done. Figures in figures/.")

#!/usr/bin/env python3
"""
Produce paper figures from the CSVs in analysis/.

Figures (figures/):
  fig1_oph_vs_n.png          Saturated capacity, pad/stand util, P(all stands busy) vs N
  fig2_open_v1_v2.png        Open V1/V2/V3: throughput, mean number/time in vertiport vs lambda
  fig3_sensitivity.png       V1 steady-state sensitivity vs unavailability P (pad/stand/weather) + turnaround (N=6)
  fig4_pad_recovery.png      Pad-closed recovery: V1 mu-sweep throughput + recovery prob + V3 comparison (N=6)
  fig5_compound_recovery.png Compound recovery: V1 k=0/1/2 throughput + restoration prob + V2 comparison (N=6)
  fig6_standweather_compound.png  Stand × weather compound sustained capacity: V1 and V2 (N=6)
  fig_envelope.png           Resilience contract envelope (compound k=2): retained-service rho(t) V1 vs V2 + V2 confidence trade-off

Run (after run_analysis.py):  python3 scripts/plot_results.py
Select figures:               python3 scripts/plot_results.py fig4 fig_envelope
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


def read_csv_optional(name):
    """Return rows if the CSV exists, else [] (used for the V2/V3 overlays
    so figures still build when only the baseline V1 data is present)."""
    try:
        return read_csv(name)
    except FileNotFoundError:
        return []


def apply_nature_style():
    # Seaborn "darkgrid"-inspired publication style: light-grey panel, white
    # gridlines, no spines/ticks, thicker traces.  The grey panel + white grid
    # is a purely aesthetic choice; every plotted point is a single exact
    # model-checking value, so no uncertainty band is drawn.
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
        "mathtext.fontset": "dejavusans",
        "svg.fonttype": "none",
        "font.size": 8,
        "axes.labelsize": 8,
        "axes.titlesize": 9,
        "xtick.labelsize": 7,
        "ytick.labelsize": 7,
        "legend.fontsize": 7,
        "legend.frameon": False,
        "axes.grid": True,
        "axes.axisbelow": True,
        "grid.color": "white",
        "grid.linestyle": "-",
        "grid.linewidth": 0.9,
        "grid.alpha": 1.0,
        "axes.linewidth": 0.0,
        "axes.edgecolor": "white",
        "axes.facecolor": "#EAEAF2",
        "figure.facecolor": "white",
        "xtick.major.width": 0.0,
        "ytick.major.width": 0.0,
        "xtick.major.size": 0.0,
        "ytick.major.size": 0.0,
        "xtick.color": "#555555",
        "ytick.color": "#555555",
        "xtick.direction": "out",
        "ytick.direction": "out",
        "lines.linewidth": 1.75,
        "lines.markersize": 5.0,
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
    # Seaborn darkgrid look: hide all spines and tick marks, keep white grid.
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(top=False, right=False, left=False, bottom=False,
                   which="both", length=0)
    if x_ticks is not None:
        ax.set_xticks(x_ticks)
    if x_lim is not None:
        ax.set_xlim(*x_lim)
    ax.set_ylim(*adaptive_ylim(y_values))
    ax.set_box_aspect(1)
    ax.grid(True, which="major", axis="both", color="white",
            linewidth=0.9, zorder=0)
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


def add_legend(ax, title=None, fontsize=None, loc="best"):
    leg = ax.legend(
        title=title,
        loc=loc,
        fontsize=fontsize,
        handlelength=1.6,
        handletextpad=0.5,
        borderaxespad=0.4,
        labelspacing=0.3,
        frameon=True,
        framealpha=0.85,
        facecolor="white",
        edgecolor="none",
    )
    if fontsize is not None and leg.get_title() is not None:
        leg.get_title().set_fontsize(fontsize)
    leg.get_frame().set_linewidth(0.0)


def add_panel_labels(axes, y=-0.25):
    """Bottom-centre (a)/(b)/(c) labels tucked just under each x-axis title."""
    if len(axes) < 2:
        return
    for ax, lab in zip(axes, "abcdefgh"):
        ax.text(0.5, y, f"({lab})", transform=ax.transAxes,
                ha="center", va="top", fontsize=9, color="#222222")


def save_figure(fig, name):
    out = os.path.join(FIGURES, name)
    stem = os.path.splitext(out)[0]
    fig.savefig(out)                 # PNG (raster)
    fig.savefig(stem + ".svg")       # SVG (vector, editable text)
    plt.close(fig)
    print("  wrote", out)
    print("  wrote", stem + ".svg")


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
    add_panel_labels(axes)
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
    add_panel_labels(axes)
    save_figure(fig, "fig2_open_v1_v2.png")


def plot_resilience_panel(ax, rows, panel, xlabel, x_ticks, x_lim,
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
    if show_legend:
        add_legend(ax)


def fig3_resilience_depth():
    apply_nature_style()
    rows = read_csv("fig3_sensitivity_oph.csv")
    # Panels a/b/c share one axis: steady-state unavailability P (fraction of
    # time the resource is closed / degraded), on the grid {0,5,10,15,20,30}%.
    unavail_ticks = [0.0, 0.1, 0.2, 0.3]
    unavail_xlim = (-0.01, 0.32)
    turn_minutes = [15, 20, 30]
    turn_xlim = (13, 32)

    fig, axes = plt.subplots(1, 4, figsize=(9.6, 2.55))
    panels = [
        ("pad",        "Pad unavailability",              unavail_ticks, unavail_xlim),
        ("stand",      "Stand unavailability (per stand)", unavail_ticks, unavail_xlim),
        ("weather",    r"Bad-weather fraction $P(\mathrm{Bad})$", unavail_ticks, unavail_xlim),
        ("turnaround", "Turnaround (min)",                turn_minutes,  turn_xlim),
    ]
    for ax, (panel, xlabel, x_ticks, x_lim) in zip(axes, panels):
        plot_resilience_panel(
            ax, rows, panel, xlabel, x_ticks, x_lim,
            FAULT_COLOURS[panel], show_legend=(panel == "pad"),
        )
    fig.subplots_adjust(wspace=0.42)
    add_panel_labels(axes)
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


def recovery_curve(rows, key_field, key_value):
    """Sorted (t, throughput_oph) points for one curve (t <= 120)."""
    return sorted(
        [(float(r["t_min"]), float(r["throughput_oph"]))
         for r in rows
         if float(r[key_field]) == key_value and float(r["t_min"]) <= 120],
        key=lambda p: p[0],
    )


def colour_for_repair_rate(rate, repair_rates):
    """Same colour index as the left-panel mu-sweep legend."""
    idx = sorted(repair_rates).index(rate)
    return RECOVERY_COLOURS[idx % len(RECOVERY_COLOURS)]


def cumulative_loss(pts, nominal, t_max=None):
    """Cumulative service loss over the recovery window.

    CSL = integral_0^T (R_nom - R_inst(t)) dt, taken only where the
    recovering throughput sits below nominal.  Points carry t in minutes
    and throughput in flights/hour, so dividing by 60 returns the loss in
    flights (departures foregone relative to undisturbed operation).
    """
    kept = [(t, y) for t, y in pts if (t_max is None or t <= t_max)]
    if len(kept) < 2:
        return 0.0
    ts = [t for t, _ in kept]
    deficit = [max(nominal - y, 0.0) for _, y in kept]
    return float(np.trapz(deficit, ts)) / 60.0


def shade_service_loss(ax, pts, nominal, colour, label=None):
    """Shade the area between the nominal line and a recovery curve, and
    return the cumulative service loss it represents (flights)."""
    if len(pts) < 2:
        return 0.0
    xs = [t for t, _ in pts]
    ys = [y for _, y in pts]
    ax.fill_between(xs, ys, nominal, where=[y < nominal for y in ys],
                    interpolate=True, color=colour, alpha=0.13, zorder=1,
                    label=label if label else "_nolegend_")
    return cumulative_loss(pts, nominal)


def v3_nominal_throughput(default=19.77):
    """V3 (N=6) saturated nominal throughput from the capacity CSV."""
    for r in read_csv_optional("fig1_capacity_oph.csv"):
        if r["model"] == "V3" and int(r["N"]) == RECOVERY_FLEET_N:
            return float(r["throughput"])
    return default


REF_MU = 0.1   # representative "typical closure" repair rate for the V3 overlay


def _recovery_prob_panel(ax, csv_name, group_key, value_key, labeller,
                         xlabel, ylabel, x_ticks, x_lim):
    """CSL time-bounded recovery-probability panel P[F<=t target] vs time.

    The curves sweep the variable the metric is sensitive to (closure
    severity mu for fig4, concurrent stand outages k for fig5).  Recovery
    timing is gated by repair rate and accumulated backlog, not by parallel
    service capacity, so the layout comparison stays in the throughput panels.
    """
    rows = read_csv_optional(csv_name)
    if not rows:
        return False
    groups = sorted({float(r[group_key]) for r in rows})
    for i, g in enumerate(groups):
        pts = sorted((int(r["t_min"]), float(r[value_key])) for r in rows
                     if float(r[group_key]) == g)
        xs, ys = zip(*pts)
        plot_trace(ax, xs, ys, RECOVERY_COLOURS[i % len(RECOVERY_COLOURS)], "o",
                   labeller(g))
    ax.axvline(REF_TIME_MIN, color="#666666", linestyle="-.", linewidth=0.8,
               label=f"$t={REF_TIME_MIN}$ min")
    style_axis(ax, [0.0, 1.0], x_ticks=x_ticks, x_lim=x_lim)
    ax.set_ylim(-0.02, 1.02)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    add_legend(ax)
    return True


def fig4_pad_recovery():
    """Pad-closed throughput recovery (N=6).

    Left panel: single-FATO V1 across repair rates mu.  When the V3 overlay
    data is present, a right panel compares the dual-FATO V3 against V1 at a
    representative repair rate (mu = 0.1): the second FATO keeps a pad running
    through the closure, so the throughput floor stays high and recovery to
    nominal is faster.
    """
    apply_nature_style()
    recovery_rows = read_csv("fig4_recovery_throughput.csv")
    v3_rows = read_csv_optional("fig4_recovery_v3.csv")
    nominal = nominal_throughput_from_resilience()
    x_ticks = list(range(0, 121, 30))
    x_lim = (-2, 122)

    repair_rates = sorted({float(r["repair_rate"]) for r in recovery_rows})

    prob_rows = read_csv_optional("fig4b_recovery_prob.csv")
    n_panels = 1 + (1 if prob_rows else 0) + (1 if v3_rows else 0)
    fig, axes = plt.subplots(1, n_panels, figsize=(3.6 * n_panels, 2.55),
                             squeeze=False)
    axes = axes[0]
    ax_v1 = axes[0]
    idx = 1
    ax_prob = axes[idx] if prob_rows else None
    idx += 1 if prob_rows else 0
    ax_cmp = axes[idx] if v3_rows else None

    # --- V1 throughput recovery (mu sweep) ------------------------------
    ax = ax_v1
    all_y = [0.0, nominal, THROUGHPUT_REF_OPH]
    for i, rr in enumerate(repair_rates):
        pts = recovery_curve(recovery_rows, "repair_rate", rr)
        xs, ys = zip(*pts)
        all_y.extend(ys)
        mean_repair = round(1.0 / rr)
        plot_trace(ax, xs, ys, RECOVERY_COLOURS[i % len(RECOVERY_COLOURS)], "o",
                   rf"repair {mean_repair} min ($\mu$={rr})")
    # Cumulative service loss: shade the area between nominal and the
    # representative mu = 0.1 curve, and report the loss for every mu.
    if REF_MU in repair_rates:
        rep_pts = recovery_curve(recovery_rows, "repair_rate", REF_MU)
        rep_colour = RECOVERY_COLOURS[sorted(repair_rates).index(REF_MU)]
        shade_service_loss(ax, rep_pts, nominal, rep_colour)
        print("  [CSL] fig4a V1 FATO-closure recovery (loss vs undisturbed):")
        for rr in sorted(repair_rates):
            p = recovery_curve(recovery_rows, "repair_rate", rr)
            print(f"        mu={rr}: CSL(30min)={cumulative_loss(p, nominal, 30):.2f}"
                  f"  CSL(full)={cumulative_loss(p, nominal):.2f} flights")
    ax.axhline(nominal, color="#BBBBBB", linestyle="--", linewidth=1.0, label="Nominal")
    ax.axhline(THROUGHPUT_REF_OPH, color="#AA3377", linestyle=":", linewidth=1.0,
               label="Throughput = 10")
    ax.axvline(REF_TIME_MIN, color="#666666", linestyle="-.", linewidth=0.8,
               label=f"$t={REF_TIME_MIN}$ min")
    style_axis(ax, all_y, x_ticks=x_ticks, x_lim=x_lim)
    ax.set_xlabel("Time since pad closure (min)")
    ax.set_ylabel(THROUGHPUT_LABEL)
    add_legend(ax)

    if ax_cmp is not None:
        _fig4_v3_panel(ax_cmp, recovery_rows, v3_rows, nominal, repair_rates,
                       x_ticks, x_lim)

    if ax_prob is not None:
        _recovery_prob_panel(
            ax_prob, "fig4b_recovery_prob.csv", "repair_rate", "p_recovered",
            lambda mu: rf"repair {round(1.0 / mu)} min ($\mu$={mu})",
            "Time since pad closure (min)",
            r"$P[\,\mathrm{recovered\ by}\ t\,]$", x_ticks, x_lim)

    fig.subplots_adjust(wspace=0.42)
    add_panel_labels(axes)
    save_figure(fig, "fig4_pad_recovery.png")


def _fig4_v3_panel(ax, v1_rows, v3_rows, v1_nominal, repair_rates,
                   x_ticks, x_lim):
    """V3-vs-V1 throughput recovery at a single repair rate (mu = 0.1)."""
    v3_nominal = v3_nominal_throughput()
    v1_pts = recovery_curve(v1_rows, "repair_rate", REF_MU)
    v3_pts = recovery_curve(v3_rows, "repair_rate", REF_MU)
    mu_colour = colour_for_repair_rate(REF_MU, repair_rates)

    all_y = [0.0, v1_nominal, v3_nominal, THROUGHPUT_REF_OPH]
    for pts, label, fill, ls, marker in (
        (v3_pts, r"V3 ($\mu=0.1$)", True, "-", MARKERS["V3"]),
        (v1_pts, r"V1 ($\mu=0.1$)", False, "--", MARKERS["V1"]),
    ):
        if not pts:
            continue
        xs, ys = zip(*pts)
        all_y.extend(ys)
        plot_trace(ax, xs, ys, mu_colour, marker, label,
                   linestyle=ls, fill=fill)
    ax.axhline(v3_nominal, color="#BBBBBB", linestyle=(0, (1, 1)),
               linewidth=0.9, label="V3 nominal")
    ax.axhline(v1_nominal, color="#BBBBBB", linestyle="--", linewidth=1.0,
               label="V1 nominal")
    ax.axhline(THROUGHPUT_REF_OPH, color="#AA3377", linestyle=":", linewidth=1.0,
               label="Throughput = 10")
    ax.axvline(REF_TIME_MIN, color="#666666", linestyle="-.", linewidth=0.8,
               label=f"$t={REF_TIME_MIN}$ min")
    style_axis(ax, all_y, x_ticks=x_ticks, x_lim=x_lim)
    ax.set_xlabel("Time since pad closure (min)")
    ax.set_ylabel(THROUGHPUT_LABEL)
    add_legend(ax)


COMPOUND_K_LABELS = {0: "pad only", 1: "pad + 1 stand", 2: "pad + 2 stands"}
WEATHER_REPAIR_RATE = 0.05          # matches COMPOUNDSW_WEATHER_REPAIR
DEMAND_OPH = 10.0                   # representative scheduled demand (flights/hour)


def v2_nominal_throughput(default=18.19):
    """V2 (N=6) saturated nominal throughput from the capacity CSV."""
    for r in read_csv_optional("fig1_capacity_oph.csv"):
        if r["model"] == "V2" and int(r["N"]) == RECOVERY_FLEET_N:
            return float(r["throughput"])
    return default


def fig5_compound_recovery():
    """Compound-fault recovery erosion: pad closure with 0/1/2 co-failed stands.

    Left panel: single-FATO V1 throughput recovery for k = 0/1/2 stands out.
    When fig5_compound_recovery_v2.csv is present, a right panel compares
    V2 (4 stands) against V1 (3 stands) at the compound scenarios (pad + 1
    stand out, pad + 2 stands out): the extra stand keeps the recovering
    throughput floor higher ("stands before pads" holds for resilience too).
    Pad repair: 10 min  |  Stand repair: 20 min
    """
    apply_nature_style()
    rows = read_csv("fig5_compound_recovery.csv")
    v2_rows = read_csv_optional("fig5_compound_recovery_v2.csv")
    nominal = nominal_throughput_from_resilience()
    ks = sorted({int(r["k_out"]) for r in rows})
    x_ticks = list(range(0, 121, 30))
    x_lim = (-2, 122)

    prob_rows = read_csv_optional("fig5b_restoration_prob.csv")
    n_panels = 1 + (1 if prob_rows else 0) + (1 if v2_rows else 0)
    fig, axes = plt.subplots(1, n_panels, figsize=(3.6 * n_panels, 2.55),
                             squeeze=False)
    axes = axes[0]
    ax_v1 = axes[0]
    idx = 1
    ax_prob = axes[idx] if prob_rows else None
    idx += 1 if prob_rows else 0
    ax_cmp = axes[idx] if v2_rows else None

    # --- V1 throughput recovery (k = 0/1/2) -----------------------------
    ax = ax_v1
    all_y = [0.0, nominal, THROUGHPUT_REF_OPH]
    for i, k in enumerate(ks):
        pts = recovery_curve(rows, "k_out", k)
        xs, ys = zip(*pts)
        all_y.extend(ys)
        plot_trace(ax, xs, ys, RECOVERY_COLOURS[i % len(RECOVERY_COLOURS)], "o",
                   COMPOUND_K_LABELS.get(k, f"pad + {k} stands"))
    # Cumulative service loss: shade the worst compound curve (most stands out)
    # and report the loss for every scenario.
    rep_k = max(ks)
    rep_pts = recovery_curve(rows, "k_out", rep_k)
    rep_colour = RECOVERY_COLOURS[ks.index(rep_k) % len(RECOVERY_COLOURS)]
    shade_service_loss(ax, rep_pts, nominal, rep_colour)
    print("  [CSL] fig5a V1 compound recovery (loss vs undisturbed):")
    for k in ks:
        p = recovery_curve(rows, "k_out", k)
        print(f"        k={k}: CSL(30min)={cumulative_loss(p, nominal, 30):.2f}"
              f"  CSL(full)={cumulative_loss(p, nominal):.2f} flights")
    ax.axhline(nominal, color="#BBBBBB", linestyle="--", linewidth=1.0, label="Nominal")
    ax.axhline(THROUGHPUT_REF_OPH, color="#AA3377", linestyle=":", linewidth=1.0,
               label="Throughput = 10")
    ax.axvline(REF_TIME_MIN, color="#666666", linestyle="-.", linewidth=0.8,
               label=f"$t={REF_TIME_MIN}$ min")
    style_axis(ax, all_y, x_ticks=x_ticks, x_lim=x_lim)
    ax.set_xlabel("Time since compound failure (min)")
    ax.set_ylabel(THROUGHPUT_LABEL)
    add_legend(ax)

    if ax_cmp is not None:
        _fig5_v2_panel(ax_cmp, rows, v2_rows, x_ticks, x_lim)

    if ax_prob is not None:
        _recovery_prob_panel(
            ax_prob, "fig5b_restoration_prob.csv", "k_out", "p_restored",
            lambda k: COMPOUND_K_LABELS.get(int(k), f"pad + {int(k)} stands"),
            "Time since compound failure (min)",
            r"$P[\,\mathrm{restored\ by}\ t\,]$", x_ticks, x_lim)

    fig.subplots_adjust(wspace=0.42)
    add_panel_labels(axes)
    save_figure(fig, "fig5_compound_recovery.png")


def _fig5_v2_panel(ax, v1_rows, v2_rows, x_ticks, x_lim):
    """V2-vs-V1 throughput recovery at the compound scenarios (k = 1, 2).

    Colour encodes the scenario; solid filled = V1 (3 stands), dashed open =
    V2 (4 stands).  The extra stand keeps the recovering throughput floor
    higher ("stands before pads" holds for resilience too).
    """
    v2_nominal = v2_nominal_throughput()
    compound_ks = [1, 2]
    all_y = [0.0, v2_nominal, THROUGHPUT_REF_OPH]
    for k in compound_ks:
        colour = RECOVERY_COLOURS[k % len(RECOVERY_COLOURS)]
        for src_rows, layout, fill, ls in (
            (v1_rows, "V1", True, "-"),
            (v2_rows, "V2", False, "--"),
        ):
            pts = recovery_curve(src_rows, "k_out", k)
            if not pts:
                continue
            xs, ys = zip(*pts)
            all_y.extend(ys)
            plot_trace(ax, xs, ys, colour, MARKERS[layout],
                       f"{layout} pad + {k} stand" + ("s" if k > 1 else ""),
                       linestyle=ls, fill=fill)
    ax.axhline(THROUGHPUT_REF_OPH, color="#AA3377", linestyle=":", linewidth=1.0,
               label="Throughput = 10")
    ax.axvline(REF_TIME_MIN, color="#666666", linestyle="-.", linewidth=0.8,
               label=f"$t={REF_TIME_MIN}$ min")
    style_axis(ax, all_y, x_ticks=x_ticks, x_lim=x_lim)
    ax.set_xlabel("Time since compound failure (min)")
    ax.set_ylabel(THROUGHPUT_LABEL)
    add_legend(ax)


# Colours and markers for stands-out levels (k=0..3)
STAND_COLOURS = {0: "#4477AA", 1: "#228833", 2: "#CCBB44", 3: "#EE6677"}
STAND_MARKERS = {0: "o", 1: "s", 2: "D", 3: "^"}
STAND_LABELS  = {
    0: "All stands operational",
    1: "$k=1$ stand out",
    2: "$k=2$ stands out",
    3: "$k=3$ stands out",
}


def _plot_sw_panel(ax, cap_rows, wffs, show_legend, y_all):
    """One weather × stands-out capacity panel (sustained throughput vs P(bad))."""
    ks = sorted({int(r["stands_out"]) for r in cap_rows})
    lut = {(int(r["stands_out"]), float(r["weather_fault_rate"])): float(r["throughput_oph"])
           for r in cap_rows}
    x_idx = list(range(len(wffs)))
    p_bads_pct = [wff / (wff + WEATHER_REPAIR_RATE) * 100 for wff in wffs]

    for k in ks:
        ys = [lut.get((k, w), np.nan) for w in wffs]
        y_all.extend([v for v in ys if not np.isnan(v)])
        colour = STAND_COLOURS.get(k, "#999999")
        marker = STAND_MARKERS.get(k, "o")
        ls = "--" if k == max(ks) else "-"
        plot_trace(ax, x_idx, ys, colour, marker, STAND_LABELS.get(k, f"k={k}"),
                   linestyle=ls, fill=(k != max(ks)))

    ax.axhline(DEMAND_OPH, color="#888888", linestyle=":", linewidth=1.1,
               label=f"Demand ({DEMAND_OPH:.0f} flights/hour)")
    ax.fill_between([-0.3, len(wffs) - 0.7], 0, DEMAND_OPH,
                    color="#EE6677", alpha=0.07, zorder=0)
    ax.set_xticks(x_idx)
    ax.set_xticklabels([f"{p:.0f}%" for p in p_bads_pct])
    ax.set_xlabel("Bad-weather fraction  P(bad)")
    ax.set_ylabel(THROUGHPUT_LABEL)
    ax.set_xlim(-0.3, len(wffs) - 0.7)
    if show_legend:
        add_legend(ax, fontsize=4.8, loc="best")


def fig6_standweather_compound():
    """Compound stand × weather steady-state capacity line chart.

    Uses compound_capacity.csv (R=?[S] steady-state — no cold-start artifact).
    Sustained throughput vs P(bad) for k=0..3 stands out, with demand
    threshold.  When fig6_compound_capacity_v2.csv is present, a second panel
    shows V2 (4 stands): its capacity floor sits a full stand higher, so the
    worst-case (bad weather + 1 stand out) that drops V1 below demand still
    clears demand for V2.
    """
    apply_nature_style()
    cap_rows = read_csv("fig6_compound_capacity.csv")
    v2_rows = read_csv_optional("fig6_compound_capacity_v2.csv")
    wffs = sorted({float(r["weather_fault_rate"]) for r in cap_rows})

    y_all = [DEMAND_OPH, 0.0]
    if v2_rows:
        fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.55))
        _plot_sw_panel(axes[0], cap_rows, wffs, True, y_all)
        _plot_sw_panel(axes[1], v2_rows, wffs, False, y_all)
        for ax in axes:
            style_axis(ax, y_all)
            ax.set_ylim(bottom=0)
        fig.subplots_adjust(wspace=0.42)
        add_panel_labels(axes)
    else:
        fig, ax = plt.subplots(figsize=(3.6, 2.55))
        _plot_sw_panel(ax, cap_rows, wffs, True, y_all)
        style_axis(ax, y_all)
        ax.set_ylim(bottom=0)
        fig.subplots_adjust()

    save_figure(fig, "fig6_standweather_compound.png")


ENVELOPE_P = 0.8                       # contract recovery-confidence threshold
ENVELOPE_P_LEVELS = [0.8, 0.9, 0.95]   # confidence-tradeoff panel
ENVELOPE_CONF_LAYOUT = "V2"
ENVELOPE_CONF_PCOL = "#4477AA"          # stable-recovery confidence p*(t)


def _envelope_axis(ax, y_top, x_ticks):
    """Square panel with both axes starting at the origin (0, 0)."""
    style_axis(ax, [0.0, y_top], x_ticks=x_ticks, x_lim=(0, 120))
    ax.set_xlim(0, 120)
    ax.set_ylim(0, y_top * 1.10)


def fig_envelope():
    """Resilience contract envelope (compound: FATO closed + 2 stands out).

    (a) Contract envelope: retained-service ratio rho(t) for V1 and V2 over
        the deadlines that meet the recovery-confidence gate p*(t) >= p
        (feasible region shaded).  The fourth stand of V2 lifts retained
        service, so at any feasible deadline V2 supports a higher retained-
        service fraction than V1.
    (b) Contract guarantees for V2 on a single 0-1 scale: the stable-recovery
        confidence p*(t) and the retained-service fraction alpha=rho(t) both
        rise with the deadline t.  A required confidence p (dotted guides at
        0.8/0.9/0.95) fixes the earliest committable deadline where p*(t) first
        meets it; the retained service available there is read off alpha(t).
    """
    apply_nature_style()
    rows = read_csv("fig_envelope.csv")
    layouts = ["V1", "V2"]
    data = {lay: sorted((int(r["t_min"]), float(r["p_star"]), float(r["rho"]))
                        for r in rows if r["layout"] == lay) for lay in layouts}
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.0))
    x_ticks = list(range(0, 121, 30))

    # (a) contract envelope: rho(t), V1 vs V2, feasible (p* >= p) shaded
    ax = axes[0]
    y_top = 0.0
    for lay in layouts:
        ts = [t for t, _, _ in data[lay]]
        rho = [r for _, _, r in data[lay]]
        feas = [p >= ENVELOPE_P for _, p, _ in data[lay]]
        y_top = max(y_top, max(rho))
        ax.plot(ts, rho, linestyle=":", color=COLOURS[lay], linewidth=1.0,
                alpha=0.35, zorder=2)
        ft = [t for t, f in zip(ts, feas) if f]
        fr = [r for r, f in zip(rho, feas) if f]
        if ft:
            plot_trace(ax, ft, fr, COLOURS[lay], MARKERS[lay], lay)
            ax.fill_between(ft, 0, fr, color=COLOURS[lay], alpha=0.10, zorder=1)
    _envelope_axis(ax, y_top, x_ticks)
    ax.set_xlabel("Recovery deadline $t$ (min)")
    ax.set_ylabel(r"$\alpha=\rho_d(t)$: retained service")
    add_legend(ax, title=rf"feasible ($p^*\!\geq\!{ENVELOPE_P}$)")

    # (b) contract guarantees (V2): confidence p*(t) and retained service
    # alpha=rho(t) on one 0-1 axis; a required p fixes the earliest deadline.
    ax = axes[1]
    d = data[ENVELOPE_CONF_LAYOUT]
    ts = [t for t, _, _ in d]
    pstar = [p for _, p, _ in d]
    rho = [r for _, _, r in d]
    plot_trace(ax, ts, pstar, ENVELOPE_CONF_PCOL, "^",
               r"$p^*_d(t)$: recovery confidence", linestyle="-")
    plot_trace(ax, ts, rho, COLOURS[ENVELOPE_CONF_LAYOUT],
               MARKERS[ENVELOPE_CONF_LAYOUT],
               r"$\alpha=\rho_d(t)$: retained service", linestyle="-")
    for p_lvl in ENVELOPE_P_LEVELS:
        pt = next(((t, r) for t, p, r in d if p >= p_lvl), None)
        if pt:
            ax.plot([0, pt[0]], [p_lvl, p_lvl], color="#888888", linestyle=":",
                    linewidth=0.8, alpha=0.8, zorder=2)
            ax.plot([pt[0], pt[0]], [pt[1], p_lvl], color="#888888",
                    linestyle=":", linewidth=0.8, alpha=0.8, zorder=2)
            ax.scatter([pt[0]], [pt[1]], color=COLOURS[ENVELOPE_CONF_LAYOUT],
                       s=40, zorder=5)
            ax.annotate(rf"$\alpha={pt[1]:.2f}$", (pt[0], pt[1]),
                        textcoords="offset points", xytext=(4, -9),
                        fontsize=6, color=COLOURS[ENVELOPE_CONF_LAYOUT])
            ax.annotate(rf"$p={p_lvl:g}$", (0, p_lvl),
                        textcoords="offset points", xytext=(2, 2),
                        fontsize=6, color="#666666")
    _envelope_axis(ax, 1.0, x_ticks)
    ax.set_xlabel("Recovery deadline $t$ (min)")
    ax.set_ylabel("Probability / retained fraction")
    add_legend(ax, title=f"{ENVELOPE_CONF_LAYOUT} guarantees")

    add_panel_labels(axes)
    fig.subplots_adjust(wspace=0.42)
    save_figure(fig, "fig_envelope.png")


# Panel (a): layout = hue (V1 blue / V2 red, matching the paper and panel b),
# demand = line style (nominal target solid, near-capacity long-dashed).
SLA_DEMANDS = [10, 15]
SLA_DEMAND_STYLE = {10: "-", 15: (0, (6, 3))}


def fig_sla_resilience():
    """Long-run service-level resilience under recurrent pad+stand faults.

    (a) SLA survival P=?[G<=t op(d)] = probability that delivered capacity
        stays at or above demand d throughout [0,t] (the advisor's
        P=?[F[0,t] !op], complemented), for demands d=5/10/14 and V1 vs V2.
        A higher demand breaches sooner; at each demand V2 holds the
        contract longer because it tolerates one more stand outage.
    (b) Demand-horizon service-contract envelope: the guaranteed horizon
        t*(d) = longest window over which demand d is met with confidence
        >= 0.9, versus demand.  t*(d) steps down as demand crosses the
        capacity ladder; V2's steps sit at higher demand, so the fourth
        stand pushes the capacity cliff outward.
    """
    from matplotlib.lines import Line2D
    apply_nature_style()
    surv = read_csv("fig_sla_survival.csv")
    env = read_csv("fig_sla_envelope.csv")
    layouts = ["V1", "V2"]
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.0))

    # (a) SLA survival curves: layout = hue (blue/red), demand = line style
    ax = axes[0]
    for lay in layouts:
        for d in SLA_DEMANDS:
            pts = sorted((int(r["t_min"]), float(r["P_hold"])) for r in surv
                         if r["layout"] == lay and int(float(r["demand"])) == d)
            if not pts:
                continue
            ts, ps = zip(*pts)
            ax.plot(ts, ps, linestyle=SLA_DEMAND_STYLE[d], color=COLOURS[lay],
                    linewidth=1.9, marker=MARKERS[lay], markevery=4,
                    markersize=4, markerfacecolor=COLOURS[lay],
                    markeredgecolor="white", markeredgewidth=0.5,
                    clip_on=False, zorder=3)
    style_axis(ax, [0.0, 1.0], x_ticks=list(range(0, 721, 180)), x_lim=(0, 720))
    ax.set_ylim(0, 1.02)
    ax.set_xlabel("Horizon $t$ (min)")
    ax.set_ylabel(r"Probability of meeting demand $d$ up to $t$")
    combo_handles = [Line2D([0], [0], color=COLOURS[lay],
                            linestyle=SLA_DEMAND_STYLE[d], lw=2.0,
                            label=rf"{lay}, $d={d}$")
                     for lay in layouts for d in SLA_DEMANDS]
    leg = ax.legend(handles=combo_handles, loc="upper right",
                    frameon=True, framealpha=0.85, facecolor="white",
                    edgecolor="none", handlelength=3.4, handletextpad=0.6)
    leg.get_frame().set_linewidth(0.0)

    # (b) demand-horizon envelope: guaranteed horizon t*(d), V1 vs V2
    ax = axes[1]
    y_top = 0.0
    for lay in layouts:
        pts = sorted((float(r["demand"]), float(r["t_star"])) for r in env
                     if r["layout"] == lay)
        if not pts:
            continue
        ds, tstar = zip(*pts)
        y_top = max(y_top, max(tstar))
        ax.plot(ds, tstar, "-", color=COLOURS[lay], linewidth=1.9,
                marker=MARKERS[lay], markevery=2, markersize=4,
                markerfacecolor=COLOURS[lay], markeredgecolor="white",
                markeredgewidth=0.5, drawstyle="steps-post",
                clip_on=False, zorder=3, label=lay)
    ax.axvline(10, color="#888888", linestyle=":", linewidth=0.9, zorder=2)
    ax.annotate(r"$d=10$", (10, y_top * 1.02), textcoords="offset points",
                xytext=(3, -2), fontsize=6, color="#666666")
    style_axis(ax, [0.0, y_top], x_ticks=list(range(4, 16, 2)), x_lim=(4, 15))
    ax.set_ylim(0, y_top * 1.12)
    ax.set_xlabel("Demand $d$ (flights/hour)")
    ax.set_ylabel(r"Guaranteed horizon $t^*(d)$ (min), $p\geq0.9$")
    add_legend(ax)

    add_panel_labels(axes)
    fig.subplots_adjust(wspace=0.42)
    save_figure(fig, "fig_sla_resilience.png")


FIGS = {
    "fig1": fig1_oph_vs_n,
    "fig2": fig2_open_v1_v2,
    "fig3": fig3_resilience_depth,
    "fig4": fig4_pad_recovery,
    "fig5": fig5_compound_recovery,
    "fig6": fig6_standweather_compound,
    "fig_envelope": fig_envelope,
    "fig_sla_resilience": fig_sla_resilience,
}


if __name__ == "__main__":
    import sys

    selected = [a for a in sys.argv[1:] if not a.startswith("-")]
    unknown = [a for a in selected if a not in FIGS]
    if unknown:
        sys.exit(f"unknown figure(s): {', '.join(unknown)}. "
                 f"Choose from: {', '.join(FIGS)}")
    names = selected or list(FIGS)
    print("Generating figures ...")
    for name in names:
        FIGS[name]()
    print("Done. Figures in figures/.")

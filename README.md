# Formal Resilience Assessment of Vertiports under Stochastic Disruptions

A reproducible **formal-methods pipeline** for assessing the *resilience* of vertiport surface operations. Each vertiport layout is modelled once as a
**stochastic bigraphical reactive system (SBRS)**, compiled to a **continuous-time
Markov chain (CTMC)** with [BigraphER](https://www.dcs.gla.ac.uk/~michele/bigrapher.html#opam),
and analysed exactly by probabilistic model checking with [PRISM](https://www.prismmodelchecker.org/).
The same model family answers questions about nominal capacity, queueing delay,
single-fault sensitivity and recovery, **compound (concurrent) disruption**, and
**long-run service-level guarantees** — all through one shared metric layer.

---

## Why this work

Most quantitative studies of vertiport surface operations focus on **nominal**
performance — capacity, throughput, delay. Far less is known about how a vertiport
**degrades and recovers** when disruptions occur, and almost nothing about
**concurrent (compound)** disruptions, where more than one channel fails at once
(for example a closed Final Approach and Take-off area together with stands out of
service). Simulation can estimate averages, but it cannot *exhaustively* certify a
probabilistic guarantee such as *"service is restored within 30 minutes with
probability at least 0.9."*

This project takes a **formal-methods** stance instead:

- A single, compositional rule set covers three layouts and every disruption
  channel, so a new layout or fault is an edit of a few rules rather than a new model.
- Resilience is stated as **model-checkable temporal-logic requirements** and
  verified over the whole state space, giving exact probabilities and time bounds.
- Both faces of resilience are covered: **recovery** after a single compound
  disruption (does it return to normal in time?) and **retention** under
  recurrent disruption (how long is a demand service level maintained?).

## Highlights

- **One rule set, many models.** An SBRS compiles to CTMCs across three layouts
  (V1, V2, V3), two demand regimes (saturated and open/Poisson arrivals), and pad,
  stand, weather, and turnaround disruptions, including compound faults.
- **Verifiable resilience.** Recovery is formalised as
  `P=?[F<=t φ]` (return to normal within a deadline) and long-run service as
  `P=?[G<=t op(d)]` (demand `d` held throughout a horizon), both discharged by PRISM.
- **Design-relevant findings.** Capacity is stand-limited rather than FATO-limited;
  the slowest-to-repair resource governs recovery; and an extra stand pushes the
  "capacity cliff" outward, extending the horizon over which a service level can be
  guaranteed.

---

## Repository layout

```
eVTOL_Vertiport/
├── Vertiport_*.big              # SBRS models (saturated / open / sensitivity /
│                                #   recovery / compound / repairable availability)
├── scripts/
│   ├── run_analysis.py          # BigraphER -> PRISM -> analysis/*.csv
│   └── plot_results.py          # analysis/*.csv -> figures/*.png|svg
└── Queries.props                # documented PRISM query templates for manual runs
```

## Requirements

- [`bigrapher`](https://uog-bigraph.gitlab.io/bigrapher/) **≥ 2.0** on your `PATH`
- [`prism`](https://www.prismmodelchecker.org/) **≥ 4.9** on your `PATH`
- Python **3.8+** with `numpy`, `scipy`, and `matplotlib`

```bash
pip install numpy scipy matplotlib
# override binary locations if needed:
export BIGRAPHER=/path/to/bigrapher PRISM=/path/to/prism
```

## Quick start

```bash
cd eVTOL_Vertiport

# Generate CTMCs and model-check them -> analysis/*.csv
python3 scripts/run_analysis.py            # all modules, in pipeline order
python3 scripts/run_analysis.py --list     # list module names
python3 scripts/run_analysis.py capacity open   # run selected modules only

## How the pipeline works

1. **Model → CTMC.** `run_analysis.py` calls `bigrapher full` on each `.big`
   model, exporting a rate-labelled transition matrix (`.tra`), atomic-proposition
   labels (`.csl`), and state rewards (`.rews`) into `prism_files/`.
2. **Model checking.** It feeds those exports plus a query to PRISM. Six query
   forms cover every metric: steady-state `S=?[φ]`, long-run reward `R=?[S]`,
   transient reward `R=?[I=t]`, reachability `P=?[F<=t φ]`, cumulative reward
   `R=?[C<=t]`, and invariance `P=?[G<=t φ]`. `Queries.props` documents each one
   for manual runs.
3. **Tidy results.** Numeric results are written as one CSV per figure into
   `analysis/`, which `plot_results.py` turns into publication-ready PNG/SVG.

## Layouts

- **V1** — 1 FATO, 3 stands (baseline).
- **V2** — 1 FATO, 4 stands (adds one stand of redundancy).
- **V3** — 2 FATOs, 4 stands over a bidirectional U-shaped taxiway with passing bays.

## Acknowledgements

Built on [BigraphER](https://www.dcs.gla.ac.uk/~michele/bigrapher.html#opam) for bigraph
rewriting and CTMC export, and [PRISM](https://www.prismmodelchecker.org/) for
probabilistic model checking.

## License

The source code developed for this research is released under the MIT License.

If you use this code or reproduce the results in your research, please cite the paper:

```bibtex
@article{zhang2026vertiport,
  title   = {Formal Resilience Assessment of Vertiports under Stochastic Disruptions},
  author  = {Zhang, Tianxiong and Das, Susmoy and Sevegnani, Michele and
             Grzelak, Dominik and Erkek, Elif and Zhao, Dezong and A{\ss}mann, Uwe},
  year    = {2026}
}
```

# Vertiport BigraphER Model for Pad Capacity analysis

## What is Capacity - OPH ?

OPH is the number of operations (each **landing** and each **take-off** counts as one operation) completed per hour. Rates are per-minute so PRISM's steady-state/transient operators give genuine "per hour" numbers. 

## Models, scripts and outputs at a glance


| File                                                        | Role                                          |
| ----------------------------------------------------------- | --------------------------------------------- |
| `Vertiport_V1_1TLOF_3Stand_SBrs.big`                        | V1 saturated capacity                   |
| `Vertiport_V2_1TLOF_4Stand_SBrs.big`                        | V2 saturated capacity                   |
| `Vertiport_V3_2TLOF_4Stand_OneWay_SBrs.big`                 | V3 canonical saturated model       |
| `Vertiport_V3_2TLOF_4Stand_SBrs.big`                        | V3 abstract baseline   |
| `Vertiport_V1_Open_SBrs.big` / `Vertiport_V2_Open_SBrs.big` | Open M/M/c/K                           |
| `Vertiport_V1_Resilience_SBrs.big`                          | V1 multi-fault saturated resilience (fig4)    |
| `Queries.props`                                             | Documented PRISM query templates              |


## Vertiport 1 
```
                     ┌─────────────┐
                     │   Approach      │  
                     └──────┬──────┘
                              │
                        ┌─────▼─────┐ 
            ─────────── │ TLOF      │─────────
           │            │              │    │
           │            └─────┬─────┘    │
           │                                 │
       TaxiwayS1                         TaxiwayS2
           ▲                                 │
           │                                 ▼
           └───────── TaxiwayS3 ─────────────┘
                          │
        ┌─────────┬───────┼
        │         │       │       
   ┌────▼───┐┌────▼──┐┌───▼───┐
   │Stand 1 ││Stand 2││Stand 3│
   └────────┘└───────┘└───────┘
```

## Vertiport 2

```
                     ┌─────────────┐
                     │   Approach  │  
                     └──────┬──────┘
                              │
                        ┌─────▼─────┐ 
            ─────────── │ TLOF      │─────────
           │            │           │        │
           │            └─────┬─────┘        │
           │                                 │
       TaxiwayS1                         TaxiwayS2
           ▲                                 │
           │                                 ▼
           └───────── TaxiwayS3 ─────────────┘
                          │
        ┌─────────┬───────┼───────┬
        │         │       │       │  
   ┌────▼───┐┌────▼──┐┌───▼───┐┌──▼────┐
   │Stand 1 ││Stand 2││Stand 3││Stand 4│
   └────────┘└───────┘└───────┘└───────┘
```

## Vertiport 3

```
                     ┌─────────────┐
                     │   Approach      │ 
                     └──────┬──────┘
                            │
           ┌────────────────┴────────────────┐
           │                  │ 
     ┌─────▼─────┐                     ┌─────▼─────┐
     │ SmallTLOF │◄───  TaxiwayS2  ───►│ LargeTLOF │
     │     └─────┬─────┘                     └─────┬─────┘
           │                                 │
       TaxiwayS1                         TaxiwayS3
           ▲                                 │
           │                                 ▼
           └───────── TaxiwayS4 ─────────────┘
                          │
        ┌─────────┬───────┼───────┬
        │         │       │       │  
   ┌────▼───┐┌────▼──┐┌───▼───┐┌──▼────┐
   │Stand 1 ││Stand 2││Stand 3││Stand 4│
   └────────┘└───────┘└───────┘└───────┘
```


### Open-arrival V1/V2

`Vertiport_V1_Open_SBrs.big` and `Vertiport_V2_Open_SBrs.big` implement a truncated M/M/c/K system.  External arrivals occur with rate `arr_rate` into `Approach.AppN(a)` until the approach queue reaches `k_app`; when full, arrivals are blocked/lost.  Departures leave the system instead of recycling to approach.

The open models use the same service rates as the saturated V1/V2 models, so the comparison isolates the demand assumption:

- saturated closed loop: maximum sustainable capacity under always-present demand;
- open M/M/c/K: throughput, blocking probability, and delay under offered load `arr_rate`.

The open model includes a practical anti-gridlock gate: landing is allowed only when the inbound taxi counter has spare capacity, so an aircraft does not occupy the pad if it cannot vacate into the finite taxi queue.

### Run

```
bigrapher full \
  -c n_evtol=3 \
  -M 200000 \
  -p capa_3.tra \
  -l capa_3.csl \
  -r capa_3.rews \
  Vertiport_V1_1TLOF_3Stand_SBrs.big
```
- n_evtol=3,4,5.

Copy queries you would like to check from Queries.props to capa_3.csl.

```
prism -importtrans capa_3.tra capa_3.csl \
      -importstaterewards capa_3.rews \
      -ctmc \
      -prop 1 \
      -gs -maxiters 2000000
```

OPH (aircraft/hour) = results * 60 


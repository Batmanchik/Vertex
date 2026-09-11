# Метод: позиция, формулы и симулятор

> **Что это:** научная часть проекта в одном файле — на что мы претендуем и
> чем это доказывается (часть I), формальные обозначения и формулы (часть II),
> устройство симулятора (часть III).
>
> Собран из трёх прежних файлов: `RESEARCH_PLAN_RKNP_2026.md`,
> `CHEOPS_AI_SCIENTIFIC_FOUNDATION.md`, `SIMULATION_LAYER.md`.
>
> Числа отсюда не цитируются: действующие — в [RESULTS.md](RESULTS.md).
> Что делается и в каком порядке — в [../PLAN.md](../PLAN.md).

---

# Часть I. Научная позиция и гипотезы

Написано 2026-09-04. Аргумент остаётся в силе; числа внутри — того же числа и
пересчитаны после появления крипто-канала.

### 1. What the work claims

Not "we detect money mules" — they are already detected, and the contents of
the systems doing it are closed, so no honest comparison is possible.

> **We build an environment in which flow-based detection can be measured,
> and we measure where it breaks and what evasion costs.**

That claim rests on a published baseline (the four AFRD criteria), matches a
roadmap item the National Bank announced itself, and cannot be refuted by
pointing at proprietary industrial systems.

### 2. Context and the gap

| Fact | Value |
|---|---|
| Anti-Fraud Centre operating since | July 2024 |
| Connected participants | 200+ |
| Incidents registered by 2026-01-01 | 80 871 |
| Funds blocked | 2.8 bn KZT |
| Mule share of incidents | 6.87 % |
| Criminal cases since September 2025 | **needs verification** — see note |
| Dropper identification rules approved | April 2026 |

**Number of criminal cases: do not quote either figure yet.** Secondary
sources give both "700+ since September 2025" and "49 cases in four months,
13 sent to court", an order of magnitude apart — probably different offences
or different periods. Take the figure from the Prosecutor General's Office
or the Committee on Legal Statistics before it goes near a slide. Every
other number in the table above traces to a National Bank publication.

The April rules define a mule by four criteria: transfers to listed persons,
a shared phone, a shared IP or device, and deviation from the customer's usual
profile. All four are about **identity and device**; none is about the shape
of the money flow. A fresh network of clean accounts, each with its own phone,
none on any list, passes the first three, and the fourth requires a "usual
profile" a newly opened account does not have.

The National Bank's own development plan names the next stage: transition
"from reaction to prevention", **transactional antifraud at the level of
national payment systems**, AI for scheme forecasting. That stage does not
exist yet, so no data from it exists for anyone.

### 3. Two hypotheses

**H1 — unit of analysis.** Raising the unit from the account to the network
yields a larger gain than increasing model complexity at the same unit.

A mule network is not a property of an account: at that level there is an
ordinary student withdrawing money. Measured evidence already supports the
premise — account-level features give ROC-AUC 0.902 against hard negatives,
while `graph_relay_share` alone separates network cases at 0.494 vs 0.000.

**H2 — speed.** A fast detector with moderate recall saves more money than a
precise slow one.

Money leaves in minutes. The metric is therefore not "how many networks were
found" but **what share of value had already left at the moment of the alert**
— the same quantity the Anti-Fraud Centre reports.

Both are falsifiable by the same grid of measurements.

### 4. Architecture

```
Layer 0  SIMULATION          events only: who paid whom, how much, when
         8 honest populations (4 confusable) + 2 fraudulent structures
                  |
Layer 1  FEATURES            derived by the detector, never by the generator
         account · neighbourhood · network, over a sliding window
                  |
Layer 2  DETECTOR LADDER     rules -> logistic -> forest -> boosting -> graph
         plus an unsupervised branch
                  |
Layer 3  ADVERSARIAL EVAL    evasion curves · time to alert · value lost
```

Window width `W` is the scale parameter: minutes for mule networks, months
for pyramids. The same code covers both, which is what makes the old nine
features a special case of the new layer rather than discarded work.

### 5. Status — 2026-09-06

| Component | State |
|---|---|
| Layer 0 simulator | **done**, accepted, tests |
| Acceptance criterion | **done**, second gate added after the first proved weak |
| Account-level features | **done** — `experiments/ladder.py` |
| Real graph and sequence features | **done** — `ml/event_features_v2.py` |
| Legacy nine from raw events | **done** — `ml/legacy_features_v2.py` |
| Case builder | replaced by blind discovery with a reported ceiling |
| Detector ladder on real matrices | **done** — E1/E2, `experiments/ladder.py` |
| Published-rule baseline | **done** — `ml/baseline_afrd.py`, three of four criteria |
| Ladder of worlds W1–W5 | **done** — `experiments/ladder_of_worlds.py` |
| Five standard diagnostics | **done** — `reporting/diagnostics.py` |
| Evasion sweep | two points measured, curve open |
| Realistic base rate (E11) | **open, and it is the next thing** |
| Crypto typologies in the generator | open — delegated |
| Online evaluation (E6, E7) | open |

Measured results and what each one does not prove: **`docs/RESULTS.md`**.

#### The week-3 checkpoint fired, and here is the answer

§9 says that if the network level does not beat the account level, that is
reported as the finding rather than hidden. It fired, and the answer turned
out to be more useful than either half of H1.

The network unit **does** beat the account unit — 0.965 to 0.999 against
0.965 to 0.982 — on every rung it can see at all. It does not then degrade
under evasion. It **disappears**: at six independent funders and four
terminals, discovery no longer places even two members of most rings into one
candidate, median overlap 1.000 → 0.000. The account unit does not notice,
0.9648 → 0.9646.

So neither unit dominates. One is stronger; the other is the one that
survives an adversary who pays. H1 as worded — that the unit matters more
than the model — is not what was found, and the finding that replaced it
prices both sides of the exchange, which is a better sentence to defend.

### 6. Experiments

Core — the work does not exist without these.

| # | Experiment | Output |
|---|---|---|
| E1 | Baseline (AFRD-4) vs the ladder | first measured answer to "why ML" |
| E2 | Effect of the unit of analysis, full grid | key table, tests H1 |
| E3 | Detectability curve over `funders` | main figure; look for the knee |

Extension — added on top of a standing bench.

| # | Experiment | Output |
|---|---|---|
| E4 | Curves over the other three knobs | which dial is cheapest for the fraudster |
| E5 | Two-dimensional evasion surface | where to place friction |
| E6 | Time to alert, per ladder cell | distribution; the tail matters |
| E7 | Share of value already gone | tests H2; comparable with AFC reporting |
| E8 | Single-bank vs three-bank view | quantifies the value of interbank exchange |
| E9 | One detector across two scales via `W` | tests the unifying idea |
| E10 | Labelled vs unlabelled | applicability where labels do not exist |
| E11 | Base rate at 6.87 %, 1 %, 0.5 %, 0.1 % | analyst workload |
| E12 | Distribution shift | robustness |
| E13 | Proxy-discrimination check on age | ethics section becomes a measurement |
| E14 | Curve translated into a countermeasure | the practical conclusion |

### 7. Ethics

Mules are usually recruited, often minors, frequently victims rather than
organisers. Three rules, all implemented rather than merely stated:

- **Age is not a model feature.** It exists in the data for exactly one
  purpose: E13, which checks whether the model learned it indirectly through
  behaviour. Using it directly would be proxy discrimination.
- **The target is the organiser.** The correct output is "a network of forty
  accounts with a common source", not "account 17 is suspicious". This is both
  more accurate and defensible.
- **Prioritisation, not verdict.** The system ranks cases for human review.

### 8. Limits, stated before they are asked about

- The data is synthetic. Absolute figures such as "we find 96 %" are not
  claimed and must not appear on a slide. Only **comparative** statements are
  made, and those are fully provable inside a controlled environment.
- **The generator is still written by us.** Separating events from features
  removes the crudest circularity, but what counts as fraudulent behaviour is
  still our model of it. The circle widens; it does not open. Only real data
  closes it.
- FIFO matching of inflows to outflows is a design decision, not a fact:
  money is fungible and the assignment is not identifiable.
- Prior art exists — PaySim, AMLSim. The difference here is Kazakh mechanics
  (ATM cash-out as the exit point) and measurement against the four published
  AFRD criteria.

### 9. Schedule

| Weeks | Work |
|---|---|
| 1–2 | port account-level features; honest referral business; wire real matrices into `engine_v2` |
| 3 | E1 and E2. **Checkpoint: does the network level beat the account level?** |
| 4–5 | E3, then E6 and E7 |
| 6–7 | write-up, ~30 pages |
| 8 | polish, hostile review, rehearsal |

The science must be finished by the end of week 5. That is the one deadline
that cannot move: a paper cannot be written without results, and results
cannot be defended without a paper.

**Checkpoint rule.** If at the end of week 3 the network level does not beat
the account level, the hypothesis is wrong and that is reported as the
finding — not hidden, not re-fitted until it passes.

---

# Часть II. Формальная часть: обозначения и формулы

Написано 21 марта 2026, под прежним названием проекта. **Это спецификация, а
не отчёт о работающем коде:** описана целевая архитектура, включая семейство
LightGBM; две ветви из трёх сейчас идут эвристическими заместителями. Где этот
текст расходится с системой — см. разрыв в [../PLAN.md](../PLAN.md).

### 1. Purpose
This document formalizes the current Cheops AI methodology:
- mathematical definitions and notation;
- what is treated as "pyramid-like" behavior in the model;
- formulas for feature engineering and scoring;
- branch fusion, calibration, and drift control.

Important: this is an operational/ML definition for risk screening, not a legal qualification.

### 2. Notation
- Event: `e_i`
- Case window: `W(c, H)` where `c` is `case_id`, `H` is window length in hours
- Number of events: `n = |W|`
- Event amount: `a_i > 0`
- Event timestamp: `t_i`
- Sender/receiver ids: `s_i`, `r_i`
- Global binary target in training: `y in {0, 1}`
- Typology target for typology `k`: `y_k in {0, 1}`
- Global risk score: `p_global in [0, 1]`

### 3. Data Contract Level
Canonical event schema (`TransactionEvent`) includes:
- `event_id, ts, amount, currency, sender_id, receiver_id, sender_type, receiver_type, channel, jurisdiction, asset_type`
- optional: `tx_hash, case_id, metadata`

Channel domain: `channel in {"legal", "crypto"}`.

Case window construction:
- sort events by `ts`,
- keep only events in last `H` hours from `end_ts`,
- resulting object: `CaseWindow(case_id, events, start_ts, end_ts, window_hours)`.

### 4. Operational Facts -> Model Features
For operational inputs:
- `new_clients_current`,
- `new_clients_previous`,
- `referred_clients_current`,
- `incoming_funds`,
- `payouts_total`,
- `top1_wallet_share`,
- `top10_wallet_share`,
- `avg_holding_days`,
- `repeat_investor_share`,
- `unique_counterparties`,
- `tx_count_total`,
- `max_referral_depth`.

Core formulas:
- `growth_rate = (new_clients_current - new_clients_previous) / max(new_clients_previous, 1)`
- `referral_ratio = referred_clients_current / max(new_clients_current, 1)`
- `payout_dependency = payouts_total / max(incoming_funds, 1)`
- `centralization_index = top1_wallet_share`
- `avg_holding_time = avg_holding_days`
- `reinvestment_rate = repeat_investor_share`
- `gini_coefficient = 0.12 + 0.72 * top10_wallet_share + 0.22 * top1_wallet_share`
- `entropy_ratio = log(1 + unique_counterparties) / log(1 + max(tx_count_total, unique_counterparties + 1))`
- `transaction_entropy = 0.3 + 4.7 * entropy_ratio * (1 - 0.55 * top1_wallet_share)`
- `structural_depth = max_referral_depth`

Each feature is clipped to predefined bounds (`FEATURE_BOUNDS`).

### 5. What Is "Pyramid-Like" in Current ML System
Cheops AI currently uses three layers of evidence:

1. Statistical class (`y=1`) in training data:
- synthetic "pyramid-like" distribution is generated with higher:
  - growth,
  - referral share,
  - payout dependency,
  - centralization,
  - inequality (`gini`),
  - depth;
- and lower entropy / lower holding time than legitimate profiles.

2. Rule-typology layer from event graph/time behavior:
- deterministic event-level labels (Section 6).

3. Continuous risk layer:
- final `p_global` from multi-branch fusion (Section 9).

Operationally, a case is treated as pyramid-like/high-risk if:
- `p_global` enters `HIGH`/`CRITICAL` band, and
- typology probabilities show strong mass on route-related suspicious patterns.

### 6. Event-Level Typology Rules (Deterministic Labels)
The current event mapper produces labels:

- `LEGAL_TO_CRYPTO_BRIDGE = 1` iff both channels exist in case (`legal` and `crypto`).
- `STRUCTURED_SPLITTING = 1` iff:
  - unique receivers `>= 5`, and
  - count of small parts `>= max(4, floor(n/3))`,
  - where "small part" means `a_i < 0.35 * mean(a)`.
- `CRYPTO_MIXING = 1` iff:
  - number of crypto events `>= 6`,
  - unique crypto receivers `>= 4`.
- `LEGAL_LAYERING = 1` iff:
  - directed graph depth `>= 4`,
  - legal events count `>= 3`.
- `CASH_OUT = 1` iff:
  - outgoing share from company/legal sender types `>= 0.62`,
  - `n >= 6`.

### 7. Typology Targets for Tabular Training
Besides event rules, tabular branch creates typology targets from features:

- `LEGAL_LAYERING_raw = ((depth >= 8.0) and (central >= 0.45)) or ((gini >= 0.62) and (payout >= 0.85))`
- `LEGAL_TO_CRYPTO_BRIDGE_raw = ((payout >= 0.92) and (entropy <= 2.35)) or ((growth >= 0.23) and (holding <= 40.0))`
- `CRYPTO_MIXING_raw = ((entropy <= 2.2) and (reinvest >= 0.56)) or ((central >= 0.58) and (depth >= 7.0))`
- `STRUCTURED_SPLITTING_raw = ((referral >= 0.52) and (depth >= 7.0)) or ((growth >= 0.28) and (entropy <= 2.6))`
- `CASH_OUT_raw = ((payout >= 1.00) and (holding <= 32.0)) or ((central >= 0.56) and (gini >= 0.68))`

Fallback signal for low-positive-rate balancing:
- `fallback = 0.55 * y_global + 0.25 * payout + 0.20 * central`

If a typology has too few positives, top fallback-ranked rows are promoted to keep minimum positive rate.

### 8. Branch Models
#### 8.1 Tabular Branch
- Model family: LightGBM binary classifiers.
- Heads:
  - global head (`p_tabular_global`),
  - one head per typology (`p_tabular_k`).
- Calibration: isotonic regression per head.

#### 8.2 Sequence Branch
Two modes:
- trained surrogate (`cheops_v2_sequence.joblib`) if available,
- heuristic fallback otherwise.

Training matrix from normalized tabular features (`x~`):
- `event_rate_hour = 0.08 + 0.92 * (0.42*growth~ + 0.19*referral~ + 0.19*depth~ + 0.20*reinvest~)`
- `burst_ratio_90s = 0.05 + 0.95 * (0.46*growth~ + 0.31*holding_short~ + 0.23*entropy_low~)`
- `median_delta_inverse = 0.06 + 0.94 * (0.44*holding_short~ + 0.30*entropy_low~ + 0.26*growth~)`
- `amount_cv_norm = 0.05 + 0.95 * (0.37*central~ + 0.34*payout~ + 0.29*gini~)`
- `unique_sender_ratio = 0.04 + 0.96 * (0.43*referral~ + 0.30*depth~ + 0.27*(1-central~))`

Runtime extraction from events:
- `span_hours = max((end_ts - start_ts), 60 sec) / 3600`
- `rate = n / span_hours`
- `event_rate_hour = 1 - exp(-rate / 4)`
- `burst_ratio_90s = count(delta_t <= 90 sec) / max(n-1, 1)`
- `median_delta_inverse = 1 / (1 + median(delta_t_minutes)/60)`
- `amount_cv_norm = min((std(amount)/mean(amount))/2, 1)`
- `unique_sender_ratio = |unique_senders| / max(n, 1)`

Sequence heuristic score:
- `p_seq_heur = 0.39*event_rate_hour + 0.29*burst_ratio_90s + 0.20*median_delta_inverse + 0.07*amount_cv_norm + 0.05*unique_sender_ratio`

#### 8.3 Graph Branch
Two modes:
- trained surrogate (`cheops_v2_graph.joblib`) if available,
- heuristic fallback otherwise.

Training matrix from normalized tabular features:
- `graph_density = 0.05 + 0.95*(0.38*central~ + 0.34*depth~ + 0.28*entropy_low~)`
- `graph_hub_share = 0.04 + 0.96*(0.55*central~ + 0.30*gini~ + 0.15*payout~)`
- `graph_component_compactness = 0.06 + 0.94*(0.42*depth~ + 0.34*referral~ + 0.24*(1-entropy_low~))`
- `graph_transitivity = 0.03 + 0.97*(0.40*central~ + 0.32*depth~ + 0.28*referral~)`
- `graph_weight_cv_norm = 0.05 + 0.95*(0.47*gini~ + 0.31*payout~ + 0.22*central~)`

Runtime extraction from event graph:
- `graph_density = density(G)`
- `graph_hub_share = max_in_degree / sum_in_degree`
- `graph_component_compactness = 1 / number_of_weakly_connected_components`
- `graph_transitivity = transitivity(undirected(G))` if nodes `>= 3`, else `0`
- `graph_weight_cv_norm = min((std(edge_weight)/mean(edge_weight))/2, 1)`

Graph heuristic score:
- `p_graph_heur = 0.34*hub_share + 0.30*density + 0.18*compactness + 0.10*transitivity + 0.08*weight_cv_norm`

### 9. Fusion and Final Risk
If fusion artifact exists:
- logistic meta-model on `[p_tabular, p_sequence, p_graph]`,
- then isotonic calibration.

Fallback fusion (deterministic):
- `p_global = 0.58*p_tabular + 0.22*p_sequence + 0.20*p_graph`

Risk bands in v2 runtime:
- `CRITICAL`: `p_global >= 0.85`
- `HIGH`: `0.70 <= p_global < 0.85`
- `MEDIUM`: `0.45 <= p_global < 0.70`
- `LOW`: `p_global < 0.45`

### 10. Calibration and Reliability Metrics
Per branch/head:
- ROC-AUC
- Brier score
- ECE (Expected Calibration Error)

ECE formula (histogram bins):
- let bins be `B_j`,
- `conf_j = mean(p_i | i in B_j)`,
- `acc_j = mean(y_i | i in B_j)`,
- `w_j = |B_j| / N`,
- then `ECE = sum_j w_j * |acc_j - conf_j|`.

### 11. Drift Control (PSI)
For each feature:
- baseline histogram rates `q_j`,
- current histogram rates `p_j`,
- `PSI = sum_j (q_j - p_j) * ln(q_j / p_j)`.

Thresholds:
- `PSI < 0.10`: stable
- `0.10 <= PSI < 0.25`: moderate drift
- `PSI >= 0.25`: high drift

Overall drift is the mean PSI across model features.

### 12. Explainability Outputs
`/api/v2/explain` returns:
- `summary`,
- `tabular_factors`,
- `sequence_factors`,
- `graph_factors`,
- `branch_scores` (`tabular`, `sequence`, `graph`, `fusion`),
- `branch_modes` (trained vs fallback),
- `confidence`.

This allows analyst and judge to trace not only final score but branch-level contribution.

### 13. Current Limitations (Important for Judges)
- Current high metrics are on synthetic benchmark data; external domain validation is a separate phase.
- "Pyramid-like" is an ML operational label, not a final legal verdict.
- Typology thresholds are currently rule-based/engineered and should be refined on real labeled cases.

### 14. Reproducibility References
- Feature/threshold definitions: `src/apris/risk_engine.py`, `src/apris/data_generator.py`
- Typology rules: `src/apris/cheops/domain/contracts.py`
- Tabular branch: `src/apris/cheops/infrastructure/ml/tabular_v2.py`
- Sequence branch: `src/apris/cheops/infrastructure/ml/sequence_v2.py`
- Graph branch: `src/apris/cheops/infrastructure/ml/graph_v2.py`
- Fusion: `src/apris/cheops/infrastructure/ml/fusion_v2.py`
- Drift: `src/apris/cheops/infrastructure/ml/drift_v2.py`
- Runtime scorer: `src/apris/cheops/infrastructure/ml/engine_v2.py`

---

# Часть III. Симулятор (слой 0)

Написано 2026-09-04. Реализовано, принято, покрыто 21 тестом. Крипто-канал
добавлен позже (задача 3.8); дробление сумм не порождается до сих пор (3.10),
поэтому срабатывают четыре типологии из пяти.

### 1. What it is

`src/apris/cheops/infrastructure/simulation/` generates a synthetic world of
accounts, ATMs and transactions with known ground truth, so that detectors
can be built and compared on data whose answers are known exactly.

It exists because the next stage of anti-fraud in Kazakhstan — transactional
antifraud at the level of national payment systems, announced by the National
Bank — does not exist yet. No data from that stage exists for anyone,
including the regulator. Simulation is therefore not a substitute for real
data here; it is the only instrument available for the problem.

### 2. The rule the whole layer obeys

**The generator writes only events. Every feature is derived by the detector.**

Not one metric is written into the stream. No `transit`, no `gini`, no
`time_to_cashout`. A generator that writes `gini = 0.67` into a pyramid's row
hands the answer to the model, which then reads it instead of finding it —
and the resulting accuracy measures nothing at all. That is precisely how the
previous generation of this project produced 0.96 that could not be defended.

Ground truth (network membership, population labels, the referral tree) is
returned in a separate structure and never reaches the event stream. A test
pins this.

### 3. What the world contains

Eight honest populations, four of which are deliberately confusable with
fraud, plus two fraudulent structures.

| Population | Behaviour | Why it exists |
|---|---|---|
| Salary earner | monthly income, gradual spending | ordinary negative |
| Freelancer | income from many distinct payers | breaks "many new counterparties" |
| Trader | many small sales, periodic large cash-out | breaks "large cash withdrawal" |
| **Fast spender** | money arrives, fully withdrawn in minutes | **hard negative 1** — indistinguishable from a mule at account level |
| **Marketplace seller** | a new unknown buyer every time, then cash | **hard negative 2** — breaks "unknown counterparty" |
| Family circle | transfers inside a small closed group | breaks dense-community signals |
| **Crowd collection** | ~40 people send to one, spent over weeks | **hard negative 3** — honest fan-in |
| **Employer** | pays all staff on one payday | **hard negative 4** — honest fan-out |
| Mule network | source → mules → ATM inside minutes | positive, fast scale |
| Pyramid | payouts funded by inflow, referral tree | positive, slow scale |

The two scales are one invariant at different observation windows: transit
without own income, compressed into minutes or stretched over months.

### 4. Evasion knobs

`EvasionKnobs` are the dials that make a network less visible. Each carries a
real cost to the organiser, and the cost — not the dial — is what the study
reports.

| Knob | Range | Breaks | Cost to the organiser |
|---|---|---|---|
| `funders` | 1 → 40 | shared source | each funder is a real account with real money |
| `terminals` | 1 → 20 | convergence on one exit | driving people across the city |
| `time_spread_minutes` | 2 → 480 | temporal tightness | the operation stops being fast |
| `split_factor` | 1 → 10 | amount thresholds | more operations, more traces |

### 5. Acceptance criterion — the check that must not be skipped

`simulation/acceptance.py`. Three naive rules must each **misfire on honest
people**, and two of them must still catch the fraud:

```
[OK] A misfires on the fast-spending student   601/650
[OK] B misfires on the payday employer          25/25
[OK] C misfires on the whip-round               25/40
[OK] A still catches mules                     372/531
[OK] B still catches the network source          11/24
```

If the rules stop misfiring, the generator has become too kind and every
result built above it describes a fiction.

**The first version of this criterion was too weak and is documented here so
the mistake is not repeated.** It checked that naive *rules* misfire — and
they did — while a gradient boosting model on the same account-level features
still separated the classes at ROC-AUC 1.0000. Rules failing is not evidence
that a task is hard. A second gate exists now:
`ACCOUNT_LEVEL_AUC_CEILING = 0.90` in `config.py`.

### 6. Side finding, pinned by a test

The most intuitive graph rule — "many senders into one account" — catches
**0 of 531 mules** while flagging 25 of 40 honest whip-rounds.

In a mule network the fan spreads *out* from the source and converges on the
*ATM*; the mule account itself sees no convergence at all. The first idea that
comes to mind when looking at a transaction graph gives zero recall and
maximum false positives simultaneously.

### 7. How to use it

```python
from apris.cheops.infrastructure.simulation import generate_world, SimulationConfig
from apris.cheops.infrastructure.simulation.cases import build_cases
from apris.cheops.infrastructure.simulation.acceptance import evaluate

world = generate_world(SimulationConfig())     # ~2 minutes at full scale
report = evaluate(world)                        # acceptance criterion
cases = build_cases(world)                      # labelled cases for detectors
```

Full-scale generation produces roughly 320 000 events over 23 000 accounts,
54 networks, with a mule share of personal accounts near the 6.87 % reported
by the Anti-Fraud Centre.

For tests use a reduced config — see `tests/unit/test_simulation_layer.py`.
Note that the fan-out rule needs at least ~20 employees per employer, so a
shrunken fixture must keep that ratio or acceptance check B cannot fire.

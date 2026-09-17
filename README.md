# Vertex (Multi-Channel Fraud Intelligence System)

> **Three documents, and that is the whole set.** [PLAN.md](PLAN.md) — the
> target, the gap to it, the queue of work and the rules agents work by;
> [docs/RESULTS.md](docs/RESULTS.md) — every measurement, with what it does not
> prove; this README — how to run the thing. Everything else is reference:
> [docs/DEFENCE.md](docs/DEFENCE.md), [docs/METHOD.md](docs/METHOD.md),
> [docs/CHECKLISTS.md](docs/CHECKLISTS.md), `docs/reviews/`, `docs/work/`, and
> `docs/archive/`, which must not be quoted.

Vertex is a local MVP for detection of multi-channel financial fraud patterns (legal + crypto).
It combines ML risk scoring, ETL for transaction logs, and a FastAPI service that
also serves the whole project as one local site.

## Where the project stands

Four facts a new session needs before reading anything else. The full gap
analysis is [PLAN.md](PLAN.md) §2.

- **Every measured number in this repository comes from a random forest**
  (`ml/case_pipeline.py`), not from the three-branch LightGBM ensemble. The
  ensemble's code exists; two of its three branches currently run heuristic
  proxies and say so in `branch_modes`. Retraining them is task 4.2, and it
  will move every number in `docs/RESULTS.md`.
- **No run against real labelled data has happened.** The Elliptic adapter and
  its tests are in the repo, the data is not. The one transfer test that was
  run came back negative (`graph_relay_share`, AUC 0.515) and is reported as a
  result rather than buried.
- **The `W` parameter is implemented and measured, but not wired in.** Its
  measured lift was −0.0022, below the shuffled control, so the project's own
  rule kept it out of the feature set.
- **Four of five typologies are generated.** Amount structuring is task 3.10.

None of this is a defect list. It is the difference between the system as
described in the research paper (the target) and the system as it runs today,
and closing it is what `PLAN.md` §8 orders.

## Current Architecture
- `src/apris/` - core backend and ML modules.
- `src/apris/api/main.py` - FastAPI REST API (`/api/v1/*`, `/api/v2/*`).
- `src/apris/cheops/` - v2 clean architecture layers (`domain`, `application`, `infrastructure`, `interfaces`).
- `src/apris/risk_engine.py` - model inference, feature validation, explainability.
- `src/apris/etl.py` - CSV/JSON ingestion and operational-to-feature transformation.
- `src/apris/train_model.py` - model training, metrics, artifact export, MLflow logging.
- `src/apris/cheops/infrastructure/ml/tabular_v2.py` - tabular v2 bundle training (global + typology + isotonic calibration).
- `src/apris/web/site.py` - the site: every section, every chart, built from
  `artifacts/*.json`. Served by the API at `/` and written to a file by
  `scripts/make_site.py`.
- `src/apris/web/data.py` - the one reader of the run artifacts.
- `src/apris/web/model_export.py` - the trained model in a form the browser can
  walk, so the page scores without a server.
- `tests/` - pytest-based test suite (`unit`, `api`, `smoke`).

## Runtime vs Source Directories
- Source code: `src/`, `tests/`, `scripts/`.
- Runtime/generated data: `artifacts/`, `mlruns/`, `.run/`.
- Virtual environments/backups: `.venv/`, `.venv_*`.

This repository keeps runtime directories for local experimentation. They are not required for code review and can be regenerated.

## Dependency Source of Truth
- Canonical dependency spec: `pyproject.toml` (`[project.dependencies]` and `[project.optional-dependencies].dev`).
- `requirements.txt` is kept in sync for convenience and mirrors runtime dependencies from `pyproject.toml`.

## Run (PowerShell)

```powershell
.\scripts\app.ps1 start     # rebuilds the queue, serves the site on 127.0.0.1:8000
.\scripts\app.ps1 status
.\scripts\app.ps1 open
.\scripts\app.ps1 stop
```

One process, one address. Logs go to `.run/api.out.log` and `.run/api.err.log`,
the pid to `.run/api.pid`.

## Run (Docker Compose)

```bash
docker compose up -d --build
docker compose ps
```

Open `http://127.0.0.1:8000` — the site and the API are one service. Stop with
`docker compose down -v`. Runtime folders are mounted from the host:
`./artifacts`, `./mlruns`, `./.run`.

## Train Model
Train on synthetic data:

```powershell
.\.venv\Scripts\python.exe -m apris.train_model
```

Train on external data via ETL (`csv` or `json`):

```powershell
.\.venv\Scripts\python.exe -m apris.train_model --data your_real_data.csv
```

External datasets are validated for required training fields (`FEATURE_COLUMNS + label`) and do not require synthetic-only column `is_borderline`.

Training exports both legacy and v2 tabular artifacts:
- `artifacts/model.joblib` + `artifacts/feature_names.json` (legacy v1 path).
- `artifacts/cheops_v2_tabular.joblib` + `artifacts/cheops_v2_metrics.json` (Cheops v2 tabular branch).
- `artifacts/cheops_v2_sequence.joblib` + `artifacts/cheops_v2_sequence_metrics.json` (Cheops v2 trainable sequence branch).
- `artifacts/cheops_v2_graph.joblib` + `artifacts/cheops_v2_graph_metrics.json` (Cheops v2 trainable graph branch).
- `artifacts/cheops_v2_fusion_meta.joblib` + `artifacts/cheops_v2_fusion_metrics.json` (Cheops v2 logistic fusion meta-head).
- `artifacts/cheops_v2_feature_profile.json` (baseline feature profile for drift monitoring).
- `artifacts/cheops_v2_model_registry.json` (model governance registry with selected candidate and branch metrics).
- `cheops_v2_metrics.json` contains calibration-aware metrics (`roc_auc`, `brier`, `ece`) for global and typology heads.
- `cheops_v2_sequence_metrics.json` contains sequence branch metrics and heuristic fallback comparison.
- `cheops_v2_graph_metrics.json` contains graph branch metrics and heuristic fallback comparison.
- `cheops_v2_fusion_metrics.json` contains calibration-aware metrics for the fusion layer and weighted-fallback comparison.

Optional benchmark run:

```powershell
.\.venv\Scripts\python.exe -m apris.train_model --benchmark
.\.venv\Scripts\python.exe -m apris.train_model --benchmark --benchmark-lightgbm-only
```

Benchmark report artifact:
- `artifacts/cheops_v2_benchmark.json`.
- Each candidate now records calibration metric `ece` in addition to `roc_auc`, `accuracy`, and `brier`.
- Benchmark now stores explicit `selection_policy`, candidate `selection_score`, ranking, and `winner_reason`.

Optional drift check against another feature dataset:

```powershell
.\.venv\Scripts\python.exe -m apris.train_model --drift-data your_features_snapshot.csv
```

Drift artifact:
- `artifacts/cheops_v2_drift_report.json` with `overall_psi`, per-feature `psi`, and drift level (`stable|moderate|high`).

Runtime inference behavior for v2:
- If `cheops_v2_sequence.joblib` exists, sequence score uses calibrated trained surrogate branch.
- If sequence artifact is absent, sequence score falls back to deterministic heuristic.
- If `cheops_v2_graph.joblib` exists, graph score uses calibrated trained surrogate branch.
- If graph artifact is absent, graph score falls back to deterministic heuristic.
- If `cheops_v2_fusion_meta.joblib` exists, engine uses calibrated logistic fusion head for `global_risk`.
- If fusion artifact is absent, engine falls back to deterministic weighted fusion (v1-compatible behavior).

## Run it (one command, one address)

```
python scripts/serve.py          # http://127.0.0.1:8000
```

That address **is** the project. Everything lives on that one page: what the
system is and how it works, the world and its typologies, discovery, a
candidate's dossier, validation, a form that scores live against the same
process, the analyst queue, every measurement with what it does not prove, the
six defects found in our own work, the gap to the target, and the questions the
panel will ask. There is no second interface to keep in sync — the Streamlit
one was removed, along with the second address and its lag.

The page is rebuilt from `artifacts/*.json` on every request: recompute a run,
refresh the tab.

## The same page as a file

```
python scripts/make_site.py
```

Writes `artifacts/site/index.html`: the same page, self-contained — no server,
no network, no fonts to fetch, images embedded. Open it by double-clicking,
from a memory stick, on someone else's laptop with the wi-fi off.

Everything works there, the scoring form included. The v1 model is gradient
boosting over 300 trees of depth 6 — thresholds and numbers, nothing a browser
cannot walk — so `src/apris/web/model_export.py` dumps the trees into the page
and the browser scores. It is the model, not an approximation of it: the export
is checked against `predict_proba` on 500 random points and on the bounds of
every feature, and agrees to within 1e-5. A split shape the walk cannot
reproduce fails the build rather than quietly scoring something else.

## The same page on the web

Published from `main` to <https://batmanchik.github.io/Vertex/> by
`.github/workflows/site.yml`. The workflow runs the site tests before it
publishes: a showcase that silently reads "no run" is worse than no showcase,
because nobody double-checks the one they were given a link to.

## The queue on its own

```
python scripts/run_pipeline.py --preset full --target-recall 0.8
```

World, discovery, features, detector, threshold — one call, writing
`artifacts/analyst_queue.json`. The threshold is read off the earlier
walk-forward folds and the queue is cut on the last one, which the model
never trained on, so the precision it reports is the precision it would have
on Monday. The queue's LENGTH is an output, not a setting: that is the
prevalence result (R6) made operational, since a fixed review budget is the
wrong policy once fraud is rare.

`scripts/serve.py` runs this for you before it opens the port.

## What the site deliberately does not do

Three things, each a defect that was removed rather than a precaution: draw a
graph built from the features it claims to support, draw a structure derived
from the verdict, or report a metric computed on a grouping the detector was
handed in advance. `tests/unit/test_site.py` checks that the page asks the
network for nothing, that a missing run is called a missing run rather than
drawn as a zero, and that every number on it came from an artifact.

## Case-Level Baseline

```powershell
python scripts/case_baseline.py --seed 42
```

Rebuilds the candidate-classification numbers from scratch — discovery,
features from events, purged walk-forward — and prints everything the
write-up is allowed to quote about case-level detection. Written because the
audit carried a baseline that no committed code reproduced.

## Simulation Layer and Event Features

`src/apris/cheops/infrastructure/simulation/` generates a synthetic world of
accounts, ATMs and transactions with known ground truth. It writes **events
only** — who paid whom, how much, when. Every feature is derived by the
detection layers from those events; the generator never writes a metric.

`src/apris/cheops/infrastructure/ml/event_features_v2.py` computes graph and
sequence features from that stream. It replaces the `*_from_tabular` builders,
which produced structural and temporal matrices as hand-written linear
combinations of nine period aggregates — so the graph branch never read a
graph and `burst_ratio_90s` was derived from a quantity measured in days.

```python
from apris.cheops.infrastructure.simulation import generate_world, SimulationConfig
from apris.cheops.infrastructure.simulation.acceptance import evaluate
from apris.cheops.infrastructure.simulation.cases import build_cases

world = generate_world(SimulationConfig())   # ~2 min, ~320k events
report = evaluate(world)                      # layer-0 acceptance criterion
cases = build_cases(world)                    # labelled cases for detectors
```

Details: [docs/METHOD.md](docs/METHOD.md), part III.
Measured findings: [docs/reviews/AUDIT_FINDINGS_2026-09-04.md](docs/reviews/AUDIT_FINDINGS_2026-09-04.md).
Plan: [PLAN.md](PLAN.md).

## Test and Quality Workflow

Run every gate CI runs, in the same order:

```powershell
python scripts/check_all.py           # everything
python scripts/check_all.py --fast    # skip the slow test suite
```

Running a subset and reading it as "the gates pass" has now cost three red CI
runs in a day: ruff, mypy and pytest passing says nothing about bandit, and
bandit is what failed. The script also distinguishes FAIL from SUSPECT — a
gate that fails while printing nothing is almost always a broken console
script rather than broken code, which is exactly what `lint-imports.exe` did
after the project directory was renamed.

Install dev tools:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Run tests:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m pytest -m smoke
```

Run quality checks:

```powershell
.\.venv\Scripts\python.exe -m ruff check src tests pages
.\.venv\Scripts\python.exe -m ruff format --check src tests pages
.\.venv\Scripts\python.exe -m mypy
```

Enable pre-commit hooks:

```powershell
.\.venv\Scripts\python.exe -m pre_commit install
```

## API Surface
Versioned API contract:
- `GET /api/v1/health`
- `POST /api/v1/predict`
- `POST /api/v1/predict/ops`
- `POST /api/v1/explain`
- `GET /api/v1/meta/features`
- `GET /api/v2/meta/typologies`
- `GET /api/v2/health/model`
- `GET /api/v2/health/model/details`
- `GET /api/v2/health/runtime`
- `POST /api/v2/score`
- `POST /api/v2/score/batch`
- `POST /api/v2/explain`

`/api/v2/explain` now includes branch-level outputs:
- `branch_scores` (`tabular`, `sequence`, `graph`, `fusion`)
- `branch_modes` (whether each branch is trained or fallback mode)

Operational observability:
- API responses include `X-Request-Id` header for request tracing.
- `/api/v2/health/runtime` returns aggregated runtime counters and per-endpoint latency/error snapshots.

## Release Readiness
- Regression and operational release checklist: [docs/CHECKLISTS.md](docs/CHECKLISTS.md).
- Scientific methodology and formulas: [docs/METHOD.md](docs/METHOD.md).

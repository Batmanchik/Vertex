"""Task 4.11 — measure the case level on a panel instead of one date per case.

    python scripts/run_case_panel.py                 # one world
    python scripts/run_case_panel.py --seeds 3       # three, pooled

Builds the panel (every candidate described at every date it was scorable by),
then scores two protocols that answer different questions, with two detectors
in each so the choice of model is measured rather than asserted:

  time forward   fit on the grid up to a date, score the dates after it. The
                 same cases sit on both sides — that is the deployment mode,
                 and the share of shared cases is printed.
  case holdout   hold out whole cases, score every date of them. Groups the
                 model has never met.

Writes artifacts/case_panel.json. Prevalence per fold is part of the report:
it is the number that exposed defect 6, and it is cheaper to print it than to
find the defect again.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import average_precision_score, roc_auc_score

from apris.cheops.infrastructure.ml.case_panel import (
    CasePanel,
    PanelSplit,
    build_case_panel,
    case_holdout_splits,
    prevalence_drift,
    time_forward_splits,
)
from apris.cheops.infrastructure.simulation import SimulationConfig, generate_world

OUT = Path("artifacts") / "case_panel.json"


def _forest(seed: int) -> RandomForestClassifier:
    return RandomForestClassifier(
        n_estimators=300, min_samples_leaf=2, random_state=seed, n_jobs=-1
    )


def _lightgbm(seed: int) -> Any:
    import lightgbm as lgb

    return lgb.LGBMClassifier(
        n_estimators=180,
        learning_rate=0.05,
        max_depth=5,
        min_child_samples=8,
        random_state=seed,
        n_jobs=-1,
        verbose=-1,
    )


DETECTORS = {"forest": _forest, "lightgbm": _lightgbm}


def _score(panel: CasePanel, splits: Sequence[PanelSplit], detector: str, seed: int) -> dict:
    scores: list[float] = []
    labels: list[int] = []
    per_fold: list[dict[str, Any]] = []

    for split in splits:
        x_train = panel.features.iloc[list(split.train)]
        y_train = panel.labels[list(split.train)]
        x_test = panel.features.iloc[list(split.test)]
        y_test = panel.labels[list(split.test)]
        if len(np.unique(y_train)) < 2 or len(np.unique(y_test)) < 2:
            continue

        model = DETECTORS[detector](seed)
        model.fit(x_train, y_train)
        fold_scores = model.predict_proba(x_test)[:, 1]
        scores.extend(float(value) for value in fold_scores)
        labels.extend(int(value) for value in y_test)
        per_fold.append(
            {
                "fold": split.index,
                **split.size,
                "prevalence": round(float(y_test.mean()), 4),
                "shared_case_share": split.shared_case_share,
                "roc_auc": round(float(roc_auc_score(y_test, fold_scores)), 4),
            }
        )

    if not labels:
        return {"pooled_roc_auc": None, "folds": []}
    return {
        "pooled_roc_auc": round(float(roc_auc_score(labels, scores)), 4),
        "pooled_pr_auc": round(float(average_precision_score(labels, scores)), 4),
        "rows_scored": len(labels),
        "positives": int(sum(labels)),
        "folds": per_fold,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--days", type=int, default=120)
    parser.add_argument("--cadence-days", type=int, default=7)
    args = parser.parse_args()

    started = time.time()
    report: dict[str, Any] = {
        "task": "4.11 case panel",
        "cadence_days": args.cadence_days,
        "worlds": [],
    }

    for offset in range(max(1, args.seeds)):
        seed = args.seed + offset
        world = generate_world(SimulationConfig(seed=seed, days=args.days))
        panel = build_case_panel(world)
        forward = time_forward_splits(panel)
        holdout = case_holdout_splits(panel, seed=seed)

        shares = list(panel.prevalence_by_date().values())
        entry: dict[str, Any] = {
            "seed": seed,
            "rows": panel.size,
            "cases": panel.cases,
            "dates": len(panel.grid),
            "fraud_share": round(panel.base_rate, 4),
            "fraud_share_by_date": {
                "min": round(min(shares), 4) if shares else None,
                "max": round(max(shares), 4) if shares else None,
            },
            "time_forward": {
                "prevalence": prevalence_drift(panel, forward),
                **{name: _score(panel, forward, name, seed) for name in DETECTORS},
            },
            "case_holdout": {
                "prevalence": prevalence_drift(panel, holdout),
                **{name: _score(panel, holdout, name, seed) for name in DETECTORS},
            },
        }
        report["worlds"].append(entry)

        print(
            f"seed {seed}: {panel.size} rows over {len(panel.grid)} dates, "
            f"{panel.cases} cases, fraud {panel.base_rate:.1%} "
            f"(per date {entry['fraud_share_by_date']['min']}–"
            f"{entry['fraud_share_by_date']['max']})"
        )
        for protocol in ("time_forward", "case_holdout"):
            line = entry[protocol]
            shared = [fold["shared_case_share"] for fold in line["forest"]["folds"]]
            print(
                f"  {protocol:>13}: forest {line['forest']['pooled_roc_auc']}, "
                f"lightgbm {line['lightgbm']['pooled_roc_auc']}, "
                f"prevalence {line['prevalence'].get('min')}–{line['prevalence'].get('max')}, "
                f"shared cases {min(shared) if shared else '—'}–{max(shared) if shared else '—'}"
            )

    report["runtime_seconds"] = round(time.time() - started, 1)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"written: {OUT}  ({report['runtime_seconds']} s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

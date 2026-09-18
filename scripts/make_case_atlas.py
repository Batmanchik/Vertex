"""Атлас дел: где лежат 46 564 размеченных дела Elliptic и куда попадёт новое.

    python scripts/make_case_atlas.py [--limit N]

Зачем. На защите даётся две минуты, и за это время нужно показать не таблицу
метрик, а то, как система принимает решение. Атлас показывает сразу обе
вещи: распределение оценок по всем реальным делам набора Elliptic — четыре с
половиной тысячи незаконных и сорок две тысячи обычных — и точку, в которую
попадает дело, собранное ползунками прямо на странице.

Что пишется в artifacts/case_atlas.json:

* гистограмма оценок отдельно для незаконных и обычных дел;
* сама модель в форме, которую обходит браузер (scripts/../web/model_export);
* границы и медианы шестнадцати признаков формы — ползунки стартуют с
  медианы, а не с нуля, иначе стартовое дело не похоже ни на что реальное.

Оценки берутся out-of-fold из того же purged walk-forward, которым получено
0.687: дело оценивается моделью, которая его не видела. Модель, уезжающая в
страницу, обучается отдельно на всех делах — она нужна только для новой
точки, а не для отчётных чисел.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from apris.cheops.infrastructure.experiments.elliptic_probe import (
    DEFAULT_PURGE_STEPS,
    DEFAULT_SPLITS,
    FEATURE_SETS,
    HEADLINE_ARM,
    build_rows,
    walk_forward,
)
from apris.cheops.infrastructure.external.elliptic import (
    DEFAULT_DATA_DIR,
    download_if_missing,
    ensure_time_steps,
    load_elliptic,
)

OUT = Path("artifacts") / "case_atlas.json"
BINS = 40


def histogram(values: list[float]) -> list[int]:
    counts, _ = np.histogram(values, bins=BINS, range=(0.0, 1.0))
    return [int(value) for value in counts]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    args = parser.parse_args()

    download_if_missing(args.data_dir)
    ensure_time_steps(args.data_dir)
    graph = load_elliptic(args.data_dir)

    names = FEATURE_SETS[HEADLINE_ARM]
    rows = build_rows(graph, hops=2, cap=400, limit=args.limit, seed=42)
    print(f"дел собрано: {len(rows)}, из них незаконных {sum(r.label for r in rows)}")

    folds = walk_forward(
        rows, names, seed=42, n_splits=DEFAULT_SPLITS, purge_steps=DEFAULT_PURGE_STEPS)
    illicit: list[float] = []
    licit: list[float] = []
    for fold in folds:
        for score, label in zip(fold.scores, fold.labels):
            (illicit if label == 1 else licit).append(float(score))
    print(f"оценок вне обучения: незаконных {len(illicit)}, обычных {len(licit)}")

    # Модель для новой точки учится на всех делах: отчётные числа она не даёт.
    from sklearn.ensemble import RandomForestClassifier

    matrix = np.array([[row.features[name] for name in names] for row in rows], dtype=float)
    labels = np.array([row.label for row in rows], dtype=int)
    model = RandomForestClassifier(
        n_estimators=30, min_samples_leaf=120, random_state=42, n_jobs=-1)
    model.fit(matrix, labels)

    report = {
        "task": "атлас дел Elliptic",
        "arm": HEADLINE_ARM,
        "features": list(names),
        "cases": {"total": len(rows), "illicit": len(illicit), "licit": len(licit)},
        "bins": BINS,
        "histogram": {"illicit": histogram(illicit), "licit": histogram(licit)},
        "percentiles": {
            "illicit": [round(float(np.percentile(illicit, p)), 4) for p in (10, 25, 50, 75, 90)],
            "licit": [round(float(np.percentile(licit, p)), 4) for p in (10, 25, 50, 75, 90)],
        },
        "bounds": {
            name: {
                "min": round(float(matrix[:, index].min()), 4),
                "max": round(float(matrix[:, index].max()), 4),
                "median": round(float(np.median(matrix[:, index])), 4),
            }
            for index, name in enumerate(names)
        },
        "forest": {
            "trees": [
                {
                    "feature": tree.tree_.feature.tolist(),
                    "threshold": [round(float(v), 4) for v in tree.tree_.threshold],
                    "left": tree.tree_.children_left.tolist(),
                    "right": tree.tree_.children_right.tolist(),
                    "value": [
                        round(float(v[0][1] / max(1.0, v[0].sum())), 4)
                        for v in tree.tree_.value
                    ],
                }
                for tree in model.estimators_
            ],
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    size = OUT.stat().st_size / 1024
    print(f"записано: {OUT} ({size:.0f} КБ)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Кривые детектора: ROC, precision-recall, калибровка, распределение оценок.

    python scripts/run_detector_curves.py                 # мир по умолчанию
    python scripts/run_detector_curves.py --days 30       # быстрее, для проверки

Пишет artifacts/detector_curves.json — то, из чего витрина рисует кривые.

Метрики в experiment_ladder.json сворачивают оценки модели в два числа,
ROC-AUC и average precision. Кривая требует сами оценки, поэтому здесь тот же
проход out-of-fold по purged walk-forward, но сохраняются точки, а не сводка.
Обе стороны зовут одну функцию ``out_of_fold_scores``, чтобы не разъехаться.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    precision_recall_curve,
    roc_auc_score,
    roc_curve,
)

from apris.cheops.infrastructure.experiments.ladder import (
    SEED,
    build_account_rows,
    build_network_rows,
    out_of_fold_scores,
)
from apris.cheops.infrastructure.simulation.config import SimulationConfig
from apris.cheops.infrastructure.simulation.discovery import (
    discover_candidates,
    label_candidates,
)
from apris.cheops.infrastructure.simulation.generator import generate_world

OUT_PATH = Path("artifacts") / "detector_curves.json"

# Кривая из тысяч точек весит много и на экране всё равно неотличима от
# кривой из полутора сотен: точки прореживаются равномерно по индексу.
MAX_POINTS = 160


def _thin(values: np.ndarray, limit: int = MAX_POINTS) -> np.ndarray:
    if len(values) <= limit:
        return np.arange(len(values))
    return np.unique(np.linspace(0, len(values) - 1, limit).astype(int))


def _roc(truths: np.ndarray, scores: np.ndarray) -> list[dict[str, float]]:
    fpr, tpr, _ = roc_curve(truths, scores)
    idx = _thin(fpr)
    return [{"x": round(float(fpr[i]), 5), "y": round(float(tpr[i]), 5)} for i in idx]


def _pr(truths: np.ndarray, scores: np.ndarray) -> list[dict[str, float]]:
    precision, recall, _ = precision_recall_curve(truths, scores)
    idx = _thin(recall)
    return [
        {"x": round(float(recall[i]), 5), "y": round(float(precision[i]), 5)} for i in idx
    ]


def _calibration(truths: np.ndarray, scores: np.ndarray, bins: int = 10) -> list[dict]:
    """Насколько оценка похожа на вероятность.

    Пустые корзины не выбрасываются, а помечаются: пустота в верхней половине
    шкалы — это тоже результат, он говорит, что модель туда никого не ставит.
    """
    edges = np.linspace(0.0, 1.0, bins + 1)
    out: list[dict] = []
    for i in range(bins):
        low, high = edges[i], edges[i + 1]
        mask = (scores >= low) & (scores < high) if i < bins - 1 else (scores >= low)
        count = int(mask.sum())
        out.append(
            {
                "low": round(float(low), 3),
                "high": round(float(high), 3),
                "count": count,
                "mean_score": round(float(scores[mask].mean()), 5) if count else None,
                "fraud_share": round(float(truths[mask].mean()), 5) if count else None,
            }
        )
    return out


def _histogram(truths: np.ndarray, scores: np.ndarray, bins: int = 20) -> list[dict]:
    edges = np.linspace(0.0, 1.0, bins + 1)
    honest, _ = np.histogram(scores[truths == 0], bins=edges)
    fraud, _ = np.histogram(scores[truths == 1], bins=edges)
    return [
        {
            "low": round(float(edges[i]), 3),
            "high": round(float(edges[i + 1]), 3),
            "honest": int(honest[i]),
            "fraud": int(fraud[i]),
        }
        for i in range(bins)
    ]


def _budget_points(truths: np.ndarray, scores: np.ndarray) -> list[dict]:
    """Что достаётся аналитику при списке фиксированной длины.

    Эта таблица отвечает на вопрос, который ROC-AUC не задаёт: если проверять
    только верхние N процентов списка, сколько из проверенных окажутся
    мошенниками и какую долю мошенников мы при этом поймаем.
    """
    order = np.argsort(-scores)
    sorted_truth = truths[order]
    total_positive = int(truths.sum())
    out: list[dict] = []
    for share in (0.01, 0.02, 0.05, 0.10, 0.20, 0.30, 0.50):
        take = max(1, int(round(len(scores) * share)))
        caught = int(sorted_truth[:take].sum())
        precision = caught / take
        out.append(
            {
                "budget_share": share,
                "reviewed": take,
                "caught": caught,
                "precision": round(precision, 5),
                "recall": round(caught / total_positive, 5) if total_positive else None,
                "reviews_per_catch": round(1.0 / precision, 3) if precision else None,
            }
        )
    return out


def _block(rows, scope: str, model: str) -> dict | None:
    scores, truths, folds = out_of_fold_scores(rows, scope, model)
    if len(truths) == 0 or len(np.unique(truths)) < 2:
        return None
    scores = np.asarray(scores, dtype=float)
    truths = np.asarray(truths, dtype=int)
    # Правила выдают счётчик срабатываний, а не вероятность: для кривых его
    # надо привести к [0, 1], иначе шкала калибровки не имеет смысла.
    span = scores.max() - scores.min()
    normalised = (scores - scores.min()) / span if span > 0 else np.zeros_like(scores)
    return {
        "scope": scope,
        "model": model,
        "rows": len(truths),
        "positives": int(truths.sum()),
        "base_rate": round(float(truths.mean()), 5),
        "folds": folds,
        "roc_auc": round(float(roc_auc_score(truths, scores)), 5),
        "average_precision": round(float(average_precision_score(truths, scores)), 5),
        "brier": round(float(brier_score_loss(truths, normalised)), 5),
        "roc": _roc(truths, scores),
        "pr": _pr(truths, scores),
        "calibration": _calibration(truths, normalised),
        "histogram": _histogram(truths, normalised),
        "budget": _budget_points(truths, scores),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--mule-networks", type=int, default=30)
    parser.add_argument("--pyramids", type=int, default=8)
    parser.add_argument("--crowd-collections", type=int, default=40)
    parser.add_argument("--family-circles", type=int, default=70)
    parser.add_argument("--employers", type=int, default=25)
    parser.add_argument("--terminals", type=int, default=60)
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    args = parser.parse_args()

    started = time.time()
    config = SimulationConfig(
        seed=args.seed,
        days=args.days,
        mule_networks=args.mule_networks,
        pyramids=args.pyramids,
        crowd_collections=args.crowd_collections,
        family_circles=args.family_circles,
        employers=args.employers,
        terminals=args.terminals,
    )

    world = generate_world(config)
    candidates = discover_candidates(world)
    labels, discovery = label_candidates(world, candidates)
    account_rows, ceiling = build_account_rows(world)
    _, structural_rows = build_network_rows(world, candidates, labels)

    wanted = [
        (account_rows, "account", "forest"),
        (account_rows, "account", "logistic"),
        (account_rows, "account", "rules"),
        (structural_rows, "network_structural", "forest"),
    ]

    blocks = []
    for rows, scope, model in wanted:
        print(f"{scope} / {model} ...", flush=True)
        block = _block(rows, scope, model)
        if block:
            blocks.append(block)

    report = {
        "detector": "forest-v1",
        "generated_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat(timespec="seconds"),
        "seed": args.seed,
        "seconds": round(time.time() - started, 2),
        "world": world.summary(),
        "discovery": {
            "coverage": discovery.coverage,
            "networks_total": discovery.networks_total,
            "networks_covered": discovery.networks_covered,
        },
        "account_ceiling": {
            "coverage": ceiling.coverage,
            "fraud_scored": ceiling.fraud_scored,
            "fraud_total": ceiling.fraud_total,
            "accounts_scored": ceiling.accounts_scored,
            "accounts_total": ceiling.accounts_total,
        },
        "blocks": blocks,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nwritten to {args.out} in {report['seconds']}s")
    for block in blocks:
        print(
            f"  {block['scope']:<20}{block['model']:<10}"
            f"AUC {block['roc_auc']:.4f}  AP {block['average_precision']:.4f}  "
            f"rows {block['rows']}  pos {block['positives']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

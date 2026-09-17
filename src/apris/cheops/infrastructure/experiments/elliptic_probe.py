"""Task 4.1 — does the shape of the flow carry signal on real labelled fraud?

Every number this project reports comes from a simulator we wrote. Separating
events from features removed the crudest circularity, but what counts as
fraudulent is still our model of it. Elliptic is the one public dataset with
real transactions, real fraud labels and graph structure at once, so it is the
only instrument available for opening that circle.

What is measured here
---------------------
One claim: **do the structural features separate illicit from licit nodes on
real data, out of time?** The unit of analysis is a labelled node with its
two-hop neighbourhood treated as one case, exactly as on simulated worlds.

Three arms run side by side, and all three are reported:

``structural``
    the five shape features alone. This is the claim under test.
``structural_plus_local``
    the same five plus how busy the node itself is. Included because a bank
    would have those columns anyway, and because it separates "the shape
    carries signal" from "activity carries signal".
``control``
    the structural arm with labels shuffled inside each training fold. A
    feature set that cannot beat its own shuffled control is not a feature
    set, and the project's rule says so; here the control also catches a
    leaking split, which is what an unexplained 0.99 would be.

What cannot be measured here, and why
-------------------------------------
*Amounts.* The 165 feature columns are anonymised, so value-weighted variants
are unavailable and every feature is computed by edge count. A result on one
is evidence about the other, not proof.

*Speed.* Time resolution is 49 steps of roughly two weeks each. Nothing in the
sequence branch survives that: ``burst_ratio_90s`` cannot be evaluated on a
series whose finest tick is a fortnight. The speed hypothesis is untestable on
this dataset and is not tested.

*Account semantics.* Elliptic nodes are transactions in Bitcoin's UTXO model,
not accounts. Relaying is what that graph is made of rather than a shape that
distinguishes anything, so a null result here has an explanation that does not
generalise to bank accounts. This is stated before the run, not after it.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_auc_score

from apris.cheops.infrastructure.external.elliptic import (
    RICH_FEATURE_NAMES,
    STRUCTURAL_FEATURE_NAMES,
    EllipticGraph,
    neighbourhood,
    rich_features,
    structural_features,
)

LOCAL_FEATURE_NAMES: tuple[str, ...] = ("in_degree", "out_degree", "case_size")

# Четыре руки, и первая остаётся ради сравнения: без неё нельзя сказать,
# насколько расширенный набор лучше, а «стало лучше» без числа — не результат.
FEATURE_SETS: dict[str, tuple[str, ...]] = {
    "structural": STRUCTURAL_FEATURE_NAMES,
    "structural_plus_local": STRUCTURAL_FEATURE_NAMES + LOCAL_FEATURE_NAMES,
    "shape": RICH_FEATURE_NAMES,
    "shape_plus_local": RICH_FEATURE_NAMES + LOCAL_FEATURE_NAMES,
}

# Рука, числом которой отчитываются: чистая форма, без активности узла.
# Проверяется гипотеза «форму потока поменять нельзя», а не «сколько
# столбцов есть в наборе».
HEADLINE_ARM = "shape"

DEFAULT_SPLITS = 5
DEFAULT_PURGE_STEPS = 1  # one Elliptic step ≈ two weeks
DEFAULT_TARGET_RECALL = 0.8
MIN_TRAIN_STEPS = 9


@dataclass(frozen=True)
class CaseRow:
    """One labelled node with its neighbourhood reduced to features."""

    node: str
    time_step: int
    label: int
    features: dict[str, float]


@dataclass
class FoldResult:
    fold: int
    train_steps: tuple[int, int]
    test_steps: tuple[int, int]
    purged_steps: tuple[int, ...]
    n_train: int
    n_test: int
    prevalence: float
    roc_auc: float | None
    scores: list[float] = field(default_factory=list)
    labels: list[int] = field(default_factory=list)


def build_rows(
    data: EllipticGraph,
    *,
    hops: int = 2,
    cap: int = 400,
    limit: int | None = None,
    seed: int = 42,
) -> list[CaseRow]:
    """Turn every labelled node into one case.

    Nodes without a time step are dropped rather than assigned one: the split
    is temporal, and a case with an invented timestamp lands on whichever side
    of the boundary the invention puts it.
    """
    nodes = data.labelled_nodes()
    if limit is not None and limit < len(nodes):
        picked = np.random.default_rng(seed).choice(len(nodes), size=limit, replace=False)
        nodes = [nodes[int(index)] for index in picked]

    rows: list[CaseRow] = []
    for node in nodes:
        step = data.time_steps.get(node)
        if step is None:
            continue
        subgraph = neighbourhood(data.graph, node, hops=hops, cap=cap)
        features = dict(structural_features(subgraph))
        features.update(rich_features(subgraph, node))
        features["in_degree"] = float(data.graph.in_degree(node))
        features["out_degree"] = float(data.graph.out_degree(node))
        features["case_size"] = float(subgraph.number_of_nodes())
        rows.append(
            CaseRow(node=node, time_step=step, label=data.labels[node], features=features)
        )
    return rows


def _matrix(rows: Sequence[CaseRow], names: Sequence[str]) -> np.ndarray:
    return np.array([[row.features[name] for name in names] for row in rows], dtype=float)


def _labels(rows: Sequence[CaseRow]) -> np.ndarray:
    return np.array([row.label for row in rows], dtype=int)


def single_feature_auc(rows: Sequence[CaseRow], names: Iterable[str]) -> dict[str, float]:
    """AUC of each feature on its own, for continuity with the 2026-09 probe.

    In sample, and labelled as such: it says what a column separates, not what
    survives a time split. The out-of-fold model numbers are the result.
    """
    labels = _labels(rows)
    if len(set(labels.tolist())) < 2:
        return {}
    out: dict[str, float] = {}
    for name in names:
        column = np.array([row.features[name] for row in rows], dtype=float)
        if float(column.std()) == 0.0:
            out[name] = 0.5
            continue
        out[name] = float(roc_auc_score(labels, column))
    return out


def _step_blocks(steps: Sequence[int], n_splits: int) -> list[tuple[int, int]]:
    """Contiguous blocks of time steps, one per fold."""
    unique = sorted(set(steps))
    if len(unique) <= MIN_TRAIN_STEPS + 1:
        return []
    usable = unique[MIN_TRAIN_STEPS:]
    width = max(1, len(usable) // n_splits)
    blocks: list[tuple[int, int]] = []
    for index in range(n_splits):
        start = index * width
        if start >= len(usable):
            break
        end = len(usable) if index == n_splits - 1 else min(len(usable), start + width)
        blocks.append((usable[start], usable[end - 1]))
    return blocks


def walk_forward(
    rows: Sequence[CaseRow],
    feature_names: Sequence[str],
    *,
    n_splits: int = DEFAULT_SPLITS,
    purge_steps: int = DEFAULT_PURGE_STEPS,
    seed: int = 42,
    shuffle_labels: bool = False,
) -> list[FoldResult]:
    """Purged walk-forward over Elliptic's time steps.

    Train on every step before the block, test on the block, and drop the
    ``purge_steps`` steps immediately before it. The gap is the analogue of
    the five-day purge used on simulated worlds: a case is a neighbourhood,
    its members sit on both sides of a boundary, and one Elliptic step is
    about a fortnight.
    """
    blocks = _step_blocks([row.time_step for row in rows], n_splits)
    rng = np.random.default_rng(seed)
    results: list[FoldResult] = []

    for index, (first, last) in enumerate(blocks):
        purged = tuple(range(max(1, first - purge_steps), first))
        train_rows = [row for row in rows if row.time_step < first and row.time_step not in purged]
        test_rows = [row for row in rows if first <= row.time_step <= last]
        if not train_rows or not test_rows:
            continue

        y_train = _labels(train_rows)
        if shuffle_labels:
            y_train = rng.permutation(y_train)
        y_test = _labels(test_rows)

        result = FoldResult(
            fold=index,
            train_steps=(min(row.time_step for row in train_rows), first - 1 - len(purged)),
            test_steps=(first, last),
            purged_steps=purged,
            n_train=len(train_rows),
            n_test=len(test_rows),
            prevalence=float(y_test.mean()),
            roc_auc=None,
        )

        if len(set(y_train.tolist())) < 2 or len(set(y_test.tolist())) < 2:
            results.append(result)
            continue

        model = RandomForestClassifier(
            n_estimators=300, min_samples_leaf=2, random_state=seed, n_jobs=-1
        )
        model.fit(_matrix(train_rows, feature_names), y_train)
        scores = model.predict_proba(_matrix(test_rows, feature_names))[:, 1]
        result.scores = [float(value) for value in scores]
        result.labels = [int(value) for value in y_test]
        result.roc_auc = float(roc_auc_score(y_test, scores))
        results.append(result)

    return results


def threshold_for_recall(
    scores: Sequence[float], labels: Sequence[int], target_recall: float
) -> float | None:
    """Lowest threshold that still reaches the target recall, on past folds."""
    positives = [score for score, label in zip(scores, labels) if label == 1]
    if not positives:
        return None
    ordered = sorted(positives, reverse=True)
    index = min(len(ordered) - 1, max(0, int(round(target_recall * len(ordered))) - 1))
    return float(ordered[index])


def operating_point(
    scores: Sequence[float], labels: Sequence[int], threshold: float
) -> dict[str, float]:
    flagged = [label for score, label in zip(scores, labels) if score >= threshold]
    total_positive = sum(labels)
    caught = sum(flagged)
    precision = (caught / len(flagged)) if flagged else 0.0
    recall = (caught / total_positive) if total_positive else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {
        "threshold": float(threshold),
        "flagged": float(len(flagged)),
        "recall": float(recall),
        "precision": float(precision),
        "f1": float(f1),
    }


def _arm_report(
    rows: Sequence[CaseRow],
    feature_names: Sequence[str],
    *,
    seed: int,
    n_splits: int,
    purge_steps: int,
    target_recall: float,
    shuffle_labels: bool = False,
) -> dict:
    folds = walk_forward(
        rows,
        feature_names,
        n_splits=n_splits,
        purge_steps=purge_steps,
        seed=seed,
        shuffle_labels=shuffle_labels,
    )
    scored = [fold for fold in folds if fold.roc_auc is not None]
    pooled_scores = [score for fold in scored for score in fold.scores]
    pooled_labels = [label for fold in scored for label in fold.labels]

    report: dict = {
        "features": list(feature_names),
        "folds": [
            {
                "fold": fold.fold,
                "train_steps": list(fold.train_steps),
                "test_steps": list(fold.test_steps),
                "purged_steps": list(fold.purged_steps),
                "n_train": fold.n_train,
                "n_test": fold.n_test,
                "prevalence": round(fold.prevalence, 4),
                "roc_auc": round(fold.roc_auc, 4) if fold.roc_auc is not None else None,
            }
            for fold in folds
        ],
        "pooled_roc_auc": (
            round(float(roc_auc_score(pooled_labels, pooled_scores)), 4)
            if len(set(pooled_labels)) > 1
            else None
        ),
        "mean_fold_roc_auc": (
            round(float(np.mean([fold.roc_auc for fold in scored])), 4) if scored else None
        ),
        "prevalence": round(float(np.mean(pooled_labels)), 4) if pooled_labels else None,
    }

    # The operating point is priced the way the pipeline prices it: the
    # threshold comes off the earlier folds and is applied to the last one,
    # which the model that scored it never trained on.
    if len(scored) >= 2:
        past_scores = [score for fold in scored[:-1] for score in fold.scores]
        past_labels = [label for fold in scored[:-1] for label in fold.labels]
        last = scored[-1]
        threshold = threshold_for_recall(past_scores, past_labels, target_recall)
        if threshold is not None:
            point = operating_point(last.scores, last.labels, threshold)
            report["operating_point"] = {
                **point,
                "target_recall": target_recall,
                "test_steps": list(last.test_steps),
                "prevalence": round(last.prevalence, 4),
            }
    return report


def run_probe(
    data: EllipticGraph,
    *,
    hops: int = 2,
    cap: int = 400,
    limit: int | None = None,
    seed: int = 42,
    n_splits: int = DEFAULT_SPLITS,
    purge_steps: int = DEFAULT_PURGE_STEPS,
    target_recall: float = DEFAULT_TARGET_RECALL,
) -> dict:
    """Run all three arms and return the report as written to disk."""
    started = time.time()
    rows = build_rows(data, hops=hops, cap=cap, limit=limit, seed=seed)
    build_seconds = time.time() - started

    arms = {
        name: _arm_report(
            rows,
            names,
            seed=seed,
            n_splits=n_splits,
            purge_steps=purge_steps,
            target_recall=target_recall,
        )
        for name, names in FEATURE_SETS.items()
    }
    # Контроль ставится на ту руку, числом которой отчитываются: контроль на
    # другом наборе признаков измеряет не тот запас.
    arms["control_shuffled_labels"] = _arm_report(
        rows,
        FEATURE_SETS[HEADLINE_ARM],
        seed=seed,
        n_splits=n_splits,
        purge_steps=purge_steps,
        target_recall=target_recall,
        shuffle_labels=True,
    )

    structural = arms[HEADLINE_ARM]["pooled_roc_auc"]
    control = arms["control_shuffled_labels"]["pooled_roc_auc"]
    return {
        "task": "4.1 Elliptic probe",
        "dataset": data.summary(),
        "cases": {
            "rows": len(rows),
            "illicit": sum(row.label for row in rows),
            "prevalence": round(sum(row.label for row in rows) / len(rows), 4) if rows else None,
            "hops": hops,
            "cap": cap,
            "limit": limit,
            "build_seconds": round(build_seconds, 1),
        },
        "protocol": {
            "detector": "RandomForestClassifier(n_estimators=300, min_samples_leaf=2)",
            "split": "purged walk-forward over Elliptic time steps",
            "n_splits": n_splits,
            "purge_steps": purge_steps,
            "threshold_policy": (
                f"chosen on earlier folds at recall {target_recall}, applied to the last"
            ),
            "seed": seed,
        },
        "single_feature_auc_in_sample": {
            name: round(value, 4)
            for name, value in single_feature_auc(
                rows, FEATURE_SETS["shape_plus_local"]
            ).items()
        },
        "arms": arms,
        "margin_over_control": (
            round(structural - control, 4)
            if structural is not None and control is not None
            else None
        ),
        "runtime_seconds": round(time.time() - started, 1),
    }


def write_report(report: dict, path: Path) -> Path:
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return path

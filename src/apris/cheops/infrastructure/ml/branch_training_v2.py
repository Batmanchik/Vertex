"""Task 4.2 — train the sequence and graph branches on what they are served.

The defect this closes
----------------------
Both branches were fitted by ``build_*_matrix_from_tabular``: hand-written
linear combinations of nine daily aggregates, wearing the names of event
features. At inference the same branches read real events. A model fitted on
one distribution and served another is not a weak model, it is a model
answering a different question, and nothing in the response says so — the
service only reports that the branch is *trained*.

So the branches are fitted here on the matrices they are actually served:
candidates proposed by blind discovery, features computed from their events,
labels attached afterwards.

How the split is drawn
----------------------
Time-ordered, never random. Candidates are sorted by when they finished; the
earliest ``train_share`` fit the model, the next ``val_share`` fit the
isotonic calibrator, the remainder is held out and scored. A purge gap sits
between fit and calibration and between calibration and test, because a
candidate spans a window of events and the window straddles a boundary.

Two protocols, and both are reported
------------------------------------
``within_world``
    the time-ordered split described above, inside each world.
``across_worlds``
    leave-one-world-out: fit on every other world, score the held-out one
    whole.

They disagree, and the disagreement is the finding. Candidates are dated by
their **last** event, so a structure that runs for months lands at the end of
its world's timeline; fraud rises from 2.9 % of the first quarter of the
candidate list to 33.3 % of the last. A within-world time split therefore fits
on an almost fraud-free slice and is scored on a fraud-heavy one, with the
feature directions flipping between them. The across-worlds protocol has no
such shift — worlds are independent draws — and there both branches land near
0.985 while the heuristics they replace read 0.096 and 0.500.

Neither number is the truth on its own. The first is pessimistic for a reason
that is an artefact of how a case is dated; the second ignores time inside a
world. Both go into ``docs/RESULTS.md`` with that sentence attached.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import roc_auc_score

from apris.cheops.infrastructure.ml.event_features_v2 import (
    GRAPH_FEATURE_COLUMNS,
    SEQUENCE_FEATURE_COLUMNS,
)
from apris.cheops.infrastructure.ml.graph_v2 import (
    DEFAULT_GRAPH_MODEL_PARAMS,
    GRAPH_FEATURE_NAMES,
)
from apris.cheops.infrastructure.ml.sequence_v2 import (
    DEFAULT_SEQUENCE_MODEL_PARAMS,
    SEQUENCE_FEATURE_NAMES,
)

DEFAULT_TRAIN_SHARE = 0.6
DEFAULT_VAL_SHARE = 0.2
DEFAULT_PURGE = timedelta(days=3)

# The weights each branch falls back to when no artifact is present. Kept
# here so the comparison is against the thing actually served, not against a
# freshly invented baseline.
GRAPH_HEURISTIC_WEIGHTS: dict[str, float] = {
    "graph_hub_share": 0.34,
    "graph_density": 0.30,
    "graph_fanout_share": 0.18,
    "graph_relay_share": 0.10,
    "graph_weight_cv_norm": 0.08,
}
SEQUENCE_HEURISTIC_WEIGHTS: dict[str, float] = {
    "event_rate_hour": 0.39,
    "burst_ratio_90s": 0.29,
    "median_delta_inverse": 0.20,
    "amount_cv_norm": 0.07,
    "unique_sender_ratio": 0.05,
}


@dataclass(frozen=True)
class BranchFit:
    """One fitted branch: what to ship, what it scored, and on what rows.

    ``test_scores`` and ``test_labels`` travel with the fit so that several
    worlds can be pooled into one measurement. A single world leaves about
    thirty rows in the held-out slice, and thirty rows is not a number this
    project is allowed to quote.
    """

    artifact: dict[str, Any]
    metrics: dict[str, Any]
    test_scores: np.ndarray
    test_labels: np.ndarray
    heuristic_scores: np.ndarray


@dataclass(frozen=True)
class BranchSplit:
    """Row positions of the three time-ordered slices."""

    train: tuple[int, ...]
    val: tuple[int, ...]
    test: tuple[int, ...]
    purged: int

    @property
    def sizes(self) -> dict[str, int]:
        return {
            "train": len(self.train),
            "val": len(self.val),
            "test": len(self.test),
            "purged": self.purged,
        }


def time_ordered_split(
    timestamps: Sequence[datetime],
    *,
    train_share: float = DEFAULT_TRAIN_SHARE,
    val_share: float = DEFAULT_VAL_SHARE,
    purge: timedelta = DEFAULT_PURGE,
) -> BranchSplit:
    """Fit on the past, calibrate on the middle, score the future.

    Rows inside ``purge`` of a boundary are dropped from the earlier side
    rather than silently kept: a candidate carries a window of events, and a
    window that straddles the boundary carries the future backwards.
    """
    order = sorted(range(len(timestamps)), key=lambda index: timestamps[index])
    total = len(order)
    if total < 10:
        return BranchSplit(train=tuple(order), val=(), test=(), purged=0)

    train_end = int(total * train_share)
    val_end = int(total * (train_share + val_share))

    val_start_ts = timestamps[order[train_end]] if train_end < total else None
    test_start_ts = timestamps[order[val_end]] if val_end < total else None

    train: list[int] = []
    val: list[int] = []
    purged = 0

    for position in order[:train_end]:
        if val_start_ts is not None and timestamps[position] > val_start_ts - purge:
            purged += 1
        else:
            train.append(position)

    for position in order[train_end:val_end]:
        if test_start_ts is not None and timestamps[position] > test_start_ts - purge:
            purged += 1
        else:
            val.append(position)

    return BranchSplit(
        train=tuple(train), val=tuple(val), test=tuple(order[val_end:]), purged=purged
    )


def _heuristic_score(matrix: pd.DataFrame, weights: dict[str, float]) -> np.ndarray:
    total = np.zeros(len(matrix), dtype=float)
    for name, weight in weights.items():
        total += weight * matrix[name].to_numpy(dtype=float)
    return np.clip(total, 0.0, 1.0)


def _safe_auc(labels: np.ndarray, scores: np.ndarray) -> float | None:
    if len(np.unique(labels)) < 2:
        return None
    return float(roc_auc_score(labels, scores))


def train_branch(
    matrix: pd.DataFrame,
    labels: np.ndarray,
    split: BranchSplit,
    *,
    feature_names: Sequence[str],
    model_params: dict[str, Any],
    heuristic_weights: dict[str, float],
    artifact_version: str,
    seed: int,
) -> BranchFit:
    """Fit one branch and price it against the heuristic it replaces."""
    columns = list(feature_names)
    frame = matrix[columns].astype(float)

    x_train = frame.iloc[list(split.train)]
    y_train = labels[list(split.train)]
    x_val = frame.iloc[list(split.val)]
    y_val = labels[list(split.val)]
    x_test = frame.iloc[list(split.test)]
    y_test = labels[list(split.test)]

    if len(np.unique(y_train)) < 2:
        raise ValueError("the training slice holds one class only; nothing to fit")

    params = dict(model_params)
    params["random_state"] = seed
    model = lgb.LGBMClassifier(**params)
    model.fit(x_train, y_train)

    calibrator: IsotonicRegression | None = None
    if len(x_val) and len(np.unique(y_val)) > 1:
        val_raw = np.asarray(model.predict_proba(x_val), dtype=float)[:, 1]
        calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        calibrator.fit(val_raw, y_val)

    trained_auc: float | None = None
    heuristic_auc: float | None = None
    test_scores = np.array([], dtype=float)
    heuristic_scores = np.array([], dtype=float)
    if len(x_test):
        test_raw = np.asarray(model.predict_proba(x_test), dtype=float)[:, 1]
        test_scores = (
            np.clip(calibrator.predict(test_raw), 0.0, 1.0)
            if calibrator is not None
            else test_raw
        )
        heuristic_scores = _heuristic_score(x_test, heuristic_weights)
        trained_auc = _safe_auc(y_test, test_scores)
        heuristic_auc = _safe_auc(y_test, heuristic_scores)

    artifact = {
        "artifact_version": artifact_version,
        "model": model,
        "calibrator": calibrator,
        "feature_names": columns,
        "trained_on": "events",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    metrics = {
        "artifact_version": artifact_version,
        "generated_at": artifact["generated_at"],
        "trained_on": "events (candidates from blind discovery)",
        "random_state": seed,
        "splits": split.sizes,
        "test_positives": int(y_test.sum()) if len(y_test) else 0,
        "roc_auc": round(trained_auc, 4) if trained_auc is not None else None,
        "heuristic_roc_auc": round(heuristic_auc, 4) if heuristic_auc is not None else None,
        "lift_over_heuristic": (
            round(trained_auc - heuristic_auc, 4)
            if trained_auc is not None and heuristic_auc is not None
            else None
        ),
        "feature_importance": {
            name: int(value)
            for name, value in zip(columns, model.feature_importances_.tolist())
        },
    }
    return BranchFit(
        artifact=artifact,
        metrics=metrics,
        test_scores=test_scores,
        test_labels=np.asarray(y_test, dtype=int),
        heuristic_scores=heuristic_scores,
    )


def train_branches(
    features: pd.DataFrame,
    labels: np.ndarray,
    timestamps: Sequence[datetime],
    *,
    seed: int = 42,
    purge: timedelta = DEFAULT_PURGE,
) -> dict[str, BranchFit]:
    """Train both branches on one case dataset."""
    split = time_ordered_split(timestamps, purge=purge)

    graph = train_branch(
        features,
        labels,
        split,
        feature_names=GRAPH_FEATURE_NAMES,
        model_params=DEFAULT_GRAPH_MODEL_PARAMS,
        heuristic_weights=GRAPH_HEURISTIC_WEIGHTS,
        artifact_version="cheops-graph-v2-events",
        seed=seed,
    )
    sequence = train_branch(
        features,
        labels,
        split,
        feature_names=SEQUENCE_FEATURE_NAMES,
        model_params=DEFAULT_SEQUENCE_MODEL_PARAMS,
        heuristic_weights=SEQUENCE_HEURISTIC_WEIGHTS,
        artifact_version="cheops-sequence-v2-events",
        seed=seed,
    )
    return {"graph": graph, "sequence": sequence}


def train_branches_over_worlds(
    worlds: Sequence[tuple[pd.DataFrame, np.ndarray, Sequence[datetime]]],
    *,
    seed: int = 42,
    purge: timedelta = DEFAULT_PURGE,
) -> dict[str, BranchFit]:
    """Fit on the early slices of several worlds at once, test on their late ones.

    One world yields about ninety training rows and fourteen fraudulent ones,
    which is not enough to fit five features without memorising them — the
    sequence branch lost to its own heuristic at that size. Worlds are
    independent draws, so pooling them adds rows without letting information
    cross a time boundary: **each world is still split by its own clock**, and
    only the slices are concatenated.
    """
    frames: list[pd.DataFrame] = []
    labels: list[np.ndarray] = []
    positions: dict[str, list[int]] = {"train": [], "val": [], "test": []}
    offset = 0

    for features, world_labels, timestamps in worlds:
        split = time_ordered_split(timestamps, purge=purge)
        frames.append(features.reset_index(drop=True))
        labels.append(np.asarray(world_labels, dtype=int))
        for slice_name, indices in (
            ("train", split.train),
            ("val", split.val),
            ("test", split.test),
        ):
            positions[slice_name].extend(offset + index for index in indices)
        offset += len(features)

    pooled_frame = pd.concat(frames, ignore_index=True)
    pooled_labels = np.concatenate(labels)
    pooled_split = BranchSplit(
        train=tuple(positions["train"]),
        val=tuple(positions["val"]),
        test=tuple(positions["test"]),
        purged=offset - sum(len(value) for value in positions.values()),
    )

    graph = train_branch(
        pooled_frame,
        pooled_labels,
        pooled_split,
        feature_names=GRAPH_FEATURE_NAMES,
        model_params=DEFAULT_GRAPH_MODEL_PARAMS,
        heuristic_weights=GRAPH_HEURISTIC_WEIGHTS,
        artifact_version="cheops-graph-v2-events",
        seed=seed,
    )
    sequence = train_branch(
        pooled_frame,
        pooled_labels,
        pooled_split,
        feature_names=SEQUENCE_FEATURE_NAMES,
        model_params=DEFAULT_SEQUENCE_MODEL_PARAMS,
        heuristic_weights=SEQUENCE_HEURISTIC_WEIGHTS,
        artifact_version="cheops-sequence-v2-events",
        seed=seed,
    )
    for fit in (graph, sequence):
        fit.metrics["worlds"] = len(worlds)
    return {"graph": graph, "sequence": sequence}


def leave_one_world_out(
    worlds: Sequence[tuple[pd.DataFrame, np.ndarray, Sequence[datetime]]],
    *,
    feature_names: Sequence[str],
    model_params: dict[str, Any],
    heuristic_weights: dict[str, float],
    seed: int = 42,
) -> dict[str, Any]:
    """Fit on every world but one, score that one whole, repeat.

    This protocol exists because of how a case is dated. Within one world a
    time-ordered split moves the fraud mix from 2.9 % to 33.3 % between fit
    and test, so what it measures is partly that shift. Worlds are independent
    draws of the same generator, so holding one out keeps the mix identical on
    both sides while still scoring rows the model never saw.

    What it does **not** do is test order inside a world. Read it next to the
    within-world figure, never instead of it.
    """
    columns = list(feature_names)
    trained_scores: list[np.ndarray] = []
    heuristic_scores: list[np.ndarray] = []
    all_labels: list[np.ndarray] = []
    per_world: list[float] = []

    for held in range(len(worlds)):
        others = [index for index in range(len(worlds)) if index != held]
        x_train = pd.concat(
            [worlds[index][0].reset_index(drop=True) for index in others], ignore_index=True
        )[columns].astype(float)
        y_train = np.concatenate([np.asarray(worlds[index][1], dtype=int) for index in others])

        x_test = worlds[held][0].reset_index(drop=True)[columns].astype(float)
        y_test = np.asarray(worlds[held][1], dtype=int)
        if len(np.unique(y_train)) < 2 or len(np.unique(y_test)) < 2:
            continue

        params = dict(model_params)
        params["random_state"] = seed
        model = lgb.LGBMClassifier(**params)
        model.fit(x_train, y_train)

        scores = np.asarray(model.predict_proba(x_test), dtype=float)[:, 1]
        trained_scores.append(scores)
        heuristic_scores.append(_heuristic_score(x_test, heuristic_weights))
        all_labels.append(y_test)
        auc = _safe_auc(y_test, scores)
        if auc is not None:
            per_world.append(round(auc, 4))

    if not all_labels:
        return {"pooled_roc_auc": None, "worlds": 0, "rows": 0}

    labels = np.concatenate(all_labels)
    pooled = _safe_auc(labels, np.concatenate(trained_scores))
    pooled_heuristic = _safe_auc(labels, np.concatenate(heuristic_scores))
    return {
        "pooled_roc_auc": round(pooled, 4) if pooled is not None else None,
        "pooled_heuristic_roc_auc": (
            round(pooled_heuristic, 4) if pooled_heuristic is not None else None
        ),
        "pooled_lift": (
            round(pooled - pooled_heuristic, 4)
            if pooled is not None and pooled_heuristic is not None
            else None
        ),
        "per_world_roc_auc": per_world,
        "worlds": len(all_labels),
        "rows": int(len(labels)),
        "positives": int(labels.sum()),
    }


def fit_shipping_artifact(
    worlds: Sequence[tuple[pd.DataFrame, np.ndarray, Sequence[datetime]]],
    *,
    feature_names: Sequence[str],
    model_params: dict[str, Any],
    artifact_version: str,
    seed: int = 42,
) -> dict[str, Any]:
    """The artifact the service loads: fitted on N−1 worlds, calibrated on the last.

    Keeping the calibration world out of the fit matters more than the extra
    rows would: an isotonic curve fitted on the model's own training scores
    reads back the training set, and the probability it produces then means
    nothing. Measurement of this artifact is the two protocols above; this
    function only builds it.
    """
    columns = list(feature_names)
    fit_worlds = worlds[:-1] if len(worlds) > 1 else worlds
    calibration_world = worlds[-1] if len(worlds) > 1 else None

    x_fit = pd.concat(
        [frame.reset_index(drop=True) for frame, _, _ in fit_worlds], ignore_index=True
    )[columns].astype(float)
    y_fit = np.concatenate([np.asarray(labels, dtype=int) for _, labels, _ in fit_worlds])

    params = dict(model_params)
    params["random_state"] = seed
    model = lgb.LGBMClassifier(**params)
    model.fit(x_fit, y_fit)

    calibrator: IsotonicRegression | None = None
    if calibration_world is not None:
        x_cal = calibration_world[0].reset_index(drop=True)[columns].astype(float)
        y_cal = np.asarray(calibration_world[1], dtype=int)
        if len(np.unique(y_cal)) > 1:
            raw = np.asarray(model.predict_proba(x_cal), dtype=float)[:, 1]
            calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
            calibrator.fit(raw, y_cal)

    return {
        "artifact_version": artifact_version,
        "model": model,
        "calibrator": calibrator,
        "feature_names": columns,
        "trained_on": "events",
        "fit_worlds": len(fit_worlds),
        "calibration_rows": int(len(calibration_world[1])) if calibration_world else 0,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def pool_branch_measurement(fits: Sequence[BranchFit]) -> dict[str, Any]:
    """One measurement out of several worlds, with the spread kept visible.

    Pooling is the honest form here: each world leaves roughly thirty rows,
    and an AUC on thirty rows swings further than any difference worth
    reporting. The per-world figures stay in the report next to the pooled
    one, so a reader can see whether the pool hides disagreement.
    """
    scored = [fit for fit in fits if len(fit.test_labels) and len(np.unique(fit.test_labels)) > 1]
    if not scored:
        return {"pooled_roc_auc": None, "per_world": [], "rows": 0}

    labels = np.concatenate([fit.test_labels for fit in scored])
    trained = np.concatenate([fit.test_scores for fit in scored])
    heuristic = np.concatenate([fit.heuristic_scores for fit in scored])
    per_world = [fit.metrics["roc_auc"] for fit in scored]
    clean = [value for value in per_world if value is not None]

    pooled_trained = _safe_auc(labels, trained)
    pooled_heuristic = _safe_auc(labels, heuristic)
    return {
        "pooled_roc_auc": round(pooled_trained, 4) if pooled_trained is not None else None,
        "pooled_heuristic_roc_auc": (
            round(pooled_heuristic, 4) if pooled_heuristic is not None else None
        ),
        "pooled_lift": (
            round(pooled_trained - pooled_heuristic, 4)
            if pooled_trained is not None and pooled_heuristic is not None
            else None
        ),
        "per_world_roc_auc": clean,
        "per_world_min": min(clean) if clean else None,
        "per_world_max": max(clean) if clean else None,
        "worlds": len(scored),
        "rows": int(len(labels)),
        "positives": int(labels.sum()),
    }


def assert_feature_contract() -> None:
    """The two name lists must stay one list.

    ``graph_v2`` and ``sequence_v2`` keep their own copies of the column
    names, and the artifact loaders reject an artifact whose ``feature_names``
    do not match them exactly. Training here off ``event_features_v2`` would
    then produce an artifact the service refuses to load — silently, through
    the fallback path, which is how this class of defect stays invisible.
    """
    if list(GRAPH_FEATURE_NAMES) != list(GRAPH_FEATURE_COLUMNS):
        raise ValueError(
            f"graph feature names drifted apart: {GRAPH_FEATURE_NAMES} "
            f"vs {list(GRAPH_FEATURE_COLUMNS)}"
        )
    if list(SEQUENCE_FEATURE_NAMES) != list(SEQUENCE_FEATURE_COLUMNS):
        raise ValueError(
            f"sequence feature names drifted apart: {SEQUENCE_FEATURE_NAMES} "
            f"vs {list(SEQUENCE_FEATURE_COLUMNS)}"
        )

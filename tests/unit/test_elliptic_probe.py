"""Tests for the Elliptic probe (task 4.1).

No download happens here. The dataset lives outside the repository; these
tests pin the split and the operating point on hand-built rows whose answers
are known by construction.

The split test is the one that matters. A leaking walk-forward is exactly the
defect that produced this project's 1.0000, and it is invisible in the output:
the numbers simply come back better than they should.
"""

from __future__ import annotations

import csv
import random

import pytest

from apris.cheops.infrastructure.experiments.elliptic_probe import (
    CaseRow,
    _step_blocks,
    operating_point,
    single_feature_auc,
    threshold_for_recall,
    walk_forward,
)
from apris.cheops.infrastructure.external.elliptic import (
    TIMESTEP_FILE,
    ensure_time_steps,
)

FEATURES = ("density", "hub_share")


def _rows(steps: int = 49, per_step: int = 20, seed: int = 1) -> list[CaseRow]:
    """Rows whose feature carries the label, so a leak shows up as a jump."""
    rng = random.Random(seed)
    rows: list[CaseRow] = []
    for step in range(1, steps + 1):
        for index in range(per_step):
            label = 1 if index % 5 == 0 else 0
            rows.append(
                CaseRow(
                    node=f"n{step}-{index}",
                    time_step=step,
                    label=label,
                    features={
                        "density": 0.6 + rng.random() * 0.2 if label else rng.random() * 0.4,
                        "hub_share": rng.random(),
                    },
                )
            )
    return rows


def test_step_blocks_are_contiguous_and_cover_the_tail():
    blocks = _step_blocks(list(range(1, 50)), 5)
    assert blocks
    assert blocks[0][0] > 1, "the first block cannot start before there is training data"
    for (_, previous_end), (next_start, _) in zip(blocks, blocks[1:]):
        assert next_start == previous_end + 1
    assert blocks[-1][1] == 49


def test_training_never_reaches_into_the_test_block_or_the_purge():
    """The bite: drop the purge filter in walk_forward and this fails."""
    rows = _rows()
    folds = walk_forward(rows, FEATURES, n_splits=5, purge_steps=1, seed=7)
    assert folds

    for fold in folds:
        first_test_step = fold.test_steps[0]
        assert fold.purged_steps == (first_test_step - 1,)
        train_steps = {
            row.time_step
            for row in rows
            if row.time_step < first_test_step and row.time_step not in fold.purged_steps
        }
        assert max(train_steps) < first_test_step - 1
        assert fold.n_train == sum(1 for row in rows if row.time_step in train_steps)


def test_a_wider_purge_drops_more_steps():
    folds = walk_forward(_rows(), FEATURES, n_splits=5, purge_steps=3, seed=7)
    for fold in folds:
        assert len(fold.purged_steps) == 3
        assert fold.purged_steps[-1] == fold.test_steps[0] - 1


def test_shuffled_labels_land_near_a_coin_flip():
    """The control has to be a control: no signal left after shuffling."""
    folds = walk_forward(_rows(), FEATURES, n_splits=5, purge_steps=1, seed=7, shuffle_labels=True)
    scored = [fold.roc_auc for fold in folds if fold.roc_auc is not None]
    assert scored
    assert sum(scored) / len(scored) == pytest.approx(0.5, abs=0.12)


def test_a_carried_signal_is_found_without_shuffling():
    folds = walk_forward(_rows(), FEATURES, n_splits=5, purge_steps=1, seed=7)
    scored = [fold.roc_auc for fold in folds if fold.roc_auc is not None]
    assert min(scored) > 0.8, "the planted signal must survive the honest split"


def test_threshold_reaches_the_recall_it_was_asked_for():
    scores = [0.9, 0.8, 0.7, 0.6, 0.5, 0.4]
    labels = [1, 1, 0, 1, 0, 0]
    threshold = threshold_for_recall(scores, labels, 0.67)
    assert threshold is not None
    point = operating_point(scores, labels, threshold)
    assert point["recall"] >= 0.66
    assert point["precision"] == pytest.approx(1.0)


def test_threshold_abstains_when_there_is_nothing_to_catch():
    assert threshold_for_recall([0.5, 0.4], [0, 0], 0.8) is None


def test_a_constant_column_scores_exactly_a_coin_flip():
    rows = [
        CaseRow(node="a", time_step=1, label=1, features={"density": 0.5, "hub_share": 0.1}),
        CaseRow(node="b", time_step=1, label=0, features={"density": 0.5, "hub_share": 0.2}),
    ]
    assert single_feature_auc(rows, ["density"])["density"] == pytest.approx(0.5)


def test_time_steps_come_from_the_cache_without_touching_the_network(tmp_path):
    cache = tmp_path / TIMESTEP_FILE
    with open(cache, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["txId", "time_step"])
        writer.writerow(["1001", "3"])
        writer.writerow(["1002", "17"])

    steps = ensure_time_steps(tmp_path)

    assert steps == {"1001": 3, "1002": 17}

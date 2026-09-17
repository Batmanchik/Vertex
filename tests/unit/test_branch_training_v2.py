"""Tests for branch training on event-derived matrices (task 4.2).

No world is generated here — that costs a minute. The split and the pooling
are pinned on hand-built rows whose answers are known, and the feature
contract is checked against the real name lists, because that is the one that
fails silently in production: an artifact whose ``feature_names`` do not match
is rejected by the loader, the service falls back to the heuristic, and the
only sign is a branch mode nobody reads.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from apris.cheops.infrastructure.ml.branch_training_v2 import (
    GRAPH_HEURISTIC_WEIGHTS,
    SEQUENCE_HEURISTIC_WEIGHTS,
    BranchFit,
    _heuristic_score,
    assert_feature_contract,
    fit_shipping_artifact,
    leave_one_world_out,
    pool_branch_measurement,
    time_ordered_split,
    train_branch,
    train_branches,
    train_branches_over_worlds,
)
from apris.cheops.infrastructure.ml.graph_v2 import (
    DEFAULT_GRAPH_MODEL_PARAMS,
    GRAPH_FEATURE_NAMES,
    _validate_graph_artifact,
)
from apris.cheops.infrastructure.ml.sequence_v2 import SEQUENCE_FEATURE_NAMES

START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _stamps(count: int, *, hours: int = 24) -> list[datetime]:
    return [START + timedelta(hours=hours * index) for index in range(count)]


def _world(rows: int = 60, *, seed: int = 0) -> tuple[pd.DataFrame, np.ndarray, list[datetime]]:
    """A world where one graph feature carries the label outright."""
    rng = np.random.default_rng(seed)
    labels = (rng.random(rows) < 0.3).astype(int)
    frame = pd.DataFrame(
        {
            name: rng.random(rows) * 0.2 + (0.7 if name == "graph_hub_share" else 0.0) * labels
            for name in GRAPH_FEATURE_NAMES
        }
    )
    return frame, labels, _stamps(rows)


def test_the_feature_contract_holds():
    """If the two name lists drift, the artifact loader rejects what we ship."""
    assert_feature_contract()


def test_the_split_keeps_time_order_and_drops_the_gap():
    stamps = _stamps(100)
    split = time_ordered_split(stamps, purge=timedelta(days=3))

    assert split.train and split.val and split.test
    last_train = max(stamps[index] for index in split.train)
    first_val = min(stamps[index] for index in split.val)
    last_val = max(stamps[index] for index in split.val)
    first_test = min(stamps[index] for index in split.test)

    assert first_val - last_train >= timedelta(days=3)
    assert first_test - last_val >= timedelta(days=3)
    assert split.purged > 0


def test_a_wider_gap_costs_more_rows():
    stamps = _stamps(100)
    narrow = time_ordered_split(stamps, purge=timedelta(days=1))
    wide = time_ordered_split(stamps, purge=timedelta(days=6))
    assert wide.purged > narrow.purged
    assert len(wide.train) < len(narrow.train)


def test_too_few_rows_do_not_produce_a_split():
    split = time_ordered_split(_stamps(5))
    assert split.test == ()
    assert len(split.train) == 5


def test_leave_one_world_out_scores_every_world_once():
    worlds = [_world(seed=seed) for seed in range(3)]
    report = leave_one_world_out(
        worlds,
        feature_names=GRAPH_FEATURE_NAMES,
        model_params=DEFAULT_GRAPH_MODEL_PARAMS,
        heuristic_weights=GRAPH_HEURISTIC_WEIGHTS,
        seed=1,
    )
    assert report["worlds"] == 3
    assert report["rows"] == sum(len(labels) for _, labels, _ in worlds)
    assert len(report["per_world_roc_auc"]) == 3
    assert report["pooled_roc_auc"] > 0.9, "a planted signal must be found"


def test_the_shipped_artifact_is_calibrated_on_a_world_it_was_not_fitted_on():
    worlds = [_world(seed=seed) for seed in range(3)]
    artifact = fit_shipping_artifact(
        worlds,
        feature_names=GRAPH_FEATURE_NAMES,
        model_params=DEFAULT_GRAPH_MODEL_PARAMS,
        artifact_version="test-graph",
        seed=1,
    )
    assert artifact["fit_worlds"] == 2
    assert artifact["calibration_rows"] == len(worlds[-1][1])
    assert artifact["calibrator"] is not None
    # The loader must accept what we ship; this is the check that the service
    # silently fails without.
    _validate_graph_artifact(artifact)


def test_a_single_world_still_produces_a_usable_artifact():
    artifact = fit_shipping_artifact(
        [_world(seed=7)],
        feature_names=GRAPH_FEATURE_NAMES,
        model_params=DEFAULT_GRAPH_MODEL_PARAMS,
        artifact_version="test-graph",
        seed=1,
    )
    assert artifact["fit_worlds"] == 1
    assert artifact["calibrator"] is None, "nothing may be calibrated on its own training rows"


def test_pooling_reports_the_spread_it_pooled():
    fits = [
        BranchFit(
            artifact={},
            metrics={"roc_auc": value},
            test_scores=np.array([0.9, 0.1]),
            test_labels=np.array([1, 0]),
            heuristic_scores=np.array([0.2, 0.8]),
        )
        for value in (0.7, 0.9)
    ]
    pooled = pool_branch_measurement(fits)
    assert pooled["rows"] == 4
    assert pooled["per_world_min"] == 0.7
    assert pooled["per_world_max"] == 0.9
    assert pooled["pooled_roc_auc"] == pytest.approx(1.0)
    assert pooled["pooled_heuristic_roc_auc"] == pytest.approx(0.0)


def test_pooling_abstains_when_no_fold_had_both_classes():
    fits = [
        BranchFit(
            artifact={},
            metrics={"roc_auc": None},
            test_scores=np.array([0.5, 0.6]),
            test_labels=np.array([0, 0]),
            heuristic_scores=np.array([0.5, 0.6]),
        )
    ]
    assert pool_branch_measurement(fits)["pooled_roc_auc"] is None


def test_the_heuristic_is_the_one_the_service_falls_back_to():
    """Weights must match the fallback, or the comparison prices nothing."""
    frame = pd.DataFrame([{name: 1.0 for name in SEQUENCE_FEATURE_NAMES}])
    assert _heuristic_score(frame, SEQUENCE_HEURISTIC_WEIGHTS)[0] == pytest.approx(1.0)
    assert sum(SEQUENCE_HEURISTIC_WEIGHTS.values()) == pytest.approx(1.0)
    assert sum(GRAPH_HEURISTIC_WEIGHTS.values()) == pytest.approx(1.0)


# ── Само обучение ────────────────────────────────────────────────────────
#
# Выше проверены разбиение, сведение нескольких прогонов и эвристика. Само
# обучение до сих пор проверялось только через ``leave_one_world_out``, то есть
# через одну из двух точек входа. Ниже — вторые две, и главное свойство
# объединения миров: каждый мир режется по своим часам.


def _both(rows: int = 60, *, seed: int = 0):
    """Мир с признаками обеих ветвей: метку несёт по одному признаку в каждой."""
    rng = np.random.default_rng(seed)
    labels = (rng.random(rows) < 0.3).astype(int)
    carriers = {"graph_hub_share", SEQUENCE_FEATURE_NAMES[0]}
    frame = pd.DataFrame(
        {
            name: rng.random(rows) * 0.2 + (0.7 if name in carriers else 0.0) * labels
            for name in list(GRAPH_FEATURE_NAMES) + list(SEQUENCE_FEATURE_NAMES)
        }
    )
    return frame, labels, _stamps(rows)


def test_one_branch_is_priced_against_the_heuristic_it_replaces():
    """Модель без цены — это не результат: её не с чем сравнить.

    Ветвь заменяет конкретную эвристику, и число, которое она стоит, — это
    разница с этой эвристикой на тех же отложенных строках, а не абсолютный
    ROC-AUC сам по себе.
    """
    frame, labels, stamps = _world(rows=120, seed=3)
    fit = train_branch(
        frame,
        labels,
        time_ordered_split(stamps),
        feature_names=GRAPH_FEATURE_NAMES,
        model_params=DEFAULT_GRAPH_MODEL_PARAMS,
        heuristic_weights=GRAPH_HEURISTIC_WEIGHTS,
        artifact_version="test-graph",
        seed=1,
    )
    assert fit.artifact["artifact_version"] == "test-graph"
    assert list(fit.artifact["feature_names"]) == list(GRAPH_FEATURE_NAMES)
    # Оценки и метки отложенной части едут вместе с моделью: без них несколько
    # миров не свести в одно измерение.
    assert len(fit.test_scores) == len(fit.test_labels) == len(fit.heuristic_scores)
    assert fit.metrics["roc_auc"] > 0.9, "посаженный сигнал обязан найтись"
    # Цена ветви — это разница с эвристикой, и она обязана быть записана.
    assert fit.metrics["lift_over_heuristic"] == pytest.approx(
        fit.metrics["roc_auc"] - fit.metrics["heuristic_roc_auc"]
    )


def test_training_both_branches_reads_only_its_own_columns():
    """Ветви делят одну таблицу, и каждая обязана брать из неё своё.

    Если ветвь однажды начнёт читать чужие столбцы, артефакт разойдётся с тем,
    что ей подают в сервисе, — и это будет видно не здесь, а в проде.
    """
    frame, labels, stamps = _both(rows=120, seed=5)
    fits = train_branches(frame, labels, stamps, seed=1)

    assert set(fits) == {"graph", "sequence"}
    assert list(fits["graph"].artifact["feature_names"]) == list(GRAPH_FEATURE_NAMES)
    assert list(fits["sequence"].artifact["feature_names"]) == list(SEQUENCE_FEATURE_NAMES)


def test_pooling_worlds_splits_each_one_by_its_own_clock():
    """Обещание из докстринга ``train_branches_over_worlds``, записанное тестом.

    Миры склеиваются срезами, а не строками: если склеить строки и резать по
    общим часам, поздние строки первого мира окажутся в обучении вместе с
    ранними строками второго — утечка через границу времени, которую ни одна
    метрика не покажет.
    """
    worlds = [_both(rows=80, seed=seed) for seed in range(3)]
    fits = train_branches_over_worlds(worlds, seed=1)

    for fit in fits.values():
        assert fit.metrics["worlds"] == 3

    # Отложенная часть объединения — это ровно сумма отложенных частей миров.
    per_world = sum(len(time_ordered_split(stamps).test) for _, _, stamps in worlds)
    assert len(fits["graph"].test_labels) == per_world
    assert len(fits["sequence"].test_labels) == per_world

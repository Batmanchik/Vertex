"""Tests for the case panel (task 4.11).

No world is generated: a panel is assembled by hand so each property is
checked against an answer known by construction. The two that bite are the
purge gap in the time-forward protocol and case disjointness in the holdout
one — both are invisible in the output when they break, and both were how
defect 6 stayed hidden for as long as it did.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from apris.cheops.infrastructure.ml.case_panel import (
    CasePanel,
    build_case_panel,
    case_holdout_splits,
    prevalence_drift,
    time_forward_splits,
)
from apris.cheops.infrastructure.ml.case_pipeline import CASE_FEATURE_COLUMNS
from apris.cheops.infrastructure.simulation.config import SimulationConfig
from apris.cheops.infrastructure.simulation.generator import generate_world

# Мир ровно такой, чтобы дела набирали события на нескольких датах и прогон
# укладывался в секунды: панель проверяется на свойствах, а не на качестве.
TINY = SimulationConfig(
    seed=13,
    days=40,
    salary_earners=120,
    freelancers=20,
    traders=12,
    fast_spenders=60,
    family_circles=6,
    crowd_collections=10,
    marketplace_sellers=30,
    employers=3,
    mule_networks=10,
    pyramids=3,
    terminals=10,
    merchants=50,
    crypto_layering=0,
    crypto_traders=0,
)

START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _panel(cases: int = 10, dates: int = 12, *, cadence_days: int = 7) -> CasePanel:
    grid = [START + timedelta(days=cadence_days * index) for index in range(dates)]
    rows, labels, case_ids, as_of = [], [], [], []
    for moment in grid:
        for case in range(cases):
            label = 1 if case % 4 == 0 else 0
            rows.append({name: 0.5 + 0.3 * label for name in CASE_FEATURE_COLUMNS})
            labels.append(label)
            case_ids.append(f"case-{case}")
            as_of.append(moment)
    return CasePanel(
        features=pd.DataFrame(rows, columns=list(CASE_FEATURE_COLUMNS)),
        labels=np.asarray(labels, dtype=int),
        case_ids=tuple(case_ids),
        as_of=tuple(as_of),
        grid=tuple(grid),
        cases=cases,
        coverage=1.0,
    )


def test_the_panel_holds_one_row_per_case_and_date():
    panel = _panel(cases=10, dates=12)
    assert panel.size == 120
    assert len(set(panel.case_ids)) == 10
    assert len(set(panel.as_of)) == 12


def test_prevalence_no_longer_depends_on_position_in_the_list():
    """Defect 6, stated as a test: the fraud share must not drift with time."""
    panel = _panel()
    shares = list(panel.prevalence_by_date().values())
    assert max(shares) - min(shares) < 1e-9


def test_time_forward_trains_only_on_the_past_and_keeps_the_gap():
    panel = _panel(dates=12)
    splits = time_forward_splits(panel, n_splits=3, purge=timedelta(days=3))
    assert splits

    for split in splits:
        boundary = split.test_dates[0]
        train_dates = {panel.as_of[row] for row in split.train}
        test_dates = {panel.as_of[row] for row in split.test}
        assert max(train_dates) < boundary - timedelta(days=3)
        assert min(test_dates) == boundary
        assert not train_dates & test_dates


def test_time_forward_reports_that_it_reuses_the_same_cases():
    """It is close to one by design; hiding it would sell the number as more."""
    panel = _panel()
    splits = time_forward_splits(panel, n_splits=3)
    assert all(split.shared_case_share > 0.9 for split in splits)


def test_case_holdout_never_shares_a_case_between_the_sides():
    panel = _panel(cases=10, dates=12)
    splits = case_holdout_splits(panel, n_splits=5, seed=1)
    assert len(splits) == 5

    for split in splits:
        train_cases = {panel.case_ids[row] for row in split.train}
        test_cases = {panel.case_ids[row] for row in split.test}
        assert not train_cases & test_cases
        assert split.shared_case_share == 0.0


def test_case_holdout_covers_every_case_exactly_once():
    panel = _panel(cases=10, dates=4)
    splits = case_holdout_splits(panel, n_splits=5, seed=1)
    held = [case for split in splits for case in {panel.case_ids[row] for row in split.test}]
    assert sorted(held) == sorted(set(panel.case_ids))


def test_prevalence_drift_reports_the_spread_between_folds():
    panel = _panel()
    splits = time_forward_splits(panel, n_splits=3)
    drift = prevalence_drift(panel, splits)
    assert drift["folds"] == len(splits)
    assert drift["ratio_max_to_min"] == pytest.approx(1.0, abs=0.01)


def test_a_panel_too_short_for_the_folds_asked_for_produces_none():
    assert time_forward_splits(_panel(dates=3), n_splits=8) == []


# ── Панель, собранная из настоящего мира ──────────────────────────────────
#
# Всё выше проверяет протоколы на панели, собранной руками. Это оставляет без
# присмотра то, ради чего панель и появилась: срез по дате. Дефект 6 состоял в
# том, что дело описывалось один раз — по всем своим событиям, включая те, что
# случились позже даты, на которую его якобы оценивают. Проверить это можно
# только на панели, собранной из событий.


@pytest.fixture(scope="module")
def built():
    world = generate_world(TINY)
    return world, build_case_panel(world, cadence=timedelta(days=5), min_events=6)


def test_a_case_at_an_early_date_is_described_by_fewer_events_than_later(built):
    """Кусачий тест на дефект 6: срез по дате обязан быть настоящим срезом.

    Если ``build_case_panel`` однажды опишет дело по всем его событиям сразу,
    строки этого дела на разных датах станут одинаковыми — и панель начнёт
    измерять то же самое, что измеряла до неё, только дороже.
    """
    _, panel = built
    assert panel.size > 0, "мир слишком мал — тест не о чем"

    by_case: dict[str, list[int]] = {}
    for row, case_id in enumerate(panel.case_ids):
        by_case.setdefault(case_id, []).append(row)

    growing = [rows for rows in by_case.values() if len(rows) >= 3]
    assert growing, "ни одно дело не описано на трёх датах"

    # Хотя бы у одного дела описание обязано меняться со временем: события
    # накапливаются, значит и признаки не могут стоять на месте.
    changed = 0
    for rows in growing:
        first = panel.features.iloc[rows[0]].to_numpy()
        last = panel.features.iloc[rows[-1]].to_numpy()
        if not np.allclose(first, last):
            changed += 1
    assert changed, "описание дела не зависит от даты — срез не работает"


def test_every_row_is_dated_by_a_moment_of_the_grid(built):
    _, panel = built
    assert set(panel.as_of) <= set(panel.grid)
    assert len(panel.case_ids) == len(panel.as_of) == panel.size == len(panel.features)


def test_a_world_without_events_yields_an_empty_panel():
    """Пустой мир — это пустая панель, а не падение на ``min`` от ничего."""
    world = generate_world(TINY)
    empty = dataclasses.replace(world, events=[])
    panel = build_case_panel(empty)
    assert panel.size == 0
    assert panel.grid == ()

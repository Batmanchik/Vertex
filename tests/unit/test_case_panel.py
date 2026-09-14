"""Tests for the case panel (task 4.11).

No world is generated: a panel is assembled by hand so each property is
checked against an answer known by construction. The two that bite are the
purge gap in the time-forward protocol and case disjointness in the holdout
one — both are invisible in the output when they break, and both were how
defect 6 stayed hidden for as long as it did.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from apris.cheops.infrastructure.ml.case_panel import (
    CasePanel,
    case_holdout_splits,
    prevalence_drift,
    time_forward_splits,
)
from apris.cheops.infrastructure.ml.case_pipeline import CASE_FEATURE_COLUMNS

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

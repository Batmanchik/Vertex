"""Task 4.11 — score a case repeatedly in time instead of dating it once.

Why one date per case cannot work
---------------------------------
``case_pipeline`` gives each candidate a single timestamp — the moment of its
last event — and every time split in the project inherits it. Measuring that
convention (defect 6) showed fraud rising from 2.9 % of the first quarter of
the candidate list to 33.3 % of the last, because a structure that runs for
months ends late by construction.

The obvious repair, dating a case by the moment it becomes scorable, was tried
and is worse. A candidate is a cluster of accounts, not a transaction: the
median candidate carries about 1 200 events spread over the whole 120 days, so
its tenth event happens within a day of the world starting. That convention
collapses the timeline into its first day and flips the bias rather than
removing it.

Neither repair works because the premise is wrong. **A long-lived cluster does
not have a date.** What it has is a state at each moment.

What this module does instead
-----------------------------
A panel. Every candidate is described at each date of a regular grid, using
only the events that had happened by then, and each such row is one
observation:

    (case, 15 March)  ->  features of that case as of 15 March
    (case, 22 March)  ->  features of that case as of 22 March

A walk-forward over the grid then means what it says: fit on the state of the
world up to a date, score what happens after. Prevalence stops drifting with
position in the list, because the same cases are present on both sides.

Two questions, two protocols, and they cannot be merged
-------------------------------------------------------
A panel raises the question of what a fold is supposed to prove, and the
answer splits in two:

``time_forward_splits``
    fit on the grid up to a date, score the dates after it. The same cases
    appear on both sides, because a cluster that exists in March still exists
    in April — that is not a defect of the split, it is what an operational
    system does when it re-scores the same accounts every morning. What it
    measures is *forecasting a known population*, and the share of test rows
    whose case was also in training is reported so nobody reads it as more.

``case_holdout_splits``
    hold out whole cases, score them across every date. What it measures is
    *generalising to groups never seen*. Time order is not tested.

The first attempt here tried to be both at once — walk forward and drop any
training row whose case appears in the test block. It returns nothing at all:
these clusters live for the whole world, so purging by case purges the entire
training set. That emptiness is the finding. On long-lived objects the two
questions are exclusive, and a project that quotes one number for both is
answering neither.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Sequence

import numpy as np
import pandas as pd

from apris.cheops.infrastructure.ml.case_pipeline import CASE_FEATURE_COLUMNS
from apris.cheops.infrastructure.ml.event_features_v2 import (
    graph_features_from_events,
    sequence_features_from_events,
)
from apris.cheops.infrastructure.simulation.discovery import (
    discover_candidates,
    label_candidates,
)
from apris.cheops.infrastructure.simulation.generator import SimulatedWorld

DEFAULT_CADENCE = timedelta(days=7)
DEFAULT_MIN_EVENTS = 10
DEFAULT_PURGE = timedelta(days=3)


@dataclass(frozen=True)
class CasePanel:
    """Every (case, date) pair that had enough history to be scored."""

    features: pd.DataFrame
    labels: np.ndarray
    case_ids: tuple[str, ...]
    as_of: tuple[datetime, ...]
    grid: tuple[datetime, ...]
    cases: int
    coverage: float

    @property
    def size(self) -> int:
        return len(self.labels)

    @property
    def base_rate(self) -> float:
        return float(self.labels.mean()) if self.size else 0.0

    def prevalence_by_date(self) -> dict[datetime, float]:
        shares: dict[datetime, float] = {}
        for moment in self.grid:
            mask = np.array([value == moment for value in self.as_of])
            if mask.any():
                shares[moment] = float(self.labels[mask].mean())
        return shares


def _grid(world: SimulatedWorld, cadence: timedelta) -> list[datetime]:
    stamps = [event.ts for event in world.events]
    if not stamps:
        return []
    start, end = min(stamps), max(stamps)
    moments: list[datetime] = []
    current = start + cadence
    while current <= end:
        moments.append(current)
        current += cadence
    return moments


def build_case_panel(
    world: SimulatedWorld,
    *,
    cadence: timedelta = DEFAULT_CADENCE,
    min_events: int = DEFAULT_MIN_EVENTS,
    **discovery_kwargs: Any,
) -> CasePanel:
    """Describe every candidate at every date it was scorable by.

    Discovery still runs blind and labels are still attached afterwards; the
    only change is that a case is described many times instead of once, each
    time from the events that had happened by that date.
    """
    candidates = discover_candidates(world, **discovery_kwargs)
    labels, report = label_candidates(world, candidates)
    grid = _grid(world, cadence)

    rows: list[dict[str, float]] = []
    row_labels: list[int] = []
    case_ids: list[str] = []
    as_of: list[datetime] = []

    ordered = [
        (candidate, sorted(candidate.events, key=lambda event: event.ts))
        for candidate in candidates
    ]

    for moment in grid:
        for (candidate, events), label in zip(ordered, labels):
            # Events are sorted, so the cut is a scan from the left; the
            # panel is quadratic in the number of dates otherwise.
            visible = [event for event in events if event.ts <= moment]
            if len(visible) < min_events:
                continue
            rows.append(
                {
                    **graph_features_from_events(visible),
                    **sequence_features_from_events(visible),
                }
            )
            row_labels.append(int(label))
            case_ids.append(candidate.candidate_id)
            as_of.append(moment)

    frame = pd.DataFrame(rows, columns=list(CASE_FEATURE_COLUMNS))
    return CasePanel(
        features=frame,
        labels=np.asarray(row_labels, dtype=int),
        case_ids=tuple(case_ids),
        as_of=tuple(as_of),
        grid=tuple(grid),
        cases=len(candidates),
        coverage=report.coverage,
    )


@dataclass(frozen=True)
class PanelSplit:
    """One fold: which rows fit, which are scored, and what it is worth."""

    index: int
    kind: str
    train: tuple[int, ...]
    test: tuple[int, ...]
    test_dates: tuple[datetime, ...]
    purged_by_time: int
    shared_case_share: float

    @property
    def size(self) -> dict[str, int]:
        return {"train": len(self.train), "test": len(self.test)}


def _shared_case_share(panel: CasePanel, train: Sequence[int], test: Sequence[int]) -> float:
    """Share of test rows whose case also appears in training.

    Never hidden. In the time-forward protocol it is close to one by design,
    and a reader who does not know that will take the fold for evidence of
    generalisation to new groups.
    """
    if not test:
        return 0.0
    trained_cases = {panel.case_ids[row] for row in train}
    shared = sum(1 for row in test if panel.case_ids[row] in trained_cases)
    return round(shared / len(test), 4)


def time_forward_splits(
    panel: CasePanel,
    *,
    n_splits: int = 4,
    purge: timedelta = DEFAULT_PURGE,
) -> list[PanelSplit]:
    """Fit on the grid up to a date, score the dates after it.

    This is the deployment question: the population is known, and what is
    unknown is what it does next. Rows inside ``purge`` of the boundary are
    dropped; rows of the same case are **not**, because dropping them empties
    the training set on objects that live for the whole world.
    """
    dates = sorted(set(panel.as_of))
    if len(dates) < n_splits + 1:
        return []

    block = max(1, len(dates) // (n_splits + 1))
    splits: list[PanelSplit] = []

    for index in range(n_splits):
        start = block * (index + 1)
        test_dates = dates[start : start + block]
        if not test_dates:
            break
        boundary = test_dates[0]

        train: list[int] = []
        test: list[int] = []
        purged_by_time = 0
        for row in range(panel.size):
            moment = panel.as_of[row]
            if boundary <= moment <= test_dates[-1]:
                test.append(row)
            elif moment < boundary:
                if moment > boundary - purge:
                    purged_by_time += 1
                else:
                    train.append(row)

        if train and test:
            splits.append(
                PanelSplit(
                    index=index,
                    kind="time_forward",
                    train=tuple(train),
                    test=tuple(test),
                    test_dates=tuple(test_dates),
                    purged_by_time=purged_by_time,
                    shared_case_share=_shared_case_share(panel, train, test),
                )
            )
    return splits


def case_holdout_splits(
    panel: CasePanel,
    *,
    n_splits: int = 5,
    seed: int = 42,
) -> list[PanelSplit]:
    """Hold out whole cases and score them on every date.

    This is the generalisation question: a cluster the model has never met.
    Every row of a held-out case is in the test set and none of it is in
    training, so ``shared_case_share`` is zero by construction — and it is
    still computed rather than asserted.
    """
    unique_cases = sorted(set(panel.case_ids))
    if len(unique_cases) < n_splits:
        return []

    order = np.random.default_rng(seed).permutation(len(unique_cases))
    folds = np.array_split(order, n_splits)
    splits: list[PanelSplit] = []

    for index, fold in enumerate(folds):
        held = {unique_cases[int(position)] for position in fold}
        train = [row for row in range(panel.size) if panel.case_ids[row] not in held]
        test = [row for row in range(panel.size) if panel.case_ids[row] in held]
        if not train or not test:
            continue
        splits.append(
            PanelSplit(
                index=index,
                kind="case_holdout",
                train=tuple(train),
                test=tuple(test),
                test_dates=tuple(sorted({panel.as_of[row] for row in test})),
                purged_by_time=0,
                shared_case_share=_shared_case_share(panel, train, test),
            )
        )
    return splits


def prevalence_drift(panel: CasePanel, splits: Sequence[PanelSplit]) -> dict[str, Any]:
    """How much the fraud share moves between folds.

    Defect 6 was found by exactly this number under the old convention: a
    fraud share of 2.9 % where the model fits and 33.3 % where it is scored.
    Reporting it on every protocol is cheaper than finding it again.
    """
    shares: list[float] = []
    for split in splits:
        test_labels = panel.labels[list(split.test)]
        if len(test_labels):
            shares.append(float(test_labels.mean()))
    if not shares:
        return {"folds": 0}
    return {
        "folds": len(shares),
        "per_fold": [round(value, 4) for value in shares],
        "min": round(min(shares), 4),
        "max": round(max(shares), 4),
        "ratio_max_to_min": round(max(shares) / max(min(shares), 1e-9), 2),
    }

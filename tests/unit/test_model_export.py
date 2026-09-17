"""Выгруженная в страницу модель обязана быть той же моделью.

Витрина показывает жюри число и называет его оценкой модели. Если браузерная
копия отвечает хоть немного иначе, чем сервис, то на защите показывают не
модель, а её пересказ — и заметить это по экрану нельзя.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

from apris.data_generator import FEATURE_BOUNDS
from apris.web.model_export import UnsupportedModel, export_model, score

MODEL_FILE = Path(__file__).resolve().parents[2] / "artifacts" / "model.joblib"


@pytest.fixture(scope="module")
def model() -> object:
    if not MODEL_FILE.exists():
        pytest.skip("модели нет — сверять не с чем")
    with warnings.catch_warnings():
        # Модель обучена другой версией sklearn; для дампа деревьев это неважно.
        warnings.simplefilter("ignore")
        return joblib.load(MODEL_FILE)


@pytest.fixture(scope="module")
def exported(model: object) -> dict[str, object]:
    return export_model(model.booster_)  # type: ignore[attr-defined]


def test_the_exported_trees_answer_exactly_what_the_service_answers(
    model: object, exported: dict[str, object]
) -> None:
    """Главный тест файла: на случайных точках расхождения быть не должно.

    Границы берутся те же, что проверяет сервис, поэтому точки — это ровно тот
    диапазон, в котором страница вообще может оказаться.
    """
    names = list(exported["names"])  # type: ignore[arg-type]
    rng = np.random.default_rng(20260917)
    rows = [
        [float(rng.uniform(*FEATURE_BOUNDS[name])) for name in names]
        for _ in range(500)
    ]
    theirs = model.predict_proba(pd.DataFrame(rows, columns=names))[:, 1]  # type: ignore[attr-defined]
    worst = max(abs(score(exported, row) - float(one)) for row, one in zip(rows, theirs))
    assert worst < 1e-5, f"браузер ответил бы иначе, чем сервис: {worst:.2e}"


def test_the_corners_of_the_range_agree_too(
    model: object, exported: dict[str, object]
) -> None:
    """Случайные точки почти никогда не попадают на границу, а ручка — попадает.

    Ползунок в крайнем положении даёт ровно ``low`` или ``high``, и это как раз
    та точка, где ошибка в сравнении «<=» против «<» вылезла бы наружу.
    """
    names = list(exported["names"])  # type: ignore[arg-type]
    corners = [
        [FEATURE_BOUNDS[name][side] for name in names]
        for side in (0, 1)
    ]
    theirs = model.predict_proba(pd.DataFrame(corners, columns=names))[:, 1]  # type: ignore[attr-defined]
    for row, one in zip(corners, theirs):
        assert abs(score(exported, row) - float(one)) < 1e-5


def test_the_export_carries_what_the_page_needs_to_refuse_a_bad_value(
    exported: dict[str, object],
) -> None:
    """Страница обязана отвергать то же, что отвергает сервис."""
    names = list(exported["names"])  # type: ignore[arg-type]
    bounds = list(exported["bounds"])  # type: ignore[arg-type]
    assert len(bounds) == len(names)
    for name, (low, high) in zip(names, bounds):  # type: ignore[misc]
        assert (low, high) == FEATURE_BOUNDS[name]
    assert exported["thresholds"] == {"medium": 0.4, "high": 0.7}


def test_the_export_is_small_enough_to_put_in_the_page(
    exported: dict[str, object],
) -> None:
    blob = json.dumps(exported["trees"], separators=(",", ":"))
    assert len(blob.encode("utf-8")) < 400 * 1024


def test_a_split_the_page_cannot_walk_is_refused_instead_of_mis_scored() -> None:
    """Кусачий тест: тихая неверная оценка хуже падения сборки.

    Категориальное ветвление сравнивает признак с множеством. Обход на странице
    сравнил бы его порогом и выдал бы правдоподобное, но чужое число.
    """
    from apris.web.model_export import _node

    with pytest.raises(UnsupportedModel, match="ветвление"):
        _node({
            "decision_type": "==",
            "split_feature": 0,
            "threshold": "1||2",
            "left_child": {"leaf_value": 0.1},
            "right_child": {"leaf_value": -0.1},
        })

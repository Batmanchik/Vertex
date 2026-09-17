"""Выгрузка обученной модели в страницу, чтобы её считал браузер.

Раздел «Проверить» был единственным местом витрины, которому нужен был живой
сервис: страница, открытая файлом, честно говорила «считать некому». Из-за
одного этого раздела всю витрину нельзя было положить по ссылке.

Модель первой версии — градиентный бустинг на 300 деревьях глубины 6, то есть
набор порогов и чисел. Ничего, кроме сравнений и сложения, для ответа не нужно,
и браузер делает это сам. Здесь дерево переводится в форму, которую можно
положить в страницу и обойти в четыре строки на любом языке:

    узел  = [номер признака, порог, левое поддерево, правое поддерево]
    лист  = число

Выгрузка не «примерно повторяет» модель, а воспроизводит её: тест сверяет
питоновский обход этой самой структуры с ``predict_proba`` на случайных точках
и требует совпадения до 1e-5. Если LightGBM однажды начнёт писать в дамп то,
чего этот обход не понимает — категориальное ветвление, другую функцию связи, —
выгрузка падает с объяснением, а не отдаёт тихо другое число.
"""

from __future__ import annotations

import math
import re
from typing import Any

# Оттуда же, откуда их берёт сервис: границы и пороги должны быть одним
# объектом, а не двумя похожими копиями в разных модулях.
from apris.data_generator import FEATURE_BOUNDS, RISK_THRESHOLDS

# Лист — число, узел — список. Рекурсия вместо плоских массивов: на 9 тысячах
# узлов разница в весе страницы неразличима, а читать так можно глазами.
Node = float | list[Any]


class UnsupportedModel(RuntimeError):
    """Модель считает не тем способом, который умеет страница."""


def _sigmoid_factor(objective: str) -> float:
    """``binary sigmoid:1`` — связь и её коэффициент, оба нужны для ответа."""
    if not objective.startswith("binary"):
        raise UnsupportedModel(f"страница умеет только бинарную задачу, дамп говорит: {objective}")
    match = re.search(r"sigmoid:([0-9.]+)", objective)
    if match is None:
        raise UnsupportedModel(f"в дампе нет коэффициента сигмоиды: {objective}")
    return float(match.group(1))


def _node(raw: dict[str, Any]) -> Node:
    if "leaf_value" in raw:
        return round(float(raw["leaf_value"]), 6)

    decision = raw.get("decision_type", "<=")
    if decision != "<=":
        # Категориальное ветвление сравнивает не порогом, а множеством, и обход
        # ниже посчитал бы его как числовое — молча и неверно.
        raise UnsupportedModel(f"страница умеет только ветвление '<=', в дампе: {decision!r}")

    return [
        int(raw["split_feature"]),
        round(float(raw["threshold"]), 6),
        _node(raw["left_child"]),
        _node(raw["right_child"]),
    ]


def export_model(booster: Any) -> dict[str, Any]:
    """Всё, что нужно браузеру для ответа: деревья, порядок признаков, границы.

    Границы здесь не украшение. Сервис отвергает значение вне диапазона, и
    страница обязана вести себя так же, иначе одна и та же девятка величин даст
    на странице ответ, а в сервисе — отказ.
    """
    dump = booster.dump_model()
    names: list[str] = list(dump["feature_names"])
    unknown = [name for name in names if name not in FEATURE_BOUNDS]
    if unknown:
        raise UnsupportedModel(f"у признаков нет границ: {unknown}")

    return {
        "names": names,
        "bounds": [list(FEATURE_BOUNDS[name]) for name in names],
        "sigmoid": _sigmoid_factor(str(dump.get("objective", ""))),
        "thresholds": dict(RISK_THRESHOLDS),
        "trees": [_node(tree["tree_structure"]) for tree in dump["tree_info"]],
    }


def score(exported: dict[str, Any], values: list[float]) -> float:
    """Эталон обхода на питоне: то же, что делает страница, строка в строку.

    Существует ради теста. Совпадение с ``predict_proba`` здесь — единственное
    доказательство, что выгруженная структура и есть модель, а не похожая на
    неё. Браузерная версия сверяется отдельно, в браузере.
    """
    total = 0.0
    for tree in exported["trees"]:
        node: Node = tree
        while isinstance(node, list):
            feature, threshold, left, right = node
            node = left if values[feature] <= threshold else right
        total += float(node)
    return 1.0 / (1.0 + math.exp(-exported["sigmoid"] * total))

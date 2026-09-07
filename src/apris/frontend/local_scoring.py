"""Расчёт оценки в процессе интерфейса, когда сервис не поднят.

Зачем это нужно
---------------
Интерфейс спроектирован так, что оценку он получает из того же сервиса, что
работает в проде: это правило не декоративное, оно закрывает целый класс
расхождений между тем, что видит аналитик, и тем, что считает система.

Но у правила есть цена, которую видно на публичном развёртывании: там нет
второго процесса под FastAPI, поэтому каждая страница со скорингом
встречала человека красной плашкой «сервис недоступен». Для витрины и для
защиты это хуже, чем отсутствие страницы.

Компромисс, который здесь реализован: при недоступности сервиса оценка
считается **тем же самым кодом** — тем же движком и теми же вариантами
использования, которые вызывает API у себя внутри. Это не второй инференс и
не упрощённая копия: разница только в том, что вызов идёт напрямую, а не
через HTTP. Результат помечается полем ``source`` со значением ``"local"``,
и интерфейс подписывает его как локальный расчёт.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from apris.cheops.application.use_cases import ExplainCase, IngestCase, ScoreCase
from apris.cheops.infrastructure.ml.engine_v2 import MultiBranchRiskEngine

_engine: MultiBranchRiskEngine | None = None
_score_case: ScoreCase | None = None
_explain_case: ExplainCase | None = None


def _ensure_engine() -> tuple[ScoreCase, ExplainCase, MultiBranchRiskEngine]:
    """Один движок на процесс: собирается лениво и переиспользуется."""
    global _engine, _score_case, _explain_case
    if _engine is None:
        _engine = MultiBranchRiskEngine()
        ingest = IngestCase()
        _score_case = ScoreCase(ingest, _engine)
        _explain_case = ExplainCase(ingest, _engine)
    assert _score_case is not None and _explain_case is not None
    return _score_case, _explain_case, _engine


def score_case(payload: dict[str, Any]) -> dict[str, Any]:
    """Оценка кейса тем же вариантом использования, что и в API."""
    score, _, _ = _ensure_engine()
    result = score.execute(
        case_id=payload["case_id"],
        events=payload.get("events", []),
        window_hours=int(payload.get("window_hours") or 24),
        tabular_features=payload.get("tabular_features"),
    )
    data = asdict(result)
    data["source"] = "local"
    return data


def explain_case(payload: dict[str, Any]) -> dict[str, Any]:
    """Объяснение вклада ветвей — тот же вариант использования, что в API."""
    _, explain, _ = _ensure_engine()
    result = explain.execute(
        case_id=payload["case_id"],
        events=payload.get("events", []),
        window_hours=int(payload.get("window_hours") or 24),
        tabular_features=payload.get("tabular_features"),
    )
    data = asdict(result)
    data["source"] = "local"
    return data


def predict_from_features(features: dict[str, float]) -> dict[str, Any]:
    """Оценка по девяти признакам ручного ввода — та же функция, что в API."""
    from apris.risk_engine import load_artifacts, predict_risk

    model, feature_names = load_artifacts()
    result = predict_risk(features, model=model, feature_names=feature_names)
    return {
        "probability": result["probability"],
        "label_text": result["label_text"],
        "threshold_policy": result["threshold_policy"],
        "threshold_values": result["threshold_values"],
        "source": "local",
    }


def health() -> dict[str, Any]:
    _, _, engine = _ensure_engine()
    payload = dict(engine.health())
    payload["source"] = "local"
    return payload


__all__ = ["explain_case", "health", "predict_from_features", "score_case"]

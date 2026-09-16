"""Витрина измерений: страница и те же числа в JSON.

Страницу собирает :mod:`apris.web.site` — один самодостаточный файл без
внешних запросов. Тот же код кладёт её на диск командой
``python scripts/make_site.py``, поэтому HTTP-версия и файл на флешке не
могут разъехаться: сборщик один.
"""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from apris.web import data, site

router = APIRouter(tags=["web"])


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def results_page() -> HTMLResponse:
    """Витрина, собранная на текущих файлах прогонов."""
    return HTMLResponse(site.build())


def _plain(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, list):
        return [_plain(item) for item in value]
    if isinstance(value, tuple):
        return list(value)
    return value


@router.get("/api/v2/viz/measurements")
def measurements() -> dict[str, Any]:
    """Те же числа в JSON — для внешних потребителей и проверки."""
    return {key: _plain(value) for key, value in data.snapshot().items()}

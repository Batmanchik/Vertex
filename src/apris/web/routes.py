"""Витрина измерений: HTML-страница и JSON тех же чисел.

Страница отдаётся тем же процессом, что и API, поэтому отдельного фронтенда
и сборки не требуется. Данные читаются из artifacts/ на каждый запрос.
"""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from apris.web import charts, data

_HERE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(_HERE / "templates"))
static = StaticFiles(directory=str(_HERE / "static"))

router = APIRouter(tags=["web"])


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def results_page(request: Request) -> HTMLResponse:
    snap = data.snapshot()
    worlds = snap["worlds"]
    rarity = snap["rarity"]

    context: dict[str, Any] = dict(snap)
    if worlds:
        context["wc"] = charts.worlds_chart(worlds)
    if snap["evasion"]:
        context["ec"] = charts.evasion_chart(snap["evasion"])
    if snap["matrix"].present:
        context["mg"] = charts.matrix_grid(snap["matrix"])
    if rarity:
        context["rc1"] = charts.rarity_chart(rarity, "roc_auc", lo=0.85, hi=1.0)
        context["rc2"] = charts.rarity_chart(rarity, "precision_at_budget", lo=0.0, hi=0.6)

    cv = snap["curves"]
    if cv.present:
        # Один цвет на модель во всех трёх квадратах: глаз тогда сравнивает
        # кривые между графиками, а не разгадывает легенду заново.
        palette = {"forest": "#1B5B66", "logistic": "#B4741C", "rules": "#A8261F"}
        account = [c for c in cv.items if c.scope == "account"]
        context["roc_chart"] = charts.unit_square([
            {"name": c.model_ru, "colour": palette.get(c.model, "#4C596A"), "points": c.roc}
            for c in account
        ])
        context["pr_chart"] = charts.unit_square([
            {"name": c.model_ru, "colour": palette.get(c.model, "#4C596A"), "points": c.pr}
            for c in account
        ])
        best = cv.at("account", "forest")
        if best:
            context["cal_chart"] = charts.unit_square([{
                "name": "лес",
                "colour": palette["forest"],
                "points": [
                    {"x": b["mean_score"], "y": b["fraud_share"]}
                    for b in best.calibration if b["count"]
                ],
            }])
            context["hist_chart"] = charts.score_histogram(best.histogram)
    return templates.TemplateResponse(request, "results.html", context)


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

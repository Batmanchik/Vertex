"""Страница измерений, собранная один раз для двух способов показа.

Витрину нужно отдавать и по HTTP из FastAPI, и внутри интерфейса на
Streamlit, где никакого сервера нет. Разметка и данные при этом обязаны
совпадать до последней цифры, поэтому контекст собирается здесь, а не
дважды на каждой стороне.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from apris.web import charts, data

HERE = Path(__file__).resolve().parent
TEMPLATES = HERE / "templates"
STATIC = HERE / "static"

# Один цвет на модель во всех квадратах: глаз тогда сравнивает кривые между
# графиками, а не разгадывает легенду заново.
MODEL_COLOURS = {"forest": "#1B5B66", "logistic": "#B4741C", "rules": "#A8261F"}


def build_context() -> dict[str, Any]:
    """Числа прогонов вместе с готовой геометрией графиков."""
    snap = data.snapshot()
    context: dict[str, Any] = dict(snap)

    worlds = snap["worlds"]
    rarity = snap["rarity"]

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
        account = [c for c in cv.items if c.scope == "account"]
        context["roc_chart"] = charts.unit_square([
            {"name": c.model_ru, "colour": MODEL_COLOURS.get(c.model, "#4C596A"), "points": c.roc}
            for c in account
        ])
        context["pr_chart"] = charts.unit_square([
            {"name": c.model_ru, "colour": MODEL_COLOURS.get(c.model, "#4C596A"), "points": c.pr}
            for c in account
        ])
        best = cv.at("account", "forest")
        if best:
            context["cal_chart"] = charts.unit_square([{
                "name": "лес",
                "colour": MODEL_COLOURS["forest"],
                "points": [
                    {"x": b["mean_score"], "y": b["fraud_share"]}
                    for b in best.calibration if b["count"]
                ],
            }])
            context["hist_chart"] = charts.score_histogram(best.histogram)
    return context


def render_standalone() -> str:
    """Та же страница одной строкой HTML, со встроенными стилями и скриптом.

    Ссылки на статику подставляются пустыми, а файлы вклеиваются в разметку:
    внутри интерфейса раздавать их некому.
    """
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("results.html")
    html = template.render(url_for=lambda *_args, **_kwargs: "", **build_context())

    css = (STATIC / "console.css").read_text(encoding="utf-8")
    js = (STATIC / "console.js").read_text(encoding="utf-8")

    html = html.replace(
        '<link rel="stylesheet" href="">',
        f"<style>{css}</style>",
    )
    html = html.replace('<script src=""></script>', f"<script>{js}</script>")
    return html


__all__ = ["build_context", "render_standalone", "STATIC", "TEMPLATES"]

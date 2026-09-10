"""Витрина измерений внутри интерфейса, чтобы адрес был один.

Раньше витрина жила на отдельном порту под FastAPI, а интерфейс на своём,
и на защите приходилось держать две ссылки. Разметка и числа здесь те же
самые: страница собирается тем же кодом, что отдаёт HTTP-версия, поэтому
разъехаться они не могут.

Страница вставляется в рамку, а не печатается через st.html: на ней есть
холст с анимацией и ползунок, а Streamlit вырезает скрипты из обычной
разметки.
"""
from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
_SRC = _PROJECT_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import streamlit as st

st.set_page_config(page_title="Измерения | Vertex", page_icon="📊", layout="wide")


@st.cache_data(ttl=60, show_spinner=False)
def _page_html() -> str:
    from apris.web.page import render_standalone

    return render_standalone()


def _embed(html: str, *, height: int) -> None:
    """Показать готовую страницу в рамке.

    ``st.iframe`` появился недавно и берёт путь к файлу, а не разметку, поэтому
    строка сначала кладётся во временный файл. На старых версиях Streamlit
    остаётся прежний вызов, который там пока работает.
    """
    if hasattr(st, "iframe"):
        import tempfile

        cache = Path(tempfile.gettempdir()) / "vertex_measurements.html"
        cache.write_text(html, encoding="utf-8")
        st.iframe(cache, height=height)
        return

    import streamlit.components.v1 as components

    components.html(html, height=height, scrolling=True)


st.title("📊 Витрина измерений")
st.caption(
    "Двенадцать разделов: лестница миров, кривая уклонения, редкость, параметр W, "
    "сравнение моделей, алгоритмы обучения, кривые детектора, формулы, признаки, "
    "очередь аналитика, типологии, состав мира. Каждое число читается из файла "
    "прогона в artifacts/ при открытии страницы."
)

try:
    html = _page_html()
except Exception as exc:  # прогонов может не быть на свежей копии
    st.error(
        "Витрина не собралась. Обычно это значит, что в artifacts/ нет файлов "
        f"прогонов.\n\nПричина: {exc}"
    )
    st.code("python scripts/run_experiment_ladder.py --seeds 1 --days 30", language="bash")
else:
    _embed(html, height=2400)
    st.caption(
        "Та же страница отдаётся и напрямую, если поднят API: "
        "`python -m uvicorn apris.api.main:app --port 8000`, адрес http://localhost:8000/"
    )

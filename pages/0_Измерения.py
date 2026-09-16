"""Витрина внутри интерфейса, чтобы адрес на защите был один.

Сама витрина — статический файл: её собирает `python scripts/make_site.py`,
и она открывается двойным щелчком, без сервера и без сети. Здесь она просто
вставлена в рамку, чтобы из интерфейса не приходилось никуда уходить.

Раньше на этом месте была страница, которую Streamlit рисовал сам: каждый
ползунок шёл на сервер, каждая перерисовка считалась питоном, и на показе это
было видно. Теперь питон работает один раз при сборке, а на защите работает
только браузер.
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

SITE = _PROJECT_ROOT / "artifacts" / "site" / "index.html"


@st.cache_data(ttl=60, show_spinner=False)
def _page_html() -> str:
    """Готовый файл, если он собран; иначе собрать прямо сейчас."""
    if SITE.exists():
        return SITE.read_text(encoding="utf-8")
    from apris.web.site import build

    return build()


st.title("📊 Витрина измерений")
st.caption(
    "Девятнадцать разделов: очередь аналитика, лестница миров, цена уклонения, редкость, "
    "правила против модели, потолки, кривые детектора, панель, ветви ансамбля, параметр W, "
    "настоящие данные, методология, шесть дефектов, разрыв до цели и вопросы жюри. "
    "Каждое число читается из файла прогона в artifacts/."
)

try:
    html = _page_html()
except Exception as exc:  # прогонов может не быть на свежей копии
    st.error(
        "Витрина не собралась. Обычно это значит, что в artifacts/ нет файлов "
        f"прогонов.\n\nПричина: {exc}"
    )
    st.code("python scripts/run_pipeline.py --preset full", language="bash")
else:
    if hasattr(st, "iframe") and SITE.exists():
        st.iframe(SITE, height=2400)
    else:
        import streamlit.components.v1 as components

        components.html(html, height=2400, scrolling=True)

    st.caption(
        "На защите лучше открывать её отдельно — файл `artifacts/site/index.html` "
        "открывается мгновенно и работает без интернета. Пересобрать: "
        "`python scripts/make_site.py`."
    )

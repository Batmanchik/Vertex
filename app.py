"""
Vertex — аналитика графов и потоков для выявления финансового мошенничества.

Главная точка входа Streamlit. Основная логика находится в pages/.
Этот модуль применяет общие стили и отображает стартовый экран.
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import streamlit as st

_SRC_DIR = Path(__file__).resolve().parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

_ASSETS_DIR = _SRC_DIR / "apris" / "frontend" / "assets"


def _read_asset(name: str) -> str:
    path = _ASSETS_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Ресурс не найден: {path}")
    return path.read_text(encoding="utf-8")


def _render_html(body: str) -> None:
    html_renderer = getattr(st, "html", None)
    if callable(html_renderer):
        html_renderer(body)
    else:
        st.markdown(body, unsafe_allow_html=True)


def _guard_streamlit_entrypoint() -> None:
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        ctx = get_script_run_ctx(suppress_warning=True)
        if ctx is None:
            print("Это Streamlit-приложение.")
            print("Запуск: streamlit run app.py")
            raise SystemExit(0)
    except Exception:
        return


def _set_style() -> None:
    css = _read_asset("streamlit_theme.css")
    _render_html(
        f"""
        <link rel=\"preconnect\" href=\"https://fonts.googleapis.com\"> 
        <link rel=\"preconnect\" href=\"https://fonts.gstatic.com\" crossorigin>
        <link href=\"https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@20..48,200..700,0..1,-50..200\" rel=\"stylesheet\">
        <link href=\"https://fonts.googleapis.com/icon?family=Material+Icons\" rel=\"stylesheet\">
        <link href=\"https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap\" rel=\"stylesheet\"> 
        <style>{css}</style>
        """
    )


def _apply_matplotlib_theme() -> None:
    """Графики в той же палитре, что и остальной интерфейс.

    Цвета взяты из streamlit_theme.css, чтобы линия на картинке и плашка
    рядом с ней означали одно и то же.
    """
    plt.style.use("seaborn-v0_8-whitegrid")
    plt.rcParams.update(
        {
            "figure.facecolor": "#FFFFFF",
            "axes.facecolor": "#FFFFFF",
            "axes.edgecolor": "#D8DEE5",
            "axes.grid": True,
            "grid.alpha": 0.55,
            "grid.color": "#E7EBEF",
            "grid.linewidth": 0.8,
            "axes.titleweight": "600",
            "axes.titlesize": 11,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "font.size": 9,
            "font.family": "sans-serif",
            "text.color": "#131A24",
            "axes.labelcolor": "#4C596A",
            "xtick.color": "#778394",
            "ytick.color": "#778394",
            "legend.frameon": False,
            "lines.linewidth": 1.8,
            "axes.prop_cycle": plt.cycler(
                color=["#1B5B66", "#A8261F", "#B4741C", "#2C6E52", "#4C596A"]
            ),
        }
    )


def _facts_strip() -> str:
    """Опорные числа прогона под шапкой.

    Читаются из artifacts/ при загрузке страницы. Если файла нет, полоса
    не рисуется вовсе: подставлять правдоподобное число нельзя.
    """
    from apris.web import data as web_data

    worlds, _ = web_data.worlds()
    matrix, _ = web_data.model_matrix()
    flow, _ = web_data.flow_weight()
    queue, _ = web_data.queue()

    cells: list[tuple[str, str]] = []
    best = matrix.at("network_structural", "forest") if matrix.present else None
    if best:
        cells.append((f"{best.roc_auc:.4f}", "ROC-AUC по группам"))
    account = matrix.at("account", "forest") if matrix.present else None
    if account:
        cells.append((f"{account.roc_auc:.4f}", "ROC-AUC по счетам"))
    if worlds:
        cells.append((str(len(worlds)), "миров в лестнице"))
    if queue.present:
        cells.append((f"{queue.world.get('events', 0):,.0f}".replace(",", " "), "событий в мире"))
    if flow.present and flow.model.get("lift") is not None:
        cells.append((f"{float(flow.model['lift']):+.4f}", "прирост от W"))

    if not cells:
        return ""
    body = "".join(
        f'<div><div class="v">{value}</div><div class="k">{label}</div></div>'
        for value, label in cells
    )
    return f'<div class="vx-facts">{body}</div>'


def main() -> None:
    st.set_page_config(
        page_title="Vertex — аналитика графов и потоков",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _set_style()
    _apply_matplotlib_theme()

    _render_html(_read_asset("hero.html"))

    try:
        strip = _facts_strip()
    except Exception:
        # Полоса чисел — украшение поверх прогонов. Если прогонов нет,
        # страница обязана открыться без неё, а не упасть.
        strip = ""
    if strip:
        _render_html(strip)
        st.caption(
            "Числа читаются из artifacts/ при загрузке страницы. "
            "Развёрнутые измерения с графиками — на витрине, "
            "страница «Витрина Vertex» в меню слева."
        )

    with st.expander("Как устроен интерфейс", expanded=True):
        c1, c2 = st.columns([1.25, 1])
        with c1:
            st.markdown(
                """
                1. **Поиск сетей** — кандидаты строятся из потока событий.
                   Файл с ответами при этом не читается, поэтому coverage
                   (доля реальных сетей, попавших хотя бы в одного кандидата)
                   является настоящим потолком полноты.
                2. **Досье кандидата** — структура, признаки и оценка сервиса
                   для выбранного кластера. Всё посчитано по его событиям.
                3. **Валидация** — purged walk-forward, лестница квинтилей и
                   проверка наивного правила. Цифры считаются при открытии
                   страницы, а не берутся из документа.
                4. **Ручная проверка** — девять признаков исходной модели для
                   ручного ввода, с явной оговоркой о некалиброванных порогах.
                """
            )
        with c2:
            st.markdown("**Что здесь не показывается**")
            st.markdown(
                """
                - Граф, построенный из признаков, которые он подтверждает.
                - Картинка структуры, выведенная из вердикта.
                - Метрика, посчитанная на разметке, которую поиск получил
                  заранее.

                Каждый пункт — исправленный дефект, а не осторожность:
                подробности в `docs/reviews/AUDIT_FINDINGS_2026-09-04.md`.
                """
            )

    st.info(
        "Данные синтетические и обрабатываются локально. Оценку возвращает API — "
        "интерфейс намеренно не считает inference сам."
    )
    st.markdown("---")
    st.markdown("Выберите страницу в боковом меню для продолжения.")


if __name__ == "__main__":
    _guard_streamlit_entrypoint()
    main()

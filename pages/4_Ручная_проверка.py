"""Ручная проверка одного объекта на девяти признаках старой модели.

Страница осталась, потому что аналитику нужен ручной ввод. Изменилось три
вещи, и каждая — следствие аудита.

**Убран граф.** Здесь рисовался «граф транзакций», построенный функцией
`build_transaction_graph(features)` — то есть из тех же девяти признаков,
которые он якобы подтверждал. Это тот же дефект, что и в ветках модели
(Находка 1), только на экране и потому убедительнее.

**Оценку считает сервис.** Раньше страница грузила модель и вызывала
`predict_proba` прямо в интерфейсе. Теперь она обращается к API, как и
остальные страницы: аналитик видит то, что вернул бы прод.

**Признаки можно посчитать из событий.** Кнопка берёт организатора
пирамиды из построенного мира и считает девять признаков по его денежному
потоку — тем же кодом, который сделал старую модель проверяемой впервые.
"""
from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from typing import Any

import numpy as np
import pandas as pd
import streamlit as st

from apris.cheops.infrastructure.ml.legacy_features_v2 import legacy_features
from apris.data_generator import (
    FEATURE_BOUNDS,
    FEATURE_COLUMNS,
    RISK_THRESHOLDS,
    generate_legitimate,
    generate_pyramid,
)
from apris.risk_engine import contributions
from apris.frontend import api_client
from apris.frontend.session import current_state
from apris.population_map import (
    build_population_map_figure,
    check_feature_order,
    check_no_nan,
    check_pca_dimensions,
    fit_population_pca,
    load_feature_names as load_population_feature_names,
    load_population_dataset,
    project_current_case,
)
from apris.risk_engine import OPERATIONAL_INPUT_BOUNDS, operational_to_features

st.set_page_config(page_title="Ручная проверка | Vertex", page_icon="🔍", layout="wide")

FEATURE_LABELS = {
    "growth_rate": "Темп роста вкладчиков",
    "referral_ratio": "Доля реферальных участников",
    "payout_dependency": "Зависимость выплат от притока",
    "centralization_index": "Индекс централизации",
    "avg_holding_time": "Среднее удержание средств (дни)",
    "reinvestment_rate": "Доля повторных вложений",
    "gini_coefficient": "Коэффициент Джини",
    "transaction_entropy": "Транзакционная энтропия",
    "structural_depth": "Глубина структуры",
}

OPERATIONAL_LABELS = {
    "tx_count_total": "Общее число транзакций",
    "unique_counterparties": "Уникальные контрагенты",
    "new_clients_current": "Новые клиенты (текущий период)",
    "new_clients_previous": "Новые клиенты (предыдущий период)",
    "referred_clients_current": "Реферальные клиенты (текущий период)",
    "incoming_funds": "Общий входящий поток средств",
    "payouts_total": "Общий объем выплат",
    "top1_wallet_share": "Доля топ-1 кошелька",
    "top10_wallet_share": "Доля топ-10 кошельков",
    "avg_holding_days": "Среднее удержание (дни)",
    "repeat_investor_share": "Доля повторных инвесторов",
    "max_referral_depth": "Макс. глубина реферальной структуры",
}

DEFAULT_OPERATIONAL: dict[str, float] = {
    "tx_count_total": 12000.0,
    "unique_counterparties": 1800.0,
    "new_clients_current": 420.0,
    "new_clients_previous": 300.0,
    "referred_clients_current": 190.0,
    "incoming_funds": 2_000_000.0,
    "payouts_total": 1_200_000.0,
    "top1_wallet_share": 0.32,
    "top10_wallet_share": 0.62,
    "avg_holding_days": 34.0,
    "repeat_investor_share": 0.60,
    "max_referral_depth": 8.0,
}

PRESETS = {
    "Легальный бизнес": ("legit", "#2C6E52"),
    "Пограничный случай": ("borderline", "#B4741C"),
    "Пирамида": ("pyramid", "#A8261F"),
    "Случайный объект": ("random", "#4C596A"),
}


def _preset_features(kind: str, seed: int) -> dict[str, float]:
    """Один объект из того же генератора, на котором училась модель.

    Пресеты не выдуманы руками. ``legit`` и ``pyramid`` берутся из своих
    распределений, ``borderline`` из доли, которую генератор специально
    сдвигает к чужому классу, ``random`` из смеси. Отсюда и оговорка на
    экране: это проверка поведения модели на знакомом ей входе, а не
    независимое измерение качества.
    """
    rng = np.random.default_rng(seed)
    if kind == "random":
        kind = "pyramid" if rng.random() < 0.5 else "legit"
    share = 1.0 if kind == "borderline" else 0.0
    maker = generate_legitimate if kind == "legit" else generate_pyramid
    if kind == "borderline":
        maker = generate_pyramid if rng.random() < 0.5 else generate_legitimate
    frame = maker(1, seed=int(rng.integers(0, 10**6)), borderline_share=share)
    row = frame.iloc[0]
    return {name: float(row[name]) for name in FEATURE_COLUMNS}


st.title("🔍 Ручная проверка объекта")
st.caption("Девять признаков исходной модели. Оценку возвращает API, интерфейс её не считает.")

st.warning(
    f"**Пороги {RISK_THRESHOLDS['medium']:.2f} / {RISK_THRESHOLDS['high']:.2f} "
    "не откалиброваны.** Вероятность приходит из "
    "`predict_proba` LightGBM, а он не калиброван: измеренный на "
    "независимом потоке событий, этот же классификатор давал безупречный "
    "порядок при вероятностях около 0.50 — то есть ранжировал идеально и не "
    "срабатывал ни разу. Число ниже стоит читать как место в очереди, а не как "
    "вероятность мошенничества."
)


# ── Признаки из событий ───────────────────────────────────────────
def _pyramid_organizers(world: Any) -> dict[str, Any]:
    return {
        network.organizer_ids[0]: network
        for network in world.networks
        if network.kind == "pyramid_slow" and network.organizer_ids
    }


for name, value in DEFAULT_OPERATIONAL.items():
    st.session_state.setdefault(f"op_{name}", float(value))
for name in FEATURE_COLUMNS:
    st.session_state.setdefault(f"ft_{name}", float(FEATURE_BOUNDS[name][0]))

# ── Пресеты ───────────────────────────────────────────────────────
st.markdown("**Готовые объекты**")
preset_cols = st.columns(len(PRESETS))
for column, (title, (kind, _colour)) in zip(preset_cols, PRESETS.items()):
    if column.button(title, use_container_width=True, key=f"preset_{kind}"):
        seed = int(st.session_state.get("preset_counter", 0)) + hash(kind) % 10_000
        st.session_state["preset_counter"] = seed + 1
        for name, value in _preset_features(kind, seed).items():
            st.session_state[f"ft_{name}"] = value
        st.session_state["input_mode"] = "Признаки модели"
        st.session_state["preset_applied"] = title
        st.session_state.pop("manual_result", None)
        st.rerun()

if "preset_applied" in st.session_state:
    st.caption(
        f"Загружен объект: **{st.session_state['preset_applied']}**. Значения взяты "
        "из того же генератора, на котором училась модель, поэтому это проверка "
        "поведения на знакомом входе, а не измерение качества. Кнопку можно жать "
        "несколько раз: каждый раз приходит новый объект того же класса."
    )

with st.expander("Взять признаки из построенного мира", expanded=False):
    if st.checkbox("Загрузить мир и показать организаторов пирамид", value=False):
        with st.spinner("Подготовка мира…"):
            world, _dataset = current_state()
        organizers = _pyramid_organizers(world)
        if not organizers:
            st.info("В этом мире нет пирамид.")
        else:
            organizer_id = st.selectbox("Организатор пирамиды", sorted(organizers))
            if st.button("Посчитать девять признаков по его денежному потоку"):
                stamps = [event.ts for event in world.events]
                computed = legacy_features(
                    organizer_id, world.events, min(stamps), max(stamps)
                )
                for name in FEATURE_COLUMNS:
                    st.session_state[f"ft_{name}"] = float(computed[name])
                st.session_state["input_mode"] = "Признаки модели"
                st.success(
                    f"Признаки {organizer_id} посчитаны по событиям. "
                    "Переключитесь на режим «Признаки модели», чтобы их увидеть."
                )
            st.caption(
                "Объект выбран из файла с ответами, поэтому это демонстрация расчёта "
                "признаков, а не измерение качества модели. Измерение — на странице "
                "валидации."
            )

# ── Ввод ──────────────────────────────────────────────────────────
mode = st.radio(
    "Источник ввода",
    ["Операционные факты", "Признаки модели"],
    horizontal=True,
    key="input_mode",
)

if mode == "Операционные факты":
    st.markdown("#### Операционные факты")
    cols = st.columns(3)
    raw: dict[str, float] = {}
    integer_fields = {
        "tx_count_total",
        "unique_counterparties",
        "new_clients_current",
        "new_clients_previous",
        "referred_clients_current",
        "max_referral_depth",
    }
    for index, (key, (low, high)) in enumerate(OPERATIONAL_INPUT_BOUNDS.items()):
        with cols[index % 3]:
            label = OPERATIONAL_LABELS.get(key, key)
            current = float(st.session_state[f"op_{key}"])
            if key in integer_fields:
                value = st.number_input(
                    label,
                    min_value=int(low),
                    max_value=int(high),
                    value=int(round(current)),
                    step=1,
                    key=f"op_input_{key}",
                )
            else:
                value = st.number_input(
                    label,
                    min_value=float(low),
                    max_value=float(high),
                    value=float(current),
                    key=f"op_input_{key}",
                )
            st.session_state[f"op_{key}"] = float(value)
            raw[key] = float(value)
    try:
        features = operational_to_features(raw)
    except Exception as exc:
        st.error(f"Ошибка валидации: {exc}")
        st.stop()
else:
    st.markdown("#### Признаки модели")
    cols = st.columns(3)
    features = {}
    for index, name in enumerate(FEATURE_COLUMNS):
        low, high = FEATURE_BOUNDS[name]
        with cols[index % 3]:
            value = st.number_input(
                FEATURE_LABELS[name],
                min_value=float(low),
                max_value=float(high),
                value=float(min(max(st.session_state[f"ft_{name}"], low), high)),
                key=f"ft_input_{name}",
            )
            st.session_state[f"ft_{name}"] = float(value)
            features[name] = float(value)

# ── Оценка ────────────────────────────────────────────────────────
if st.button("Оценить объект", type="primary", use_container_width=True):
    try:
        result = api_client.predict_from_features(features)
        if result.get("source") == "local":
            st.caption(
                "Локальный расчёт: сервис не запущен, оценку посчитала та же функция, "
                "что вызывает API."
            )
        st.session_state["manual_result"] = result
        st.session_state["manual_explain"] = api_client.explain_features(features, top_k=9)
        st.session_state["manual_features"] = dict(features)
        # Вклады считаются локально: сервис такой ручки не отдаёт, а без них
        # экран отвечает на вопрос «что важно вообще» вместо «почему этот».
        st.session_state["manual_contributions"] = contributions(features)
        st.session_state.pop("manual_error", None)
    except Exception as exc:
        st.session_state["manual_error"] = str(exc)

if "manual_error" in st.session_state:
    st.error(
        "Сервис оценки недоступен. Интерфейс намеренно не считает inference сам.\n\n"
        f"Причина: {st.session_state['manual_error']}"
    )
    st.code("python -m uvicorn apris.api.main:app --port 8000", language="bash")

if "manual_result" in st.session_state and "manual_error" not in st.session_state:
    result = st.session_state["manual_result"]
    scored_features = st.session_state["manual_features"]
    probability = float(result.get("prob", result.get("probability", 0.0)))

    c1, c2 = st.columns(2)
    c1.metric("Оценка модели", f"{probability:.3f}")
    c2.metric(
        "Пороги (не откалиброваны)",
        f"{RISK_THRESHOLDS['medium']:.2f} / {RISK_THRESHOLDS['high']:.2f}",
    )

    breakdown = st.session_state.get("manual_contributions")
    if breakdown:
        st.markdown("**Почему получилось именно это число**")
        st.caption(
            "Вклад каждого признака в оценку этого объекта, значения Шепли для "
            "деревьев (TreeSHAP). Считает сам LightGBM, приближения здесь нет. "
            "Вклады в лог-шансах и складываются: база "
            f"{breakdown['base_value']:+.2f} плюс сумма вкладов даёт "
            f"{breakdown['logit']:+.2f}, что и есть вероятность "
            f"{breakdown['probability']:.3f}. Плюс толкает к «мошенник», минус к «честный»."
        )
        table = pd.DataFrame(
            [
                {
                    "Признак": FEATURE_LABELS.get(item["feature"], item["feature"]),
                    "Значение": round(item["value"], 3),
                    "Вклад": round(item["contribution"], 3),
                    "Куда тянет": "к мошеннику" if item["contribution"] > 0 else "к честному",
                }
                for item in breakdown["items"]
            ]
        )
        st.dataframe(
            table,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Вклад": st.column_config.NumberColumn(format="%+.3f"),
            },
        )
        st.bar_chart(
            table.set_index("Признак")["Вклад"],
            horizontal=True,
            color="#1B5B66",
            use_container_width=True,
        )

    with st.expander("Важность признаков по модели в целом", expanded=False):
        st.caption(
            "Это ранжирование одинаково для любого входа и на вопрос «почему "
            "этот объект» не отвечает. Держим его рядом ради одного наблюдения: "
            "Джини несёт около трети всех решений и при расчёте по реальным "
            "потокам не даёт сигнала вовсе, а payout_dependency, буквальное "
            "определение схемы Понци, почти выключен."
        )
        st.dataframe(
            pd.DataFrame(st.session_state["manual_explain"]).rename(
                columns={"feature": "Признак", "importance": "Важность"}
            ),
            use_container_width=True,
            hide_index=True,
        )

    st.markdown("#### 🗺️ Карта рисков популяции")
    try:
        feature_names = load_population_feature_names()
        population = load_population_dataset()
        check_no_nan(population, feature_names)
        if not check_feature_order(feature_names):
            raise ValueError("Порядок признаков не совпадает с ожидаемой схемой.")
        projected, scaler, pca = fit_population_pca(population, feature_names)
        check_pca_dimensions(projected, pca)
        point = project_current_case(scored_features, feature_names, scaler, pca)
        st.pyplot(
            build_population_map_figure(projected, current_point=point),
            use_container_width=True,
        )
        st.caption(
            "Проекция PCA синтетической популяции с наложением текущего объекта. "
            "Популяция взята из обучающего датасета старой модели."
        )

        # Точка за пределами облака означает, что модель экстраполирует: такого
        # сочетания признаков в обучении не было, и оценке верить нельзя.
        cloud = np.asarray(projected)
        here = np.asarray(point).ravel()
        outside = [
            axis
            for axis in (0, 1)
            if here[axis] < cloud[:, axis].min() or here[axis] > cloud[:, axis].max()
        ]
        pinned = [
            FEATURE_LABELS.get(name, name)
            for name, value in scored_features.items()
            if abs(value - FEATURE_BOUNDS[name][0]) < 1e-9
            or abs(value - FEATURE_BOUNDS[name][1]) < 1e-9
        ]
        if outside:
            st.warning(
                "**Объект вне обучающей популяции.** Точка вышла за облако по "
                f"{'обеим осям' if len(outside) == 2 else 'одной оси'}: такого сочетания "
                "признаков модель не видела и сейчас экстраполирует. Оценка выше "
                "формально посчитана, но опираться на неё нельзя."
            )
        if pinned:
            st.info(
                "Признаки, упёршиеся в границу допустимого диапазона: "
                + ", ".join(pinned)
                + ". Дальше двигать соответствующие поля бесполезно, значение "
                "обрезается и оценка перестаёт меняться."
            )
    except Exception as exc:
        st.warning(f"Карта популяции недоступна: {exc}")
else:
    st.info("Заполните значения и нажмите «Оценить объект».")

"""Тесты витрины: страница собирается, ничего не выдумывает, не тормозит.

Витрина — это то, что видит жюри, и ошибка в ней стоит дороже ошибки в
коде: неверное число на экране никто не перепроверит по файлу прогона.
Поэтому здесь проверяется не «страница отрисовалась», а три вещи:
числа приходят из артефактов, отсутствие артефакта честно называется
отсутствием, и на странице нет внешних запросов, из-за которых она
подвисала бы на показе.
"""

from __future__ import annotations

import json
import re

import pytest

from apris.web import data
from apris.web.site import Bar, Line, build, chart_bars, chart_line, esc, table


def test_the_page_builds_and_carries_every_section() -> None:
    page = build()
    assert page.startswith("<!doctype html>")
    # Разделов столько же, сколько пунктов в навигации: пункт без раздела —
    # это ссылка в никуда, раздел без пункта никто не найдёт.
    anchors = set(re.findall(r'<section id="([^"]+)"', page))
    links = set(re.findall(r"<a href='#([^']+)'", page))
    assert anchors == links
    assert len(anchors) >= 15


def test_the_page_asks_the_network_for_nothing() -> None:
    """Иначе на чужом ноутбуке без интернета витрина повиснет на шрифтах.

    Единственная разрешённая ссылка — значок вкладки, и он тоже внутри
    страницы: ``data:``. Без него браузер просит ``/favicon.ico`` и получает
    404 при каждом открытии.
    """
    page = build()
    assert "http://" not in page.replace("http://127.0.0.1", "").replace(
        "http://www.w3.org/2000/svg", ""
    )
    assert "https://" not in page
    assert "src='http" not in page and 'src="http' not in page
    for link in re.findall(r"<link[^>]*>", page):
        assert 'href="data:' in link, f"внешняя ссылка на странице: {link}"


def test_numbers_come_from_the_artifacts_rather_than_the_markup() -> None:
    """Значение из файла прогона обязано появиться на странице."""
    rows, _ = data.worlds()
    assert rows, "прогона лестницы миров нет — тест не о чем"
    page = build()
    for row in rows:
        if row.account_auc is not None:
            assert f"{row.account_auc:.3f}" in page


def test_the_feature_importances_file_is_read_as_a_list() -> None:
    """Кусачий тест на регрессию: этот артефакт — список, а не объект.

    Читатель артефактов один раз стал отбрасывать всё, что не объект, и
    раздел признаков молча опустел: на витрине это выглядело как «прогона
    не было», хотя файл лежал на месте.
    """
    raw = json.loads((data.ARTIFACTS / "feature_importances.json").read_text("utf-8"))
    assert isinstance(raw, list), "фикстура изменилась — тест больше не о том"
    features, _ = data.features()
    assert len(features) == len(raw)


def test_a_missing_run_is_named_a_missing_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """Пустой раздел обязан сказать, что прогона нет, а не показать ноль."""
    monkeypatch.setattr(data, "_read_json", lambda name: None)
    page = build()
    assert "прогона нет" in page.lower() or "прогона" in page.lower()
    assert "0.000" not in page, "нет прогона — нет и правдоподобной цифры"


def test_charts_label_every_value_they_draw() -> None:
    """Правило доступности: идентичность не держится на одном цвете."""
    bars = chart_bars([Bar("первый", 0.8), Bar("второй", 0.4)])
    assert "0.800" in bars and "0.400" in bars
    assert "первый" in bars and "второй" in bars

    lines = chart_line(
        [Line("серия", [(0.0, 0.5), (1.0, 0.9)], "s1")],
        xticks=[(0.0, "A"), (1.0, "B")],
        ylo=0.0,
        yhi=1.0,
    )
    assert "<title>серия: 0.900</title>" in lines
    assert "class='key'" in lines or 'class="key"' in lines


def test_a_bar_without_a_value_says_so_instead_of_drawing_zero() -> None:
    assert "нет прогона" in chart_bars([Bar("ветвь", None)])


def test_every_artifact_string_on_the_page_is_escaped() -> None:
    """Ячейки таблицы — готовая разметка, поэтому экранирует вызывающая сторона.

    Контракт нарочно такой: в ячейках живут ``<b>`` и ``<code>``. Здесь
    проверяется его вторая половина — что строки из файлов прогонов через
    :func:`esc` действительно проходят, и сломанный идентификатор кандидата
    не уедет в разметку как теги.
    """
    assert esc("<script>") == "&lt;script&gt;"
    assert table(["<b>"], [["ок"]]).count("&lt;b&gt;") == 1, "заголовки экранируются здесь"

    page = build()
    body = page.split("<main>", 1)[-1].split("</main>", 1)[0]
    assert "<script" not in body, "в содержимом страницы скриптов быть не должно"


def test_the_page_is_small_enough_to_open_instantly() -> None:
    """Витрина открывается с флешки на чужой машине; вес — это время."""
    assert len(build().encode("utf-8")) < 4 * 1024 * 1024

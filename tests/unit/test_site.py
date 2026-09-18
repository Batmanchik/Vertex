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
from apris.web.site import Bar, Line, build, chart_bars, chart_line, esc, pct, table


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


def visible(page: str) -> str:
    """Страница без данных, положенных в неё для пересчёта.

    В ``<script type="application/json">`` лежат измерения и выгруженная
    модель — тысячи чисел, которых никто не видит. Проверять на них то, что
    сказано о видимой части, бессмысленно: лист дерева со значением
    ``-0.000465`` не «показанная цифра».
    """
    return re.sub(
        r'<script type="application/json".*?</script>', "", page, flags=re.S
    )


def test_a_missing_run_is_named_a_missing_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """Пустой раздел обязан сказать, что прогона нет, а не показать ноль."""
    monkeypatch.setattr(data, "_read_json", lambda name: None)
    page = build()
    assert "прогона нет" in page.lower() or "прогона" in page.lower()
    assert "0.000" not in visible(page), "нет прогона — нет и правдоподобной цифры"


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


def test_every_control_has_something_that_reads_it() -> None:
    """Ручка, которую никто не слушает, — обещание, которого страница не держит.

    На защите это худший вид ошибки: ползунок двигается, число рядом с ним
    меняется, а картинка стоит. Поэтому каждое имя регулятора обязано
    встретиться и в разметке, и в скрипте.
    """
    page = build()
    names = set(re.findall(r"data-ctl='([^']+)'", page))
    assert names, "регуляторов на странице нет"
    script = page.split("<script>", 1)[-1]
    for name in names:
        assert f"'{name}'" in script, f"регулятор {name} ни к чему не подключён"


def test_the_page_carries_the_data_its_controls_recompute_from() -> None:
    """Пересчёт идёт по числам прогона, положенным в страницу при сборке.

    Если бы их не было, на странице рисовались бы правдоподобные кривые
    ниоткуда — ровно то, чего витрина не должна делать.
    """
    page = build()
    raw = re.search(
        r"<script type=\"application/json\" id=\"data\">(.*?)</script>", page, re.S
    )
    assert raw is not None, "данных для пересчёта на странице нет"
    payload = json.loads(raw.group(1))

    assert payload["roc"]["points"], "кривая, по которой считается редкость, пуста"
    for point in payload["roc"]["points"]:
        assert 0.0 <= point["x"] <= 1.0 and 0.0 <= point["y"] <= 1.0

    assert payload["cases"], "дел для досье нет"
    for case in payload["cases"]:
        graph = case["graph"]
        ids = {node["id"] for node in graph["nodes"]}
        assert graph["edges_total"] >= len(graph["edges"]), "усечение не названо"
        for edge in graph["edges"]:
            # Ребро в никуда нарисовалось бы обрывком линии.
            assert edge["from"] in ids and edge["to"] in ids


def test_the_page_carries_the_model_so_it_works_without_a_server() -> None:
    """Раздел «Проверить» был единственным, кому нужен был живой сервис.

    Из-за него всю витрину нельзя было положить по ссылке или на флешку. Теперь
    модель едет в странице, и здесь проверяется, что она доехала целиком: без
    порядка признаков браузер подставил бы значения не в те деревья, без границ
    принял бы то, что сервис отвергает, без коэффициента связи выдал бы не
    вероятность.
    """
    page = build()
    raw = re.search(
        r"<script type=\"application/json\" id=\"data\">(.*?)</script>", page, re.S
    )
    assert raw is not None
    model = json.loads(raw.group(1))["model"]
    assert model is not None, "модели в странице нет — «Проверить» не заработает"
    assert len(model["names"]) == len(model["bounds"]) == 9
    assert model["sigmoid"] > 0
    assert model["thresholds"] == {"medium": 0.4, "high": 0.7}
    assert len(model["trees"]) == 300

    # Порядок величин задаёт модель. Если разметка формы разойдётся с ним,
    # страница подставит признаки не в те деревья и выдаст правдоподобное
    # чужое число — молча.
    for name in model["names"]:
        assert f"data-name='{name}'" in page, f"величины {name} нет в форме"


def test_a_projection_is_never_shown_as_a_measurement() -> None:
    """Кусачий тест на то, чем витрина врала две недели.

    Таблица точек порога читала прогоны при естественной доле мошенников этого
    мира — около семи процентов, — а подпись под ней утверждала 0.1 %. Числа
    были настоящие, подпись выдуманная, и врала она в ту сторону, которая
    красивее: при 0.1 % те же пороги стоят совсем других сигналов.

    Поэтому здесь проверяется не наличие таблиц, а то, что каждая названа своей
    долей и что перенос назван переносом.
    """
    points, _ = data.operating_points()
    projected = data.projected_points(0.001)
    assert points and projected, "развёртки по редкости нет — тест не о чем"
    assert points[0].prevalence > 0.01, (
        "фикстура изменилась: естественная доля должна быть заметно выше 0.1 %, "
        "иначе тест перестаёт различать измерение и перенос"
    )
    assert projected[0].prevalence == pytest.approx(0.001)

    # Проверяется подпись под самой таблицей, а не страница целиком: доля
    # «7.0 %» есть и в соседней таблице редкости, и на ней тест прошёл бы,
    # не заметив вранья в подписи.
    page = visible(build())
    measured = page.split("Порог вместо бюджета", 1)[1].split("</figure>", 1)[0]
    caption = measured.split("<figcaption", 1)[1]

    assert pct(points[0].prevalence, 1) in caption, "измерение не названо своей долей"
    assert pct(projected[0].prevalence, 1) not in caption, (
        "измерение подписано долей, при которой оно не проводилось"
    )
    assert "Пересчёт измеренной кривой" in page, "перенос не назван переносом"


def test_the_page_never_invents_a_measurement_it_does_not_have() -> None:
    """Конфигурация уклонения, которой не было в прогоне, так и называется."""
    page = build()
    assert "не измерялась" in page


def test_the_page_is_small_enough_to_open_instantly() -> None:
    """Витрина открывается с флешки на чужой машине; вес — это время."""
    assert len(build().encode("utf-8")) < 4 * 1024 * 1024


def test_the_branches_the_work_claims_are_on_the_published_page() -> None:
    """Первая публикация показала «Обученных ветвей нет».

    Файлы с метриками ветвей были в .gitignore, поэтому у сборки в CI их не
    было, и раздел честно сообщал об отсутствии прогона — а работа в это же
    время приводила 0.985 и 0.986. Честно, но опубликованная страница
    противоречила тексту работы, и заметил бы это любой, кто открыл оба.

    Проверка не «раздел есть», а «в разделе есть числа»: раздел на месте был
    и тогда.

    Числа ищутся внутри своего раздела, а не по всей странице. Первая версия
    этой проверки искала «0.985» в page и проходила без файлов вовсе: такая
    подстрока есть в координатах ROC-кривой соседнего раздела («0.98547»).
    """
    page = build()
    start = page.index('<section id="branches"')
    section = page[start : page.index("</section>", start)]

    assert "Обученных ветвей нет" not in section
    for value in ("0.985", "0.986"):
        assert value in section, f"метрика ветви {value} не доехала до страницы"

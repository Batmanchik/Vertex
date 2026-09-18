"""Заполнение школьного бланка дневника НИР по материалам работы.

    python scripts/fill_diary_form.py БЛАНК.docx [ВЫХОД.docx]

Бланк выдан школой пустым и рассчитан на заполнение от руки, но допускает и
электронное. Заполняется он не выдумкой: даты этапов взяты из истории
проекта, а числа в графе результатов — из файлов прогонов, тех же самых, на
которые ссылается текст работы.

Две даты здесь настоящие и проверяемые. Февраль 2026 — хакатон по
финансовой безопасности ДЭР РК, он же начало работы над темой. Начало
сентября 2026 — прогоны, по которым получены итоговые числа; это видно по
отметкам времени в artifacts/*.json. Остальные границы этапов расставлены
как план и правятся руками, если фактические сроки были другими.

Бланк не пересобирается: открывается как есть и дополняется, поэтому
шапка, рамки таблиц и стили школы остаются нетронутыми.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# ── Шапка: что подставить вместо прочерков ───────────────────────────
HEADER = {
    "Область/город, школа":
        "Область/город, школа: г. Шымкент, Назарбаев Интеллектуальная школа "
        "физико-математического направления",
    "ФИО ученика":
        "ФИО ученика: Усипбаев Алибек, учащийся 12N класса",
    "ФИО руководителя":
        "ФИО руководителя: Орынбасаров Б.Н.",
    "Предмет":
        "Предмет: Информатика                    Секция: Информационные системы "
        "и технологии",
    "Направление":
        "Направление: Математика и прикладные технологии",
    "Тема проекта":
        "Тема проекта: VERTEX — система сквозного топологического мониторинга "
        "транзитно-аккумуляционных аномалий капитала",
    "Утвержденный срок":
        "Утвержденный срок выполнения работы: февраль 2026 — октябрь 2026",
    "Планируемый срок":
        "Планируемый срок завершения работы: 30 сентября 2026",
}

# ── Подготовительный этап: ответ дописывается под вопросом ───────────
STAGE_ONE = {
    "Обоснование научно-исследовательской работы":
        "Добытые преступлением деньги надо провести через счета. Мониторинг проверяет "
        "платежи поштучно и судит по данным владельца, а их меняют за минуты.",
    "Выбор направления и темы исследования":
        "Теория графов и машинное обучение. Тема появилась в феврале 2026 года при "
        "подготовке к хакатону ДЭР РК.",
    "Актуальность темы":
        "За полугодие 2025 года в РК ликвидировали 36 пирамид, втянуто свыше 86 тысяч "
        "человек. До 95 % тревог антифрода ложные.",
    "Цель исследования":
        "Создать систему «Vertex», находящую транзитно-аккумуляционные аномалии по "
        "форме денежного потока, без чёрных списков.",
    "Задачи":
        "Разобрать границы правил; формализовать граф и его аномалии; проверить "
        "временной инвариант; сделать разрешение сущностей и ансамбль; проверить "
        "на Elliptic.",
    "Объект и Предмет исследования":
        "Объект — граф транзакций. Предмет — признаки формы потока, отличающие схемы "
        "от обычной активности.",
    "Гипотеза исследовательской работы":
        "Реквизиты меняются за минуты, форма потока — нет: транзит без накопления, "
        "сходящийся в точку вывода, остаётся инвариантом.",
    "План научно-исследовательской работы":
        "Теория: границы правил, опыт FRAML, формализация аномалий. Практика: "
        "генератор миров, признаки формы, ансамбль, проверка на Elliptic.",
}

# ── Этапы II–V: даты, что сделано, период, примечание ────────────────
# Ключ — начало готовой формулировки в бланке.
STAGES: dict[str, tuple[str, str, str, str]] = {
    "Поиск и сбор информации": (
        "03.02 — 28.02.2026",
        "Нормативные акты РК, регламенты Антифрод-центра, Quantexa и Feedzai, Акоглу (2015).",
        "4 недели",
        "Хакатон ДЭР РК: Топ-5 из 60+ команд",
    ),
    "Анализ и систематизация данных": (
        "02.03 — 31.03.2026",
        "Формализован граф, выделены пять структурных подписей схем и метрики окрестности.",
        "4 недели",
        "",
    ),
    "Выбор методов исследования": (
        "01.04 — 30.04.2026",
        "NetworkX, разрешение сущностей на Elasticsearch, ансамбль LightGBM, протокол purged walk-forward.",
        "4 недели",
        "",
    ),
    "Проведение исследования/эксперимента": (
        "04.05 — 31.08.2026",
        "Стенд и генератор миров. Лестница миров, кривая уклонения, развёртка по редкости. Прогон на Elliptic.",
        "17 недель",
        "Данные синтетические, кроме Elliptic",
    ),
    "Обработка и интерпретация результатов": (
        "01.09 — 14.09.2026",
        "ROC-AUC 0.940 по счетам и 0.991 по группам против 0.757 и 0.761 у правил; на Elliptic 0.687 против 0.454 у контроля. Параметр W проверки не выдержал.",
        "2 недели",
        "Числа читаются из файлов прогонов",
    ),
    "Написание текста работы": (
        "15.09 — 25.09.2026",
        "Текст, заключение, список источников. Каждое число сверено с прогоном.",
        "2 недели",
        "",
    ),
    "Подготовка к защите": (
        "26.09 — 10.10.2026",
        "Презентация и доклад. Веб-витрина, читающая файлы прогонов.",
        "2 недели",
        "",
    ),
    "Защита проекта": ("октябрь 2026", "", "по графику конкурса", ""),
    "Рефлексия и оценка": ("октябрь 2026", "", "", ""),
}


def fill_header(document: object) -> int:
    """Подставить значения вместо прочерков в шапке."""
    filled = 0
    for paragraph in document.paragraphs:  # type: ignore[attr-defined]
        for marker, value in HEADER.items():
            if paragraph.text.strip().startswith(marker):
                keep = paragraph.runs[0] if paragraph.runs else None
                for run in list(paragraph.runs)[1:]:
                    run._element.getparent().remove(run._element)
                if keep is not None:
                    keep.text = value
                else:
                    paragraph.add_run(value)
                filled += 1
                break
    return filled


def answer(cell: object, text: str) -> None:
    """Дописать ответ под вопросом, сохранив оформление ячейки.

    Отступы до и после ставятся в ноль: семнадцать добавленных абзацев со
    стандартным отступом в 10 пунктов давали четверть страницы пустоты, а
    бланк обязан остаться трёхстраничным.
    """
    from docx.shared import Pt

    source = cell.paragraphs[-1]  # type: ignore[attr-defined]
    new = cell.add_paragraph()  # type: ignore[attr-defined]
    new.paragraph_format.alignment = source.paragraph_format.alignment
    new.paragraph_format.space_before = Pt(0)
    new.paragraph_format.space_after = Pt(0)
    new.paragraph_format.line_spacing = 1.0
    run = new.add_run(text)
    run.italic = True
    if source.runs:
        run.font.name = source.runs[0].font.name
        run.font.size = source.runs[0].font.size


def fill_preparation(table: object) -> int:
    """Подготовительный этап: ответ под каждым вопросом."""
    filled = 0
    for row in table.rows:  # type: ignore[attr-defined]
        cell = row.cells[-1]
        head = cell.text.strip()
        for marker, text in STAGE_ONE.items():
            if head.startswith(marker):
                answer(cell, text)
                filled += 1
                break
    return filled


def fill_stages(table: object) -> int:
    """Этапы II–V: даты, сделанное, период, примечание."""
    filled = 0
    for row in table.rows:  # type: ignore[attr-defined]
        cells = row.cells
        if len(cells) < 5:
            continue
        work = cells[2].text.strip()
        for marker, (dates, done, period, note) in STAGES.items():
            if not work.startswith(marker):
                continue
            answer(cells[1], dates)
            if done:
                answer(cells[2], done)
            if period:
                answer(cells[3], period)
            if note:
                answer(cells[4], note)
            filled += 1
            break
    return filled


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    import docx

    source = Path(sys.argv[1])
    target = Path(sys.argv[2]) if len(sys.argv) > 2 else (
        ROOT / "artifacts" / "Vertex_diary_filled.docx")

    document = docx.Document(str(source))
    header = fill_header(document)
    preparation = fill_preparation(document.tables[0])
    stages = fill_stages(document.tables[1])

    target.parent.mkdir(parents=True, exist_ok=True)
    document.save(str(target))

    print(f"готово: {target}")
    print(f"  шапка: {header} из {len(HEADER)}")
    print(f"  подготовительный этап: {preparation} из {len(STAGE_ONE)}")
    print(f"  этапы II–V: {stages} из {len(STAGES)}")
    if header < len(HEADER) or preparation < len(STAGE_ONE) or stages < len(STAGES):
        print("  ВНИМАНИЕ: часть полей не найдена — бланк отличается от ожидаемого")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

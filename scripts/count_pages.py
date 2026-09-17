"""Сколько страниц займёт docx: не коэффициенты, а имитация потока.

    python scripts/count_pages.py РАБОТА.docx

Зачем. Ни LibreOffice, ни pandoc в окружении проекта не работают, а печатный
лимит школы жёсткий: двадцать страниц. Прошлый счётчик складывал средние и
ошибся на шесть страниц — он не считал принудительные разрывы. Здесь абзацы
кладутся на страницу по очереди, как в Word: рисунок не рвётся посередине,
разрыв уводит на новую страницу, а остаток прежней просто теряется.

Единственный подогнанный параметр — знаков в строке. Он откалиброван по
счётчику Word на версии этой же работы, которую Word показал как 23 страницы,
и оценка не меняется на всём диапазоне 70–82 знака: страничный итог держат
разрывы, а не точность переноса слов. Проверять калибровку следует так же:
взять версию с известным по Word числом страниц и убедиться, что счётчик
даёт то же число.
"""

from __future__ import annotations

import math
import sys
import zipfile

from lxml import etree

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"

CHARS_PER_LINE_AT_12PT = 78.0
ASCENT = 1.15          # высота строки TNR относительно кегля
ROW_PADDING_PT = 3.0


def usable(section: etree._Element) -> tuple[float, float]:
    size = section.find(f"{W}pgSz")
    margin = section.find(f"{W}pgMar")
    height = int(size.get(f"{W}h")) / 20
    width = int(size.get(f"{W}w")) / 20
    top = int(margin.get(f"{W}top")) / 20
    bottom = int(margin.get(f"{W}bottom")) / 20
    left = int(margin.get(f"{W}left")) / 20
    right = int(margin.get(f"{W}right")) / 20
    return width - left - right, height - top - bottom


class Styles:
    """Кегль и междустрочие, унаследованные абзацем от своего стиля."""

    def __init__(self, xml: bytes) -> None:
        self.root = etree.fromstring(xml)
        self.by_id: dict[str, etree._Element] = {
            style.get(f"{W}styleId"): style for style in self.root.iter(f"{W}style")
        }
        defaults = self.root.find(f"{W}docDefaults")
        self.default = self.read(defaults) if defaults is not None else (12.0, 1.0, 0.0, 0.0)

    def read(self, node: etree._Element | None) -> tuple[float, float, float, float]:
        size, line, after, before = 0.0, 0.0, 0.0, 0.0
        if node is None:
            return size, line, after, before
        sz = next(iter(node.iter(f"{W}sz")), None)
        if sz is not None:
            size = int(sz.get(f"{W}val")) / 2
        spacing = next(iter(node.iter(f"{W}spacing")), None)
        if spacing is not None:
            if spacing.get(f"{W}line"):
                line = int(spacing.get(f"{W}line")) / 240
            if spacing.get(f"{W}after"):
                after = int(spacing.get(f"{W}after")) / 20
            if spacing.get(f"{W}before"):
                before = int(spacing.get(f"{W}before")) / 20
        return size, line, after, before

    def resolve(self, style_id: str | None) -> tuple[float, float, float, float]:
        chain: list[tuple[float, float, float, float]] = []
        seen: set[str] = set()
        while style_id and style_id in self.by_id and style_id not in seen:
            seen.add(style_id)
            style = self.by_id[style_id]
            chain.append(self.read(style))
            parent = style.find(f"{W}basedOn")
            style_id = parent.get(f"{W}val") if parent is not None else None
        chain.append(self.read(self.root.find(f"{W}docDefaults")))
        chain.append((12.0, 1.15, 4.0, 0.0))
        out: list[float] = []
        for index in range(4):
            out.append(next((c[index] for c in chain if c[index]), 0.0))
        return out[0], out[1], out[2], out[3]


def paragraph_metrics(
    paragraph: etree._Element, styles: Styles
) -> tuple[float, float, float, float]:
    props = paragraph.find(f"{W}pPr")
    style = props.find(f"{W}pStyle") if props is not None else None
    size, line, after, before = styles.resolve(style.get(f"{W}val") if style is not None else None)
    direct = styles.read(props)
    if direct[1]:
        line = direct[1]
    if direct[2]:
        after = direct[2]
    if direct[3]:
        before = direct[3]
    run = next(iter(paragraph.iter(f"{W}rPr")), None)
    if run is not None:
        sz = next(iter(run.iter(f"{W}sz")), None)
        if sz is not None:
            size = int(sz.get(f"{W}val")) / 2
    return size, line, after, before


def main(path: str) -> int:
    archive = zipfile.ZipFile(path)
    document = etree.fromstring(archive.read("word/document.xml"))
    styles = Styles(archive.read("word/styles.xml"))
    body = document.find(f"{W}body")
    width, height = usable(list(document.iter(f"{W}sectPr"))[-1])

    pages = 1
    cursor = 0.0
    figure_pt = 0.0
    text_chars = 0
    breaks = 0
    wasted = 0.0

    def place(block: float, atomic: bool) -> None:
        nonlocal pages, cursor, wasted
        if atomic and cursor > 0 and cursor + block > height:
            wasted += height - cursor
            pages += 1
            cursor = 0.0
        cursor += block
        while cursor > height:
            cursor -= height
            pages += 1

    for node in body:
        tag = etree.QName(node).localname
        if tag == "p":
            size, line, after, before = paragraph_metrics(node, styles)
            line_pt = size * ASCENT * (line or 1.0)
            extent = next(iter(node.iter(f"{WP}extent")), None)
            if extent is not None:
                block = int(extent.get("cy")) / 12700 + after + before
                figure_pt += block
                place(block, atomic=True)
                continue
            text = "".join(t.text or "" for t in node.iter(f"{W}t"))
            text_chars += len(text)
            per_line = CHARS_PER_LINE_AT_12PT * (12.0 / size) * (width / 403.0)
            lines = max(1, math.ceil(len(text) / per_line)) if text else 1
            place(lines * line_pt + after + before, atomic=False)
            if any(br.get(f"{W}type") == "page" for br in node.iter(f"{W}br")):
                breaks += 1
                wasted += height - cursor
                pages += 1
                cursor = 0.0
        elif tag == "tbl":
            for row in node.iter(f"{W}tr"):
                cells = [
                    "".join(t.text or "" for t in cell.iter(f"{W}t"))
                    for cell in row.iter(f"{W}tc")
                ]
                per_cell = max(1, len(cells))
                widest = max(
                    (math.ceil(len(c) / max(8.0, CHARS_PER_LINE_AT_12PT / per_cell)) for c in cells),
                    default=1,
                )
                place(max(1, widest) * 12 * ASCENT * 1.15 + ROW_PADDING_PT, atomic=True)
            place(6.0, atomic=False)

    print(f"{path.split('/')[-1]}")
    print(f"  знаков текста   {text_chars}")
    print(f"  рисунки         {figure_pt / height:.1f} стр. ({figure_pt:.0f} pt)")
    print(f"  разрывов        {breaks}, потеряно на них и переносах "
          f"{wasted / height:.1f} стр.")
    print(f"  ВСЕГО           {pages} страниц (поле {width:.0f}×{height:.0f} pt), "
          f"последняя заполнена на {cursor / height:.0%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))

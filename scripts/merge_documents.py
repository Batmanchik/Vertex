"""Сшить научную работу и заполненный дневник в один файл.

    python scripts/merge_documents.py РАБОТА.docx ДНЕВНИК.docx [ВЫХОД.docx]

Почему не «скопировать и вставить». У документов разная разметка страницы:
у работы поле 484×679 пунктов, у школьного бланка 513×815. Если просто
слить содержимое, бланк примет поля работы и разъедется — таблицы вылезут
за край. Поэтому вставка идёт через разрыв раздела: каждая часть сохраняет
свой размер страницы, поля и колонтитулы.

Тем же разрывом решается и вторая беда — совпадающие имена стилей. Если у
обоих файлов есть свой ``Normal`` или ``Table Grid``, наивная склейка молча
подменит оформление одной части оформлением другой. docxcompose переносит
стили, нумерацию и картинки с переименованием там, где имена сталкиваются.

Проверка после сшивки обязательна: число картинок и таблиц должно равняться
сумме по частям, иначе что-то потерялось по дороге.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def count(path: Path) -> tuple[int, int, int]:
    """Картинки, таблицы и абзацы — то, что не должно потеряться."""
    from lxml import etree

    archive = zipfile.ZipFile(path)
    document = etree.fromstring(archive.read("word/document.xml"))
    images = sum(
        1 for name in archive.namelist()
        if name.startswith("word/media/")
        and name.rsplit(".", 1)[-1].lower() in {"png", "jpg", "jpeg", "emf", "wmf", "gif"}
    )
    tables = len(list(document.iter(f"{W}tbl")))
    paragraphs = len(list(document.iter(f"{W}p")))
    return images, tables, paragraphs


DIARY_FIRST_LINE = "Дневник заполняется от руки"


def split_sections(merged: Path, second: Path) -> bool:
    """Поставить разрыв раздела на стыке, чтобы части сохранили свои поля.

    docxcompose сливает тело в один раздел, и вторая часть принимает поля
    первой. Здесь на стык ставится разрыв: свойства страницы работы уезжают
    в абзац перед дневником, а свойства дневника становятся свойствами
    последнего раздела.
    """
    import copy

    import docx

    document = docx.Document(str(merged))
    body = document.element.body
    tail = body.find(f"{W}sectPr")
    if tail is None:
        return False

    def text_of(node: object) -> str:
        return "".join(run.text or "" for run in node.iter(f"{W}t")).strip()

    boundary = next(
        (node for node in body if text_of(node).startswith(DIARY_FIRST_LINE)), None)
    if boundary is None:
        return False

    # Абзац-носитель разрыва: в нём лежат свойства страницы первой части.
    carrier = copy.deepcopy(boundary)
    for child in list(carrier):
        carrier.remove(child)
    props = carrier.makeelement(f"{W}pPr", {})
    props.append(copy.deepcopy(tail))
    carrier.append(props)
    boundary.addprevious(carrier)

    # Последний раздел получает разметку страницы дневника.
    own = docx.Document(str(second)).element.body.find(f"{W}sectPr")
    if own is not None:
        body.remove(tail)
        body.append(copy.deepcopy(own))

    document.save(str(merged))
    return True


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 1

    import docx
    from docxcompose.composer import Composer

    first = Path(sys.argv[1])
    second = Path(sys.argv[2])
    target = Path(sys.argv[3]) if len(sys.argv) > 3 else (
        ROOT / "artifacts" / "Vertex_full.docx")

    before = [count(first), count(second)]

    document = docx.Document(str(first))
    composer = Composer(document)
    composer.append(docx.Document(str(second)))

    target.parent.mkdir(parents=True, exist_ok=True)
    composer.save(str(target))
    split_sections(target, second)

    after = count(target)
    expected = tuple(a + b for a, b in zip(before[0], before[1]))

    print(f"готово: {target}")
    names = ("картинок", "таблиц", "абзацев")
    ok = True
    for index, name in enumerate(names):
        got, want = after[index], expected[index]
        mark = "✓" if got >= want else "ПОТЕРЯНО"
        if got < want:
            ok = False
        print(f"  {name:<10} {got:4d}  (работа {before[0][index]} + дневник "
              f"{before[1][index]} = {want}) {mark}")

    from lxml import etree

    archive = zipfile.ZipFile(target)
    for name in archive.namelist():
        if name.endswith((".xml", ".rels")):
            etree.fromstring(archive.read(name))
    print("  XML целостен ✓")

    sections = len(list(
        etree.fromstring(archive.read("word/document.xml")).iter(f"{W}sectPr")))
    print(f"  разделов   {sections} (нужно 2: у частей разная разметка страницы)")
    if sections < 2:
        print("  ВНИМАНИЕ: разрыва раздела нет, бланк примет поля работы")
        ok = False

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

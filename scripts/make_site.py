"""Собрать витрину: один статический файл со всеми измерениями.

    python scripts/make_site.py
    python scripts/make_site.py --out /tmp/vertex.html

Читает `artifacts/*.json` и кладёт `artifacts/site/index.html` — страницу без
единого внешнего запроса: шрифты системные, графики инлайновым SVG, картинки
вшиты. Открывается двойным щелчком, в том числе с флешки и без интернета.

Прежняя витрина была страницей Streamlit, и на защите её задержки видно. Здесь
питон работает один раз, при сборке; на показе работает только браузер.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from apris.web.site import write


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=None, help="куда положить файл")
    args = parser.parse_args()

    started = time.time()
    path = write(args.out)
    size = path.stat().st_size / 1024
    print(f"собрано: {path}  ({size:.0f} КБ, {time.time() - started:.1f} с)")
    print("открыть: file://" + str(path.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

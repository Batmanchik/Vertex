"""Поднять сайт на локальной машине: одна команда, один адрес.

    python scripts/serve.py                 # http://127.0.0.1:8000
    python scripts/serve.py --port 9000
    python scripts/serve.py --no-pipeline   # не пересобирать очередь

Сайт и есть проект: на нём все измерения, разбор системы по шагам, дефекты,
ответы на вопросы жюри и форма, которая считает прямо сейчас. Отдельного
интерфейса больше нет — раньше рядом крутился Streamlit, и на защите это
были два адреса и заметные задержки.

Страница пересобирается на каждый запрос из `artifacts/*.json`: пересчитали
прогон — обновили вкладку. Собрать её же в файл, который работает без
сервера: `python scripts/make_site.py`.
"""

from __future__ import annotations

import argparse
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--preset", choices=("quick", "full"), default="full")
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--no-pipeline", action="store_true",
                        help="не пересобирать очередь, взять последнюю")
    args = parser.parse_args()

    if not args.no_pipeline:
        print("1/2  собираю очередь аналитика…", flush=True)
        pipeline = subprocess.run(
            [sys.executable, "scripts/run_pipeline.py",
             "--preset", args.preset, "--seed", str(args.seed)],
            check=False,
        )
        if pipeline.returncode != 0:
            print("     конвейер упал — сайт поднимется, очередь будет прежней")
    else:
        print("1/2  очередь не пересобираю")

    print(f"2/2  поднимаю сайт: http://{args.host}:{args.port}", flush=True)
    import uvicorn

    uvicorn.run("apris.api.main:app", host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

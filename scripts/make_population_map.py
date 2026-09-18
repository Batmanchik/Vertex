"""Карта популяции: четыре тысячи дел на плоскости и место нового среди них.

    python scripts/make_population_map.py

Девять признаков — это девятимерное пространство, и показать его нельзя.
PCA сворачивает его в плоскость: две оси, на которых рассеяние точек
наибольшее. Каждая точка — одно из 4 000 синтетических дел полигона, цвет
говорит правду о нём: честное, пирамида или пограничное.

Витрине нужны не картинка, а числа, чтобы точку нового дела считал браузер
и она двигалась вместе с регуляторами раздела «Проверить». Поэтому сюда
пишутся и сами точки, и преобразование целиком: средние и масштабы
нормировки, центр и две главные компоненты. Проекция нового дела — это
вычитание, деление и два скалярных произведения, браузер делает их сам.

Пишет artifacts/population_map.json.
"""

from __future__ import annotations

import json
from pathlib import Path

from apris.population_map import (
    FEATURE_COLUMNS,
    fit_population_pca,
    load_population_dataset,
)

OUT = Path("artifacts") / "population_map.json"


def main() -> int:
    frame = load_population_dataset()
    projected, scaler, pca = fit_population_pca(frame, FEATURE_COLUMNS)
    print(f"дел: {len(projected)}, из них пирамид {int(projected['label'].sum())}, "
          f"пограничных {int(projected['is_borderline'].sum())}")

    # Класс точки: 0 честное, 1 пирамида, 2 пограничное. Пограничные рисуются
    # отдельно — это дела, про которые генератор сам не уверен, и именно на
    # них видно, где у модели проходит граница.
    points = [
        [round(float(row.PCA1), 3), round(float(row.PCA2), 3),
         2 if bool(row.is_borderline) else int(row.label)]
        for row in projected.itertuples()
    ]

    report = {
        "task": "карта популяции, PCA по девяти признакам",
        "features": list(FEATURE_COLUMNS),
        "cases": {
            "total": len(points),
            "legit": int((projected["label"] == 0).sum()),
            "pyramid": int((projected["label"] == 1).sum()),
            "borderline": int(projected["is_borderline"].sum()),
        },
        "explained": [round(float(v), 4) for v in pca.explained_variance_ratio_],
        "transform": {
            "mean": [round(float(v), 6) for v in scaler.mean_],
            "scale": [round(float(v), 6) for v in scaler.scale_],
            "center": [round(float(v), 6) for v in pca.mean_],
            "components": [[round(float(v), 6) for v in row] for row in pca.components_],
        },
        "bounds": {
            "x": [round(float(projected["PCA1"].min()), 3),
                  round(float(projected["PCA1"].max()), 3)],
            "y": [round(float(projected["PCA2"].min()), 3),
                  round(float(projected["PCA2"].max()), 3)],
        },
        "points": points,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, separators=(",", ":")),
                   encoding="utf-8")
    share = sum(report["explained"])
    print(f"две оси держат {share:.1%} разброса")
    print(f"записано: {OUT} ({OUT.stat().st_size / 1024:.0f} КБ)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

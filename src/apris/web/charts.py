"""Геометрия графиков витрины.

Координаты считаются здесь, а не пишутся в шаблоне руками: если прогон
пересчитают и числа сдвинутся, график сдвинется вместе с ними.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Axis:
    """Отображение значения в координату холста."""

    lo: float
    hi: float
    a: float
    b: float
    flip: bool = False

    def __call__(self, value: float) -> float:
        span = (self.hi - self.lo) or 1.0
        t = (value - self.lo) / span
        if self.flip:
            t = 1.0 - t
        return self.a + t * (self.b - self.a)


@dataclass
class Series:
    points: str
    dots: list[tuple[float, float]]


def _series(pairs: list[tuple[float, float]], x: Axis, y: Axis) -> Series:
    dots = [(round(x(px), 1), round(y(py), 1)) for px, py in pairs]
    return Series(" ".join(f"{a},{b}" for a, b in dots), dots)


# ──────────────────────────────────────────────────────────────────────
def worlds_chart(rows, *, width=506, height=150, pad_left=46, pad_top=12):
    """Две линии по мирам: счётный уровень и групповой."""
    lo, hi = 0.90, 1.005
    y = Axis(lo, hi, pad_top, height, flip=True)
    n = max(len(rows) - 1, 1)
    x = Axis(0, n, pad_left, width)

    acct = [(i, r.account_auc) for i, r in enumerate(rows) if r.account_auc is not None]
    net = [(i, r.network_auc) for i, r in enumerate(rows) if r.network_auc is not None]

    missing = [i for i, r in enumerate(rows) if r.network_auc is None]
    # Полоса разброса по сидам: честнее одной средней точки.
    band = [
        {
            "x": round(x(i), 1),
            "top": round(y(r.auc_max), 1),
            "bottom": round(y(r.auc_min), 1),
        }
        for i, r in enumerate(rows)
        if r.auc_min is not None and r.auc_max is not None
    ]
    return {
        "band": band,
        "account": _series(acct, x, y),
        "network": _series(net, x, y),
        "ticks_y": [(f"{g:.3f}".rstrip("0").rstrip("."), round(y(g), 1))
                    for g in (0.90, 0.925, 0.95, 0.975, 1.0)],
        "ticks_x": [(r.key, round(x(i), 1), r.note) for i, r in enumerate(rows)],
        "missing_x": [round(x(i), 1) for i in missing],
        "missing_y": round(y(hi - 0.005), 1),
        "width": width,
        "height": height,
        "pad_left": pad_left,
        "canvas": width + 78,
    }


def evasion_chart(rows, *, width=498, height=140, pad_left=46, pad_top=12):
    """Доля найденных банд против числа источников и числа банкоматов."""
    y = Axis(0.0, 1.0, pad_top, height, flip=True)
    x = Axis(1, 6, pad_left, width)

    funders = [(r.funders, r.found_share) for r in rows
               if r.atms == 1 and r.found_share is not None]
    atms = [(r.atms, r.found_share) for r in rows
            if r.funders == 1 and r.found_share is not None]
    funders.sort()
    atms.sort()

    return {
        "funders": _series(funders, x, y),
        "atms": _series(atms, x, y),
        "ticks_y": [(f"{g:.2f}", round(y(g), 1)) for g in (0, 0.25, 0.5, 0.75, 1.0)],
        "ticks_x": [(str(v), round(x(v), 1)) for v in (1, 2, 3, 4, 5, 6)],
        "break_x": round(x(3), 1),
        "width": width,
        "height": height,
        "pad_left": pad_left,
        "canvas": width + 72,
    }


def rarity_chart(rows, key, *, lo, hi, width=270, height=110, pad_left=44, pad_top=10):
    """Одна метрика против доли мошенников. Две метрики — два графика."""
    y = Axis(lo, hi, pad_top, height, flip=True)
    n = max(len(rows) - 1, 1)
    x = Axis(0, n, pad_left, width)
    pairs = [(i, getattr(r, key)) for i, r in enumerate(rows) if getattr(r, key) is not None]
    step = (hi - lo) / 3
    return {
        "line": _series(pairs, x, y),
        "ticks_y": [(g, round(y(g), 1)) for g in (lo, lo + step, lo + 2 * step, hi)],
        "ticks_x": [(f"{r.prevalence * 100:.1f}%".replace(".0%", "%"), round(x(i), 1))
                    for i, r in enumerate(rows)],
        "width": width,
        "height": height,
        "pad_left": pad_left,
    }


def matrix_grid(matrix, *, cell_w=118, cell_h=40, label_w=176, head_h=30):
    """Сетка «модель × уровень» с заливкой по ROC-AUC."""
    lo, hi = 0.70, 1.0

    def shade(value: float) -> float:
        return max(0.0, min(1.0, (value - lo) / (hi - lo)))

    cells = []
    for r, scope in enumerate(matrix.scopes):
        for c, model in enumerate(matrix.models):
            cell = matrix.at(scope, model)
            if cell is None:
                continue
            cells.append({
                "x": label_w + c * cell_w,
                "y": head_h + r * cell_h,
                "w": cell_w,
                "h": cell_h,
                "alpha": round(0.08 + 0.62 * shade(cell.roc_auc), 3),
                "auc": cell.roc_auc,
                "ap": cell.average_precision,
                "best": False,
                "cell": cell,
            })
    if cells:
        top = max(cells, key=lambda d: d["auc"])
        top["best"] = True
    return {
        "cells": cells,
        "cols": [(matrix.models[c], label_w + c * cell_w + cell_w // 2)
                 for c in range(len(matrix.models))],
        "rows": [(matrix.scopes[r], head_h + r * cell_h + cell_h // 2)
                 for r in range(len(matrix.scopes))],
        "width": label_w + len(matrix.models) * cell_w,
        "height": head_h + len(matrix.scopes) * cell_h,
        "label_w": label_w,
        "head_h": head_h,
    }

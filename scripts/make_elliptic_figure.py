"""Рисунок 12: измеренные руки прогона на Elliptic вместо непроверенных.

Прежняя версия рисунка показывала сравнение с MLP и GCN, которого никто не
проводил, и результат ансамбля, который не обучался. Здесь то, что измерено:
четыре набора признаков формы и контроль с перемешанными метками.

Стиль и палитра — те же, что у остальных рисунков работы
(scripts/make_defence_figures.py), чтобы он не выбивался из документа.
"""
import sys
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, "src")
from apris.web import data

BLUE, AMBER = "#2563EB", "#B45309"
INK, MUTED, GRID = "#1f2328", "#6b7280", "#e5e7eb"
plt.rcParams.update({
    "figure.dpi": 160, "savefig.dpi": 160, "font.size": 11,
    "axes.titlesize": 13, "axes.titleweight": "bold",
    "axes.labelcolor": MUTED, "axes.edgecolor": GRID, "text.color": INK,
    "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.spines.top": False, "axes.spines.right": False,
})

el = data.snapshot()["elliptic"]
order = ["structural", "structural_plus_local", "shape", "shape_plus_local",
         "control_shuffled_labels"]
names = {
    "structural": "Форма\n5 признаков",
    "structural_plus_local": "Первый набор\n+ активность",
    "shape": "Форма\n16 признаков",
    "shape_plus_local": "Расширенный\n+ активность",
    "control_shuffled_labels": "Контроль\nметки перемешаны",
}
arms = {a.key: a.pooled for a in el.arms}
labels = [names[k] for k in order if arms.get(k) is not None]
values = [arms[k] for k in order if arms.get(k) is not None]
colors = [AMBER if k == "control_shuffled_labels" else BLUE
          for k in order if arms.get(k) is not None]

fig, ax = plt.subplots(figsize=(10.4, 4.9))
bars = ax.bar(labels, values, color=colors, width=0.62)
for bar, value in zip(bars, values):
    ax.annotate(f"{value:.3f}", (bar.get_x() + bar.get_width() / 2, value),
                xytext=(0, 6), textcoords="offset points",
                ha="center", fontsize=12, fontweight="bold", color=INK)

ax.axhline(0.5, color=MUTED, linewidth=1, linestyle="--")
# Подпись ставится над контрольным столбцом: единственное место выше линии,
# где нет ни столбца, ни числа над ним.
ax.annotate("0.5 — уровень\nслучайного угадывания", (len(labels) - 1, 0.53),
            ha="center", va="bottom", fontsize=10, color=MUTED)

ax.set_ylim(0, 0.82)
ax.set_ylabel("ROC-AUC, вне обучения")
title = ("Признаки формы потока на наборе Elliptic\n"
         + f"{el.dataset['labelled']:,}".replace(",", " ")
         + " размеченных дел, пять складок с карантином")
ax.set_title(title, loc="left", fontsize=13)
ax.grid(True, axis="y", color=GRID, linewidth=0.8)
ax.set_axisbelow(True)
fig.tight_layout()

out = Path("artifacts") / "figures" / "elliptic_arms.png"
out.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(out, facecolor="white")
print("рисунок 12 пересобран:", ", ".join(f"{l.splitlines()[0]} {v:.3f}"
                                          for l, v in zip(labels, values)))

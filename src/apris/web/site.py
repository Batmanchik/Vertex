"""Сайт Vertex: измерения проекта на одной странице.

Страницу отдаёт FastAPI по адресу ``/``; та же сборка кладётся в файл
скриптом ``scripts/make_site.py``. Сборщик один, поэтому версии не
расходятся.

Правила страницы
----------------
Числа читаются из ``artifacts/*.json`` при сборке; в разметке их нет. Текста
столько, чтобы понять, что измерено и на чём: заголовок, одна-две строки по
существу, данные, ограничение, источник. Нет артефакта — раздел говорит, что
прогона нет, и не показывает правдоподобную цифру.

Внешних запросов нет: шрифты системные, графики — инлайновый SVG, картинки
вшиты как data-URI.
"""

from __future__ import annotations

import base64
import html
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

from apris.web import data as D

ROOT = D.ROOT
FIGURES = ROOT / "artifacts" / "figures"


# ──────────────────────────────────────────────────────────────────────
# Форматирование
# ──────────────────────────────────────────────────────────────────────
def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def num(value: float | None, digits: int = 3, dash: str = "—") -> str:
    if value is None:
        return dash
    return f"{value:.{digits}f}"


def pct(value: float | None, digits: int = 1, dash: str = "—") -> str:
    if value is None:
        return dash
    return f"{value * 100:.{digits}f} %".replace(".0 %", " %")


def thousands(value: float | int | None, dash: str = "—") -> str:
    if value is None:
        return dash
    return f"{int(value):,}".replace(",", " ")


def money(value: float | int | None, dash: str = "—") -> str:
    if value is None:
        return dash
    amount = float(value)
    if amount >= 1e9:
        return f"{amount / 1e9:.1f} млрд ₸"
    if amount >= 1e6:
        return f"{amount / 1e6:.1f} млн ₸"
    if amount >= 1e3:
        return f"{amount / 1e3:.0f} тыс ₸"
    return f"{amount:.0f} ₸"


def data_uri(path: Path) -> str:
    if not path.exists():
        return ""
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


# ──────────────────────────────────────────────────────────────────────
# Блоки
# ──────────────────────────────────────────────────────────────────────
def facts(items: Sequence[tuple[str, str]]) -> str:
    """Величина и что она означает. Без комментариев к величине."""
    cells = "".join(
        f"<div><b>{esc(value)}</b><span>{esc(label)}</span></div>" for value, label in items
    )
    return f"<div class='facts'>{cells}</div>"


def table(
    headers: Sequence[str],
    rows: Iterable[Sequence[str]],
    *,
    caption: str = "",
    align_right_from: int = 1,
) -> str:
    """Таблица. **Ячейки — готовая разметка, а не текст.**

    В них живут ``<b>`` и ``<code>``, поэтому строку из файла прогона
    вызывающая сторона обязана пропустить через :func:`esc` сама. Заголовки
    экранируются здесь.
    """
    head = "".join(
        f"<th{' class=num' if index >= align_right_from else ''}>{esc(name)}</th>"
        for index, name in enumerate(headers)
    )
    body = "".join(
        "<tr>"
        + "".join(
            f"<td{' class=num' if index >= align_right_from else ''}>{cell}</td>"
            for index, cell in enumerate(row)
        )
        + "</tr>"
        for row in rows
    )
    cap = f"<figcaption>{caption}</figcaption>" if caption else ""
    return (
        "<figure class='tbl'><table><thead><tr>"
        + head
        + "</tr></thead><tbody>"
        + body
        + "</tbody></table>"
        + cap
        + "</figure>"
    )


def control(kind: str, name: str, label: str, **attrs: Any) -> str:
    """Один регулятор. Значение всегда показано рядом — цифрой, а не на глаз."""
    pairs = " ".join(f'{key.replace("_", "-")}="{esc(value)}"' for key, value in attrs.items())
    if kind == "select":
        options = "".join(
            f"<option value='{esc(value)}'>{esc(title)}</option>"
            for value, title in attrs.get("options", [])
        )
        return (
            f"<label class='ctl'><span>{esc(label)}</span>"
            f"<select data-ctl='{esc(name)}'>{options}</select></label>"
        )
    return (
        f"<label class='ctl'><span>{esc(label)}</span>"
        f"<input type='range' data-ctl='{esc(name)}' {pairs}>"
        f"<output data-out='{esc(name)}'></output></label>"
    )


def controls(*items: str) -> str:
    return f"<div class='ctls'>{''.join(items)}</div>"


# Роли в графе задаются степенью узла: не принимает — источник, не отдаёт —
# точка вывода, остальные — посредники. Та же легенда подходит и схемам, и делу.
GRAPH_LEGEND = (
    "<div class='legend'>"
    "<span class='key'><i class='s2'></i>источник</span>"
    "<span class='key'><i class='s1'></i>посредник</span>"
    "<span class='key'><i class='s3'></i>точка вывода</span>"
    "<span class='key'><i class='s4'></i>вне дела</span>"
    "</div>"
)


def limit(text: str) -> str:
    """Что этими числами сказать нельзя."""
    return f"<p class='lim'><span>Ограничение</span>{text}</p>"


def source(path: str = "", command: str = "") -> str:
    """Откуда число: команда, файл, или и то и другое."""
    parts = []
    if command:
        parts.append(f"<code>{esc(command)}</code>")
    if path:
        parts.append(f"<code>{esc(path)}</code>")
    return f"<p class='src'>{' · '.join(parts)}</p>" if parts else ""


def section(anchor: str, title: str, lead: str, body: str) -> str:
    return f"""
<section id="{anchor}" class="sec">
  <h2>{title}</h2>
  <p class="lead">{lead}</p>
  {body}
</section>"""


# ──────────────────────────────────────────────────────────────────────
# Графики
# ──────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Line:
    label: str
    points: list[tuple[float, float]]
    slot: str = "s1"
    dashed: bool = False


@dataclass(frozen=True)
class Bar:
    label: str
    value: float | None
    slot: str = "s1"
    note: str = ""


def _scale(value: float, lo: float, hi: float, a: float, b: float, flip: bool = False) -> float:
    span = (hi - lo) or 1.0
    t = (value - lo) / span
    if flip:
        t = 1.0 - t
    return a + t * (b - a)


def chart_line(
    lines: Sequence[Line],
    *,
    xticks: Sequence[tuple[float, str]],
    ylo: float,
    yhi: float,
    ysteps: int = 4,
    ylabel: str = "",
    xlabel: str = "",
    height: int = 180,
    value_digits: int = 3,
) -> str:
    width, pad_l, pad_r, pad_t, pad_b = 640, 48, 56, 14, 32
    plot_b = height - pad_b
    xs = [value for value, _ in xticks]
    xlo, xhi = (min(xs), max(xs)) if xs else (0.0, 1.0)

    def px(value: float) -> float:
        return round(_scale(value, xlo, xhi, pad_l, width - pad_r), 1)

    def py(value: float) -> float:
        return round(_scale(value, ylo, yhi, pad_t, plot_b, flip=True), 1)

    parts = [
        f'<svg viewBox="0 0 {width} {height}" class="chart" role="img" '
        f'aria-label="{esc(ylabel or "график")}">'
    ]
    for index in range(ysteps + 1):
        value = ylo + (yhi - ylo) * index / ysteps
        y = py(value)
        parts.append(
            f'<line class="grid" x1="{pad_l}" y1="{y}" x2="{width - pad_r}" y2="{y}"/>'
            f'<text class="tick" x="{pad_l - 7}" y="{y + 3.5}" text-anchor="end">'
            f'{num(value, value_digits).rstrip("0").rstrip(".")}</text>'
        )
    for value, label in xticks:
        parts.append(
            f'<text class="tick" x="{px(value)}" y="{plot_b + 15}" text-anchor="middle">'
            f"{esc(label)}</text>"
        )
    if xlabel:
        parts.append(
            f'<text class="axis" x="{(pad_l + width - pad_r) / 2}" y="{height - 3}" '
            f'text-anchor="middle">{esc(xlabel)}</text>'
        )
    for line in lines:
        if not line.points:
            continue
        path = " ".join(f"{px(x)},{py(y)}" for x, y in line.points)
        dash = ' stroke-dasharray="5 4"' if line.dashed else ""
        parts.append(f'<polyline class="ln {line.slot}" points="{path}"{dash}/>')
        for x, y in line.points:
            parts.append(
                f'<circle class="dot {line.slot}" cx="{px(x)}" cy="{py(y)}" r="3.5">'
                f"<title>{esc(line.label)}: {num(y, value_digits)}</title></circle>"
            )
        last_x, last_y = line.points[-1]
        parts.append(
            f'<text class="edge {line.slot}" x="{px(last_x) + 7}" y="{py(last_y) + 3.5}">'
            f"{num(last_y, value_digits)}</text>"
        )
    parts.append("</svg>")
    legend = "".join(
        f'<span class="key"><i class="{line.slot}"></i>{esc(line.label)}</span>' for line in lines
    )
    return f"<figure class='fig'>{''.join(parts)}<div class='legend'>{legend}</div></figure>"


def chart_bars(
    bars: Sequence[Bar],
    *,
    lo: float = 0.0,
    hi: float = 1.0,
    digits: int = 3,
    label_width: int | None = None,
    reference: float | None = None,
    reference_label: str = "",
) -> str:
    row_h, gap, width = 26, 6, 640
    longest = max((len(bar.label) for bar in bars), default=10)
    plot_l = label_width if label_width is not None else min(320, max(96, int(longest * 7.9) + 16))
    plot_r = width - 70
    height = len(bars) * (row_h + gap) + 22

    def px(value: float) -> float:
        return round(_scale(value, lo, hi, plot_l, plot_r), 1)

    parts = [
        f'<svg viewBox="0 0 {width} {height}" class="chart" role="img" aria-label="сравнение">'
    ]
    if reference is not None:
        x = px(reference)
        parts.append(
            f'<line class="ref" x1="{x}" y1="4" x2="{x}" y2="{height - 18}"/>'
            f'<text class="tick" x="{x}" y="{height - 5}" text-anchor="middle">'
            f"{esc(reference_label)}</text>"
        )
    for index, bar in enumerate(bars):
        y = 4 + index * (row_h + gap)
        parts.append(
            f'<text class="blabel" x="{plot_l - 9}" y="{y + row_h / 2 + 4}" '
            f'text-anchor="end">{esc(bar.label)}</text>'
        )
        if bar.value is None:
            parts.append(
                f'<text class="muted" x="{plot_l + 4}" y="{y + row_h / 2 + 4}">нет прогона</text>'
            )
            continue
        x2 = px(bar.value)
        parts.append(
            f'<rect class="bar {bar.slot}" x="{plot_l}" y="{y + 4}" '
            f'width="{max(x2 - plot_l, 1)}" height="{row_h - 8}" rx="2">'
            f"<title>{esc(bar.label)}: {num(bar.value, digits)}"
            f"{' · ' + esc(bar.note) if bar.note else ''}</title></rect>"
            f'<text class="bvalue" x="{x2 + 7}" y="{y + row_h / 2 + 4}">'
            f"{num(bar.value, digits)}</text>"
        )
    parts.append("</svg>")
    return f"<figure class='fig'>{''.join(parts)}</figure>"


def chart_curve(
    curves: Sequence[Line],
    *,
    xlabel: str,
    ylabel: str,
    diagonal: bool = True,
    size: int = 230,
) -> str:
    pad_l, pad_b, pad_t, pad_r = 36, 30, 10, 10
    width, height = size + pad_l + pad_r, size + pad_t + pad_b

    def px(value: float) -> float:
        return round(pad_l + value * size, 1)

    def py(value: float) -> float:
        return round(pad_t + (1.0 - value) * size, 1)

    parts = [
        f'<svg viewBox="0 0 {width} {height}" class="chart square" role="img" '
        f'aria-label="{esc(ylabel)} против {esc(xlabel)}">'
    ]
    for step in range(5):
        value = step / 4
        parts.append(
            f'<line class="grid" x1="{pad_l}" y1="{py(value)}" x2="{pad_l + size}" '
            f'y2="{py(value)}"/>'
            f'<text class="tick" x="{pad_l - 6}" y="{py(value) + 3.5}" text-anchor="end">'
            f"{value:.2f}</text>"
            f'<text class="tick" x="{px(value)}" y="{pad_t + size + 14}" text-anchor="middle">'
            f"{value:.2f}</text>"
        )
    if diagonal:
        parts.append(f'<line class="ref" x1="{px(0)}" y1="{py(0)}" x2="{px(1)}" y2="{py(1)}"/>')
    for curve in curves:
        if curve.points:
            path = " ".join(f"{px(x)},{py(y)}" for x, y in curve.points)
            dash = ' stroke-dasharray="5 4"' if curve.dashed else ""
            parts.append(f'<polyline class="ln {curve.slot}" points="{path}"{dash}/>')
    parts.append(
        f'<text class="axis" x="{pad_l + size / 2}" y="{height - 3}" text-anchor="middle">'
        f"{esc(xlabel)}</text></svg>"
    )
    legend = "".join(
        f'<span class="key"><i class="{curve.slot}"></i>{esc(curve.label)}</span>'
        for curve in curves
    )
    return (
        f"<figure class='fig sq'>{''.join(parts)}<div class='legend'>{legend}</div></figure>"
    )


def figure_png(path: Path, caption: str) -> str:
    uri = data_uri(path)
    if not uri:
        return ""
    return (
        f"<figure class='pic'><img src='{uri}' alt='{esc(caption)}'>"
        f"<figcaption>{esc(caption)}</figcaption></figure>"
    )


CSS = """
:root{
  color-scheme: light;
  --plane:#ffffff; --ink:#111214; --ink2:#4a4d52; --muted:#84888f;
  --grid:#e6e7ea; --rule:#d9dade;
  --s1:#2a78d6; --s2:#eb6834; --s3:#1baf7a; --s4:#84888f;
  --wash:#f4f6f9;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    color-scheme: dark;
    --plane:#131416; --ink:#f2f3f5; --ink2:#b9bcc2; --muted:#8a8e95;
    --grid:#26282c; --rule:#2e3035;
    --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#8a8e95;
    --wash:#1a1c1f;
  }
}
:root[data-theme="dark"]{
  color-scheme: dark;
  --plane:#131416; --ink:#f2f3f5; --ink2:#b9bcc2; --muted:#8a8e95;
  --grid:#26282c; --rule:#2e3035;
  --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#8a8e95;
  --wash:#1a1c1f;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth; scroll-padding-top:56px}
body{margin:0; background:var(--plane); color:var(--ink);
  font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:.85em; color:var(--ink2)}

header.top{position:sticky; top:0; z-index:9; background:var(--plane);
  border-bottom:1px solid var(--rule)}
header.top .in{max-width:1150px; margin:0 auto; padding:9px 24px;
  display:flex; gap:20px; align-items:baseline; flex-wrap:wrap}
header.top .name{font-weight:600; letter-spacing:.02em}
header.top dl{display:flex; gap:18px; margin:0; flex:1; flex-wrap:wrap;
  font-size:12.5px; color:var(--muted)}
header.top dl div{display:flex; gap:5px}
header.top dd{margin:0; color:var(--ink2); font-variant-numeric:tabular-nums}
button{font:inherit; font-size:12.5px; color:var(--muted); background:none;
  border:0; padding:2px 0; cursor:pointer}
button:hover{color:var(--ink)}

.shell{max-width:1150px; margin:0 auto; padding:26px 24px 80px;
  display:grid; grid-template-columns:200px minmax(0,1fr); gap:44px; align-items:start}
nav{position:sticky; top:60px; font-size:13px; line-height:1.5}
nav b{display:block; color:var(--muted); font-size:11px; letter-spacing:.06em;
  text-transform:uppercase; font-weight:500; margin:14px 0 5px}
nav b:first-child{margin-top:0}
nav a{display:block; padding:2px 0; color:var(--ink2); text-decoration:none}
nav a:hover{color:var(--ink)}
nav a.on{color:var(--ink); font-weight:500}

.sec{padding:0 0 34px; margin:0 0 34px; border-bottom:1px solid var(--rule)}
.sec:last-child{border-bottom:0}
h1{font-size:24px; font-weight:600; margin:0 0 6px; letter-spacing:-.01em}
h2{font-size:18px; font-weight:600; margin:0 0 8px; letter-spacing:-.01em}
h3{font-size:14px; font-weight:600; margin:22px 0 6px; color:var(--ink2)}
p{margin:0 0 10px; max-width:74ch}
.lead{color:var(--ink2); margin-bottom:16px}
.sub{color:var(--muted); font-size:13.5px}

.facts{display:flex; flex-wrap:wrap; gap:18px 34px; margin:0 0 18px;
  padding:14px 0; border-top:1px solid var(--rule); border-bottom:1px solid var(--rule)}
.facts b{display:block; font-size:21px; font-weight:600; line-height:1.2;
  font-variant-numeric:tabular-nums}
.facts span{display:block; color:var(--muted); font-size:12.5px; margin-top:2px}

figure{margin:14px 0}
.tbl{overflow-x:auto}
table{border-collapse:collapse; width:100%; font-size:13.5px}
th,td{padding:6px 12px 6px 0; text-align:left; border-bottom:1px solid var(--grid);
  vertical-align:top}
th{color:var(--muted); font-weight:500; font-size:12px; white-space:nowrap;
  border-bottom-color:var(--rule)}
td.num,th.num{text-align:right; font-variant-numeric:tabular-nums; padding-right:0}
figcaption{color:var(--muted); font-size:12.5px; margin-top:7px; max-width:74ch}

.chart{width:100%; height:auto; display:block; overflow:visible}
.fig.sq .chart{max-width:300px}
.grid{stroke:var(--grid); stroke-width:1}
.ref{stroke:var(--rule); stroke-width:1; stroke-dasharray:3 3}
.tick{fill:var(--muted); font-size:10px; font-family:ui-monospace,Menlo,monospace}
.axis{fill:var(--muted); font-size:11px}
.ln{fill:none; stroke-width:1.8; stroke-linejoin:round; stroke-linecap:round}
.dot{stroke:var(--plane); stroke-width:1.5}
.edge{font-size:10.5px; font-variant-numeric:tabular-nums; font-weight:600}
.bar{stroke:var(--plane); stroke-width:1}
.blabel{fill:var(--ink2); font-size:12.5px}
.bvalue{fill:var(--ink); font-size:12.5px; font-variant-numeric:tabular-nums}
.muted{fill:var(--muted); font-size:12px}
.s1{stroke:var(--s1)} .s2{stroke:var(--s2)} .s3{stroke:var(--s3)} .s4{stroke:var(--s4)}
rect.s1,circle.s1{fill:var(--s1)} rect.s2,circle.s2{fill:var(--s2)}
rect.s3,circle.s3{fill:var(--s3)} rect.s4,circle.s4{fill:var(--s4)}
text.s1{fill:var(--s1); stroke:none} text.s2{fill:var(--s2); stroke:none}
text.s3{fill:var(--s3); stroke:none} text.s4{fill:var(--s4); stroke:none}
.legend{display:flex; gap:16px; flex-wrap:wrap; margin-top:7px;
  color:var(--muted); font-size:12.5px}
.key{display:flex; align-items:center; gap:5px}
.key i{width:9px; height:9px; border-radius:2px; display:inline-block}
.key i.s1{background:var(--s1)} .key i.s2{background:var(--s2)}
.key i.s3{background:var(--s3)} .key i.s4{background:var(--s4)}

.pic img{width:100%; border:1px solid var(--rule); background:#fff}
.gallery{display:grid; grid-template-columns:repeat(auto-fit,minmax(250px,1fr)); gap:16px}
.gallery figure{margin:0}
.pair{display:grid; grid-template-columns:repeat(auto-fit,minmax(290px,1fr)); gap:22px}

.lim{font-size:13.5px; color:var(--ink2); margin:12px 0}
.lim span{color:var(--muted); font-size:11.5px; text-transform:uppercase;
  letter-spacing:.06em; margin-right:8px}
.src{font-size:12px; color:var(--muted); margin:10px 0 0}
.src code{color:var(--muted)}

.form{display:grid; grid-template-columns:repeat(auto-fit,minmax(215px,1fr));
  gap:10px 18px; margin:14px 0; align-items:end; max-width:820px}
.fld{display:flex; flex-direction:column; gap:3px; font-size:13px; color:var(--ink2)}
.fld input{font:inherit; font-size:13.5px; padding:5px 8px; border:1px solid var(--rule);
  background:var(--plane); color:var(--ink); border-radius:3px;
  font-variant-numeric:tabular-nums}
.fld input:focus{outline:1px solid var(--s1); outline-offset:0}
.fld small{color:var(--muted); font-size:11px; font-family:ui-monospace,Menlo,monospace}
button.go{border:1px solid var(--ink2); color:var(--ink); padding:6px 16px;
  border-radius:3px; font-size:13.5px; height:31px}
button.go:hover{background:var(--wash)}
button.go:disabled{color:var(--muted); border-color:var(--rule); cursor:default}
.fld input[type=range]{padding:0; border:0; background:none; height:22px}
.out{font-size:13.5px; color:var(--ink2); min-height:22px}
.out b{font-size:19px; color:var(--ink); font-variant-numeric:tabular-nums;
  margin-right:10px}

/* Регуляторы. Значение всегда стоит цифрой рядом с ручкой: положение ползунка
   само по себе ничего не сообщает, а цифру можно назвать вслух на защите. */
.ctls{display:flex; flex-wrap:wrap; gap:14px 26px; margin:12px 0 16px;
  padding:12px 0; border-top:1px solid var(--rule); border-bottom:1px solid var(--rule)}
.ctl{display:flex; flex-direction:column; gap:3px; font-size:12.5px; color:var(--muted);
  min-width:0}
.ctl span{white-space:nowrap}
.ctl output{color:var(--ink); font-size:14px; font-variant-numeric:tabular-nums;
  line-height:1.2}
.ctl input[type=range]{width:170px; max-width:100%; height:20px; margin:0;
  accent-color:var(--s1); background:none; border:0; padding:0}
.ctl select{font:inherit; font-size:13.5px; padding:4px 8px; color:var(--ink);
  background:var(--plane); border:1px solid var(--rule); border-radius:3px;
  max-width:100%}
.ctl select:focus, .ctl input:focus{outline:1px solid var(--s1); outline-offset:1px}
.ctl.off{opacity:.4}

/* Граф: слои по ролям. Цвет — роль, толщина ребра — доля оборота. */
.graph{width:100%; height:auto; display:block}
.graph line.edge{stroke:var(--s4); opacity:.45; stroke-linecap:round}
.graph circle.node{stroke:var(--plane); stroke-width:1.2; fill:var(--s1)}
.graph circle.n-source{fill:var(--s2)}
.graph circle.n-relay{fill:var(--s1)}
.graph circle.n-sink{fill:var(--s3)}
.graph circle.outside{fill:var(--s4); opacity:.5}

@media (max-width:880px){
  .shell{grid-template-columns:minmax(0,1fr); gap:0; padding:18px 16px 60px}
  nav{position:static; margin-bottom:20px; min-width:0; max-width:100%;
    display:flex; gap:14px; overflow-x:auto; padding-bottom:8px;
    border-bottom:1px solid var(--rule)}
  nav b{display:none}
  nav a{white-space:nowrap}
  header.top dl div:nth-child(n+3){display:none}
}
@media print{
  nav, header.top button{display:none}
  .sec{break-inside:avoid}
}
"""

SCRIPT = """
(function(){
  var root=document.documentElement, key='vertex-theme';
  try{var saved=localStorage.getItem(key); if(saved) root.dataset.theme=saved;}catch(e){}
  var toggle=document.getElementById('theme');
  if(toggle) toggle.addEventListener('click',function(){
    root.dataset.theme = root.dataset.theme==='dark' ? 'light' : 'dark';
    try{localStorage.setItem(key, root.dataset.theme);}catch(e){}
  });

  var links=[].slice.call(document.querySelectorAll('nav a'));
  var map={}; links.forEach(function(a){map[a.getAttribute('href').slice(1)]=a;});
  var obs=new IntersectionObserver(function(entries){
    entries.forEach(function(entry){
      var a=map[entry.target.id];
      if(a && entry.isIntersecting){
        links.forEach(function(l){l.classList.remove('on');});
        a.classList.add('on');
      }
    });
  },{rootMargin:'-8% 0px -80% 0px'});
  document.querySelectorAll('section.sec').forEach(function(s){obs.observe(s);});

// ── данные прогонов, положенные в страницу при сборке ───────────────────
var DATA = {};
try { DATA = JSON.parse(document.getElementById('data').textContent); } catch (e) { DATA = {}; }

function fmt(value, digits){ return (value === null || value === undefined || isNaN(value))
  ? '—' : Number(value).toFixed(digits === undefined ? 3 : digits); }
function spaced(value){ return Math.round(value).toLocaleString('ru-RU').replace(/,/g, ' '); }
function money(value){
  if (value >= 1e9) return (value/1e9).toFixed(1) + ' млрд ₸';
  if (value >= 1e6) return (value/1e6).toFixed(1) + ' млн ₸';
  if (value >= 1e3) return Math.round(value/1e3) + ' тыс ₸';
  return Math.round(value) + ' ₸';
}
// «1 участник», а не «1 участников»: на защите это читают вслух.
function plural(value, one, few, many){
  var n = Math.abs(Math.round(value)) % 100, tail = n % 10;
  if (n > 10 && n < 20) return many;
  if (tail > 1 && tail < 5) return few;
  if (tail === 1) return one;
  return many;
}
function count(value, one, few, many){
  return spaced(value) + ' ' + plural(value, one, few, many);
}
function el(id){ return document.getElementById(id); }
function ctl(name){ return document.querySelector('[data-ctl="' + name + '"]'); }
function out(name){ return document.querySelector('[data-out="' + name + '"]'); }

// ── рисование графа: слои по ролям, толщина ребра по обороту ────────────
function drawGraph(target, nodes, edges, options){
  options = options || {};
  var width = 520, height = options.height || 300, pad = 26;
  var incoming = {}, outgoing = {};
  nodes.forEach(function(node){ incoming[node.id] = 0; outgoing[node.id] = 0; });
  edges.forEach(function(edge){
    outgoing[edge.from] = (outgoing[edge.from] || 0) + 1;
    incoming[edge.to] = (incoming[edge.to] || 0) + 1;
  });

  var layers = [[], [], []];
  nodes.forEach(function(node){
    if (!incoming[node.id]) layers[0].push(node);
    else if (!outgoing[node.id]) layers[2].push(node);
    else layers[1].push(node);
  });
  if (!layers[1].length && layers[2].length > 2){ layers[1] = layers[2].splice(0, layers[2].length - 1); }

  var position = {}, byLayer = ['source', 'relay', 'sink'];
  layers.forEach(function(layer, index){
    var x = pad + index * (width - 2*pad) / 2;
    layer.forEach(function(node, order){
      if (!node.role) node.role = byLayer[index];
      var span = height - 2*pad;
      var y = layer.length === 1 ? height/2 : pad + order * span / (layer.length - 1);
      position[node.id] = {x: x, y: y, node: node};
    });
  });

  var peak = edges.reduce(function(max, edge){ return Math.max(max, edge.amount || 1); }, 1);
  var svg = ['<svg viewBox="0 0 ' + width + ' ' + height + '" class="chart graph" role="img" aria-label="граф дела">'];
  edges.forEach(function(edge){
    var a = position[edge.from], b = position[edge.to];
    if (!a || !b) return;
    var weight = 0.6 + 3.4 * Math.sqrt((edge.amount || 1) / peak);
    svg.push('<line class="edge" x1="' + a.x.toFixed(1) + '" y1="' + a.y.toFixed(1) +
      '" x2="' + b.x.toFixed(1) + '" y2="' + b.y.toFixed(1) +
      '" stroke-width="' + weight.toFixed(2) + '"><title>' + edge.from + ' → ' + edge.to +
      (edge.amount ? ': ' + money(edge.amount) : '') + '</title></line>');
  });
  nodes.forEach(function(node){
    var spot = position[node.id];
    if (!spot) return;
    var radius = node.role === 'sink' ? 7 : (node.role === 'source' ? 6.5 : 4.5);
    var kind = 'n-' + (node.role || 'relay') + (node.member === false ? ' outside' : '');
    svg.push('<circle class="node ' + kind + '" cx="' +
      spot.x.toFixed(1) + '" cy="' + spot.y.toFixed(1) + '" r="' + radius +
      '"><title>' + node.id + '</title></circle>');
  });
  svg.push('</svg>');
  target.innerHTML = svg.join('');
}

// ── схемы типологий: строятся по параметрам, не по данным ──────────────
function buildShape(kind, members, sources, sinks){
  var nodes = [], edges = [], index = 0;
  function add(id, role){ nodes.push({id: id, role: role, member: true}); return id; }

  if (kind === 'pyramid'){
    var top = add('организатор', 'sink');
    for (var level = 0; level < members; level++){
      var participant = add('участник ' + (level + 1), 'source');
      edges.push({from: participant, to: top, amount: 1 + (members - level)});
    }
    return {nodes: nodes, edges: edges,
      note: 'Пирамида: сбор средств множества участников в одну точку.'};
  }
  if (kind === 'fan'){
    var origin = add('источник', 'source');
    var collector = add('получатель', 'sink');
    for (index = 0; index < members; index++){
      var hop = add('посредник ' + (index + 1), 'relay');
      edges.push({from: origin, to: hop, amount: 2});
      edges.push({from: hop, to: collector, amount: 2});
    }
    return {nodes: nodes, edges: edges,
      note: 'Веерный транзит: сумма дробится, проходит через посредников и собирается обратно.'};
  }
  if (kind === 'cycle'){
    var ring = [];
    for (index = 0; index < Math.max(3, members); index++){ ring.push(add('счёт ' + (index + 1), 'relay')); }
    ring.forEach(function(node, order){
      edges.push({from: node, to: ring[(order + 1) % ring.length], amount: 2});
    });
    return {nodes: nodes, edges: edges,
      note: 'Циклический транзит: деньги ходят по кругу подконтрольных счетов.'};
  }

  var sourceIds = [], sinkIds = [];
  for (index = 0; index < sources; index++){ sourceIds.push(add('источник ' + (index + 1), 'source')); }
  for (index = 0; index < sinks; index++){ sinkIds.push(add('банкомат ' + (index + 1), 'sink')); }
  for (index = 0; index < members; index++){
    var mule = add('дроп ' + (index + 1), 'relay');
    edges.push({from: sourceIds[index % sourceIds.length], to: mule, amount: 3});
    edges.push({from: mule, to: sinkIds[index % sinkIds.length], amount: 3});
  }
  return {nodes: nodes, edges: edges, note: kind === 'flash'
    ? 'Банкоматная вспышка: десятки веток сходятся к нескольким банкоматам в узком окне.'
    : 'Кольцо обналички: источник, дропы, точка вывода.'};
}

function renderShape(){
  var host = el('shape');
  if (!host) return;
  var kind = ctl('shape').value;
  var members = parseInt(ctl('shape-members').value, 10);
  var sources = parseInt(ctl('shape-sources').value, 10);
  var sinks = parseInt(ctl('shape-sinks').value, 10);
  // Пирамида, веер и цикл не читают число источников и точек вывода — ручка,
  // которая ничего не меняет, вводит в заблуждение, поэтому она гаснет.
  var splits = (kind === 'ring' || kind === 'flash');
  ['shape-sources', 'shape-sinks'].forEach(function(name){
    var input = ctl(name);
    if (!input) return;
    input.disabled = !splits;
    if (input.parentNode) input.parentNode.classList.toggle('off', !splits);
  });

  var shape = buildShape(kind, members, sources, sinks);
  drawGraph(host, shape.nodes, shape.edges, {height: 300});
  el('shape-note').textContent = shape.note + ' Узлов ' + shape.nodes.length +
    ', рёбер ' + shape.edges.length + '.';
}

// ── досье: выбор дела, его граф и его признаки ─────────────────────────
function renderCase(){
  var picker = ctl('case');
  if (!picker || !DATA.cases || !DATA.cases.length) return;
  var chosen = DATA.cases[parseInt(picker.value, 10)] || DATA.cases[0];

  el('case-facts').innerHTML = [
    ['<b>' + fmt(chosen.score) + '</b><span>оценка детектора</span>'],
    ['<b>' + spaced(chosen.members) + '</b><span>' +
      plural(chosen.members, 'участник', 'участника', 'участников') + '</span>'],
    ['<b>' + spaced(chosen.events) + '</b><span>' +
      plural(chosen.events, 'событие', 'события', 'событий') + '</span>'],
    ['<b>' + money(chosen.amount) + '</b><span>оборот</span>'],
    ['<b>' + (chosen.truth ? 'мошенническая' : 'честная') + '</b><span>разметка</span>']
  ].map(function(cell){ return '<div>' + cell + '</div>'; }).join('');

  var graph = chosen.graph || {};
  drawGraph(el('case-graph'), graph.nodes || [], graph.edges || [], {height: 300});
  el('case-graph-note').textContent = 'Рёбер показано ' + (graph.edges || []).length +
    ' из ' + (graph.edges_total || 0) + ', узлов ' + (graph.nodes || []).length + '.';

  var names = Object.keys(chosen.features || {}).sort(function(a, b){
    return chosen.features[b] - chosen.features[a];
  });
  var rowHeight = 22, width = 520, labelWidth = 200;
  var bars = ['<svg viewBox="0 0 ' + width + ' ' + (names.length * rowHeight + 10) +
    '" class="chart" role="img" aria-label="признаки дела">'];
  names.forEach(function(name, order){
    var value = chosen.features[name];
    var y = 5 + order * rowHeight;
    var x2 = labelWidth + value * (width - labelWidth - 56);
    bars.push('<text class="blabel" x="' + (labelWidth - 8) + '" y="' + (y + 12) +
      '" text-anchor="end">' + ((DATA.feature_ru || {})[name] || name) + '</text>');
    bars.push('<rect class="bar s1" x="' + labelWidth + '" y="' + (y + 4) + '" width="' +
      Math.max(x2 - labelWidth, 1).toFixed(1) + '" height="' + (rowHeight - 10) +
      '" rx="2"><title>' + name + ': ' + fmt(value) + '</title></rect>');
    bars.push('<text class="bvalue" x="' + (x2 + 6).toFixed(1) + '" y="' + (y + 12) + '">' +
      fmt(value) + '</text>');
  });
  bars.push('</svg>');
  el('case-features').innerHTML = bars.join('');
}

// ── редкость: пересчёт измеренной ROC-кривой ──────────────────────────
function renderRarity(){
  var host = el('rarity-out');
  if (!host || !DATA.roc || !DATA.roc.points.length) return;
  var prevalence = parseFloat(ctl('prevalence').value) / 100;
  var target = parseFloat(ctl('recall').value) / 100;

  var point = null;
  DATA.roc.points.forEach(function(candidate){
    if (candidate.y >= target && (point === null || candidate.x < point.x)) point = candidate;
  });
  if (!point) point = DATA.roc.points[DATA.roc.points.length - 1];

  var caught = prevalence * point.y;
  var false_alarms = (1 - prevalence) * point.x;
  var precision = (caught + false_alarms) > 0 ? caught / (caught + false_alarms) : 0;
  var alerts = 1000 * (caught + false_alarms);

  host.innerHTML = [
    ['<b>' + fmt(precision, 3) + '</b><span>точность очереди</span>'],
    ['<b>' + (precision > 0 ? fmt(1 / precision, 1 / precision < 10 ? 1 : 0) : '—') +
      '</b><span>проверок на находку</span>'],
    ['<b>' + fmt(alerts, 1) + '</b><span>сигналов на 1000 счетов</span>'],
    ['<b>' + fmt(point.y, 2) + '</b><span>полнота в этой точке</span>'],
    ['<b>' + fmt(point.x, 4) + '</b><span>доля ложных тревог</span>']
  ].map(function(cell){ return '<div>' + cell + '</div>'; }).join('');
}

// ── уклонение: измеренная точка или честное «не измерялась» ────────────
function renderEvasion(){
  var host = el('evasion-out');
  if (!host || !DATA.evasion) return;
  var funders = parseInt(ctl('ev-funders').value, 10);
  var atms = parseInt(ctl('ev-atms').value, 10);
  var found = null;
  DATA.evasion.forEach(function(row){
    if (row.funders === funders && row.atms === atms) found = row;
  });
  host.innerHTML = found
    ? [['<b>' + fmt(found.found, 3) + '</b><span>найдено групп</span>'],
       ['<b>' + fmt(found.overlap, 3) + '</b><span>медиана перекрытия</span>'],
       ['<b>' + found.label + '</b><span>настройка прогона</span>']]
        .map(function(cell){ return '<div>' + cell + '</div>'; }).join('')
    : '<div><b>не измерялась</b><span>такой конфигурации в прогоне не было</span></div>';
}

// ── модель: те же 300 деревьев, что и в сервисе, только их обходит браузер ──
// Узел — [признак, порог, левое, правое], лист — число. Больше для ответа
// ничего не нужно, поэтому раздел «Проверить» работает и без сервера.
function runModel(values){
  var model = DATA.model;
  if (!model) return null;
  var total = 0;
  for (var i = 0; i < model.trees.length; i++){
    var node = model.trees[i];
    while (Array.isArray(node)){ node = values[node[0]] <= node[1] ? node[2] : node[3]; }
    total += node;
  }
  return 1 / (1 + Math.exp(-model.sigmoid * total));
}

function riskLabel(probability){
  var t = DATA.model.thresholds;
  if (probability >= t.high) return 'High';
  if (probability >= t.medium) return 'Medium';
  return 'Low';
}

// ── живая оценка: движение регулятора пересчитывает ответ модели ───────
function setupManual(){
  var form = el('manual'), result = el('manual-out');
  if (!form || !result) return;
  if (!DATA.model){
    result.textContent = 'Модели в сборке нет: проверять нечем.';
    return;
  }

  function show(){
    form.querySelectorAll('input[data-name]').forEach(function(input){
      var target = out(input.dataset.name);
      if (target) target.textContent = input.value;
    });
  }
  function run(){
    // Порядок величин задаёт модель, а не разметка: перепутанные местами
    // признаки дали бы правдоподобное и неверное число.
    var values = DATA.model.names.map(function(name, index){
      var input = form.querySelector('input[data-name="' + name + '"]');
      var bounds = DATA.model.bounds[index];
      var value = input ? parseFloat(input.value) : bounds[0];
      return Math.max(bounds[0], Math.min(bounds[1], value));
    });
    var probability = runModel(values);
    result.innerHTML = '<b>' + (probability * 100).toFixed(1) + ' %</b>класс ' +
      riskLabel(probability) + ' · пороги ' + DATA.model.thresholds.medium +
      ' / ' + DATA.model.thresholds.high;
  }
  form.addEventListener('input', function(){ show(); run(); });
  form.addEventListener('submit', function(event){ event.preventDefault(); run(); });
  show();
  run();
}

// ── общая проводка регуляторов ────────────────────────────────────────
function wire(names, render){
  var found = false;
  names.forEach(function(name){
    var input = ctl(name);
    if (!input) return;
    found = true;
    input.addEventListener('input', function(){
      var target = out(name);
      if (target) target.textContent = input.value;
      render();
    });
    var target = out(name);
    if (target) target.textContent = input.value;
  });
  if (found) render();
}

(function setupInteractive(){
  var picker = ctl('case');
  if (picker && DATA.cases && DATA.cases.length){
    picker.innerHTML = DATA.cases.map(function(item, index){
      return '<option value="' + index + '">' + item.key + ' · ' + item.unit +
        ' · оценка ' + fmt(item.score) + '</option>';
    }).join('');
    picker.addEventListener('change', renderCase);
    renderCase();
  }
  wire(['shape', 'shape-members', 'shape-sources', 'shape-sinks'], renderShape);
  var shapePicker = ctl('shape');
  if (shapePicker) shapePicker.addEventListener('change', renderShape);
  wire(['prevalence', 'recall'], renderRarity);
  wire(['ev-funders', 'ev-atms'], renderEvasion);
  setupManual();
})();
})();
"""


# ──────────────────────────────────────────────────────────────────────
# Разделы
# ──────────────────────────────────────────────────────────────────────
NAV: list[tuple[str, list[tuple[str, str]]]] = [
    ("Система", [("overview", "Обзор"), ("pipeline", "Конвейер"), ("world", "Мир"),
                 ("shapes", "Схемы"), ("discovery", "Поиск сетей"), ("dossier", "Досье"),
                 ("validation", "Валидация"), ("manual", "Проверить")]),
    ("Измерения", [("queue", "Очередь"), ("ladder", "Лестница миров"),
                   ("evasion", "Уклонение"), ("rarity", "Редкость"),
                   ("rules", "Правила"), ("ceiling", "Потолки"),
                   ("curves", "Кривые"), ("panel", "Панель"),
                   ("branches", "Ветви"), ("flowweight", "Параметр W"),
                   ("elliptic", "Elliptic")]),
    ("Служебное", [("defects", "Дефекты"), ("gap", "Разрыв до цели"),
                   ("sources", "Файлы")]),
]

FEATURE_RU = {
    "graph_density": "плотность связей",
    "graph_hub_share": "схождение потока",
    "graph_fanout_share": "расхождение потока",
    "graph_relay_share": "транзит через посредника",
    "graph_weight_cv_norm": "разброс сумм по рёбрам",
    "event_rate_hour": "плотность событий",
    "burst_ratio_90s": "всплеск в окне 90 с",
    "median_delta_inverse": "короткие паузы",
    "amount_cv_norm": "разброс сумм",
    "unique_sender_ratio": "уникальные отправители",
    "active_day_share": "активные дни",
    "cash_out_share": "вывод наличными",
    "counterparty_concentration": "концентрация контрагентов",
    "median_hold_hours_inverse": "короткое удержание",
    "out_in_ratio": "ушло к пришло",
    "hub_share": "схождение потока",
    "density": "плотность окрестности",
    "reciprocity": "взаимность переводов",
    "fanout_share": "расхождение потока",
    "relay_share": "транзит через посредника",
    "in_degree": "входящие связи узла",
    "out_degree": "исходящие связи узла",
    "case_size": "размер окрестности",
}


def sec_overview(snap: dict[str, Any]) -> str:
    worlds = snap["worlds"]
    rarity = snap["rarity"]
    panel = snap["panel"]
    elliptic = snap["elliptic"]
    w4 = next((row for row in worlds if row.key == "W4"), None)
    holdout = panel.pooled("case_holdout", "forest")
    rare = rarity[-1] if rarity else None
    structural = next((arm for arm in elliptic.arms if arm.key == "structural"), None)

    return section(
        "overview", "Vertex — измерения",
        "Детектор мошеннических схем по форме денежного потока: кандидаты строятся из "
        "потока событий, признаки считаются из событий, проверка — по времени с зазором. "
        "Ниже измерения, каждое с указанием протокола и файла прогона.",
        facts([
            (num(max(holdout), 3) if holdout else "—", "ROC-AUC, новые кластеры"),
            (num(w4.network_auc, 4) if w4 and w4.network_auc else "—", "ROC-AUC, группы, мир W4"),
            (num(rare.roc_auc, 3) if rare else "—",
             f"ROC-AUC при доле мошенников {pct(rare.prevalence, 1)}" if rare else "редкость"),
            (num(structural.pooled, 3) if structural else "—", "ROC-AUC на данных Elliptic"),
        ])
        + "<p class='sub'>Данные синтетические, кроме раздела Elliptic. Числа читаются "
          "из <code>artifacts/*.json</code> при сборке страницы.</p>",
    )


def sec_pipeline(snap: dict[str, Any]) -> str:
    queue = snap["queue"]
    rows = [
        ["1. мир", "события: отправитель, получатель, сумма, время, канал",
         "генератор не выпускает ни одного признака"],
        ["2. поиск", "кандидаты из потока событий",
         "метки прикладываются после, отсюда потолок полноты"],
        ["3. признаки", "15 величин на кандидата", "считает детектор, не генератор"],
        ["4. детектор", "случайный лес, purged walk-forward",
         "обучение на прошлом, проверка на следующем отрезке, зазор 2 дня"],
        ["5. очередь", "дела выше порога", "порог выбран на прошлых отрезках"],
    ]
    speed = (
        f"Полный прогон: {thousands(queue.world.get('events'))} событий, "
        f"{queue.seconds:.0f} с."
        if queue.present and queue.seconds else ""
    )
    return section(
        "pipeline", "Конвейер",
        "Пять шагов от события до дела в очереди. " + speed,
        table(["шаг", "что делает", "условие"], rows, align_right_from=99)
        + source("", "python scripts/run_pipeline.py --preset full"),
    )


def sec_world(snap: dict[str, Any]) -> str:
    worlds = snap["worlds"]
    w4 = next((row for row in worlds if row.key == "W4"), None)
    rows = []
    if w4:
        rows = [
            ["счетов", thousands(w4.accounts)],
            ["из них личных", thousands(w4.personal)],
            ["событий", thousands(w4.events)],
            ["мошеннических счетов", thousands(w4.fraud_accounts)],
            ["групп", thousands(w4.networks)],
            ["доля мошенников среди личных счетов", pct(w4.fraud_share)],
        ]
    gallery = "".join(
        figure_png(FIGURES / "topology" / name, caption)
        for name, caption in [
            ("ring.png", "Кольцо обналички: источник → дропы → банкомат, минуты"),
            ("pyramid.png", "Пирамида: схождение в одну точку, месяцы"),
            ("crypto.png", "Мост в криптовалюту: легальный вход, крипто-выход"),
            ("honest.png", "Зарплатный проект: та же форма, честный"),
        ]
    )
    return section(
        "world", "Мир",
        "Синтетический мир с известной разметкой: 8 честных популяций, 4 популяции "
        "трудных отрицательных примеров, кольца обналички, пирамиды, крипто-цепочки. "
        "Порождаются четыре типологии из пяти; дробление сумм у порогов — нет.",
        (table(["что", "сколько"], rows, caption="Мир W4, среднее по трём сидам") if rows else "")
        + f"<div class='gallery'>{gallery}</div>"
        + figure_png(FIGURES / "network_anatomy.png",
                     "Кольцо из симулятора: 3 933 151 ₸ входящего потока, на счетах "
                     "осталось 172 504 ₸ (4,4 %), окно 17 минут")
        + source("artifacts/ladder_of_worlds.json"),
    )


def sec_shapes(snap: dict[str, Any]) -> str:
    return section(
        "shapes", "Схемы: формы, которые ищет детектор",
        "Пять типологий в виде графа. Это схема формы, а не данные прогона: "
        "число участников задаётся регуляторами, чтобы было видно, как форма ведёт "
        "себя при росте. Граф конкретного дела из прогона — в разделе «Досье».",
        controls(
            control("select", "shape", "типология", options=[
                ("ring", "кольцо обналички"),
                ("pyramid", "пирамида"),
                ("fan", "веерный транзит"),
                ("cycle", "циклический транзит"),
                ("flash", "банкоматная вспышка"),
            ]),
            control("range", "shape-members", "участников", min=4, max=40, value=12, step=1),
            control("range", "shape-sources", "источников", min=1, max=6, value=1, step=1),
            control("range", "shape-sinks", "точек вывода", min=1, max=6, value=1, step=1),
        )
        + "<figure class='fig'><div id='shape'></div>"
        + GRAPH_LEGEND
        + "<figcaption id='shape-note'></figcaption></figure>"
        + "<p class='sub'>Толщина ребра пропорциональна доле потока. Слева источники, "
          "справа точки вывода, между ними посредники.</p>",
    )


def sec_discovery(snap: dict[str, Any]) -> str:
    blocks = snap["blocks"]
    worlds = snap["worlds"]
    if not blocks:
        return section("discovery", "Поиск сетей", "Прогона нет.", "")
    nets = next((b for b in blocks if b.unit == "сети"), blocks[0])
    coverage = [(r.key, r.account_coverage) for r in worlds if r.account_coverage is not None]
    rows = [
        [str(item.get("rank")), esc(str(item.get("key"))), thousands(item.get("members")),
         thousands(item.get("events")), money(item.get("amount_total")),
         str(item.get("first_seen", ""))[:10] + " – " + str(item.get("last_seen", ""))[:10]]
        for item in nets.items[:10]
    ]
    return section(
        "discovery", "Поиск сетей",
        "Кандидаты строятся из событий: общий банкомат в узком окне, общий предок по "
        "деньгам, общий получатель. Разметка при построении не читается и нужна только "
        "для покрытия — доли реальных групп, попавших хотя бы в одного кандидата.",
        facts([
            (thousands(nets.rows), "кандидатов в блоке"),
            (num(nets.ceiling, 3), "покрытие"),
            (thousands(nets.positives), "настоящих групп в блоке"),
        ])
        + table(["№", "кандидат", "участников", "событий", "оборот", "окно"], rows,
                caption="Первые десять кандидатов по оценке детектора")
        + (table(["мир", "покрытие счётного уровня"],
                 [[esc(k), num(v, 3)] for k, v in coverage]) if coverage else "")
        + limit("Покрытие — верхняя граница полноты: группа, не попавшая ни в одного "
                "кандидата, не может быть найдена моделью.")
        + source("artifacts/analyst_queue.json"),
    )


def sec_dossier(snap: dict[str, Any]) -> str:
    blocks = snap["blocks"]
    nets = next((b for b in blocks if b.unit == "сети"), None)
    item = nets.items[0] if nets and nets.items else None
    if item is None:
        return section("dossier", "Досье кандидата", "Прогона нет.", "")
    features = item.get("features") or {}
    bars = [
        Bar(FEATURE_RU.get(name, name), value, "s1", note=name)
        for name, value in sorted(features.items(), key=lambda pair: -pair[1])
    ]
    return section(
        "dossier", "Досье кандидата",
        "Дело из очереди целиком: его граф, построенный из его же событий, и признаки, "
        "по которым он получил оценку. Дело выбирается списком.",
        controls(control("select", "case", "дело", options=[]))
        + "<div id='case-facts' class='facts'></div>"
        + "<div class='pair'>"
        + "<figure class='fig'><div id='case-graph'></div>"
        + GRAPH_LEGEND
        + "<figcaption id='case-graph-note'></figcaption></figure>"
        + f"<figure class='fig'><div id='case-features'>{chart_bars(bars, lo=0.0, hi=1.0)}"
          "</div></figure>"
        + "</div>"
        + "<p class='sub'>Рёбра просуммированы по паре «отправитель → получатель», "
          "в графе показаны крупнейшие по обороту. Признаки приведены к отрезку [0, 1]; "
          "их английские имена видны в подсказках.</p>"
        + limit("Картинка построена из событий дела. Она не выводится ни из признаков, "
                "ни из вердикта модели — такая картинка соглашалась бы с оценкой всегда.")
        + source("artifacts/analyst_queue.json"),
    )


def sec_validation(snap: dict[str, Any]) -> str:
    panel = snap["panel"]
    blocks = snap["blocks"]
    rows: list[list[str]] = []
    if panel.present and panel.worlds:
        world = panel.worlds[0]
        for name, title in (("time_forward", "известные кейсы"),
                            ("case_holdout", "новые кластеры")):
            for fold in (world.protocols.get(name, {}).get("forest") or {}).get("folds", []):
                rows.append([
                    esc(title), str(fold.get("fold")), thousands(fold.get("train")),
                    thousands(fold.get("test")), pct(fold.get("prevalence")),
                    num(fold.get("shared_case_share"), 2), num(fold.get("roc_auc")),
                ])
    queue_rows = [
        [esc(b.unit), num(b.threshold, 3), pct(b.prevalence), thousands(b.queued),
         pct(b.precision, 0), pct(b.recall, 0), num(b.ceiling, 3)]
        for b in blocks
    ]
    return section(
        "validation", "Валидация",
        "Разбиение по времени, случайное перемешивание не используется. Между обучением "
        "и проверкой зазор шире времени жизни транзитной цепочки. Порог выбирается на "
        "прошлых отрезках и применяется к следующему.",
        (table(["протокол", "фолд", "обучение", "проверка", "доля мошенников",
                "общих кейсов", "ROC-AUC"], rows,
               caption="Панель кейсов, первый мир. «Общих кейсов» — доля проверяемых "
                       "строк, чей кластер встречался в обучении")
         if rows else "<p class='sub'>Прогона панели нет.</p>")
        + "<h3>Очередь на невиданном блоке</h3>"
        + table(["уровень", "порог", "доля мошенников", "дел", "точность", "полнота",
                 "потолок"], queue_rows)
        + limit("В протоколе «известные кейсы» 93–100 % проверяемых строк относятся к "
                "кластерам из обучения; обобщение на новые группы этим протоколом не "
                "измеряется.")
        + source("artifacts/case_panel.json, artifacts/analyst_queue.json"),
    )


def sec_manual(snap: dict[str, Any]) -> str:
    # Начальные значения — не «типичная пирамида», а точка, где движок даёт
    # примерно 0.5. Взяты бинарным поиском по отрезку между явно честным и явно
    # мошенническим набором: в любой другой точке движок насыщен и сдвиг ручки
    # ничего не меняет на экране.
    bounds = {
        "growth_rate": (0.0, 1.2, 0.285, "прирост участников"),
        "referral_ratio": (0.0, 1.0, 0.384, "доля по реферальной цепочке"),
        "payout_dependency": (0.1, 1.9, 1.164, "выплаты к поступлениям"),
        "centralization_index": (0.0, 1.0, 0.458, "централизация потока"),
        "avg_holding_time": (3.0, 120.0, 44.0, "удержание средств, часы"),
        "reinvestment_rate": (0.0, 1.0, 0.361, "реинвестирование"),
        "gini_coefficient": (0.1, 1.0, 0.482, "неравенство сумм"),
        "transaction_entropy": (0.3, 5.0, 2.7, "энтропия операций"),
        "structural_depth": (2.0, 16.0, 5.0, "глубина структуры"),
    }
    step = {"avg_holding_time": 1, "structural_depth": 1, "transaction_entropy": 0.1}
    fields = "".join(
        f"<label class='fld'><span>{esc(title)}</span>"
        f"<input type='range' min='{low}' max='{high}' value='{default}' "
        f"step='{step.get(name, 0.01)}' data-name='{name}'>"
        f"<small><output data-out='{name}'>{default}</output> · {name}</small></label>"
        for name, (low, high, default, title) in bounds.items()
    )
    return section(
        "manual", "Проверить",
        "Девять величин уходят в модель, ответ обновляется при движении любого "
        "регулятора. Считает сама страница: обученная модель — градиентный бустинг "
        "на 300 деревьях глубины 6, то есть набор порогов, и браузер обходит их "
        "сам. Тот же расчёт отдаёт <code>/api/v1/predict</code>; расхождение между "
        "страницей и сервисом проверяется тестом и не превышает 1e-5.",
        f"<form id='manual' class='form'>{fields}</form>"
        "<div id='manual-out' class='out'></div>"
        + limit("Пороги 0.4 и 0.7 в ответе зашиты в старом движке и не калиброваны под "
                "заданную полноту; рабочий порог выбирается прогоном и показан в разделе "
                "«Валидация».")
        + limit("Ручки стоят в точке, где движок даёт около половины. В стороне от неё "
                "ответ упирается в ноль или единицу и перестаёт отзываться на сдвиг: "
                "это свойство старого движка, а не измерение.")
        + source("artifacts/model.joblib"),
    )


def sec_queue(snap: dict[str, Any]) -> str:
    blocks = snap["blocks"]
    queue = snap["queue"]
    if not blocks:
        return section("queue", "Очередь аналитика", "Прогона нет.", "")
    rows = [
        [esc(b.unit), thousands(b.rows), thousands(b.positives), pct(b.prevalence),
         thousands(b.queued), pct(b.precision, 0), pct(b.recall, 0), num(b.threshold),
         num(b.ceiling)]
        for b in blocks
    ]
    item_rows = [
        [str(i.get("rank")), esc(str(i.get("key"))), thousands(i.get("members")),
         thousands(i.get("events")), num(i.get("score"), 3),
         "мошенник" if i.get("truth") else "честный"]
        for i in blocks[0].items[:8]
    ]
    return section(
        "queue", "Очередь аналитика",
        f"Дела выше порога на последнем временном блоке, который модель не видела. "
        f"Мир {thousands(queue.world.get('events'))} событий, прогон "
        f"{queue.seconds:.0f} с. Длина очереди — следствие порога, а не заданный бюджет.",
        table(["уровень", "объектов", "мошенников", "доля", "в очереди", "точность",
               "полнота", "порог", "потолок"], rows)
        + "<h3>Верх очереди</h3>"
        + table(["№", "кандидат", "участников", "событий", "оценка", "разметка"], item_rows)
        + limit("Доля мошенников в этом мире — проценты; при доле в десятые доли процента "
                "точность падает, см. раздел «Редкость».")
        + source("artifacts/analyst_queue.json", "python scripts/run_pipeline.py --preset full"),
    )


def sec_ladder(snap: dict[str, Any]) -> str:
    worlds = snap["worlds"]
    if not worlds:
        return section("ladder", "Лестница миров", "Прогона нет.", "")
    xticks = [(float(index), row.key) for index, row in enumerate(worlds)]
    account = Line("счёт", [(float(i), r.account_auc) for i, r in enumerate(worlds)
                            if r.account_auc], "s1")
    network = Line("группа", [(float(i), r.network_auc) for i, r in enumerate(worlds)
                              if r.network_auc], "s3")
    rows = [
        [f"{esc(r.key)} · {esc(r.note)}", num(r.account_auc), num(r.network_auc, 4),
         f"{num(r.auc_min)} – {num(r.auc_max)}", str(r.seeds)]
        for r in worlds
    ]
    return section(
        "ladder", "Лестница миров",
        "Пять миров нарастающей сложности, один детектор, три сида. Ступень меняет вид "
        "честных участников, а не их количество. Состав ступеней объявлен до прогонов.",
        chart_line([account, network], xticks=xticks, ylo=0.90, yhi=1.0,
                   ylabel="ROC-AUC", xlabel="ступень")
        + table(["мир", "счёт", "группа", "разброс по сидам", "сидов"], rows,
                caption="На W5 групповой уровень оценки не даёт: ни один кандидат не "
                        "проходит порог покрытия")
        + limit("На W5 медиана наибольшего перекрытия группы одним кандидатом — 0.000; "
                "счётный уровень при этом не меняется (0.950 → 0.966).")
        + source("artifacts/ladder_of_worlds.json", "python scripts/run_ladder_of_worlds.py"),
    )


def sec_evasion(snap: dict[str, Any]) -> str:
    rows = snap["evasion"]
    if not rows:
        return section("evasion", "Цена уклонения", "Прогона нет.", "")
    funders = Line("источников денег", sorted((float(r.funders), r.found_share) for r in rows
                                              if r.atms == 1 and r.found_share is not None), "s2")
    atms = Line("банкоматов", sorted((float(r.atms), r.found_share) for r in rows
                                     if r.funders == 1 and r.found_share is not None), "s1")
    table_rows = [
        [esc(r.label), str(r.funders), str(r.atms), num(r.found_share), num(r.median_overlap)]
        for r in rows
    ]
    return section(
        "evasion", "Цена уклонения",
        "Организатор дробит источники финансирования и разводит снятия по банкоматам. "
        "Ручки крутятся по одной и вместе; мир и детектор те же, три сида.",
        chart_line([funders, atms], xticks=[(float(v), str(v)) for v in (1, 2, 3, 4, 5, 6)],
                   ylo=0.0, yhi=1.0, ylabel="доля найденных групп",
                   xlabel="источников / банкоматов", value_digits=2)
        + table(["настройка", "источников", "банкоматов", "найдено групп",
                 "медиана перекрытия"], table_rows)
        + "<h3>Выбрать конфигурацию</h3>"
        + controls(
            control("range", "ev-funders", "источников", min=1, max=6, value=1, step=1),
            control("range", "ev-atms", "банкоматов", min=1, max=4, value=1, step=1),
        )
        + "<div id='evasion-out' class='facts'></div>"
        + "<p class='sub'>Показываются измеренные значения. Конфигурация, которой в "
          "прогоне не было, так и называется — не измерялась.</p>"
        + limit("Набор зацепок задан нами: общий источник и общий банкомат. У банка их "
                "больше (устройство, IP, телефон), поэтому цифры относятся к этому "
                "набору, а не к поиску групп вообще.")
        + source("artifacts/evasion_curve.json", "python scripts/run_evasion_curve.py"),
    )


def sec_rarity(snap: dict[str, Any]) -> str:
    rows = snap["rarity"]
    points = snap["points"]
    if not rows:
        return section("rarity", "Редкость", "Прогона нет.", "")
    auc = Line("ROC-AUC", [(float(i), r.roc_auc) for i, r in enumerate(rows) if r.roc_auc], "s1")
    xticks = [(float(i), pct(r.prevalence, 1)) for i, r in enumerate(rows)]
    reviews = [
        Bar(pct(r.prevalence, 1), r.reviews_per_catch, "s2",
            note=f"точность {num(r.precision_at_budget, 3)}")
        for r in rows if r.reviews_per_catch
    ]
    top = max((bar.value or 0) for bar in reviews) if reviews else 1
    table_rows = [
        [pct(r.prevalence, 1), thousands(r.positives), num(r.roc_auc),
         num(r.precision_at_budget, 3),
         f"{r.reviews_per_catch:.0f}" if r.reviews_per_catch else "—"]
        for r in rows
    ]
    def point_table(items: list[D.Point]) -> list[list[str]]:
        return [
            [pct(p.recall, 0), f"{p.alerts_per_1000:.1f}", num(p.precision, 3),
             f"{p.reviews_per_catch:.1f}"]
            for p in items
        ]

    point_rows = point_table(points)
    projected_rows = point_table(snap["projected"])
    return section(
        "rarity", "Редкость",
        "Мошенники прореживаются до разбиения, поэтому модель и обучается, и проверяется "
        "при заданной доле. Три сида на ячейку.",
        "<div class='pair'>"
        + chart_line([auc], xticks=xticks, ylo=0.85, yhi=1.0, ylabel="ROC-AUC",
                     xlabel="доля мошенников", height=190)
        + chart_bars(reviews, lo=0, hi=top * 1.15, digits=0, label_width=80)
        + "</div>"
        + table(["доля мошенников", "их в мире", "ROC-AUC", "точность верхних 10 %",
                 "проверок на находку"], table_rows)
        + "<h3>Пересчёт при своей доле мошенников</h3>"
        + controls(
            control("range", "prevalence", "доля мошенников, %",
                    min=0.05, max=10, value=1, step=0.05),
            control("range", "recall", "поймать дропов, %", min=10, max=95, value=50, step=5),
        )
        + "<div id='rarity-out' class='facts'></div>"
        + "<p class='sub'>Считается по измеренной ROC-кривой: "
          "<code>точность = π·TPR / (π·TPR + (1−π)·FPR)</code>. Модель не переобучается, "
          "меняется только цена порога при заданной редкости.</p>"
        + ("<h3>Порог вместо бюджета: измеренные точки</h3>"
           + table(["поймать дропов", "сигналов на 1000 счетов", "точность",
                    "проверок на находку"], point_rows,
                   caption="Измерено на естественной доле мошенников этого мира — "
                           f"{pct(points[0].prevalence, 1)}, три сида")
           if point_rows else "")
        + ("<h3>Тот же порог, перенесённый на 0.1 % мошенников</h3>"
           + table(["поймать дропов", "сигналов на 1000 счетов", "точность",
                    "проверок на находку"], projected_rows,
                   caption="Пересчёт измеренной кривой, а не отдельный прогон")
           + limit("Это перенос, а не измерение. Детектор тот же и кривая та же; "
                   "меняется доля мошенников, из которой считается точность. "
                   "Подписать перенос измерением значило бы соврать в ту сторону, "
                   "которая красивее.")
           if projected_rows else "")
        + limit("Ячейка 0.1 % стоит на 13 мошеннических строках, разброс по сидам там "
                "0.842–0.997. Редкость получена прореживанием: окружение оставшегося "
                "мошенника осталось прежним.")
        + source("artifacts/prevalence_sweep.json", "python scripts/run_prevalence_sweep.py"),
    )


def sec_rules(snap: dict[str, Any]) -> str:
    matrix = snap["matrix"]
    if not matrix.cells:
        return section("rules", "Правила против модели", "Прогона нет.", "")
    bars = []
    for model in matrix.models:
        cell = matrix.at("account", model)
        if cell is not None:
            bars.append(Bar(cell.model_ru, cell.roc_auc, "s4" if model == "rules" else "s1",
                            note=f"{thousands(cell.rows)} строк, {cell.folds} фолдов"))
    rows = []
    for scope in matrix.scopes:
        for model in matrix.models:
            cell = matrix.at(scope, model)
            if cell is not None:
                rows.append([esc(cell.scope_ru), esc(cell.model_ru), num(cell.roc_auc),
                             num(cell.average_precision), thousands(cell.rows),
                             thousands(cell.positives), pct(cell.base_rate)])
    return section(
        "rules", "Правила против модели",
        "Три критерия из четырёх, по которым дроппер определяется приказом, выразимы на "
        "платёжных данных; четвёртый (общий телефон) не выразим и исключён из подсчёта. "
        "Сравнение на одних и тех же данных, десять сидов.",
        chart_bars(bars, lo=0.5, hi=1.0, reference=0.5, reference_label="0.5")
        + table(["уровень анализа", "модель", "ROC-AUC", "средняя точность", "строк",
                 "мошенников", "доля"], rows, align_right_from=2)
        + limit("Критерии приказа описывают клиента и оборудование, модель — денежный "
                "поток. Это разные наборы входных данных, а не две версии одного детектора.")
        + source("artifacts/experiment_ladder.json", "python scripts/run_experiment_ladder.py"),
    )


def sec_ceiling(snap: dict[str, Any]) -> str:
    worlds = snap["worlds"]
    blocks = snap["blocks"]
    account = next((b.ceiling for b in blocks if b.unit == "счета"), None)
    network = next((b.ceiling for b in blocks if b.unit == "сети"), None)
    coverage = [(r.key, r.account_coverage) for r in worlds if r.account_coverage is not None]
    return section(
        "ceiling", "Потолки уровней",
        "Доля мошенников, которую объект анализа способен увидеть в принципе. Счёт без "
        "десяти собственных событий не имеет ни времени удержания, ни концентрации, ни "
        "всплесковости.",
        facts([
            (num(account, 3) if account else "—", "потолок счётного уровня, текущий прогон"),
            (num(network, 3) if network else "—", "потолок группового уровня"),
        ])
        + (table(["мир", "покрытие счётного уровня"],
                 [[esc(k), num(v, 3)] for k, v in coverage]) if coverage else "")
        + limit("Потолок зависит от мира: на прогоне от 6 сентября он читался 0.617, на "
                "текущем — 0.459. Величина пересчитывается вместе с миром, константой не "
                "является."),
    )


def sec_curves(snap: dict[str, Any]) -> str:
    curves = snap["curves"]
    if not curves.present or not curves.items:
        return section("curves", "Кривые детектора", "Прогона нет.", "")
    best = max(curves.items, key=lambda c: c.roc_auc)
    worst = min(curves.items, key=lambda c: c.roc_auc)
    roc = [
        Line(f"{best.model_ru}, {best.scope_ru}", [(p["x"], p["y"]) for p in best.roc], "s1"),
        Line(f"{worst.model_ru}, {worst.scope_ru}", [(p["x"], p["y"]) for p in worst.roc], "s2"),
    ]
    pr = [
        Line(best.model_ru, [(p["x"], p["y"]) for p in best.pr], "s1"),
        Line(worst.model_ru, [(p["x"], p["y"]) for p in worst.pr], "s2"),
    ]
    calib = [
        Line("идеальная калибровка", [(0.0, 0.0), (1.0, 1.0)], "s4", dashed=True),
        Line(best.model_ru, [(c["mean_score"], c["fraud_share"]) for c in best.calibration], "s1"),
    ]
    rows = [
        [esc(c.model_ru), esc(c.scope_ru), num(c.roc_auc), num(c.average_precision),
         num(c.brier), thousands(c.rows), thousands(c.positives)]
        for c in sorted(curves.items, key=lambda c: -c.roc_auc)
    ]
    return section(
        "curves", "Кривые детектора",
        "ROC, полнота-точность и калибровка для лучшего и худшего разрезов сетки.",
        "<div class='pair'>"
        + chart_curve(roc, xlabel="доля ложных тревог", ylabel="доля пойманных")
        + chart_curve(pr, xlabel="полнота", ylabel="точность", diagonal=False)
        + chart_curve(calib, xlabel="предсказанная вероятность", ylabel="наблюдаемая доля")
        + "</div>"
        + table(["модель", "уровень", "ROC-AUC", "средняя точность", "Бриер", "строк",
                 "мошенников"], rows, align_right_from=2)
        + source("artifacts/detector_curves.json", "python scripts/run_detector_curves.py"),
    )


def sec_panel(snap: dict[str, Any]) -> str:
    panel = snap["panel"]
    if not panel.present or not panel.worlds:
        return section("panel", "Панель кейсов", "Прогона нет.", "")
    forward = panel.pooled("time_forward", "forest")
    holdout = panel.pooled("case_holdout", "forest")
    forward_lgb = panel.pooled("time_forward", "lightgbm")
    holdout_lgb = panel.pooled("case_holdout", "lightgbm")
    bars = [
        Bar("известные кейсы · лес", max(forward) if forward else None, "s1"),
        Bar("известные кейсы · бустинг", max(forward_lgb) if forward_lgb else None, "s1"),
        Bar("новые кластеры · лес", max(holdout) if holdout else None, "s3"),
        Bar("новые кластеры · бустинг", max(holdout_lgb) if holdout_lgb else None, "s3"),
    ]
    rows = [
        [str(w.seed), thousands(w.rows), thousands(w.cases), str(w.dates), pct(w.fraud_share),
         f"{num(w.share_min, 3)} – {num(w.share_max, 3)}",
         num((w.protocols.get("time_forward", {}).get("forest") or {}).get("pooled_roc_auc")),
         num((w.protocols.get("case_holdout", {}).get("forest") or {}).get("pooled_roc_auc"))]
        for w in panel.worlds
    ]
    return section(
        "panel", "Панель кейсов",
        "Кандидат описан на каждую дату недельной сетки по событиям, случившимся к этому "
        "моменту. Два протокола: обучение до даты и проверка после неё; и отложенные "
        "целиком кластеры.",
        chart_bars(bars, lo=0.5, hi=1.0)
        + table(["сид", "строк", "кейсов", "дат", "доля мошенников", "разброс по датам",
                 "известные кейсы", "новые кластеры"], rows)
        + limit("В протоколе «известные кейсы» 93–100 % проверяемых строк относятся к "
                "кластерам из обучения. Протокол «новые кластеры» не проверяет порядок "
                "внутри мира. Совместить оба в одном разбиении нельзя: кластеры живут "
                "весь мир, и выбрасывание по кейсу опустошает обучение.")
        + source("artifacts/case_panel.json", "python scripts/run_case_panel.py --seeds 3"),
    )


def sec_branches(snap: dict[str, Any]) -> str:
    branches = snap["branches"]
    if not any(b.present for b in branches):
        return section("branches", "Ветви ансамбля", "Обученных ветвей нет.", "")
    bars: list[Bar] = []
    rows: list[list[str]] = []
    for branch in branches:
        if not branch.present:
            continue
        across, within = branch.across, branch.within
        bars.append(Bar(f"{branch.label} · обученная", across.get("pooled_roc_auc"), "s1"))
        bars.append(Bar(f"{branch.label} · эвристика", across.get("pooled_heuristic_roc_auc"), "s4"))
        rows.append([
            esc(branch.label), num(across.get("pooled_roc_auc")),
            num(across.get("pooled_heuristic_roc_auc")),
            ", ".join(num(v) for v in across.get("per_world_roc_auc", [])),
            num(within.get("pooled_roc_auc")), num(within.get("pooled_heuristic_roc_auc")),
            thousands(across.get("rows")),
        ])
    return section(
        "branches", "Ветви ансамбля",
        "Графовая и последовательностная ветви обучены на кандидатах из слепого поиска, "
        "признаки — из их событий. «Между мирами» — обучение на четырёх мирах, проверка "
        "на пятом целиком; «внутри мира» — временной срез с зазором.",
        chart_bars(bars, lo=0.0, hi=1.0, reference=0.5, reference_label="0.5")
        + table(["ветвь", "между мирами", "эвристика", "по мирам", "внутри мира",
                 "эвристика", "строк"], rows)
        + limit("Межмировой протокол не проверяет порядок внутри мира; внутримировой "
                "искажён датировкой кейса по последнему событию (дефект 6). Табличная "
                "ветвь и слияние не обучены.")
        + source("artifacts/cheops_v2_graph_metrics.json",
                 "python scripts/train_branches_on_events.py --preset full --seeds 5"),
    )


def sec_flow_weight(snap: dict[str, Any]) -> str:
    fw = snap["flow_weight"]
    if not fw.present:
        return section("flowweight", "Параметр W", "Замера нет.", "")
    lift = fw.model.get("lift")
    return section(
        "flowweight", "Параметр W",
        "W — доля входящего потока, ушедшая с затуханием по времени удержания, "
        "FIFO-сопоставление прихода и расхода. Замерен отдельно и в составе модели.",
        facts([
            (num(fw.standalone.get("w_fast"), 3), "ROC-AUC, W быстрый"),
            (num(fw.standalone.get("w_slow"), 3), "ROC-AUC, W медленный"),
            (f"{lift:+.4f}" if lift is not None else "—", "прирост к модели"),
        ])
        + "<p class='sub'>Признак не побил перемешанный контроль, поэтому в набор "
          "признаков не подключён. На счётном уровне W выражается через два признака, "
          "которые в наборе уже есть.</p>"
        + limit("Замер сделан на счётном уровне. На уровне кандидата и сети величина не "
                "измерялась.")
        + source("artifacts/flow_weight_probe.json", "python scripts/measure_flow_weight.py"),
    )


def sec_elliptic(snap: dict[str, Any]) -> str:
    el = snap["elliptic"]
    if not el.present:
        return section("elliptic", "Elliptic", "Прогона нет.", "")
    bars = [
        Bar(arm.label, arm.pooled, "s4" if arm.key.startswith("control") else "s1")
        for arm in el.arms
    ]
    feature_bars = [
        Bar(FEATURE_RU.get(name, name), value, "s3" if value >= 0.55 else "s4", note=name)
        for name, value in el.single_feature[:6]
    ]
    point = el.operating_point
    return section(
        "elliptic", "Elliptic: настоящие данные",
        f"Публичный размеченный набор: {thousands(el.dataset.get('nodes'))} транзакций, "
        f"{thousands(el.dataset.get('labelled'))} с разметкой, "
        f"{thousands(el.dataset.get('illicit'))} мошеннических. Каждый размеченный узел — "
        "кейс со своей двухшаговой окрестностью, purged walk-forward по 49 шагам.",
        chart_bars(bars, lo=0.4, hi=1.0, reference=0.5, reference_label="0.5")
        + "<h3>По одиночным признакам, в выборке</h3>"
        + chart_bars(feature_bars, lo=0.4, hi=0.7, label_width=190)
        + (f"<p class='sub'>Рабочая точка на невиданном отрезке: полнота "
           f"{pct(point.get('recall'), 0)}, точность {num(point.get('precision'), 2)}, "
           f"{1 / point['precision']:.0f} проверок на находку.</p>"
           if point.get("precision") else "")
        + limit("Узлы Elliptic — транзакции модели UTXO, а не счета; класс illicit — "
                "вымогатели, даркнет-рынки и скам. Суммы анонимизированы, все признаки "
                "считаны по числу рёбер. Шаг времени — около двух недель, скоростные "
                "признаки на этом наборе не проверяемы.")
        + source("artifacts/elliptic_probe.json", "python scripts/run_elliptic_probe.py"),
    )


DEFECTS = [
    ("Генератор писал ответ в признаки", "ROC-AUC 1.0000",
     "события и признаки разделены; стало 0.81"),
    ("Сборщик дел брал группы из файла с ответами", "покрытие 1.0 по построению",
     "группы ищутся вслепую, метки прикладываются после"),
    ("Критерий «общее устройство» срабатывал на 100 % групп",
     "поиск сам связывал людей по общему банкомату",
     "критерий исключён из подсчёта, оставлен в отчёте"),
    ("79 % честной выборки — счета с одним-двумя событиями", "счётчик событий давал 0.84",
     "порог в десять событий; цена порога — потолок счётного уровня"),
    ("Первая лестница миров меняла количество честных", "мир на 96 % из мошенников",
     "ступень меняет вид честных; закреплено тестом"),
    ("Кейс датировался последним событием",
     "доля мошенников 2.9 % в первой четверти списка против 33.3 % в последней",
     "панель: кейс описан на каждую дату"),
]


def sec_defects(snap: dict[str, Any]) -> str:
    return section(
        "defects", "Дефекты измерения",
        "Шесть ошибок измерения, найденных внутренним аудитом. Каждая завышала результат; "
        "ни одна не была ошибкой в коде — код работал и отвечал не на тот вопрос.",
        table(["что было", "как проявлялось", "что сделано"],
              [[esc(a), esc(b), esc(c)] for a, b, c in DEFECTS], align_right_from=99)
        + source("docs/reviews/AUDIT_FINDINGS_2026-09-04.md, docs/RESULTS.md"),
    )


def sec_gap(snap: dict[str, Any]) -> str:
    rows = [
        ["Валидация на Elliptic", "разведка: 0.665 против 0.473 у контроля",
         "повтор на обученном ансамбле"],
        ["Три обученные ветви LightGBM", "две из трёх обучены на событиях",
         "табличная ветвь и слияние"],
        ["W как вклад в модель", "прирост −0.0022, не подключён",
         "замер на уровне кандидата и сети"],
        ["Разрешение сущностей за 50 мс", "модуль есть, замера нет",
         "починить путь через Elasticsearch, замерить"],
        ["Пять типологий", "порождаются четыре", "дробление сумм у порогов"],
        ["SHAP", "только в legacy-движке", "подключить к ансамблю"],
        ["GNN, федеративное обучение", "нет", "после устоявшейся базовой линии"],
    ]
    return section(
        "gap", "Разрыв до цели",
        "Целевое состояние описано научной работой. Таблица — разница между ним и тем, "
        "что работает сейчас.",
        table(["требование", "состояние", "что закрывает"], rows, align_right_from=99)
        + limit("Числа 0.96 / 0.92 / 0.99 для Elliptic в тексте работы — ориентир, "
                "измерение дало другое.")
        + source("PLAN.md §2"),
    )


def sec_sources(snap: dict[str, Any]) -> str:
    rows = []
    for path in sorted((ROOT / "artifacts").glob("*.json")):
        if path.name.startswith(("evasion_curve_", "ladder_of_worlds_", "prevalence_sweep_")):
            continue
        stamp = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        rows.append([f"<code>artifacts/{esc(path.name)}</code>",
                     f"{path.stat().st_size / 1024:.0f} КБ",
                     stamp.strftime("%Y-%m-%d %H:%M")])
    commands = [
        ("конвейер и очередь", "python scripts/run_pipeline.py --preset full"),
        ("лестница миров", "python scripts/run_ladder_of_worlds.py"),
        ("кривая уклонения", "python scripts/run_evasion_curve.py"),
        ("редкость", "python scripts/run_prevalence_sweep.py"),
        ("кривые детектора", "python scripts/run_detector_curves.py"),
        ("панель кейсов", "python scripts/run_case_panel.py --seeds 3"),
        ("обучение ветвей", "python scripts/train_branches_on_events.py --preset full --seeds 5"),
        ("Elliptic", "python scripts/run_elliptic_probe.py"),
        ("сайт", "python scripts/serve.py"),
        ("сайт файлом", "python scripts/make_site.py"),
    ]
    return section(
        "sources", "Файлы и команды",
        "Страница читает эти файлы при сборке. Команды воспроизводят их с нуля.",
        table(["файл", "размер", "обновлён"], rows)
        + table(["что считает", "команда"],
                [[esc(what), f"<code>{esc(cmd)}</code>"] for what, cmd in commands],
                align_right_from=99)
        + "<p class='sub'>Те же числа в JSON: "
          "<code>/api/v2/viz/measurements</code>.</p>",
    )


def payload(snap: dict[str, Any]) -> str:
    """Измерения, которые пересчитывает браузер.

    В страницу кладутся только те величины, по которым регуляторы считают
    арифметику: измеренная ROC-кривая, строки развёртки по редкости,
    измеренные точки уклонения и дела очереди вместе с их графами. Ничего
    нового браузер не выдумывает — он пересчитывает уже измеренное по
    формуле, которая написана рядом.
    """
    curves = snap["curves"]
    best = None
    if curves.present and curves.items:
        account = [c for c in curves.items if c.scope == "account"]
        best = max(account or curves.items, key=lambda c: c.roc_auc)

    blocks = snap["blocks"]
    cases = [
        {
            "key": item.get("key"),
            "unit": block.unit,
            "score": item.get("score"),
            "truth": item.get("truth"),
            "members": item.get("members"),
            "events": item.get("events"),
            "amount": item.get("amount_total"),
            "features": item.get("features") or {},
            "graph": item.get("graph") or {},
        }
        for block in blocks
        for item in block.items[:12]
        if item.get("graph")
    ]

    body = {
        "roc": {
            "points": [{"x": point["x"], "y": point["y"]} for point in best.roc] if best else [],
            "model": f"{best.model_ru}, {best.scope_ru}" if best else "",
            "base_rate": best.base_rate if best else None,
        },
        "rarity": [
            {"prevalence": row.prevalence, "roc_auc": row.roc_auc,
             "precision": row.precision_at_budget, "reviews": row.reviews_per_catch}
            for row in snap["rarity"]
        ],
        "evasion": [
            {"funders": row.funders, "atms": row.atms, "found": row.found_share,
             "overlap": row.median_overlap, "label": row.label}
            for row in snap["evasion"]
        ],
        "cases": cases,
        "feature_ru": FEATURE_RU,
        "model": D.scorer(),
    }
    return json.dumps(body, ensure_ascii=False, separators=(",", ":"))


SECTIONS = (
    sec_overview, sec_pipeline, sec_world, sec_shapes, sec_discovery, sec_dossier, sec_validation,
    sec_manual, sec_queue, sec_ladder, sec_evasion, sec_rarity, sec_rules, sec_ceiling,
    sec_curves, sec_panel, sec_branches, sec_flow_weight, sec_elliptic, sec_defects,
    sec_gap, sec_sources,
)


def build(snap: dict[str, Any] | None = None) -> str:
    snap = snap or D.snapshot()
    meta = snap["worlds_meta"]
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    nav = "".join(
        f"<b>{esc(group)}</b>"
        + "".join(f"<a href='#{anchor}'>{esc(label)}</a>" for anchor, label in links)
        for group, links in NAV
    )
    body = "".join(render(snap) for render in SECTIONS)
    return f"""<!doctype html>
<html lang="ru" data-theme="">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Vertex — измерения</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' fill='%232a78d6'/%3E%3Cpath d='M8 9l8 15 8-15' stroke='white' stroke-width='3.4' fill='none'/%3E%3C/svg%3E">
<style>{CSS}</style>
</head>
<body>
<header class="top"><div class="in">
  <span class="name">VERTEX</span>
  <dl>
    <div><dt>детектор</dt><dd>{esc(meta.detector)}</dd></div>
    <div><dt>прогон</dt><dd>{esc(meta.generated_at)}</dd></div>
    <div><dt>сидов</dt><dd>{meta.seed_count}</dd></div>
    <div><dt>собрано</dt><dd>{esc(built)}</dd></div>
  </dl>
  <button id="theme" type="button">тема</button>
  <button type="button" onclick="window.print()">печать</button>
</div></header>
<div class="shell">
  <nav>{nav}</nav>
  <main>{body}</main>
</div>
<script type="application/json" id="data">{payload(snap)}</script>
<script>{SCRIPT}</script>
</body>
</html>"""


def write(path: Path | None = None, snap: dict[str, Any] | None = None) -> Path:
    target = path or (ROOT / "artifacts" / "site" / "index.html")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(build(snap), encoding="utf-8")
    return target

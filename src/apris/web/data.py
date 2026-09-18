"""Чтение измерений из artifacts/ для витрины.

Ни одно число на витрине не записано в шаблон руками. Всё, что показывается,
читается отсюда, а отсюда — из файлов прогонов. Если файла нет, раздел
показывает это прямо, а не подставляет правдоподобную цифру.
"""
from __future__ import annotations

import json
import statistics
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Корень репозитория: src/apris/web/data.py -> ../../..
ROOT = Path(__file__).resolve().parents[3]
ARTIFACTS = ROOT / "artifacts"


def _read_json(name: str) -> Any:
    """Сырое содержимое файла прогона, или ``None``, если его нет."""
    path = ARTIFACTS / name
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _load(name: str) -> dict[str, Any] | None:
    """Прогон, записанный объектом.

    Почти каждый артефакт этого проекта — объект с шапкой, и вызывающая
    сторона читает его через ``.get``. Файл другой формы считается
    отсутствующим: раздел витрины тогда честно скажет «прогона не было»
    вместо того, чтобы падать на первом же обращении.

    Список — законный формат ровно для одного файла, и он читается
    ``_load_list``. Не путайте их: тихо возвращённый ``None`` на списке
    выглядит на витрине как «прогона не было», хотя прогон есть.
    """
    raw = _read_json(name)
    return raw if isinstance(raw, dict) else None


def _load_list(name: str) -> list[Any] | None:
    """Прогон, записанный списком (``feature_importances.json``)."""
    raw = _read_json(name)
    return raw if isinstance(raw, list) else None


def _mean(values: Sequence[float | None]) -> float | None:
    clean = [value for value in values if value is not None]
    return statistics.fmean(clean) if clean else None


@dataclass(frozen=True)
class RunMeta:
    """Шапка прогона: кто, когда, на скольких сидах."""

    detector: str = "—"
    generated_at: str = "—"
    seeds: tuple[int, ...] = ()
    run_id: str = ""
    source: str = ""

    @property
    def seed_count(self) -> int:
        return len(self.seeds)


def _meta(raw: dict[str, Any] | None, source: str) -> RunMeta:
    if not raw:
        return RunMeta(source=source)
    return RunMeta(
        detector=raw.get("detector", "—"),
        generated_at=str(raw.get("generated_at", "—")).replace("T", " ")[:19],
        seeds=tuple(raw.get("seeds", []) or []),
        run_id=raw.get("run_id", ""),
        source=source,
    )


# ──────────────────────────────────────────────────────────────────────
# Лестница миров
# ──────────────────────────────────────────────────────────────────────
WORLD_TITLES_RU = {
    "W1": "негативы, не похожие ни на что",
    "W2": "те, кто тоже опустошает счёт",
    "W3": "негативы той же формы",
    "W4": "пирамиды и крипто рядом с дропами",
    "W5": "организатор прячется",
}


@dataclass
class WorldRow:
    key: str
    note: str
    account_auc: float | None
    network_auc: float | None
    account_coverage: float | None
    seeds: int
    auc_min: float | None = None
    auc_max: float | None = None
    accounts: float = 0.0
    personal: float = 0.0
    events: float = 0.0
    fraud_accounts: float = 0.0
    networks: float = 0.0
    fraud_share: float = 0.0


def worlds() -> tuple[list[WorldRow], RunMeta]:
    raw = _load("ladder_of_worlds.json")
    meta = _meta(raw, "artifacts/ladder_of_worlds.json")
    if not raw:
        return [], meta

    buckets: dict[tuple[str, str], list[dict[str, Any]]] = {}
    worlds_raw: dict[str, list[dict[str, Any]]] = {}
    for entry in raw.get("results", []):
        worlds_raw.setdefault(entry["key"], []).append(entry.get("world", {}))
        for unit in entry.get("units", []):
            buckets.setdefault((entry["key"], unit["unit"]), []).append(unit)

    rows: list[WorldRow] = []
    for key in sorted({k for k, _ in buckets}):
        acc = buckets.get((key, "account"), [])
        net = buckets.get((key, "network"), [])
        aucs = [u["roc_auc"] for u in acc if u["roc_auc"] is not None]
        comp = worlds_raw.get(key, [{}])
        pick = lambda name: _mean([float(w.get(name, 0.0)) for w in comp]) or 0.0
        rows.append(
            WorldRow(
                key=key,
                note=WORLD_TITLES_RU.get(key, ""),
                account_auc=_mean(aucs),
                network_auc=_mean([u["roc_auc"] for u in net]),
                account_coverage=_mean([u["coverage"] for u in acc]),
                seeds=len(acc),
                auc_min=min(aucs) if aucs else None,
                auc_max=max(aucs) if aucs else None,
                accounts=pick("accounts"),
                personal=pick("personal_accounts"),
                events=pick("events"),
                fraud_accounts=pick("fraud_accounts"),
                networks=pick("networks"),
                fraud_share=pick("fraud_share_of_personal"),
            )
        )
    return rows, meta


# ──────────────────────────────────────────────────────────────────────
# Кривая уклонения
# ──────────────────────────────────────────────────────────────────────
EVASION_LABELS = {
    "naive": ("1 источник, 1 банкомат", 1, 1),
    "f2": ("2 источника", 2, 1),
    "f3": ("3 источника", 3, 1),
    "f4": ("4 источника", 4, 1),
    "f6": ("6 источников", 6, 1),
    "t2": ("2 банкомата", 1, 2),
    "t3": ("3 банкомата", 1, 3),
    "t4": ("4 банкомата", 1, 4),
    "f6t4": ("6 источников и 4 банкомата", 6, 4),
}


@dataclass
class EvasionRow:
    key: str
    label: str
    funders: int
    atms: int
    found_share: float | None
    median_overlap: float | None
    networks: int


def evasion() -> tuple[list[EvasionRow], RunMeta]:
    raw = _load("evasion_curve.json")
    meta = _meta(raw, "artifacts/evasion_curve.json")
    if not raw:
        return [], meta

    buckets: dict[str, list[dict[str, Any]]] = {}
    for entry in raw.get("results", []):
        buckets.setdefault(entry["key"], []).append(entry)

    rows: list[EvasionRow] = []
    for key in EVASION_LABELS:
        runs = buckets.get(key)
        if not runs:
            continue
        label, funders, atms = EVASION_LABELS[key]
        shares, medians, nets = [], [], []
        for run in runs:
            overlap = run.get("overlap") or {}
            total = overlap.get("networks") or 0
            reaching = overlap.get("reaching_coverage") or 0
            if total:
                shares.append(reaching / total)
                nets.append(total)
            medians.append(overlap.get("median"))
        rows.append(
            EvasionRow(
                key=key,
                label=label,
                funders=funders,
                atms=atms,
                found_share=_mean(shares),
                median_overlap=_mean(medians),
                networks=int(_mean([float(n) for n in nets]) or 0),
            )
        )
    return rows, meta


# ──────────────────────────────────────────────────────────────────────
# Редкость
# ──────────────────────────────────────────────────────────────────────
@dataclass
class RarityRow:
    prevalence: float
    positives: int
    roc_auc: float | None
    precision_at_budget: float | None
    reviews_per_catch: float | None


def rarity() -> tuple[list[RarityRow], RunMeta]:
    raw = _load("prevalence_sweep.json")
    meta = _meta(raw, "artifacts/prevalence_sweep.json")
    if not raw:
        return [], meta

    def _row(runs: list[dict[str, Any]], target: float) -> RarityRow:
        precision = _mean([r["precision_at_budget"] for r in runs])
        return RarityRow(
            prevalence=target,
            positives=int(_mean([float(r["positives"]) for r in runs]) or 0),
            roc_auc=_mean([r["roc_auc"] for r in runs]),
            precision_at_budget=precision,
            # Сколько дел разбирает аналитик на одну находку: обратная точность.
            reviews_per_catch=(1.0 / precision) if precision else None,
        )

    rows: list[RarityRow] = []

    natural = raw.get("natural") or []
    if natural:
        achieved = _mean([r["achieved_prevalence"] for r in natural]) or 0.0
        rows.append(_row(natural, achieved))

    buckets: dict[float, list[dict[str, Any]]] = {}
    for entry in raw.get("measured", []):
        buckets.setdefault(float(entry["target_prevalence"]), []).append(entry)
    for target in sorted(buckets, reverse=True):
        rows.append(_row(buckets[target], target))

    return rows, meta


# ──────────────────────────────────────────────────────────────────────
# Параметр W
# ──────────────────────────────────────────────────────────────────────
@dataclass
class FlowWeight:
    standalone: dict[str, float] = field(default_factory=dict)
    model: dict[str, float] = field(default_factory=dict)
    importance: dict[str, Any] = field(default_factory=dict)
    verdict: str = ""
    present: bool = False


def flow_weight() -> tuple[FlowWeight, RunMeta]:
    raw = _load("flow_weight_probe.json")
    meta = RunMeta(source="artifacts/flow_weight_probe.json")
    if not raw:
        return FlowWeight(), meta
    return (
        FlowWeight(
            standalone=raw.get("standalone_auc", {}),
            model=raw.get("model_auc", {}),
            importance=raw.get("permutation_importance", {}),
            verdict=raw.get("verdict", ""),
            present=True,
        ),
        meta,
    )


# ──────────────────────────────────────────────────────────────────────
# Признаки
# ──────────────────────────────────────────────────────────────────────
def features() -> tuple[list[tuple[str, float]], RunMeta]:
    raw = _load_list("feature_importances.json")
    meta = RunMeta(source="artifacts/feature_importances.json")
    if raw is None:
        return [], meta
    rows = [(item["feature"], float(item["importance"])) for item in raw]
    rows.sort(key=lambda pair: pair[1], reverse=True)
    return rows, meta


# ──────────────────────────────────────────────────────────────────────
# Очередь аналитика
# ──────────────────────────────────────────────────────────────────────
@dataclass
class Queue:
    world: dict[str, float] = field(default_factory=dict)
    outcomes: list[dict[str, Any]] = field(default_factory=list)
    preset: str = ""
    seconds: float = 0.0
    present: bool = False


def queue() -> tuple[Queue, RunMeta]:
    raw = _load("analyst_queue.json")
    meta = _meta(raw, "artifacts/analyst_queue.json")
    if not raw:
        return Queue(), meta
    return (
        Queue(
            world=raw.get("world", {}),
            outcomes=raw.get("outcomes", []),
            preset=raw.get("preset", ""),
            seconds=float(raw.get("seconds", 0.0)),
            present=True,
        ),
        meta,
    )



# ──────────────────────────────────────────────────────────────────────
# Сравнение моделей: четыре алгоритма на трёх уровнях анализа
# ──────────────────────────────────────────────────────────────────────
MODEL_NAMES_RU = {
    "rules": "Правила",
    "logistic": "Логистическая",
    "forest": "Лес",
    "boosting": "Бустинг",
}
SCOPE_NAMES_RU = {
    "account": "по счетам",
    "network_pooled": "по группам, признаки счетов",
    "network_structural": "по группам, структура",
}


@dataclass
class Cell:
    scope: str
    scope_ru: str
    model: str
    model_ru: str
    roc_auc: float
    average_precision: float
    rows: int
    positives: int
    base_rate: float
    folds: int
    monotonic: bool


@dataclass
class ModelMatrix:
    cells: list[Cell] = field(default_factory=list)
    scopes: list[str] = field(default_factory=list)
    models: list[str] = field(default_factory=list)
    world: dict[str, float] = field(default_factory=dict)
    account_unit: dict[str, float] = field(default_factory=dict)
    discovery: dict[str, float] = field(default_factory=dict)
    seed: int = 0
    present: bool = False

    def at(self, scope: str, model: str) -> Cell | None:
        for cell in self.cells:
            if cell.scope == scope and cell.model == model:
                return cell
        return None


def model_matrix() -> tuple[ModelMatrix, RunMeta]:
    raw = _load("experiment_ladder.json")
    meta = RunMeta(source="artifacts/experiment_ladder.json")
    if not raw:
        return ModelMatrix(), meta

    cells = [
        Cell(
            scope=c["scope"],
            scope_ru=SCOPE_NAMES_RU.get(c["scope"], c["scope"]),
            model=c["model"],
            model_ru=MODEL_NAMES_RU.get(c["model"], c["model"]),
            roc_auc=float(c["roc_auc"]),
            average_precision=float(c["average_precision"]),
            rows=int(c["rows"]),
            positives=int(c["positives"]),
            base_rate=float(c["base_rate"]),
            folds=int(c["folds"]),
            monotonic=str(c.get("ladder", "")).startswith("monotonic"),
        )
        for c in raw.get("cells", [])
    ]
    scopes, models = [], []
    for c in cells:
        if c.scope not in scopes:
            scopes.append(c.scope)
        if c.model not in models:
            models.append(c.model)
    return (
        ModelMatrix(
            cells=cells,
            scopes=scopes,
            models=models,
            world=raw.get("world", {}),
            account_unit=raw.get("account_unit", {}),
            discovery=raw.get("discovery", {}),
            seed=int(raw.get("seed", 0)),
            present=bool(cells),
        ),
        meta,
    )


# ──────────────────────────────────────────────────────────────────────
# Очередь аналитика: настоящие дела
# ──────────────────────────────────────────────────────────────────────
@dataclass
class Block:
    unit: str
    rows: int
    positives: int
    prevalence: float
    caught: int
    queued: int
    precision: float
    recall: float
    threshold: float
    ceiling: float
    items: list[dict[str, Any]] = field(default_factory=list)


def blocks() -> tuple[list[Block], RunMeta]:
    raw = _load("analyst_queue.json")
    meta = _meta(raw, "artifacts/analyst_queue.json")
    if not raw:
        return [], meta
    out = []
    for o in raw.get("outcomes", []):
        items = sorted(o.get("items", []), key=lambda i: i.get("rank", 0))
        out.append(
            Block(
                unit=o.get("unit", ""),
                rows=int(o.get("block_rows", 0)),
                positives=int(o.get("block_positives", 0)),
                prevalence=float(o.get("block_prevalence", 0.0)),
                caught=int(o.get("caught", 0)),
                queued=int(o.get("queued", 0)),
                precision=float(o.get("precision", 0.0)),
                recall=float(o.get("recall", 0.0)),
                threshold=float(o.get("threshold", 0.0)),
                ceiling=float(o.get("unit_ceiling", 0.0)),
                items=items,
            )
        )
    return out, meta


# ──────────────────────────────────────────────────────────────────────
# Рабочие точки: цена каждой следующей доли пойманных
# ──────────────────────────────────────────────────────────────────────
@dataclass
class Point:
    prevalence: float
    alerts_per_1000: float
    precision: float
    recall: float
    reviews_per_catch: float


def _points_from(runs: Sequence[dict[str, Any]]) -> list[Point]:
    """Точки порога, усреднённые по сидам: первая — половина дропов, вторая — хвост."""
    groups: dict[int, list[dict[str, Any]]] = {}
    for run in runs:
        for i, p in enumerate(run.get("operating_points", [])):
            groups.setdefault(i, []).append(p)
    return [
        Point(
            prevalence=_mean([p["prevalence"] for p in ps]) or 0.0,
            alerts_per_1000=_mean([p["alerts_per_1000_accounts"] for p in ps]) or 0.0,
            precision=_mean([p["precision"] for p in ps]) or 0.0,
            recall=_mean([p["recall"] for p in ps]) or 0.0,
            reviews_per_catch=_mean([p["reviews_per_catch"] for p in ps]) or 0.0,
        )
        for _, ps in sorted(groups.items())
    ]


def operating_points() -> tuple[list[Point], RunMeta]:
    """Точки порога на естественной доле мошенников — там, где они измерены."""
    raw = _load("prevalence_sweep.json")
    meta = _meta(raw, "artifacts/prevalence_sweep.json")
    if not raw:
        return [], meta
    return _points_from(raw.get("natural", [])), meta


def projected_points(prevalence: float = 0.001) -> list[Point]:
    """Те же точки, пересчитанные на заданную редкость.

    Разница с :func:`operating_points` — не в детекторе, а в том, что
    измерено, и её нельзя стирать: «естественная» ветка измерена на мире, где
    мошенников около семи процентов, а эта — арифметический перенос той же
    кривой на долю, при которой антифрод работает в жизни. Подписать перенос
    измерением значит соврать в ту сторону, которая красивее.
    """
    raw = _load("prevalence_sweep.json")
    if not raw:
        return []
    runs = [
        run for run in raw.get("projected", [])
        if abs(float(run.get("prevalence", -1)) - prevalence) < 1e-9
    ]
    return _points_from(runs)


# ──────────────────────────────────────────────────────────────────────
# Кривые детектора: ROC, precision-recall, калибровка, бюджет проверок
# ──────────────────────────────────────────────────────────────────────
@dataclass
class Curve:
    """Один разрез: модель на одном уровне анализа, со всеми её кривыми."""

    scope: str
    model: str
    rows: int
    positives: int
    base_rate: float
    folds: int
    roc_auc: float
    average_precision: float
    brier: float
    roc: list[dict[str, float]]
    pr: list[dict[str, float]]
    calibration: list[dict[str, Any]]
    histogram: list[dict[str, Any]]
    budget: list[dict[str, Any]]

    @property
    def key(self) -> str:
        return f"{self.scope}:{self.model}"

    @property
    def scope_ru(self) -> str:
        return SCOPE_NAMES_RU.get(self.scope, self.scope)

    @property
    def model_ru(self) -> str:
        return MODEL_NAMES_RU.get(self.model, self.model)


@dataclass
class CurveSet:
    items: list[Curve] = field(default_factory=list)
    world: dict[str, Any] = field(default_factory=dict)
    seed: int = 0
    present: bool = False

    def at(self, scope: str, model: str) -> Curve | None:
        for c in self.items:
            if c.scope == scope and c.model == model:
                return c
        return None


def curves() -> tuple[CurveSet, RunMeta]:
    raw = _load("detector_curves.json")
    meta = _meta(raw, "artifacts/detector_curves.json")
    if not raw:
        return CurveSet(), meta
    items = [
        Curve(
            scope=b["scope"],
            model=b["model"],
            rows=int(b["rows"]),
            positives=int(b["positives"]),
            base_rate=float(b["base_rate"]),
            folds=int(b["folds"]),
            roc_auc=float(b["roc_auc"]),
            average_precision=float(b["average_precision"]),
            brier=float(b["brier"]),
            roc=b["roc"],
            pr=b["pr"],
            calibration=b["calibration"],
            histogram=b["histogram"],
            budget=b["budget"],
        )
        for b in raw.get("blocks", [])
    ]
    return (
        CurveSet(
            items=items,
            world=raw.get("world", {}),
            seed=int(raw.get("seed", 0)),
            present=bool(items),
        ),
        meta,
    )



# ──────────────────────────────────────────────────────────────────────
# Внешняя валидация: Elliptic (задача 4.1)
# ──────────────────────────────────────────────────────────────────────
@dataclass
class EllipticArm:
    key: str
    label: str
    pooled: float | None
    mean_fold: float | None
    folds: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Elliptic:
    dataset: dict[str, int] = field(default_factory=dict)
    cases: dict[str, Any] = field(default_factory=dict)
    arms: list[EllipticArm] = field(default_factory=list)
    single_feature: list[tuple[str, float]] = field(default_factory=list)
    operating_point: dict[str, float] = field(default_factory=dict)
    margin: float | None = None
    present: bool = False


# Порядок здесь и есть порядок на витрине: сначала первый набор признаков,
# потом расширенный, потом контроль. Первый оставлен нарочно — без него
# «стало лучше» нечем подтвердить.
ELLIPTIC_ARM_LABELS = {
    "structural": "форма: первый набор, 5 признаков",
    "structural_plus_local": "первый набор плюс активность узла",
    "shape": "форма: расширенный набор, 16 признаков",
    "shape_plus_local": "расширенный набор плюс активность узла",
    "control_shuffled_labels": "контроль: метки перемешаны",
}


def elliptic() -> tuple[Elliptic, RunMeta]:
    raw = _load("elliptic_probe.json")
    meta = RunMeta(source="artifacts/elliptic_probe.json")
    if not raw:
        return Elliptic(), meta

    arms = [
        EllipticArm(
            key=key,
            label=ELLIPTIC_ARM_LABELS.get(key, key),
            pooled=(raw.get("arms", {}).get(key) or {}).get("pooled_roc_auc"),
            mean_fold=(raw.get("arms", {}).get(key) or {}).get("mean_fold_roc_auc"),
            folds=(raw.get("arms", {}).get(key) or {}).get("folds", []),
        )
        for key in ELLIPTIC_ARM_LABELS
        if key in raw.get("arms", {})
    ]
    # Рабочая точка берётся у той руки, которой отчитываются.
    point = (raw.get("arms", {}).get("shape") or {}).get("operating_point") or {}
    return (
        Elliptic(
            dataset=raw.get("dataset", {}),
            cases=raw.get("cases", {}),
            arms=arms,
            single_feature=sorted(
                raw.get("single_feature_auc_in_sample", {}).items(),
                key=lambda pair: pair[1],
                reverse=True,
            ),
            operating_point=point,
            margin=raw.get("margin_over_control"),
            present=True,
        ),
        meta,
    )


# ──────────────────────────────────────────────────────────────────────
# Панель: кейс на каждую дату (задача 4.11)
# ──────────────────────────────────────────────────────────────────────
@dataclass
class PanelWorld:
    seed: int
    rows: int
    cases: int
    dates: int
    fraud_share: float
    share_min: float | None
    share_max: float | None
    protocols: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class Panel:
    worlds: list[PanelWorld] = field(default_factory=list)
    cadence_days: int = 0
    present: bool = False

    def pooled(self, protocol: str, detector: str) -> list[float]:
        out = []
        for world in self.worlds:
            value = (world.protocols.get(protocol, {}).get(detector) or {}).get("pooled_roc_auc")
            if value is not None:
                out.append(float(value))
        return out


def panel() -> tuple[Panel, RunMeta]:
    raw = _load("case_panel.json")
    meta = RunMeta(source="artifacts/case_panel.json")
    if not raw:
        return Panel(), meta
    worlds_out: list[PanelWorld] = []
    for entry in raw.get("worlds", []):
        share = entry.get("fraud_share_by_date", {})
        worlds_out.append(
            PanelWorld(
                seed=int(entry.get("seed", 0)),
                rows=int(entry.get("rows", 0)),
                cases=int(entry.get("cases", 0)),
                dates=int(entry.get("dates", 0)),
                fraud_share=float(entry.get("fraud_share", 0.0)),
                share_min=share.get("min"),
                share_max=share.get("max"),
                protocols={
                    name: entry.get(name, {})
                    for name in ("time_forward", "case_holdout")
                },
            )
        )
    return Panel(worlds=worlds_out, cadence_days=int(raw.get("cadence_days", 0)), present=True), meta


# ──────────────────────────────────────────────────────────────────────
# Ветви ансамбля (задача 4.2)
# ──────────────────────────────────────────────────────────────────────
@dataclass
class Branch:
    key: str
    label: str
    across: dict[str, Any] = field(default_factory=dict)
    within: dict[str, Any] = field(default_factory=dict)
    seeds: list[int] = field(default_factory=list)
    generated_at: str = ""
    present: bool = False


BRANCH_FILES = {
    "graph": ("cheops_v2_graph_metrics.json", "графовая"),
    "sequence": ("cheops_v2_sequence_metrics.json", "последовательностная"),
}


def branches() -> list[Branch]:
    out: list[Branch] = []
    for key, (name, label) in BRANCH_FILES.items():
        raw = _load(name)
        if not raw or "across_worlds" not in raw:
            out.append(Branch(key=key, label=label))
            continue
        out.append(
            Branch(
                key=key,
                label=label,
                across=raw.get("across_worlds", {}),
                within=raw.get("within_world", {}),
                seeds=list(raw.get("seeds", [])),
                generated_at=str(raw.get("generated_at", ""))[:19].replace("T", " "),
                present=True,
            )
        )
    return out


def atlas() -> dict[str, Any] | None:
    """Атлас дел Elliptic: распределение оценок и модель для новой точки.

    Собирается scripts/make_case_atlas.py. Без файла раздел честно скажет,
    что прогона нет, — как и любой другой раздел витрины.
    """
    return _load("case_atlas.json")


def population_map() -> dict[str, Any] | None:
    """Карта популяции: 4 000 дел полигона на плоскости и само преобразование.

    Собирается scripts/make_population_map.py. Кроме точек в файле лежит
    вся арифметика PCA, чтобы точку нового дела считал браузер.
    """
    return _load("population_map.json")


def scorer() -> dict[str, Any] | None:
    """Модель в форме, которую считает браузер, или ``None``, если её нет.

    Единственное место витрины, где в страницу едет не измерение, а сама
    модель. Без неё раздел «Проверить» скажет, что модели нет, — как и любой
    другой раздел без своего файла прогона.
    """
    path = ARTIFACTS / "model.joblib"
    if not path.exists():
        return None
    # Внутри функции: joblib тянет за собой numpy и scipy, а витрина без
    # модели должна собираться и на машине, где их не ставили.
    import warnings

    import joblib

    from apris.web.model_export import export_model

    try:
        with warnings.catch_warnings():
            # Модель обучена другой версией sklearn. На дамп деревьев это не
            # влияет, а тест сверки поймал бы, если бы влияло.
            warnings.simplefilter("ignore")
            model = joblib.load(path)
        return export_model(model.booster_)
    except Exception:
        # Сломанная или незнакомая модель — это «модели нет», а не молча
        # другое число на экране.
        return None


def snapshot() -> dict[str, Any]:
    """Всё сразу — то, что рендерит витрина."""
    world_rows, world_meta = worlds()
    evasion_rows, evasion_meta = evasion()
    rarity_rows, rarity_meta = rarity()
    fw, fw_meta = flow_weight()
    feats, feat_meta = features()
    q, q_meta = queue()
    mm, mm_meta = model_matrix()
    bl, bl_meta = blocks()
    op, op_meta = operating_points()
    cv, cv_meta = curves()
    el, el_meta = elliptic()
    pn, pn_meta = panel()
    return {
        "elliptic": el, "elliptic_meta": el_meta,
        "panel": pn, "panel_meta": pn_meta,
        "branches": branches(),
        "curves": cv, "curves_meta": cv_meta,
        "matrix": mm, "matrix_meta": mm_meta,
        "blocks": bl, "blocks_meta": bl_meta,
        "points": op, "points_meta": op_meta,
        "projected": projected_points(0.001),
        "worlds": world_rows,
        "worlds_meta": world_meta,
        "evasion": evasion_rows,
        "evasion_meta": evasion_meta,
        "rarity": rarity_rows,
        "rarity_meta": rarity_meta,
        "flow_weight": fw,
        "flow_weight_meta": fw_meta,
        "features": feats,
        "features_meta": feat_meta,
        "queue": q,
        "queue_meta": q_meta,
    }

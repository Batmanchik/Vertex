"""Tests for the Elliptic adapter.

No download happens here. The dataset is ~690 MB and lives outside the
repository; these tests pin the logic on hand-built graphs whose answers are
known by construction.
"""

from __future__ import annotations

import networkx as nx
import pytest

from apris.cheops.infrastructure.external.elliptic import (
    RICH_FEATURE_NAMES,
    STRUCTURAL_FEATURE_NAMES,
    neighbourhood,
    rich_features,
    structural_features,
)


def _relay_graph(intermediaries: int = 8) -> nx.DiGraph:
    """source -> many -> single sink."""
    graph = nx.DiGraph()
    for i in range(intermediaries):
        graph.add_edge("SRC", f"M{i}")
        graph.add_edge(f"M{i}", "SINK")
    return graph


def _fan_out_graph(receivers: int = 8) -> nx.DiGraph:
    graph = nx.DiGraph()
    for i in range(receivers):
        graph.add_edge("SRC", f"R{i}")
    return graph


def _fan_in_graph(senders: int = 8) -> nx.DiGraph:
    graph = nx.DiGraph()
    for i in range(senders):
        graph.add_edge(f"S{i}", "COL")
    return graph


def test_structural_features_return_the_full_contract():
    features = structural_features(_relay_graph())
    assert set(features) == set(STRUCTURAL_FEATURE_NAMES)
    assert all(0.0 <= value <= 1.0 for value in features.values())


def test_relay_share_detects_a_relay_without_amounts():
    """The unweighted counterpart still recognises the shape.

    This is what makes the Elliptic result interpretable: if the counting
    version could not see a relay at all, a null result there would say
    nothing about the domain.
    """
    assert structural_features(_relay_graph())["relay_share"] > 0.3
    assert structural_features(_fan_out_graph())["relay_share"] == pytest.approx(0.0)
    assert structural_features(_fan_in_graph())["relay_share"] == pytest.approx(0.0)


def test_hub_and_fanout_point_in_opposite_directions():
    fan_out = structural_features(_fan_out_graph())
    fan_in = structural_features(_fan_in_graph())
    assert fan_out["fanout_share"] > 0.9
    assert fan_out["hub_share"] < 0.3
    assert fan_in["hub_share"] > 0.9
    assert fan_in["fanout_share"] < 0.3


def test_tiny_graphs_return_zeros_rather_than_raising():
    assert structural_features(nx.DiGraph()) == {n: 0.0 for n in STRUCTURAL_FEATURE_NAMES}
    single = nx.DiGraph()
    single.add_edge("A", "B")
    assert structural_features(single) == {n: 0.0 for n in STRUCTURAL_FEATURE_NAMES}


def test_neighbourhood_ignores_edge_direction():
    """A relay is invisible unless both feeders and fed nodes are included."""
    graph = _relay_graph(intermediaries=5)
    around_sink = neighbourhood(graph, "SINK", hops=2)
    assert "SRC" in around_sink
    assert any(node.startswith("M") for node in around_sink)


def test_neighbourhood_respects_the_cap():
    hub = nx.DiGraph()
    for i in range(2000):
        hub.add_edge("HUB", f"N{i}")
    assert neighbourhood(hub, "HUB", hops=2, cap=150).number_of_nodes() <= 150


# ── Обрезка окрестности ──────────────────────────────────────────────────


def test_the_case_always_contains_the_node_it_was_built_around():
    """Кусачий тест: метка стоит на узле, значит узел обязан быть в деле.

    Обрезка брала срез неупорядоченного множества, и на крупных окрестностях
    это выбрасывало сам узел: дело оставалось построенным вокруг узла,
    которого в нём нет, вместе с его меткой. На разрежённом графе Elliptic
    это задевало 0.1 % дел, на плотном — треть.
    """
    hub = nx.DiGraph()
    for index in range(2000):
        hub.add_edge(f"N{index}", "FOCAL")
    for size in (10, 150, 999):
        case = neighbourhood(hub, "FOCAL", hops=2, cap=size)
        assert "FOCAL" in case, f"дело на {size} узлов построено без своего узла"


def test_truncation_keeps_the_near_neighbours_rather_than_a_random_slice():
    """Обрезка обязана резать дальних: ближние и есть форма дела.

    Срез множества выбрасывал соседей первого шага наравне со вторым, то есть
    ровно то, ради чего дело и строится.
    """
    graph = nx.DiGraph()
    for index in range(20):
        graph.add_edge("FOCAL", f"NEAR{index}")
        for far in range(20):
            graph.add_edge(f"NEAR{index}", f"FAR{index}_{far}")

    # Потолок выбран так, чтобы второй шаг успел набрать дальних: при потолке
    # ровно по числу ближних обрезке нечего делать и тест ничего не проверяет.
    case = neighbourhood(graph, "FOCAL", hops=2, cap=25)
    near = [node for node in case if node.startswith("NEAR")]
    assert len(near) == 20, "ближние соседи вытеснены дальними"


# ── Расширенный набор признаков формы ────────────────────────────────────


def test_rich_features_return_the_full_contract():
    features = rich_features(_relay_graph(), "SRC")
    assert set(features) == set(RICH_FEATURE_NAMES)
    for name, value in features.items():
        assert isinstance(value, float), name


def test_a_node_missing_from_its_own_case_gets_zeros_not_a_crash():
    """Признаки роли узла без узла не определены, и выдумывать их нельзя."""
    assert rich_features(_relay_graph(), "НЕТ ТАКОГО") == {
        name: 0.0 for name in RICH_FEATURE_NAMES
    }


def test_the_focal_role_features_tell_a_source_from_a_sink():
    """Прежний набор не говорил о самом узле ничего, хотя метка стоит на нём."""
    graph = _relay_graph(intermediaries=6)

    source = rich_features(graph, "SRC")
    sink = rich_features(graph, "SINK")
    relay = rich_features(graph, "M0")

    assert source["focal_is_source"] == 1.0 and source["focal_is_sink"] == 0.0
    assert sink["focal_is_sink"] == 1.0 and sink["focal_is_source"] == 0.0
    assert relay["focal_is_sink"] == 0.0 and relay["focal_is_source"] == 0.0
    # −1 чистый источник, +1 чистый сток.
    assert source["focal_balance"] == pytest.approx(-1.0)
    assert sink["focal_balance"] == pytest.approx(1.0)
    assert relay["focal_balance"] == pytest.approx(0.0)


def test_shape_features_do_not_secretly_measure_case_size():
    """Иначе признак формы — это признак размера под другим именем.

    Сравнивается форма с той же формой, увеличенной пропорционально: две
    несвязанные копии одного графа. Пропорции ролей в них те же, значит и доли
    обязаны совпасть. Сравнение «пять посредников против шестидесяти» тут не
    годится — там пропорции меняются, и доля сквозных узлов честно растёт.
    """
    one = _relay_graph(intermediaries=6)
    two = nx.union(one, nx.relabel_nodes(one, lambda name: f"{name}#2"))

    small = rich_features(one, "SRC")
    large = rich_features(two, "SRC")
    assert two.number_of_nodes() == 2 * one.number_of_nodes()
    for name in ("passthrough_share", "sink_share", "source_share", "focal_balance"):
        assert small[name] == pytest.approx(large[name], abs=1e-9), name


def test_reciprocity_is_structurally_impossible_on_a_directed_acyclic_graph():
    """Почему reciprocity выброшен из расширенного набора.

    Elliptic — это DAG: транзакция не может заплатить назад в прошлое. На всех
    46 564 делах прогона признак равен нулю, то есть он не редкий, а
    невозможный. Здесь это закреплено на графе, где ответ известен заранее.
    """
    chain = nx.DiGraph([("A", "B"), ("B", "C"), ("C", "D")])
    assert nx.is_directed_acyclic_graph(chain)
    assert structural_features(chain)["reciprocity"] == 0.0
    assert "reciprocity" not in RICH_FEATURE_NAMES

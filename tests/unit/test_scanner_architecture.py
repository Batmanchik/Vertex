"""The interface does not run models, and does not draw pictures it invented.

Both rules are here because both were broken before, and neither breach was
visible from the screen — which is exactly why they are pinned as tests.

Local inference in a page means the demo can disagree with production while
looking identical. And a picture built from the verdict rather than from the
data will always agree with the verdict: the old dashboard chose a preset by
the risk score, generated transactions from a hash of the object's id, and
presented the result as that object's transaction network.
"""

from __future__ import annotations

import ast
from pathlib import Path

PAGES = sorted(Path("pages").glob("*.py"))

# Names that mean the page is scoring locally rather than asking the service.
LOCAL_INFERENCE_NAMES = frozenset({"predict_proba", "predict_risk", "load_artifacts"})

# Modules that either score locally or fabricate a structure to look at.
FORBIDDEN_IMPORTS = (
    "apris.graph_module",
    "apris.crypto_ponzi.tx_generator",
    "apris.crypto_ponzi.visualizations",
)

# The showcase page is allowed to draw the company-level demo, because that
# scenario is generated rather than detected and the picture is built from
# its transactions, not from a verdict. The permission is conditional: the
# page must say so on screen, and this marker is what says it.
DEMO_MARKER = "синтетический демонстрационный сценарий"
DEMO_ALLOWED = {"6_Витрина_Vertex.py"}


def test_there_are_pages_to_check() -> None:
    assert PAGES, "no pages found — the glob or the layout changed"


def _referenced_names(path: Path) -> set[str]:
    """Names the page actually uses, ignoring prose.

    Grepping the raw text was the first version and it was wrong: a page that
    *explains* why `predict_proba` is uncalibrated failed a test meant to
    catch a page that *calls* it. The check has to read code as code.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.name)
                if alias.asname:
                    names.add(alias.asname)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
    return names


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
        elif isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
    return modules


def test_no_page_runs_inference_locally() -> None:
    for path in PAGES:
        offenders = LOCAL_INFERENCE_NAMES & _referenced_names(path)
        assert not offenders, f"{path} calls {sorted(offenders)} instead of the API"


def test_no_page_draws_a_graph_built_from_the_verdict() -> None:
    for path in PAGES:
        modules = _imported_modules(path)
        for module in FORBIDDEN_IMPORTS:
            if module.startswith("apris.crypto_ponzi") and path.name in DEMO_ALLOWED:
                continue
            assert module not in modules, f"{path} imports {module}"


def test_a_page_showing_the_generated_company_says_it_is_a_demo() -> None:
    """Разрешение показывать сгенерированную компанию — условное.

    Картинка строится из транзакций, а не из вердикта, поэтому исходный
    запрет она не нарушает. Но кейс всё равно придуман, и на защите разница
    между «мы это нашли» и «мы это нарисовали» решает всё. Поэтому страница,
    которая его показывает, обязана сказать это на экране, и проверяется
    именно текст, а не намерение.
    """
    for path in PAGES:
        modules = _imported_modules(path)
        if not any(m.startswith("apris.crypto_ponzi") for m in modules):
            continue
        text = path.read_text(encoding="utf-8")
        assert DEMO_MARKER in text, (
            f"{path} показывает сгенерированную компанию, но нигде не говорит, "
            f"что это {DEMO_MARKER}"
        )


def test_scoring_pages_go_through_the_api_client() -> None:
    scoring_pages = [
        path for path in PAGES if "Досье" in path.name or "Ручная" in path.name
    ]
    assert scoring_pages, "expected the dossier and manual pages to exist"
    for path in scoring_pages:
        assert "apris.frontend" in " ".join(_imported_modules(path)), path
        assert "api_client" in _referenced_names(path), path

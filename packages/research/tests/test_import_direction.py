"""Core and pipeline must never import the research arena.

The project already claims "core imports nothing from pipeline" structurally;
the same one-way rule keeps research code from ever changing product
behaviour except through opt-in hooks.
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
    return out


def test_product_packages_do_not_import_research():
    offenders = []
    for pkg in ("core", "pipeline"):
        for f in (ROOT / "packages" / pkg / "src").rglob("*.py"):
            if any(m.startswith("echotales.research") for m in _imports(f)):
                offenders.append(str(f.relative_to(ROOT)))
    assert not offenders, offenders


def test_core_does_not_import_pipeline():
    offenders = [str(f.relative_to(ROOT)) for f in (ROOT / "packages/core/src").rglob("*.py")
                 if any(m.startswith("echotales.pipeline") for m in _imports(f))]
    assert not offenders, offenders

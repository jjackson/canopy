"""Discover pytest tests in a repo via AST scan."""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

try:
    import tomllib  # py 3.11+
except ImportError:  # pragma: no cover
    import tomli as tomllib  # type: ignore


@dataclass
class TestItem:
    __test__ = False  # don't let pytest try to collect this dataclass
    nodeid: str
    file: Path
    name: str
    line: int
    classname: str | None = None


def _is_test_file(path: Path) -> bool:
    n = path.name
    return path.suffix == ".py" and (n.startswith("test_") or n.endswith("_test.py"))


def _is_test_func_name(name: str) -> bool:
    return name.startswith("test_") or name == "test"


def _read_pytest_config(repo: Path) -> tuple[list[str], list[str]]:
    """Return (testpaths, norecursedirs) from pyproject.toml [tool.pytest.ini_options].

    Both lists may be empty. Missing pyproject or missing keys are not errors.
    """
    pyproject = repo / "pyproject.toml"
    if not pyproject.exists():
        return [], []
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError):
        return [], []
    cfg = data.get("tool", {}).get("pytest", {}).get("ini_options", {})
    testpaths = list(cfg.get("testpaths") or [])
    norecursedirs = list(cfg.get("norecursedirs") or [])
    return testpaths, norecursedirs


def _is_under(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


def collect(repo: Path, scope: str = "all") -> list[TestItem]:
    """Walk the repo and return every test function as a TestItem.

    Respects `[tool.pytest.ini_options]` in `pyproject.toml`:
    - `testpaths`: only walk these subdirectories (otherwise walk the repo).
    - `norecursedirs`: skip these subtrees.

    `scope` is reserved for `--scope changed` support; v1 always scans all.
    """
    repo = repo.resolve()
    testpaths, norecursedirs = _read_pytest_config(repo)
    roots = [repo / p for p in testpaths] if testpaths else [repo]
    excluded = [(repo / p).resolve() for p in norecursedirs]

    items: list[TestItem] = []
    seen: set[Path] = set()
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            if path in seen:
                continue
            seen.add(path)
            if not _is_test_file(path):
                continue
            # Skip vendored / virtualenv / build dirs.
            parts = set(path.parts)
            if parts & {".venv", "venv", "node_modules", "build", "dist", "__pycache__"}:
                continue
            # Skip pytest's norecursedirs.
            resolved = path.resolve()
            if any(_is_under(resolved, ex) for ex in excluded):
                continue
            try:
                src = path.read_text(encoding="utf-8")
                tree = ast.parse(src)
            except (SyntaxError, UnicodeDecodeError):
                continue
            rel = path.relative_to(repo) if path.is_relative_to(repo) else path
            for node in tree.body:
                if isinstance(node, ast.FunctionDef) and _is_test_func_name(node.name):
                    items.append(TestItem(
                        nodeid=f"{rel}::{node.name}",
                        file=path,
                        name=node.name,
                        line=node.lineno,
                    ))
                elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
                    for sub in node.body:
                        if isinstance(sub, ast.FunctionDef) and _is_test_func_name(sub.name):
                            items.append(TestItem(
                                nodeid=f"{rel}::{node.name}::{sub.name}",
                                file=path,
                                name=sub.name,
                                line=sub.lineno,
                                classname=node.name,
                            ))
    return items

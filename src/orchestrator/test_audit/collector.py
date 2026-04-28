"""Discover pytest tests in a repo via AST scan."""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path


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


def collect(repo: Path, scope: str = "all") -> list[TestItem]:
    """Walk the repo and return every test function as a TestItem.

    `scope` is reserved for `--scope changed` support; v1 always scans all.
    """
    items: list[TestItem] = []
    for path in sorted(repo.rglob("*.py")):
        if not _is_test_file(path):
            continue
        # Skip vendored / virtualenv / build dirs.
        parts = set(path.parts)
        if parts & {".venv", "venv", "node_modules", "build", "dist", "__pycache__"}:
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

"""Static AST analysis of a single pytest test."""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

from orchestrator.test_audit.collector import TestItem


@dataclass
class StaticAnalysis:
    nodeid: str
    name: str
    body_source: str
    assertion_count: int
    mock_targets: list[str] = field(default_factory=list)
    fixtures_used: list[str] = field(default_factory=list)
    source_funcs_referenced: list[str] = field(default_factory=list)
    has_real_assertion: bool = False  # at least one assert with a non-trivial expression
    line_count: int = 0


# Names whose calls indicate "this is a mock setup," not a meaningful assertion.
_MOCK_FUNCS = {"patch", "patch.object", "Mock", "MagicMock", "AsyncMock", "create_autospec"}
# Names that usually indicate the function under test (heuristic — tracked but
# refined by the judge LLM).
_FRAMEWORK_NAMES = {
    "assert", "assertEqual", "assertTrue", "assertFalse", "assertRaises",
    "pytest", "fixture", "monkeypatch", "tmp_path", "capsys", "caplog",
    "mock", "Mock", "MagicMock", "patch", "AsyncMock",
}


def _node_source(file: Path, node: ast.FunctionDef) -> str:
    """Return the source of `node` from its file. Stdlib `ast.get_source_segment`."""
    try:
        return ast.get_source_segment(file.read_text(encoding="utf-8"), node) or ""
    except Exception:
        return ""


def _find_func(tree: ast.Module, item: TestItem) -> ast.FunctionDef | None:
    if item.classname:
        for cls in tree.body:
            if isinstance(cls, ast.ClassDef) and cls.name == item.classname:
                for sub in cls.body:
                    if isinstance(sub, ast.FunctionDef) and sub.name == item.name:
                        return sub
        return None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == item.name:
            return node
    return None


def _extract_call_name(call: ast.Call) -> str:
    """Best-effort dotted name for a Call node."""
    f = call.func
    parts: list[str] = []
    while isinstance(f, ast.Attribute):
        parts.append(f.attr)
        f = f.value
    if isinstance(f, ast.Name):
        parts.append(f.id)
    return ".".join(reversed(parts))


def analyze(item: TestItem) -> StaticAnalysis:
    """Return static facts for a single test function."""
    src_full = item.file.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src_full)
    except SyntaxError:
        return StaticAnalysis(nodeid=item.nodeid, name=item.name, body_source="",
                              assertion_count=0, line_count=0)

    func = _find_func(tree, item)
    if func is None:
        return StaticAnalysis(nodeid=item.nodeid, name=item.name, body_source="",
                              assertion_count=0, line_count=0)

    body_source = ast.get_source_segment(src_full, func) or ""
    assertion_count = 0
    has_real_assertion = False
    mock_targets: list[str] = []
    source_funcs: list[str] = []

    for sub in ast.walk(func):
        if isinstance(sub, ast.Assert):
            assertion_count += 1
            # "assert True" or "assert 1" is a no-op; flag only those that test a value.
            if not (isinstance(sub.test, ast.Constant)):
                has_real_assertion = True
        elif isinstance(sub, ast.Call):
            name = _extract_call_name(sub)
            short = name.split(".")[-1]
            if short in _MOCK_FUNCS or name in _MOCK_FUNCS:
                # Capture the patch target. Common shapes:
                #   patch("pkg.mod.func")        — string constant
                #   patch(__name__ + ".func")    — BinOp; pull the string suffix
                #   patch.object(SomeClass, "m") — attribute + string
                target_str: str | None = None
                if sub.args:
                    first = sub.args[0]
                    if isinstance(first, ast.Constant) and isinstance(first.value, str):
                        target_str = first.value
                    else:
                        # Find the longest string constant inside the expression.
                        for inner in ast.walk(first):
                            if isinstance(inner, ast.Constant) and isinstance(inner.value, str):
                                if target_str is None or len(inner.value) > len(target_str):
                                    target_str = inner.value
                if target_str:
                    mock_targets.append(target_str.lstrip("."))
                else:
                    mock_targets.append(name)
            elif name and name.split(".")[0] not in _FRAMEWORK_NAMES:
                source_funcs.append(name)

    fixtures = [a.arg for a in func.args.args if a.arg not in ("self", "cls")]

    return StaticAnalysis(
        nodeid=item.nodeid,
        name=item.name,
        body_source=body_source,
        assertion_count=assertion_count,
        mock_targets=sorted(set(mock_targets)),
        fixtures_used=fixtures,
        source_funcs_referenced=sorted(set(source_funcs)),
        has_real_assertion=has_real_assertion,
        line_count=body_source.count("\n") + 1 if body_source else 0,
    )

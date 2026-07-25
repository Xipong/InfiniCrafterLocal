from __future__ import annotations

import ast
from pathlib import Path


def _duplicate_literal_dict_keys(path: Path) -> list[tuple[int, object]]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    duplicates: list[tuple[int, object]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        seen: set[tuple[type[object], object]] = set()
        for key_node in node.keys:
            if not isinstance(key_node, ast.Constant):
                continue
            value = key_node.value
            if not isinstance(value, (str, int, float, bool, type(None))):
                continue
            identity = (type(value), value)
            if identity in seen:
                duplicates.append((key_node.lineno, value))
            seen.add(identity)
    return duplicates


def test_python_sources_have_no_shadowed_literal_dict_keys() -> None:
    """A repeated literal key is silent last-wins and must fail source hygiene."""

    root = Path(__file__).resolve().parents[1]
    problems: list[str] = []
    for source_root in (root / "infini_local", root.parent / "tools"):
        for path in sorted(source_root.rglob("*.py")):
            for line, value in _duplicate_literal_dict_keys(path):
                problems.append(
                    f"{path.relative_to(root.parent).as_posix()}:{line}: {value!r}"
                )
    assert problems == []


def _duplicate_adjacent_assignments(path: Path) -> list[int]:
    """Return exact same-target/same-value assignments repeated in one block."""

    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    duplicates: list[int] = []
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(body, list):
            continue
        previous: ast.stmt | None = None
        for statement in body:
            if (
                previous is not None
                and isinstance(statement, (ast.Assign, ast.AnnAssign))
                and isinstance(previous, type(statement))
                and ast.dump(statement, include_attributes=False)
                == ast.dump(previous, include_attributes=False)
            ):
                duplicates.append(statement.lineno)
            previous = statement
    return duplicates


def test_python_sources_have_no_exact_adjacent_duplicate_assignments() -> None:
    """Exact adjacent writes are a hidden second owner, even when currently equal."""

    root = Path(__file__).resolve().parents[1]
    problems: list[str] = []
    for source_root in (root / "infini_local", root.parent / "tools"):
        for path in sorted(source_root.rglob("*.py")):
            for line in _duplicate_adjacent_assignments(path):
                problems.append(f"{path.relative_to(root.parent).as_posix()}:{line}")
    assert problems == []


def _top_level_constant_owners(root: Path, names: set[str]) -> dict[str, list[str]]:
    owners = {name: [] for name in names}
    for path in sorted((root / "infini_local").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        for statement in tree.body:
            target_name: str | None = None
            if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
                target = statement.targets[0]
                if isinstance(target, ast.Name):
                    target_name = target.id
            elif isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
                target_name = statement.target.id
            if target_name in owners:
                owners[target_name].append(path.relative_to(root).as_posix())
    return owners


def test_visual_identity_tables_have_one_canonical_owner() -> None:
    """Naming/palette policy must not silently fork across pipeline modules."""

    root = Path(__file__).resolve().parents[1]
    owners = _top_level_constant_owners(root, {"PALETTES", "BAD_NAME_PATTERNS"})
    expected = "infini_local/pipelines/pipeline_runtime_constants.py"
    assert owners == {
        "BAD_NAME_PATTERNS": [expected],
        "PALETTES": [expected],
    }

    from infini_local.pipelines import pipeline_runtime_constants
    from infini_local.pipelines import result_identity_policy

    assert result_identity_policy.PALETTES is pipeline_runtime_constants.PALETTES
    assert (
        result_identity_policy.BAD_NAME_PATTERNS
        is pipeline_runtime_constants.BAD_NAME_PATTERNS
    )

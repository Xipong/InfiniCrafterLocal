from __future__ import annotations

from contextlib import ExitStack
import inspect
import os
from pathlib import Path
import re
from typing import Any, Callable, Mapping, Sequence

import pytest


def _case_tmp_path(base: Path, name: str) -> Path:
    case_name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", name).strip("._") or "case"
    path = base / case_name
    path.mkdir(parents=True, exist_ok=True)
    return path


def run_contract_checks(
    namespace: Mapping[str, Any],
    request: Any,
    names: Sequence[str],
) -> None:
    """Run former pytest items as one isolated module-level contract.

    Each check gets its own MonkeyPatch context and tmp_path child, preserving the
    isolation that separate function-scoped pytest items provided. Other fixtures are
    resolved through the active pytest request only when a check explicitly asks for one.
    """
    base_tmp_path: Path | None = None
    original_cwd = Path.cwd()
    for name in names:
        check = namespace.get(name)
        if not callable(check):
            raise AssertionError(f"missing contract check: {name}")
        signature = inspect.signature(check)
        kwargs: dict[str, Any] = {}
        with ExitStack() as stack:
            for parameter in signature.parameters.values():
                fixture_name = parameter.name
                if fixture_name == "monkeypatch":
                    kwargs[fixture_name] = stack.enter_context(pytest.MonkeyPatch.context())
                elif fixture_name == "tmp_path":
                    if base_tmp_path is None:
                        base_tmp_path = Path(request.getfixturevalue("tmp_path"))
                    kwargs[fixture_name] = _case_tmp_path(base_tmp_path, name)
                else:
                    kwargs[fixture_name] = request.getfixturevalue(fixture_name)
            try:
                check(**kwargs)
            finally:
                os.chdir(original_cwd)

from __future__ import annotations

import ast
from pathlib import Path
import re

import pytest

from contract_checks import (
    assert_pipeline_phase_order,
    assert_pipeline_terminal_phase,
    discover_contract_checks,
    literal_string_arguments,
    pipeline_phase_count,
    run_contract_checks,
)

TESTS_DIR = Path(__file__).resolve().parent


def _unsafe_contract_calls(source: str) -> list[int]:
    """Find explicit check lists lacking a no-omission gate, regardless of layout."""
    unsafe = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        function_name = (node.func.id if isinstance(node.func, ast.Name)
                         else node.func.attr if isinstance(node.func, ast.Attribute) else None)
        if function_name != "run_contract_checks":
            continue
        names = node.args[2] if len(node.args) >= 3 else next(
            (kw.value for kw in node.keywords if kw.arg == "names"), None
        )
        if names is None:
            continue
        gated = any(
            kw.arg == "require_all" and isinstance(kw.value, ast.Constant)
            and kw.value.value is True for kw in node.keywords
        )
        if not gated:
            unsafe.append(node.lineno)
    return unsafe


def _contract_check_first() -> None:
    pass


def _contract_check_second() -> None:
    pass


def test_contract_check_discovery_is_ordered_and_explicit_lists_cannot_hide_checks() -> None:
    namespace = {
        "__name__": __name__,
        "_contract_check_first": _contract_check_first,
        "foreign_check": lambda: None,
        "_contract_check_second": _contract_check_second,
    }
    assert discover_contract_checks(namespace) == (
        "_contract_check_first",
        "_contract_check_second",
    )

    with pytest.raises(AssertionError, match="unregistered contract checks.*_contract_check_second"):
        run_contract_checks(
            namespace,
            request=object(),
            names=("_contract_check_first",),
            require_all=True,
        )


def test_contract_modules_use_the_shared_runner_instead_of_a_copied_dispatch_loop() -> None:
    """No test module may hand-maintain its own list of checks.

    Ten modules used to carry a copy of the runner with the check names written out
    by hand. A hand-kept list drifts silently: a new check is simply never called,
    and the module still reports one passing item. The copies also lost behaviour
    the shared runner has -- cwd restoration and fixtures other than monkeypatch.
    """
    offenders: list[str] = []
    stale_lists: list[str] = []
    for path in sorted(TESTS_DIR.glob("test_*.py")):
        if path.name == Path(__file__).name:
            # This module names the banned pattern in its own assertions.
            continue
        source = path.read_text(encoding="utf-8")
        if "_run_coarse_contracts" in source:
            offenders.append(path.name)
        if "run_contract_checks" not in source:
            continue
        # Parse actual calls, not a regex terminated by a nested close-paren.
        stale_lists.extend(f"{path.name}:{line}" for line in _unsafe_contract_calls(source))

    assert not offenders, (
        "these modules copy the dispatch loop instead of using contract_checks."
        f"run_contract_checks: {offenders}"
    )
    assert not stale_lists, (
        "explicit check lists must pass require_all=True so a new check cannot be "
        f"silently omitted: {stale_lists}"
    )


def test_contract_runner_gate_detects_nested_explicit_lists_without_misreading_comments() -> None:
    source = '''
def example(request):
    # require_all=True in a comment does not enforce discovery coverage.
    run_contract_checks(globals(), request, tuple(["_contract_check_first"]))
    run_contract_checks(globals(), request, names=("_contract_check_first",), require_all=True)
    run_contract_checks(globals(), request)
    contract_checks.run_contract_checks(globals(), request, names=("_contract_check_first",))
    contract_checks.run_contract_checks(globals(), request, names=("_contract_check_first",), require_all=True)
'''
    assert _unsafe_contract_calls(source) == [4, 7]


def test_literal_string_arguments_survives_parentheses_that_defeat_regex_scraping() -> None:
    """Source-shape contracts must not depend on call-site formatting.

    The GUI reachability contract used ``self\\.row\\([^)]*?["'](INFINI_...)["']``.
    That pattern stops at the first ``)``, so a label like "Label (advanced)" or a
    nested ``self._card(...)`` argument hid the row completely -- reporting an
    exposed setting as missing.
    """
    brittle = r"self\.(?:row|check_row)\([^)]*?[\"'](INFINI_[A-Z0-9_]+)[\"']"
    source = (
        "class Gui:\n"
        "    def build(self):\n"
        '        self.row(card, "Plain", "INFINI_PLAIN")\n'
        '        self.row(card, "Label (advanced)", "INFINI_PAREN_LABEL")\n'
        '        self.row(self._card(parent, "x"), "Nested", "INFINI_NESTED_CALL")\n'
        '        self.check_row(card, "Flag", hint="see (docs)", key="INFINI_HINT_FIRST")\n'
        '        self.ignored(card, "Other", "INFINI_NOT_A_ROW")\n'
    )

    found = literal_string_arguments(
        source, ("row", "check_row"), match=r"INFINI_[A-Z0-9_]+"
    )
    assert found == (
        "INFINI_PLAIN",
        "INFINI_PAREN_LABEL",
        "INFINI_NESTED_CALL",
        "INFINI_HINT_FIRST",
    )
    # Calls to other methods are not row declarations and must stay out.
    assert "INFINI_NOT_A_ROW" not in found

    # Demonstrate the regression this replaces: a parenthesis anywhere before the
    # key hides that call site from the old pattern.
    regex_found = set(re.findall(brittle, source, flags=re.S))
    assert set(found) - regex_found == {
        "INFINI_PAREN_LABEL",
        "INFINI_NESTED_CALL",
        "INFINI_HINT_FIRST",
    }


def test_pipeline_phase_assertions_hide_stage_spelling_from_behavior_tests() -> None:
    labels = [
        "02_strict_author_validation",
        "04_author_gameplay_to_runtime_envelope",
        "04d_structural_final_wire_preflight",
        "04e_same_author_scoped_repair",
        "04k_repaired_structural_final_wire_preflight",
        "08_visual_director_asset_pack",
        "09_visual_asset_generation",
        "12_final_normalize",
        "12a_final_runtime_promise_boundary",
    ]
    assert_pipeline_phase_order(
        labels,
        "author_validation",
        "runtime_compile",
        "initial_final_wire",
        "author_recovery",
        "recovered_final_wire",
        "visual_director",
        "asset_generation",
        "final_normalize",
        "final_runtime_boundary",
    )
    assert pipeline_phase_count(labels, "runtime_compile") == 1
    assert_pipeline_terminal_phase(labels, "final_runtime_boundary")

    source = "\n".join(f'step("{label}", fn)' for label in labels)
    assert_pipeline_phase_order(
        source,
        "initial_final_wire",
        "visual_director",
        "asset_generation",
        "final_normalize",
        "final_runtime_boundary",
    )

    with pytest.raises(AssertionError, match="pipeline phase order"):
        assert_pipeline_phase_order(labels, "asset_generation", "visual_director")

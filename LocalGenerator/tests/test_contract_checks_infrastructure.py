from __future__ import annotations

import pytest

from contract_checks import (
    assert_pipeline_phase_order,
    assert_pipeline_terminal_phase,
    discover_contract_checks,
    pipeline_phase_count,
    run_contract_checks,
)


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

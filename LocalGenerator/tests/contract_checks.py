from __future__ import annotations

from contextlib import ExitStack
import inspect
import os
from pathlib import Path
import re
from typing import Any, Callable, Mapping, Sequence

import pytest


# Stable semantic names for high-churn pipeline tests. Production stage labels remain
# useful telemetry, but behavior tests should depend on these meanings rather than on
# numbering or repair terminology spread across many files.
PIPELINE_PHASE_MARKERS: Mapping[str, tuple[str, ...]] = {
    "author_validation": ("strict_author_validation",),
    "runtime_compile": ("gameplay_to_runtime_envelope",),
    "initial_executable_preflight": ("04c_strict_executable_preflight",),
    "initial_final_wire": ("04d_structural_final_wire_preflight",),
    "author_recovery": ("same_author_scoped_repair",),
    "recovered_final_wire": ("repaired_structural_final_wire_preflight",),
    "visual_director": ("visual_director_asset_pack",),
    "post_visual_executable_preflight": ("08c_strict_executable_preflight",),
    "vfx_manifest": ("08d_hybrid_vfx_manifest",),
    "asset_runtime_gates": ("08e_visual_asset_runtime_gates",),
    "visual_author_boundary": ("08f_strict_visual_authoring_boundaries",),
    "asset_generation": ("visual_asset_generation",),
    "final_projection": ("11a_project_presentation_out_of_attack",),
    "final_executable_boundary": ("11b_strict_executable_boundary",),
    "final_normalize": ("12_final_normalize",),
    "final_runtime_boundary": ("12a_final_runtime_promise_boundary",),
}


def discover_contract_checks(
    namespace: Mapping[str, Any],
    *,
    prefix: str = "_contract_check_",
) -> tuple[str, ...]:
    """Discover local checks in definition order without collecting imported helpers."""
    module_name = str(namespace.get("__name__") or "")
    return tuple(
        name
        for name, value in namespace.items()
        if name.startswith(prefix)
        and callable(value)
        and (not module_name or getattr(value, "__module__", None) == module_name)
    )


def _phase_positions(labels_or_source: Sequence[str] | str, phases: Sequence[str]) -> list[int]:
    positions: list[int] = []
    for phase in phases:
        markers = PIPELINE_PHASE_MARKERS.get(phase)
        if markers is None:
            raise AssertionError(f"unknown pipeline phase: {phase}")
        if isinstance(labels_or_source, str):
            candidates = [labels_or_source.find(marker) for marker in markers]
            candidates = [position for position in candidates if position >= 0]
        else:
            candidates = [
                index
                for index, label in enumerate(labels_or_source)
                if any(marker in str(label) for marker in markers)
            ]
        if not candidates:
            raise AssertionError(f"missing pipeline phase {phase}: markers={markers!r}")
        positions.append(min(candidates))
    return positions


def assert_pipeline_phase_order(
    labels_or_source: Sequence[str] | str,
    *phases: str,
) -> None:
    """Assert semantic pipeline order while centralizing volatile stage spellings."""
    positions = _phase_positions(labels_or_source, phases)
    if positions != sorted(positions) or len(set(positions)) != len(positions):
        raise AssertionError(
            f"pipeline phase order mismatch: phases={phases!r}, positions={positions!r}"
        )


def assert_pipeline_terminal_phase(labels: Sequence[str], phase: str) -> None:
    """Require the final observed stage to carry the requested semantic phase."""
    if not labels:
        raise AssertionError("pipeline phase order mismatch: no observed stages")
    position = _phase_positions(labels, (phase,))[0]
    if position != len(labels) - 1:
        raise AssertionError(
            f"pipeline terminal phase mismatch: phase={phase!r}, "
            f"position={position}, final={len(labels) - 1}"
        )


def pipeline_phase_count(labels_or_source: Sequence[str] | str, phase: str) -> int:
    markers = PIPELINE_PHASE_MARKERS.get(phase)
    if markers is None:
        raise AssertionError(f"unknown pipeline phase: {phase}")
    if isinstance(labels_or_source, str):
        return sum(labels_or_source.count(marker) for marker in markers)
    return sum(
        1
        for label in labels_or_source
        if any(marker in str(label) for marker in markers)
    )


def _case_tmp_path(base: Path, name: str) -> Path:
    case_name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", name).strip("._") or "case"
    path = base / case_name
    path.mkdir(parents=True, exist_ok=True)
    return path


def run_contract_checks(
    namespace: Mapping[str, Any],
    request: Any,
    names: Sequence[str] | None = None,
    *,
    prefix: str = "_contract_check_",
    require_all: bool = False,
) -> None:
    """Run former pytest items as one isolated module-level contract.

    Each check gets its own MonkeyPatch context and tmp_path child, preserving the
    isolation that separate function-scoped pytest items provided. Other fixtures are
    resolved through the active pytest request only when a check explicitly asks for one.
    Omit ``names`` for definition-order discovery in high-churn modules. Explicit lists
    remain available for intentional module partitions; ``require_all=True`` turns them
    into a no-omission gate.
    """
    discovered = discover_contract_checks(namespace, prefix=prefix)
    if names is None:
        names = discovered
    else:
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise AssertionError(f"duplicate contract checks: {duplicates}")
        omitted = [name for name in discovered if name not in names]
        if require_all and omitted:
            raise AssertionError(f"unregistered contract checks: {omitted}")
    if not names:
        raise AssertionError(f"no contract checks discovered for prefix {prefix!r}")

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

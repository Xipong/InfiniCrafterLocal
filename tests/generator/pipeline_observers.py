from __future__ import annotations

from typing import Mapping, Sequence


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


def _phase_positions(labels: Sequence[str], phases: Sequence[str]) -> list[int]:
    positions: list[int] = []
    for phase in phases:
        markers = PIPELINE_PHASE_MARKERS.get(phase)
        if markers is None:
            raise AssertionError(f"unknown pipeline phase: {phase}")
        candidates = [index for index, label in enumerate(labels) if any(marker in label for marker in markers)]
        if not candidates:
            raise AssertionError(f"missing pipeline phase {phase}: markers={markers!r}")
        positions.append(min(candidates))
    return positions


def assert_pipeline_phase_order(
    labels: Sequence[str],
    *phases: str,
) -> None:
    """Assert semantic pipeline order while centralizing volatile stage spellings."""
    positions = _phase_positions(labels, phases)
    if positions != sorted(positions) or len(set(positions)) != len(positions):
        raise AssertionError(f"pipeline phase order mismatch: phases={phases!r}, positions={positions!r}")


def assert_pipeline_terminal_phase(labels: Sequence[str], phase: str) -> None:
    """Require the final observed stage to carry the requested semantic phase."""
    if not labels:
        raise AssertionError("pipeline phase order mismatch: no observed stages")
    position = _phase_positions(labels, (phase,))[0]
    if position != len(labels) - 1:
        raise AssertionError(f"pipeline terminal phase mismatch: phase={phase!r}, position={position}, final={len(labels) - 1}")


def pipeline_phase_count(labels: Sequence[str], phase: str) -> int:
    markers = PIPELINE_PHASE_MARKERS.get(phase)
    if markers is None:
        raise AssertionError(f"unknown pipeline phase: {phase}")
    return sum(1 for label in labels if any(marker in str(label) for marker in markers))

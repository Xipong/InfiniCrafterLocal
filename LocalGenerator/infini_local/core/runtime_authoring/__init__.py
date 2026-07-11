from __future__ import annotations

# Stable external API for runtime-plan authoring. Internal compiler helpers stay
# in their owning modules and are intentionally not re-exported here.
from infini_local.core.runtime_authoring.common import ENGINE_RUNTIME_API_VERSION
from infini_local.core.runtime_authoring.compiler import compile_runtime_plan_to_genome_patch
from infini_local.core.runtime_authoring.normalize import normalize_runtime_plan_inplace, runtime_plan
from infini_local.core.runtime_authoring.reports import (
    compile_runtime_plan_to_genome_result,
    compiled_runtime_contract,
    infer_attack_pattern_from_runtime,
    runtime_plan_provenance_report,
    runtime_plan_quality_report,
    runtime_plan_validation_report,
)
from infini_local.core.runtime_authoring.schema import ENGINE_FN_CATALOG_V2
from infini_local.core.runtime_authoring.structural import (
    all_calls,
    find_call,
    structural_repair_runtime_plan_inplace,
)


__all__ = [
    "ENGINE_FN_CATALOG_V2",
    "ENGINE_RUNTIME_API_VERSION",
    "all_calls",
    "compile_runtime_plan_to_genome_patch",
    "compile_runtime_plan_to_genome_result",
    "compiled_runtime_contract",
    "find_call",
    "infer_attack_pattern_from_runtime",
    "normalize_runtime_plan_inplace",
    "runtime_plan",
    "runtime_plan_provenance_report",
    "runtime_plan_quality_report",
    "runtime_plan_validation_report",
    "structural_repair_runtime_plan_inplace",
]

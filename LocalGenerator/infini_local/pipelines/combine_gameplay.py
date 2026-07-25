from __future__ import annotations

"""Low-level gameplay compilation seam.

Gameplay Author already owns every design decision in runtimeProgram.  This
module only compiles the validated author form to the typed wire DTO and adds
parent/recipe metadata that does not route gameplay.
"""

import copy
from typing import Any

from infini_local.core.runtime_authoring import (
    RUNTIME_PROGRAM_API_VERSION,
    assert_valid_runtime_wire,
    compile_runtime_program,
)


def attach_gameplay_and_runtime_program(
    data: dict[str, Any],
    a: dict[str, Any],
    b: dict[str, Any],
    ca: dict[str, Any],
    cb: dict[str, Any],
) -> dict[str, Any]:
    del ca, cb  # Parent cards informed the Author; they never route compilation.
    compiled = compile_runtime_program(data)
    compiled["runtimeApiVersion"] = RUNTIME_PROGRAM_API_VERSION
    compiled.setdefault("schemaVersion", 5)
    compiled.setdefault("parentA", str(a.get("name") or a.get("displayName") or ""))
    compiled.setdefault("parentB", str(b.get("name") or b.get("displayName") or ""))
    compiled.setdefault("debug", {})["gameplayCompiler"] = "explicit_low_level_runtime_program_v5"
    compiled["debug"]["gameplayDesignAuthorship"] = "gameplay_author"
    compiled["debug"]["deterministicRole"] = "validate_compile_execute_only"
    assert_valid_runtime_wire(compiled)
    return compiled


def low_level_balance_report(data: dict[str, Any]) -> dict[str, Any]:
    """Report authored values and hard bounds without archetype normalization."""
    runtime = data.get("runtimeProgram") if isinstance(data.get("runtimeProgram"), dict) else {}
    entities = runtime.get("entities") if isinstance(runtime.get("entities"), list) else []
    damage_values: list[int] = []
    lifetime_values: list[int] = []
    spawn_values: list[int] = []
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        damage = entity.get("damage") if isinstance(entity.get("damage"), dict) else {}
        lifetime = entity.get("lifetime") if isinstance(entity.get("lifetime"), dict) else {}
        spawn = entity.get("spawn") if isinstance(entity.get("spawn"), dict) else {}
        if damage.get("enabled"):
            damage_values.append(int(damage.get("damage") or 0))
        if lifetime:
            lifetime_values.append(int(lifetime.get("timeLeftTicks") or 0))
        if spawn:
            spawn_values.append(int(spawn.get("count") or 0))
    return {
        "schema": "infini.low-level-balance-report.v1",
        "authority": "authored_values_with_hard_runtime_bounds",
        "semanticNormalization": False,
        "entityCount": len(entities),
        "authoredDamageValues": damage_values,
        "authoredLifetimeTicks": lifetime_values,
        "authoredSpawnCounts": spawn_values,
    }


__all__ = ["attach_gameplay_and_runtime_program", "low_level_balance_report"]

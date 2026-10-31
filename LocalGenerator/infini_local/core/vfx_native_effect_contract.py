"""Curated stock Terraria one-shots; native recipes, not geometry lowering."""

from __future__ import annotations

from infini_local.core.vfx_material_contract import _number, _object

NATIVE_EFFECT_TYPES = {
    "goldCrossBurst": "Golden axial sparkle burst (Terraria Excalibur), 8 sparkles lasting 30 ticks plus 8 native Dust. Fixed palette/size/layer, no movement input.",
    "rainbowBurst": "Radial multicolored sparkle burst (Terraria RainbowRodHit), 12 sparkles lasting 60 ticks plus 24 native Dust. movement is world-pixel/tick native input, distributed/scaled by the stock burst, not exact particle speed or damage.",
    "darkLightningBurst": "Short animated black/indigo lightning fragments (Terraria BlackLightningHit), native 24-tick animation. Fixed palette/size/layer, no movement input; loads a native texture, never a gameplay projectile.",
    "shimmerStar": "One randomly colored drifting star (Terraria ShimmerBlock), native 45-tick lifetime and acceleration. movement is initial world-pixel/tick velocity; native acceleration adds movement/45 each tick.",
}
NATIVE_EFFECT_COSTS = {"goldCrossBurst": 16, "rainbowBurst": 36, "darkLightningBurst": 8, "shimmerStar": 1}
MOVING_NATIVE_EFFECTS = ("rainbowBurst", "shimmerStar")
NATIVE_EFFECT_SEMANTICS = (
    "Explicit stock native one-shot recipe, not a customizable shape. Native owns color, scale, "
    "lifetime and over-player layer; no tint, count, duration, blend or attachment controls. "
    "Spawns detached at captured anchor; particles may finish after source disappears. "
    "Whole burst reservations are goldCrossBurst=16, rainbowBurst=36, darkLightningBurst=8 "
    "(conservative native float-loop bound), shimmerStar=1 particles. Configured per-tick and total "
    "budgets must each cover one reservation; shared live occupancy and a 256-particle global native "
    "per-tick limit may suppress the whole burst under contention. "
    "Client-only local dispatch, "
    "no network packets, gameplay projectiles or sound. Native randomness is Terraria Main.rand, "
    "not the slot seed. startTick delays an event; periodic repeatEvery>=1 is exact cadence "
    "and item periodic startTick=0. " + " ".join(f"{key}: {value}" for key, value in NATIVE_EFFECT_TYPES.items())
)


def native_effect_schema() -> dict:
    result = _object(
        {
            "type": {"type": "string", "enum": list(NATIVE_EFFECT_TYPES)},
            "movement": {
                **_object(
                    {
                        "x": _number(-24, 24, "World X pixels per tick, positive right."),
                        "y": _number(-24, 24, "World Y pixels per tick, positive down."),
                    }
                ),
                "description": "Stock velocity input in world pixels/tick, not guaranteed speed of every particle; native recipe may scale/distribute/accelerate it. Zero is explicit, never inferred from source.",
            },
        }
    )
    result["required"] = ["type"]
    result["description"] = (
        "Select one stock recipe from rendererSemantics.nativeEffect; movement exists only for rainbowBurst and shimmerStar."
    )
    result["allOf"] = [
        {"if": {"properties": {"type": {"enum": list(MOVING_NATIVE_EFFECTS)}}, "required": ["type"]}, "then": {"required": ["movement"]}},
        {
            "if": {
                "properties": {"type": {"enum": [t for t in NATIVE_EFFECT_TYPES if t not in MOVING_NATIVE_EFFECTS]}},
                "required": ["type"],
            },
            "then": {"properties": {"movement": {"enum": []}}},
        },
    ]
    return result


def native_effect_slot_clauses(item_ids: list[str], renderers: list[str], events: list[str]) -> list[dict]:
    def when(props: dict, then: dict) -> dict:
        return {"if": {"properties": props, "required": list(props)}, "then": then}

    selected = {"rendererKind": {"const": "nativeEffect"}}
    return [
        when(selected, {"required": ["nativeEffect", "startTick", "repeatEvery"]}),
        when({"rendererKind": {"enum": [r for r in renderers if r != "nativeEffect"]}}, {"properties": {"nativeEffect": {"enum": []}}}),
        when({**selected, "event": {"const": "periodic"}}, {"properties": {"repeatEvery": {"minimum": 1}}}),
        when({**selected, "event": {"enum": [e for e in events if e != "periodic"]}}, {"properties": {"repeatEvery": {"const": 0}}}),
        when({**selected, "event": {"const": "periodic"}, "entityId": {"enum": item_ids}}, {"properties": {"startTick": {"const": 0}}}),
    ]


def native_effect_budget_errors(slot, budget, path="$.vfxManifest.budget") -> list[dict]:
    if not isinstance(slot, dict) or slot.get("rendererKind") != "nativeEffect" or not isinstance(budget, dict):
        return []
    payload = slot.get("nativeEffect")
    kind = payload.get("type") if isinstance(payload, dict) else None
    cost = NATIVE_EFFECT_COSTS.get(kind) if isinstance(kind, str) else None
    if cost is None:
        return []
    return [
        {"path": f"{path}.{key}", "message": f"must cover nativeEffect {kind} whole-burst reservation of {cost} particles"}
        for key in ("maxParticlesPerTick", "maxParticlesTotal")
        if type(budget.get(key)) is int and budget[key] < cost
    ]

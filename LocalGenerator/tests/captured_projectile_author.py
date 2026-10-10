"""Finite test-only projection of the two captured Author corpora.

The archived JSON and its hashes remain evidence of their original contracts.
These rewrites let the same captured choices exercise the current production
compiler and Repair. No runtime, storage loader or provider imports this helper.
"""

from typing import Any


def project_captured_projectile_call(call: dict[str, Any]) -> None:
    params = call.get("params", {})
    fn = call.get("fn")
    if fn == "configure_spawn" and "placement" in params:
        anchor = params.pop("placement")
        assert anchor in {"item_use_origin", "ground_at_cursor", "cursor"}
        assert "position" not in params
        params["position"] = {"at": "activation_origin" if anchor == "item_use_origin" else anchor}
    elif fn == "set_projectile_collision" and "npcImmunityMode" in params:
        mode = params.pop("npcImmunityMode")
        cooldown = params.pop("localNpcHitCooldownEngineUnits")
        assert mode in {"owner", "local"}
        assert "immunity" not in params and "updatesPerTick" not in params
        # Preserve negative invalid values in the captured diagnostic case.
        # Only -1 is the historical once-per-NPC choice.
        params["immunity"] = (
            "owner_shared" if mode == "owner" else
            "once_per_npc" if cooldown == -1 else {"localCooldown": cooldown}
        )
        params["updatesPerTick"] = params.pop("extraUpdates") + 1
    elif fn in {"apply_status_on_event", "heal_owner_on_event", "damage_area_on_event", "spawn_entity_on_event"}:
        assert params.get("event") in {"on_hit", "on_expire"}
        assert "when" not in params
        params["when"] = params.pop("event")
        if fn == "damage_area_on_event":
            assert params["radiusPx"] == 112
            params["radiusTiles"] = params.pop("radiusPx") / 16

from __future__ import annotations

"""Debug routes for the runtime-entity/event VFX contract.

Legacy recipe selectors and attack-pattern matrices were removed with the weapon
IR. The remaining endpoints inspect or regenerate only exact entity/event slots.
"""

import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from infini_local.core.runtime_authoring import RUNTIME_PROGRAM_API_VERSION, RUNTIME_WIRE_SCHEMA, runtime_event_inventory
from infini_local.core.vfx_manifest import VFX_MANIFEST_SCHEMA, attach_hybrid_vfx_manifest, validate_vfx_director_output, vfx_director_surface


def _sample_data() -> dict[str, Any]:
    return {
        "schemaVersion": 5,
        "runtimeApiVersion": RUNTIME_PROGRAM_API_VERSION,
        "id": "debug_vfx_runtime",
        "name": "Debug Runtime VFX",
        "sourceMode": "generated",
        "runtimeProgram": {
            "apiVersion": RUNTIME_PROGRAM_API_VERSION,
            "schema": RUNTIME_WIRE_SCHEMA,
            "itemEntityId": "item",
            "limits": {"maxEntityCount": 12, "maxChildDepth": 4, "maxEventSpawnsPerActivation": 32},
            "itemUse": {"configured": True, "useStyle": "shoot", "hideUseGraphic": True, "disableMeleeHitbox": True, "channel": False, "holdoutOffsetX": 0, "holdoutOffsetY": 0, "handPose": "one_handed", "releaseTiming": "immediate"},
            "itemContact": {"enabled": False, "hitboxScale": 1.0, "contactForgivenessPx": 0},
            "bindings": [{"id": "primary", "input": "primary_use", "action": "spawn_entity", "target": "orb"}],
            "entities": [
                {"id": "item", "kind": "item_body", "visualRole": "inventory_item", "events": [], "visual": {"role": "inventory_item", "assetMode": "baked_sprite", "spriteStatus": "generated", "spritePath": "debug.png"}},
                {"id": "orb", "kind": "free_projectile", "visualRole": "projectile", "spawn": {"enabled": True, "speedPxPerTick": 8.0, "count": 1, "spreadRadians": 0.0, "offsetPx": 0, "aim": "cursor", "placement": "item_use_origin", "overTarget": {"heightTiles": 0.0, "delayTicks": 0}}, "damage": {"enabled": True, "damageClass": "magic", "damage": 10, "knockback": 1.0, "ownerHitCheck": False}, "lifetimeTicks": 90, "hitbox": {"widthPx": 12, "heightPx": 12, "drawScale": 1.0, "hitboxScale": 1.0}, "collision": {"tileCollide": True, "ignoreWater": False, "bounceCount": 0, "pierce": 1, "extraUpdates": 0, "npcImmunityMode": "owner", "localNpcHitCooldownTicks": -1}, "movement": {"code": 0, "name": "move_straight", "params": {}}, "controller": {"code": 0, "name": "", "params": {}}, "targeting": {"shotEntityId": "", "rangeTiles": 0.0, "intervalTicks": 0}, "events": [], "visual": {"role": "projectile", "assetMode": "runtime_geometry", "spriteStatus": "not_required", "spritePath": ""}},
            ],
        },
    }


@dataclass(frozen=True)
class VfxDebugRoutes:
    app_version: str
    normalize_world_id_from_payload: Callable[[dict[str, Any]], str]
    read_world_recipe_cache: Callable[..., dict[str, Any] | None]
    write_world_recipe_cache: Callable[..., None]
    final_normalize: Callable[[dict[str, Any]], dict[str, Any]]

    def handle_get(self, handler: Any, path: str) -> bool:
        request_path = urlparse(path).path
        if not request_path.startswith("/debug/vfx"):
            return False
        if request_path in {"/debug/vfx_contract", "/debug/vfx_matrix", "/debug/vfx_recipes"}:
            sample = _sample_data()
            handler.json({
                "ok": True,
                "version": self.app_version,
                "schema": VFX_MANIFEST_SCHEMA,
                "directorSurface": vfx_director_surface(sample),
                "sampleRuntimeEvents": runtime_event_inventory(sample),
                "note": "VFX slots bind only to exact runtimeProgram entityId/event pairs.",
            })
            return True
        if request_path == "/debug/vfx_timeline":
            handler.json({"ok": True, "version": self.app_version, "message": "Timeline is runtime event driven; inspect vfxManifest.slots."})
            return True
        return False

    def handle_post(self, handler: Any, path: str, payload: dict[str, Any]) -> bool:
        request_path = urlparse(path).path
        if request_path == "/debug/vfx_select":
            handler.json(self.select_manifest(payload))
            return True
        if request_path == "/debug/vfx_validate":
            data = payload.get("data") if isinstance(payload.get("data"), dict) else _sample_data()
            authored = payload.get("vfx") if isinstance(payload.get("vfx"), dict) else payload
            handler.json(validate_vfx_director_output(authored, data))
            return True
        if request_path == "/debug/vfx_reroll":
            handler.json(self.reroll_cached_manifest(payload))
            return True
        return False

    def select_manifest(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = dict(payload.get("data")) if isinstance(payload.get("data"), dict) else _sample_data()
        meta = data.setdefault("recipeMeta", {})
        if isinstance(meta, dict):
            meta.pop("vfxForcedRecipeId", None)
            meta.pop("vfxRerollSalt", None)
        key = str(payload.get("recipeKey") or data.get("recipeKey") or data.get("id") or "debug_vfx")
        out = attach_hybrid_vfx_manifest(data, key)
        return {"ok": True, "version": self.app_version, "recipeKey": key, "runtimeEvents": runtime_event_inventory(out), "vfxManifest": out.get("vfxManifest")}

    def reroll_cached_manifest(self, payload: dict[str, Any]) -> dict[str, Any]:
        world_id = self.normalize_world_id_from_payload(payload)
        world_name = str(payload.get("worldName") or "").strip()
        recipe_key_value = str(payload.get("recipeKey") or "").strip()
        if not recipe_key_value:
            raise ValueError("missing recipeKey for VFX reroll")
        data = self.read_world_recipe_cache(recipe_key_value, world_id, world_name)
        if not data:
            raise FileNotFoundError(f"recipe not found for worldId={world_id} recipeKey={recipe_key_value}")
        meta = data.setdefault("recipeMeta", {})
        if isinstance(meta, dict):
            meta.pop("vfxForcedRecipeId", None)
            meta.pop("vfxRerollSalt", None)
        data.setdefault("debug", {})["vfxRerollRequestedAt"] = time.time()
        data = attach_hybrid_vfx_manifest(data, recipe_key_value)
        data = self.final_normalize(data)
        self.write_world_recipe_cache(recipe_key_value, world_id, data, world_name=world_name)
        return {"ok": True, "version": self.app_version, "worldId": str(world_id), "recipeKey": recipe_key_value, "vfxManifest": data.get("vfxManifest"), "data": data if bool(payload.get("returnData")) else None}


__all__ = ["VfxDebugRoutes"]

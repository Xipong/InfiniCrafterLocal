from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from infini_local.core.vfx_composition_parent import _vfx_parent_effect_profile
from infini_local.core.vfx_composition_primitives import (
    _vfx_event_group,
    _vfx_infer_channel,
    _vfx_infer_lane,
    _vfx_particle_address_catalog,
    _vfx_resolve_particle_system_id,
    _vfx_slot_score,
)
from infini_local.core.vfx_director_prompt import vfx_director_name_bank
from infini_local.core.vfx_lint_timeline import (
    VFX_MAGNITUDE_CLASSES,
    _vfx_lint_recipe,
    _vfx_timeline_from_manifest,
    vfx_manifest_effect_stack,
)
from infini_local.core.vfx_manifest import (
    _vfx_find_recipe,
    _vfx_manifest_from_recipe,
    attach_hybrid_vfx_manifest,
    compact_vfx_recipe_card,
)
from infini_local.core.vfx_manifest_config import (
    VFX_EMERGENCY_MAX_DRAW_CALLS,
    VFX_EMERGENCY_MAX_PARTICLES_PER_TICK,
    VFX_EMERGENCY_MAX_PARTICLES_TOTAL,
    VFX_MORPH_RECIPES_RAW,
    VFX_RENDER_QUALITY,
    VFX_SLOT_MACROS,
    VFX_SLOT_MACRO_LIBRARY,
)
from infini_local.core.vfx_recipe_library import (
    _vfx_expand_recipe_macros,
    compact_vfx_macro_card,
    get_vfx_recipes,
)


@dataclass(frozen=True)
class VfxDebugRoutes:
    """Debug-only VFX endpoints as one coarse scenario block.

    The HTTP server owns only routing and JSON I/O; this class owns the whole
    VFX debug surface: selector probes, recipe/macro matrices, lint, composer,
    timeline, budget audit and cached-manifest rerolls.
    """

    app_version: str
    normalize_world_id_from_payload: Callable[[dict[str, Any]], str]
    read_world_recipe_cache: Callable[..., dict[str, Any] | None]
    write_world_recipe_cache: Callable[..., None]
    final_normalize: Callable[[dict[str, Any]], dict[str, Any]]

    def handle_get(self, handler: Any, path: str) -> bool:
        request_path = urlparse(path).path
        if not request_path.startswith("/debug/vfx"):
            return False
        if request_path == "/debug/vfx_matrix":
            handler.json(self.recipe_matrix())
            return True
        if request_path == "/debug/vfx_macros":
            handler.json(self.macro_matrix())
            return True
        if request_path == "/debug/vfx_recipe_expanded":
            q = parse_qs(urlparse(path).query)
            handler.json(self.recipe_expanded(q.get("recipeId", [""])[0] or q.get("id", [""])[0] or ""))
            return True
        if request_path == "/debug/vfx_lint":
            q = parse_qs(urlparse(path).query)
            handler.json(self.lint({"recipeId": (q.get("recipeId", [""])[0] or ""), "verbose": (q.get("verbose", ["0"])[0] in {"1", "true", "yes"})}))
            return True
        if request_path == "/debug/vfx_stack":
            q = parse_qs(urlparse(path).query)
            handler.json(self.effect_stack({"pattern": q.get("pattern", ["slash_holdout"])[0], "forceRecipeId": q.get("recipeId", [""])[0], "returnManifest": q.get("returnManifest", ["0"])[0] in {"1", "true", "yes"}}))
            return True
        if request_path == "/debug/vfx_composer":
            q = parse_qs(urlparse(path).query)
            handler.json(self.composer({"pattern": q.get("pattern", ["slash_holdout"])[0], "forceRecipeId": q.get("recipeId", [""])[0], "returnManifest": q.get("returnManifest", ["0"])[0] in {"1", "true", "yes"}}))
            return True
        if request_path == "/debug/vfx_procedural":
            q = parse_qs(urlparse(path).query)
            handler.json(self.procedural({"pattern": q.get("pattern", ["slash_holdout"])[0], "forceRecipeId": q.get("recipeId", [""])[0], "returnManifest": q.get("returnManifest", ["0"])[0] in {"1", "true", "yes"}}))
            return True
        if request_path == "/debug/vfx_timeline":
            q = parse_qs(urlparse(path).query)
            handler.json(self.timeline({"pattern": q.get("pattern", ["slash_holdout"])[0], "forceRecipeId": q.get("recipeId", [""])[0], "maxTicks": int(q.get("maxTicks", ["180"])[0] or "180"), "returnManifest": q.get("returnManifest", ["0"])[0] in {"1", "true", "yes"}}))
            return True
        if request_path == "/debug/vfx_budget_audit":
            q = parse_qs(urlparse(path).query)
            handler.json(self.budget_audit({"pattern": q.get("pattern", [""])[0], "verbose": q.get("verbose", ["0"])[0] in {"1", "true", "yes"}}))
            return True
        if request_path in {"/debug/vfx_quality", "/debug/vfx_magnitude"}:
            handler.json(self.quality_presets())
            return True
        if request_path == "/debug/vfx_parent_effects":
            handler.json(self.parent_effects({}))
            return True
        if request_path == "/debug/vfx_particle_addresses":
            q = parse_qs(urlparse(path).query)
            handler.json(self.particle_addresses({
                "particleSystemId": q.get("particleSystemId", [""])[0],
                "rendererKind": q.get("renderer", [""])[0],
                "event": q.get("event", [""])[0],
                "channel": q.get("channel", [""])[0],
                "blend": q.get("blend", [""])[0],
                "emissionMode": q.get("emissionMode", [""])[0],
            }))
            return True
        if request_path == "/debug/vfx_name_bank":
            handler.json({"ok": True, "version": self.app_version, "bank": vfx_director_name_bank()})
            return True
        if request_path == "/debug/vfx_recipes":
            q = parse_qs(urlparse(path).query)
            pattern = (q.get("pattern", [""])[0] or "").strip()
            cards = [compact_vfx_recipe_card(r) for r in get_vfx_recipes()]
            if pattern:
                cards = [c for c in cards if pattern in set(c.get("compatiblePatterns") or []) or "basic" in set(c.get("compatiblePatterns") or [])]
            handler.json({"ok": True, "version": self.app_version, "count": len(cards), "recipes": cards})
            return True
        return False

    def handle_post(self, handler: Any, path: str, payload: dict[str, Any]) -> bool:
        request_path = urlparse(path).path
        if not request_path.startswith("/debug/vfx"):
            return False
        if request_path == "/debug/vfx_select":
            handler.json(self.select_manifest(payload))
            return True
        if request_path == "/debug/vfx_reroll":
            handler.json(self.reroll_cached_manifest(payload))
            return True
        if request_path == "/debug/vfx_probe_matrix":
            handler.json(self.probe_matrix(payload))
            return True
        if request_path == "/debug/vfx_bake_preview":
            handler.json(self.bake_preview(payload))
            return True
        if request_path == "/debug/vfx_lint":
            handler.json(self.lint(payload))
            return True
        if request_path == "/debug/vfx_stack":
            handler.json(self.effect_stack(payload))
            return True
        if request_path == "/debug/vfx_composer":
            handler.json(self.composer(payload))
            return True
        if request_path == "/debug/vfx_procedural":
            handler.json(self.procedural(payload))
            return True
        if request_path == "/debug/vfx_timeline":
            handler.json(self.timeline(payload))
            return True
        if request_path == "/debug/vfx_budget_audit":
            handler.json(self.budget_audit(payload))
            return True
        if request_path == "/debug/vfx_parent_effects":
            handler.json(self.parent_effects(payload))
            return True
        if request_path == "/debug/vfx_particle_addresses":
            handler.json(self.particle_addresses(payload))
            return True
        return False

    def select_manifest(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = payload.get("data") if isinstance(payload.get("data"), dict) else dict(payload.get("item") or {})
        if not data:
            data = {
                "id": "debug_vfx",
                "name": payload.get("name", "Debug VFX Item"),
                "tooltip": payload.get("tooltip", "debug selector item"),
                "attack": {
                    "enabled": True,
                    "pattern": payload.get("pattern", "thrown_simple"),
                    "projectileSpritePrompt": payload.get("projectile", "small glowing projectile"),
                    "impactSpritePrompt": payload.get("impact", "small impact flash"),
                    "childSpritePrompt": payload.get("child", "tiny spark mote"),
                    "fieldSpritePrompt": payload.get("field", ""),
                    "vfxIntent": payload.get("vfxIntent", ""),
                },
                "visual": {},
                "visualKit": {"vfxIntent": payload.get("vfxIntent", "")},
                "debug": {},
            }
        key = str(payload.get("recipeKey") or data.get("recipeMeta", {}).get("recipeKey") or data.get("id") or "debug_vfx")
        salt = str(payload.get("rerollSalt") or payload.get("salt") or "")
        out = attach_hybrid_vfx_manifest(dict(data), key, salt, payload.get("itemA") if isinstance(payload.get("itemA"), dict) else None, payload.get("itemB") if isinstance(payload.get("itemB"), dict) else None)
        return {
            "ok": True,
            "version": self.app_version,
            "recipeKey": key,
            "rerollSalt": salt,
            "vfxManifest": out.get("vfxManifest"),
            "attackVfxManifestJson": (out.get("attack") or {}).get("vfxManifestJson", ""),
            "debug": (out.get("debug") or {}).get("vfxManifest", ""),
        }

    def reroll_cached_manifest(self, payload: dict[str, Any]) -> dict[str, Any]:
        world_id = self.normalize_world_id_from_payload(payload)
        world_name = str(payload.get("worldName") or "").strip()
        recipe_key_value = str(payload.get("recipeKey") or "").strip()
        if not recipe_key_value:
            raise ValueError("missing recipeKey for VFX reroll")
        data = self.read_world_recipe_cache(recipe_key_value, world_id, world_name)
        if not data:
            raise FileNotFoundError(f"recipe not found for worldId={world_id} recipeKey={recipe_key_value}")
        salt = str(payload.get("rerollSalt") or payload.get("salt") or int(time.time() * 1000))
        meta = data.setdefault("recipeMeta", {})
        meta["vfxRerollSalt"] = salt
        meta.pop("vfxForcedRecipeId", None)
        data.setdefault("debug", {})["vfxRerollRequestedAt"] = time.time()
        data = attach_hybrid_vfx_manifest(data, recipe_key_value, salt)
        data = self.final_normalize(data)
        self.write_world_recipe_cache(recipe_key_value, world_id, data, world_name=world_name)
        return {
            "ok": True,
            "version": self.app_version,
            "worldId": str(world_id),
            "recipeKey": recipe_key_value,
            "rerollSalt": salt,
            "vfxManifest": data.get("vfxManifest"),
            "debug": (data.get("debug") or {}).get("vfxManifest", ""),
            "data": data if bool(payload.get("returnData")) else None,
        }

    def recipe_matrix(self) -> dict[str, Any]:
        by_pattern: dict[str, dict[str, Any]] = {}
        renderers: dict[str, int] = {}
        for recipe in get_vfx_recipes():
            rid = str(recipe.get("id") or "")
            patterns = [str(x) for x in (recipe.get("compatiblePatterns") or [])]
            for p in patterns or ["(none)"]:
                bucket = by_pattern.setdefault(p, {"count": 0, "recipes": []})
                bucket["count"] += 1
                bucket["recipes"].append(rid)
            for slot in recipe.get("slots") or []:
                if isinstance(slot, dict):
                    r = str(slot.get("rendererKind") or "")
                    if r:
                        renderers[r] = renderers.get(r, 0) + 1
        return {
            "ok": True,
            "version": self.app_version,
            "recipeCount": len(get_vfx_recipes()),
            "rawRecipeCount": len(VFX_MORPH_RECIPES_RAW),
            "macroCount": len(VFX_SLOT_MACROS),
            "byPattern": by_pattern,
            "renderers": dict(sorted(renderers.items(), key=lambda kv: (-kv[1], kv[0]))),
        }

    def macro_matrix(self) -> dict[str, Any]:
        usage: dict[str, int] = {k: 0 for k in VFX_SLOT_MACROS.keys()}
        missing: dict[str, int] = {}
        for recipe in VFX_MORPH_RECIPES_RAW:
            refs: list[Any] = []
            refs.extend(recipe.get("useMacros") or [])
            refs.extend([s for s in (recipe.get("slots") or []) if isinstance(s, dict) and s.get("macro")])
            for ref in refs:
                mid = str((ref.get("macro") if isinstance(ref, dict) else ref) or "").strip()
                if not mid:
                    continue
                if mid in usage:
                    usage[mid] += 1
                else:
                    missing[mid] = missing.get(mid, 0) + 1
        cards = [compact_vfx_macro_card(k, v) | {"usedByRecipes": usage.get(k, 0)} for k, v in sorted(VFX_SLOT_MACROS.items())]
        return {
            "ok": True,
            "version": self.app_version,
            "schema": VFX_SLOT_MACRO_LIBRARY.get("schema", "") if isinstance(VFX_SLOT_MACRO_LIBRARY, dict) else "",
            "macroCount": len(VFX_SLOT_MACROS),
            "rawRecipeCount": len(VFX_MORPH_RECIPES_RAW),
            "expandedRecipeCount": len(get_vfx_recipes()),
            "missingMacroRefs": missing,
            "macros": cards,
        }

    def recipe_expanded(self, recipe_id: str) -> dict[str, Any]:
        recipe_id = str(recipe_id or "").strip()
        if not recipe_id:
            return {"ok": False, "version": self.app_version, "error": "missing recipeId"}
        raw = None
        for recipe in VFX_MORPH_RECIPES_RAW:
            if str(recipe.get("id") or "") == recipe_id:
                raw = recipe
                break
        if raw is None:
            return {"ok": False, "version": self.app_version, "error": f"recipe not found: {recipe_id}"}
        expanded = _vfx_expand_recipe_macros(raw)
        return {
            "ok": True,
            "version": self.app_version,
            "recipeId": recipe_id,
            "raw": raw,
            "expanded": expanded,
            "card": compact_vfx_recipe_card(expanded),
            "lint": _vfx_lint_recipe(expanded),
        }

    def probe_matrix(self, payload: dict[str, Any]) -> dict[str, Any]:
        patterns = payload.get("patterns") or ["thrown_simple", "slash_holdout", "beam_slash", "laser_beam", "field_trap", "spawner_on_hit", "orbiting_projectile", "impact_burst"]
        intents = payload.get("intents") or [
            "small physical dart with clean hit flash",
            "large bright burst with drifting motes",
            "slow smoky residue and field pulse",
            "snappy star sparks and sharp ring",
            "goo drip splat with bubbles",
        ]
        out = []
        for pattern in patterns:
            for idx, intent in enumerate(intents):
                result = self.select_manifest({
                    "pattern": str(pattern),
                    "vfxIntent": str(intent),
                    "projectile": f"debug projectile {intent}",
                    "impact": f"debug impact {intent}",
                    "child": "debug mote spark",
                    "recipeKey": f"probe:{pattern}:{idx}",
                })
                m = result.get("vfxManifest") or {}
                out.append({
                    "pattern": pattern,
                    "intent": intent,
                    "recipeId": m.get("recipeId"),
                    "confidence": m.get("confidence"),
                    "slotRenderers": [s.get("rendererKind") for s in (m.get("slots") or []) if isinstance(s, dict)],
                    "top": ((m.get("debug") or {}).get("topCandidates") or [])[:3],
                })
        return {"ok": True, "version": self.app_version, "count": len(out), "results": out}

    def particle_addresses(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        sample_renderer = str(payload.get("rendererKind") or "")
        sample_event = str(payload.get("event") or "")
        sample_channel = str(payload.get("channel") or "")
        sample_blend = str(payload.get("blend") or "")
        sample_emission = str(payload.get("emissionMode") or "")
        requested = payload.get("particleSystemId") or payload.get("particleSystem") or payload.get("particleAddress")
        return {
            "ok": True,
            "version": self.app_version,
            "catalog": _vfx_particle_address_catalog(),
            "sample": {
                "requested": requested,
                "rendererKind": sample_renderer,
                "event": sample_event,
                "channel": sample_channel,
                "blend": sample_blend,
                "emissionMode": sample_emission,
                "resolved": _vfx_resolve_particle_system_id({"particleSystemId": requested}, sample_renderer, sample_event, sample_channel, sample_blend, sample_emission),
            },
        }

    def bake_preview(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = self.select_manifest(payload)
        manifest = result.get("vfxManifest") or {}
        rows = []
        for idx, slot in enumerate(manifest.get("slots") or []):
            if not isinstance(slot, dict):
                continue
            cmds = slot.get("bakedCommands") if isinstance(slot.get("bakedCommands"), list) else []
            rows.append({
                "index": idx,
                "event": slot.get("event"),
                "stage": slot.get("stage"),
                "backend": slot.get("backend"),
                "rendererKind": slot.get("rendererKind"),
                "commandCount": len(cmds),
                "ticks": sorted({int(c.get("tick", 0)) for c in cmds if isinstance(c, dict)})[:64],
                "firstCommands": cmds[:5],
            })
        return {
            "ok": True,
            "version": self.app_version,
            "recipeId": manifest.get("recipeId"),
            "schema": manifest.get("schema"),
            "playbackMode": manifest.get("playbackMode"),
            "slotCount": len(manifest.get("slots") or []),
            "bakedCommandTotal": sum(r["commandCount"] for r in rows),
            "slots": rows,
            "manifest": manifest if bool(payload.get("returnManifest")) else None,
        }

    def timeline(self, payload: dict[str, Any]) -> dict[str, Any]:
        manifest = payload.get("manifest") if isinstance(payload.get("manifest"), dict) else None
        if manifest is None:
            result = self.select_manifest(payload)
            manifest = result.get("vfxManifest") or {}
        timeline = _vfx_timeline_from_manifest(manifest, int(payload.get("maxTicks") or 180))
        return {
            "ok": True,
            "version": self.app_version,
            "timeline": timeline,
            "stack": vfx_manifest_effect_stack(manifest),
            "manifest": manifest if bool(payload.get("returnManifest")) else None,
        }

    def budget_audit(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        pattern = str(payload.get("pattern") or "").strip()
        rows: list[dict[str, Any]] = []
        for recipe in get_vfx_recipes():
            if pattern and pattern not in set(recipe.get("compatiblePatterns") or []) and "basic" not in set(recipe.get("compatiblePatterns") or []):
                continue
            data = {
                "id": f"audit_{recipe.get('id')}",
                "attack": {"enabled": True, "attackPattern": (pattern or (recipe.get("compatiblePatterns") or ["thrown_simple"])[0]), "projectileSpritePath": "debug_projectile.png", "impactSpritePath": "debug_impact.png", "childSpritePath": "debug_child.png", "fieldSpritePath": "debug_field.png"},
                "visual": {"vfxIntent": "budget audit"},
                "debug": {},
            }
            manifest = _vfx_manifest_from_recipe(data, recipe, f"audit:{recipe.get('id')}")
            stack = vfx_manifest_effect_stack(manifest)
            baked = sum(len((s.get("bakedCommands") if isinstance(s, dict) else []) or []) for s in manifest.get("slots") or [])
            budget = manifest.get("budget") or {}
            rows.append({
                "recipeId": recipe.get("id"),
                "patterns": recipe.get("compatiblePatterns") or [],
                "slotCount": len(manifest.get("slots") or []),
                "playbackMode": manifest.get("playbackMode"),
                "renderQuality": budget.get("renderQuality") or budget.get("quality"),
                "effectMagnitude": budget.get("effectMagnitude"),
                "visualBudgetClass": budget.get("visualBudgetClass"),
                "maxParticlesPerTick": budget.get("maxParticlesPerTick"),
                "maxParticlesTotal": budget.get("maxParticlesTotal"),
                "estimatedParticles": stack.get("estimatedParticles"),
                "estimatedDrawCalls": stack.get("estimatedDrawCalls"),
                "bakedCommands": baked,
                "heavy": (stack.get("estimatedParticles", 0) or 0) > (budget.get("maxParticlesTotal", 0) or 0) * 0.75,
                "renderers": [s.get("rendererKind") for s in (manifest.get("slots") or []) if isinstance(s, dict)],
            })
        rows.sort(key=lambda x: (x.get("estimatedParticles") or 0, x.get("bakedCommands") or 0), reverse=True)
        return {
            "ok": True,
            "version": self.app_version,
            "schema": "infini.vfx.budget_audit.v0",
            "recipeCount": len(rows),
            "renderQuality": VFX_RENDER_QUALITY,
            "heavyCount": sum(1 for r in rows if r.get("heavy")),
            "topHeavy": rows[:20],
            "rows": rows if bool(payload.get("verbose")) else rows[:80],
        }

    def effect_stack(self, payload: dict[str, Any]) -> dict[str, Any]:
        manifest = payload.get("manifest") if isinstance(payload.get("manifest"), dict) else None
        if manifest is None:
            result = self.select_manifest(payload)
            manifest = result.get("vfxManifest") or {}
        stack = vfx_manifest_effect_stack(manifest)
        return {
            "ok": True,
            "version": self.app_version,
            "stack": stack,
            "manifest": manifest if bool(payload.get("returnManifest")) else None,
        }

    def procedural(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = self.select_manifest({**payload, "returnData": True, "returnManifest": True})
        manifest = result.get("vfxManifest") or {}
        debug = manifest.get("debug") if isinstance(manifest.get("debug"), dict) else {}
        return {
            "ok": True,
            "version": self.app_version,
            "schema": manifest.get("schema"),
            "recipeId": manifest.get("recipeId"),
            "visualBudgetClass": manifest.get("visualBudgetClass"),
            "effectMagnitude": manifest.get("effectMagnitude"),
            "composition": debug.get("composition") or {},
            "slots": [
                {
                    "event": s.get("event"), "rendererKind": s.get("rendererKind"), "channel": s.get("channel"), "lane": s.get("lane"),
                    "source": s.get("source"), "importance": s.get("importance"), "signatureWeight": s.get("signatureWeight"),
                    "visualCost": s.get("visualCost"), "score": round(_vfx_slot_score(s), 3),
                }
                for s in (manifest.get("slots") or []) if isinstance(s, dict)
            ],
            "manifest": manifest if payload.get("returnManifest") else None,
        }

    def composer(self, payload: dict[str, Any]) -> dict[str, Any]:
        manifest = payload.get("manifest") if isinstance(payload.get("manifest"), dict) else None
        if manifest is None:
            result = self.select_manifest(payload)
            manifest = result.get("vfxManifest") or {}
        slots = manifest.get("slots") if isinstance(manifest.get("slots"), list) else []
        groups: dict[str, list[dict[str, Any]]] = {}
        for slot in slots:
            if not isinstance(slot, dict):
                continue
            group = _vfx_event_group(slot.get("event"))
            channel = str(slot.get("channel") or _vfx_infer_channel(slot.get("rendererKind"), slot.get("event")))
            lane = str(slot.get("lane") or _vfx_infer_lane(slot))
            key = f"{group}:{channel}:{lane}"
            groups.setdefault(key, []).append({
                "rendererKind": slot.get("rendererKind"),
                "event": slot.get("event"),
                "stage": slot.get("stage"),
                "lane": lane,
                "importance": slot.get("importance"),
                "signatureWeight": slot.get("signatureWeight"),
                "visualCost": slot.get("visualCost"),
                "score": round(_vfx_slot_score(slot), 3),
                "emissionMode": slot.get("emissionMode"),
                "fadeIn": slot.get("fadeIn"),
                "fadeOut": slot.get("fadeOut"),
            })
        return {
            "ok": True,
            "version": self.app_version,
            "schema": manifest.get("schema"),
            "recipeId": manifest.get("recipeId"),
            "motif": manifest.get("motif"),
            "slotCount": len(slots),
            "groups": {k: sorted(v, key=lambda x: x.get("score", 0), reverse=True) for k, v in sorted(groups.items())},
            "manifest": manifest if payload.get("returnManifest") else None,
        }

    def parent_effects(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = dict(payload.get("data") or {}) if isinstance(payload.get("data"), dict) else dict(payload)
        a = payload.get("itemA") if isinstance(payload.get("itemA"), dict) else None
        b = payload.get("itemB") if isinstance(payload.get("itemB"), dict) else None
        profile = _vfx_parent_effect_profile(data, a, b)
        return {"ok": True, "version": self.app_version, "profile": {k: v for k, v in profile.items() if k != "_rawParentSlots"}}

    def quality_presets(self) -> dict[str, Any]:
        return {
            "ok": True,
            "version": self.app_version,
            "schema": "infini.vfx.magnitude_classes.v0",
            "renderQuality": VFX_RENDER_QUALITY,
            "magnitudeClasses": VFX_MAGNITUDE_CLASSES,
            "emergencyCaps": {
                "maxParticlesPerTick": VFX_EMERGENCY_MAX_PARTICLES_PER_TICK,
                "maxParticlesTotal": VFX_EMERGENCY_MAX_PARTICLES_TOTAL,
                "maxDrawCalls": VFX_EMERGENCY_MAX_DRAW_CALLS,
            },
            "note": "v0.3.26: render quality is always Full. These classes describe item-driven effect magnitude; caps are only emergency throttles.",
        }

    def lint(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        recipe_id = str(payload.get("recipeId") or payload.get("id") or "").strip()
        manifest = payload.get("manifest") if isinstance(payload.get("manifest"), dict) else None
        reports: list[dict[str, Any]] = []
        if manifest:
            pseudo = {"id": str(manifest.get("recipeId") or "manifest"), "compatiblePatterns": [((manifest.get("debug") or {}).get("pattern") or "unknown")], "slots": manifest.get("slots") or []}
            reports.append(_vfx_lint_recipe(pseudo))
        elif recipe_id:
            recipe = _vfx_find_recipe(recipe_id)
            if not recipe:
                return {"ok": False, "version": self.app_version, "error": f"recipe not found: {recipe_id}"}
            reports.append(_vfx_lint_recipe(recipe))
        else:
            for recipe in get_vfx_recipes():
                reports.append(_vfx_lint_recipe(recipe))
        error_count = sum(len(r.get("errors") or []) for r in reports)
        warning_count = sum(len(r.get("warnings") or []) for r in reports)
        worst = [r for r in reports if (r.get("errors") or r.get("warnings"))]
        return {
            "ok": error_count == 0,
            "version": self.app_version,
            "recipeCount": len(reports),
            "errorCount": error_count,
            "warningCount": warning_count,
            "reports": reports if bool(payload.get("verbose")) or recipe_id or manifest else worst[:80],
        }

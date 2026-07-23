from __future__ import annotations

from typing import Any


from infini_local.core.runtime_overhead_barrage_policy import apply_overhead_barrage_contract
from infini_local.core.runtime_charge_release_policy import apply_charge_release_contract
from infini_local.core.runtime_sentry_policy import apply_sentry_contract, reject_recursive_sentry_onhit
from infini_local.core.runtime_authoring.common import _clamp, _enum, _intish, _norm_name, _num
from infini_local.core.runtime_authoring.normalize import normalize_runtime_plan_inplace, runtime_plan
from infini_local.core.runtime_authoring.result_identity import effective_runtime_result_kind
from infini_local.core.runtime_executor_vocabulary import EFFECTS, MOVEMENTS, ONHITS
from infini_local.core.runtime_family_policy import (
    CANONICAL_RUNTIME_FAMILIES as RUNTIME_FAMILIES,
    runtime_family_accepts_delivery,
)
from infini_local.core.runtime_color_policy import normalize_runtime_color
from infini_local.core.sound_catalog import (
    SOUND_CATALOG_SOURCE,
    normalize_sound_catalog_id,
)
from infini_local.core.vfx_composition_primitives import (
    VFX_CUE_CHANNELS,
    VFX_CUE_EVENTS,
    VFX_CUE_RENDERERS,
)
from infini_local.core.runtime_authoring.schema import NUMERIC_LIMITS, _runtime_family_affordances
from infini_local.core.runtime_authoring.vocabulary import DELIVERIES
from infini_local.core.runtime_authoring.equipment import apply_accessory_calls, apply_armor_calls
from infini_local.core.runtime_authoring.secondary import (
    apply_primary_onhit_child_gates,
    apply_secondary_projectile_calls,
)
from infini_local.core.runtime_authoring.semantics import _truthy
from infini_local.core.runtime_authoring.structural import _first_non_empty, _merged_params, _select_root_executor_call, all_calls


TERRARIA_TILE_SIZE_PX = 16


def project_aoe_radius_tiles_to_damage_pixels(value: Any) -> int:
    """Compile the authored tile radius into the exact AttackSpec pixel unit."""
    tiles = float(_num(value, 0) or 0)
    return max(0, min(160, int(tiles * TERRARIA_TILE_SIZE_PX)))


def project_authored_pierce_to_runtime_hit_budget(value: Any) -> int:
    """Compile authored pierce sentinels to Terraria projectile.penetrate truth."""
    pierce = int(_num(value, 1) or 0)
    return -1 if pierce == -1 else max(1, pierce)


def compile_runtime_plan_to_genome_patch(data: dict[str, Any]) -> dict[str, Any]:
    normalize_runtime_plan_inplace(data)
    rp = runtime_plan(data)
    if not rp:
        return {}
    shoots = all_calls(rp, "shoot_projectile")
    hits = all_calls(rp, "apply_on_hit_effect")
    particle_calls = [
        call for call in all_calls(rp, "spawn_contact_particles")
        if (_num(call.get("amount"), 0) or 0) > 0
    ]
    secondary_calls = all_calls(rp, "spawn_secondary_projectiles")
    trail_calls = all_calls(rp, "leave_trail_or_field")
    use_effect_calls = all_calls(rp, "apply_player_effect_on_use")
    tool_calls = all_calls(rp, "tool_capability")
    placeable_calls = all_calls(rp, "placeable_behavior")
    light_calls = all_calls(rp, "emit_light")
    vfx_cue_calls = all_calls(rp, "visual_effect_cue")
    mobility_calls = all_calls(rp, "mobility_effect")
    alt_use_calls = all_calls(rp, "set_alt_use_mode")
    hold_effect_calls = all_calls(rp, "hold_item_effect")

    use_affordance_calls = all_calls(rp, "use_affordance")
    consumption_calls = all_calls(rp, "consumption_behavior")
    ammo_behavior_calls = all_calls(rp, "ammo_behavior")
    use_condition_calls = all_calls(rp, "use_condition")
    accessory_calls = all_calls(rp, "accessory_effect")
    armor_calls = all_calls(rp, "armor_effect")

    itemstats_calls = all_calls(rp, "set_item_stats")
    shoot, rejected_roots = _select_root_executor_call(shoots) if shoots else ({}, [])
    hit = _merged_params(hits) if hits else {}
    itemstats = _merged_params(itemstats_calls) if itemstats_calls else {}
    patch: dict[str, Any] = {}
    authored_result_kind = effective_runtime_result_kind(data)
    if authored_result_kind in {"weapon", "ammo", "consumable_weapon", "tool", "accessory", "armor", "potion", "material", "furniture", "generic"}:
        patch["kind"] = authored_result_kind
    norm = rp.get("_normalization") if isinstance(rp.get("_normalization"), dict) else {}
    if isinstance(norm.get("rejectedEngineCalls"), list) and norm.get("rejectedEngineCalls"):
        patch["rejectedEngineCalls"] = norm.get("rejectedEngineCalls")[:16]

    # One root executor owns the item-use lifecycle. A preserved item hitbox is a
    # bounded damage lane of that same use, not a second controller.
    if rejected_roots:
        patch["rejectedRootExecutorCalls"] = rejected_roots[:8]

    raw_delivery = _norm_name(shoot.get("delivery"))
    delivery = _enum(shoot.get("delivery"), DELIVERIES, None)
    movement = _enum(shoot.get("movement"), MOVEMENTS, None)
    if raw_delivery and raw_delivery != delivery:
        patch["deliveryAlias"] = raw_delivery
    if delivery: patch["delivery"] = delivery
    if movement: patch["movement"] = movement
    if shoot.get("weaponFamily") not in (None, ""):
        patch["weaponFamily"] = _norm_name(shoot.get("weaponFamily"))[:40]
    if shoot.get("projectileFamily") not in (None, ""):
        patch["projectileFamily"] = _norm_name(shoot.get("projectileFamily"))[:40]
    if shoot.get("ammoFor") not in (None, ""):
        patch["ammoFor"] = _norm_name(shoot.get("ammoFor"))[:24]
    explicit_runtime_family = _enum(shoot.get("runtimeFamily"), RUNTIME_FAMILIES, None)
    runtime_family = explicit_runtime_family or "none"
    if shoots and runtime_family == "none":
        patch["runtimeContractError"] = "root_executor_requires_runtimeFamily"
    elif shoots and not runtime_family_accepts_delivery(runtime_family, delivery):
        patch["runtimeContractError"] = f"runtimeFamily={runtime_family} rejects delivery={delivery or 'missing'}"
    else:
        patch["runtimeFamily"] = runtime_family
        patch.update(_runtime_family_affordances(runtime_family, patch.get("weaponFamily") or shoot.get("weaponFamily"), patch.get("delivery") or shoot.get("delivery")))

    # Aggregate pure VFX calls. This is still not gameplay child logic.
    particle_effects: list[str] = []
    particle_amount = 0.0
    particle_scale = 0.0
    particle_duration = 0.0
    particle_materials: list[str] = []
    for pc in particle_calls:
        eff = _enum(pc.get("effect"), EFFECTS, None)
        if eff and eff != "none":
            particle_effects.append(eff)
        particle_amount += _num(pc.get("amount"), 0) or 0
        particle_scale = max(particle_scale, _num(pc.get("scale"), 0) or 0)
        particle_duration = max(particle_duration, _clamp(pc.get("durationTicks"), "durationTicks", 0) or 0)
        material = _norm_name(pc.get("material"))
        if material not in {"", "none"}:
            particle_materials.append(material)
    effect = _enum(_first_non_empty(*particle_effects, shoot.get("effect")), EFFECTS, None)
    if particle_calls and not particle_effects:
        effect = "none"
    if effect:
        patch["effect"] = effect
    if particle_calls:
        patch["burstDustCap"] = int(round(max(0, min(NUMERIC_LIMITS["burstDustCap"][1], particle_amount))))
        # v0.4.13: C# distinguishes effect=none from mundane dust via DustSpawnDenom.
        # effectCode 0 is shared by none/dust; exact material is the only other
        # explicit route that may enable dust for that code.
        if particle_amount <= 0 or (effect in {None, "none"} and not particle_materials):
            patch["dustSpawnDenom"] = 0
            patch["burstDustCap"] = 0
        else:
            # Higher authored amount = more frequent, but still bounded; no WhiteTorch fallback in runtime.
            patch["dustSpawnDenom"] = int(max(2, min(12, round(10 - min(8, particle_amount / 5.0)))))
        if particle_scale:
            patch["vfxParticleScale"] = max(0.0, min(2.0, round(particle_scale, 3)))
        if particle_duration:
            patch["vfxParticleDurationTicks"] = int(round(min(80, particle_duration)))
        if particle_materials:
            # Finite visual material lineage; C# resolves it only to a dust family.
            patch["vfxMaterial"] = particle_materials[0]

    # Trails/fields are visual-only in this runtime. Do not let field prose become gameplay.
    rejected_trails: list[dict[str, Any]] = []
    if trail_calls:
        for t in trail_calls:
            if t.get("visualOnly") not in (None, "", True) and not _truthy(t.get("visualOnly")):
                rejected_trails.append({"index": t.get("_index"), "reason": "visualOnly_false_not_executable"})
        vals = [_clamp(t.get("trailLength"), "trailLength") for t in trail_calls if t.get("trailLength") not in (None, "")]
        vals = [v for v in vals if v is not None]
        if vals:
            patch["trailLength"] = _intish("trailLength", max(vals))
        for field, out_field in [
            ("fieldLifetimeTicks", "vfxFieldLifetimeTicks"),
            ("fieldRadiusTiles", "vfxFieldRadiusTiles"),
            ("tickRate", "vfxFieldTickRate"),
        ]:
            raw_vals = [_clamp(t.get(field), field) for t in trail_calls if t.get(field) not in (None, "")]
            raw_vals = [value for value in raw_vals if value is not None]
            if raw_vals:
                value = max(raw_vals)
                patch[out_field] = _intish(field, value) if field != "fieldRadiusTiles" else round(float(value), 3)
        if rejected_trails:
            patch["rejectedTrailCalls"] = rejected_trails[:8]


    # Executable utility calls: these expand runtime options without routing item identity
    # into rigid presets.  They only write concrete supported fields/provenance.
    extra_buffs: list[dict[str, int]] = []
    for uc in use_effect_calls:
        for field in ["healLife", "healMana"]:
            if uc.get(field) not in (None, ""):
                v = _clamp(uc.get(field), field, 0)
                if v is not None:
                    patch[field] = max(int(patch.get(field) or 0), int(round(v)))
        raw_buffs = uc.get("buffs") if isinstance(uc.get("buffs"), list) else []
        if uc.get("buffType") not in (None, ""):
            raw_buffs = list(raw_buffs) + [{"buffType": uc.get("buffType"), "buffTime": uc.get("buffTime")}]
        for b in raw_buffs:
            if not isinstance(b, dict):
                continue
            bt = _clamp(b.get("buffType"), "buffType", 0)
            tm = _clamp(b.get("buffTime"), "buffTime", 0)
            if bt and bt > 0 and tm and tm > 0:
                extra_buffs.append({"buffCode": int(round(bt)), "buffTime": int(round(tm))})
    if extra_buffs:
        dedup: dict[int, int] = {}
        for b in extra_buffs:
            dedup[int(b["buffCode"])] = max(dedup.get(int(b["buffCode"]), 0), int(b["buffTime"]))
        patch["extraBuffs"] = [{"buffCode": k, "buffTime": max(1, min(21600, v))} for k, v in list(dedup.items())[:4]]
        patch.setdefault("buffCode", patch["extraBuffs"][0]["buffCode"])
        patch.setdefault("buffTime", patch["extraBuffs"][0]["buffTime"])
        patch["useEffectCallCount"] = len(use_effect_calls)

    generated_buff: dict[str, Any] = {}
    for uc in use_effect_calls:
        gb = uc.get("generatedBuff") if isinstance(uc.get("generatedBuff"), dict) else {}
        duration_raw = gb.get("durationTicks") or uc.get("durationTicks") or uc.get("buffTime")
        duration = _num(duration_raw, 0) if duration_raw not in (None, "") else 0
        if duration:
            generated_buff["durationTicks"] = max(int(generated_buff.get("durationTicks") or 0), int(round(max(1, min(21600, duration)))))
        for src, out, lo, hi in [
            ("miningSpeedMultiplier", "miningSpeedMultiplier", 0.25, 4.0),
            ("emitLightStrength", "emitLightStrength", 0.0, 1.5),
            ("oreSenseRadiusTiles", "oreSenseRadiusTiles", 0.0, 60.0),
            ("movementSpeed", "movementSpeed", -0.5, 2.0),
            ("jumpBoost", "jumpBoost", 0.0, 8.0),
            ("manaRegen", "manaRegen", 0.0, 120.0),
            ("lifeRegen", "lifeRegen", 0.0, 120.0),
        ]:
            raw = gb.get(src, uc.get(src))
            if raw in (None, ""):
                continue
            val = _num(raw, None)
            if val is None:
                continue
            val = max(lo, min(hi, val))
            if out in {"oreSenseRadiusTiles", "manaRegen", "lifeRegen"}:
                val = int(round(val))
            generated_buff[out] = max(generated_buff.get(out, val), val) if isinstance(val, (int, float)) and out not in {"movementSpeed"} else val
        color = str(gb.get("lightColorName") or gb.get("color") or uc.get("lightColorName") or "").strip()
        if color:
            normalized_color = normalize_runtime_color(color)
            if normalized_color:
                generated_buff["lightColorName"] = normalized_color
    if generated_buff and int(generated_buff.get("durationTicks") or 0) > 0:
        patch["generatedBuff"] = generated_buff

    if tool_calls:
        merged_tool = _merged_params(tool_calls)
        for field in ["pickPower", "axePower", "hammerPower"]:
            if merged_tool.get(field) not in (None, ""):
                v = _clamp(merged_tool.get(field), field, 0)
                if v is not None:
                    patch[field] = int(round(v))
        if merged_tool.get("miningSpeedScale") not in (None, ""):
            patch["miningSpeedScale"] = max(0.25, min(2.0, _num(merged_tool.get("miningSpeedScale"), 1.0) or 1.0))

    if placeable_calls:
        placeable = _merged_params(placeable_calls)
        for field in ("createTile", "createWall", "placeStyle"):
            if placeable.get(field) not in (None, ""):
                value = _clamp(placeable.get(field), field, -1 if field != "placeStyle" else 0)
                if value is not None:
                    patch[field] = int(round(value))

    if light_calls:
        strengths = [_clamp(c.get("strength"), "lightStrength", 0) for c in light_calls if c.get("strength") not in (None, "")]
        strengths = [s for s in strengths if s is not None]
        if strengths:
            patch["runtimeLightStrength"] = round(max(strengths), 3)
        durations = [_clamp(c.get("durationTicks"), "durationTicks", 0) for c in light_calls if c.get("durationTicks") not in (None, "")]
        durations = [duration for duration in durations if duration is not None]
        if durations:
            patch["runtimeLightDurationTicks"] = int(round(min(240, max(durations))))
        colors = [
            str(c.get("lightColorName") or c.get("color") or "").strip()
            for c in light_calls
            if str(c.get("lightColorName") or c.get("color") or "").strip()
        ]
        if colors:
            normalized_color = normalize_runtime_color(colors[0])
            if normalized_color:
                patch.setdefault("primaryColorName", normalized_color)
                patch.setdefault("runtimeLightColorName", normalized_color)
        if authored_result_kind == "potion" and strengths and durations:
            strength = float(max(strengths))
            duration = int(round(max(durations)))
            if strength > 0 and duration > 0:
                use_buff = dict(patch.get("generatedBuff") or {}) if isinstance(patch.get("generatedBuff"), dict) else {}
                use_buff["durationTicks"] = max(int(use_buff.get("durationTicks") or 0), duration)
                use_buff["emitLightStrength"] = max(float(use_buff.get("emitLightStrength") or 0.0), strength)
                color = str(patch.get("runtimeLightColorName") or "").strip()
                if color:
                    use_buff["lightColorName"] = color
                patch["generatedBuff"] = use_buff
        patch["lightCallCount"] = len(light_calls)

    if vfx_cue_calls:
        allowed_events = VFX_CUE_EVENTS
        allowed_renderers = VFX_CUE_RENDERERS
        allowed_channels = VFX_CUE_CHANNELS
        allowed_lanes = {"primary", "support", "accent", "ornament", "cue"}
        allowed_roles = {"projectile", "impact", "child", "field"}
        allowed_emission = {"wake", "orbit", "residue", "burst", "cone", "ring", "spiral", "point"}
        allowed_particles = {"pl:glow", "pl:shard", "pl:smoke", "pl:spark", "dust"}
        cues: list[dict[str, Any]] = []
        for call in vfx_cue_calls[:8]:
            p = call.get("params") if isinstance(call, dict) and isinstance(call.get("params"), dict) else call if isinstance(call, dict) else {}
            event = str(p.get("event") or "").strip()
            renderer = str(p.get("rendererKind") or "").strip()
            channel = str(p.get("channel") or "").strip()
            lane = str(p.get("lane") or "").strip()
            texture_role = str(p.get("textureRole") or "projectile").strip()
            particle_role = str(p.get("particleRole") or texture_role or "child").strip()
            emission = str(p.get("emissionMode") or "").strip()
            particle_id = str(p.get("particleSystemId") or "").strip()
            cue: dict[str, Any] = {"source": "runtimePlan.visual_effect_cue"}
            if event in allowed_events: cue["event"] = event
            if renderer in allowed_renderers: cue["rendererKind"] = renderer
            if channel in allowed_channels: cue["channel"] = channel
            if lane in allowed_lanes: cue["lane"] = lane
            if texture_role in allowed_roles: cue["textureRole"] = texture_role
            if particle_role in allowed_roles: cue["particleRole"] = particle_role
            if emission in allowed_emission: cue["emissionMode"] = emission
            if particle_id in allowed_particles: cue["particleSystemId"] = particle_id
            for field in ("scale", "density", "duration", "alpha", "spread", "jitter", "startTick", "repeatEvery"):
                if field in p and p.get(field) not in (None, ""):
                    cue[field] = _clamp(p.get(field), field, 0)
                    if field in {"duration", "startTick", "repeatEvery"}:
                        cue[field] = int(round(cue[field]))
            importance = str(p.get("importance") or "").strip()
            if importance in {"core", "secondary", "accent", "luxury"}:
                cue["importance"] = importance
            note = str(p.get("note") or p.get("identity") or "").strip()
            if note:
                cue["note"] = note[:80]
            if any(k in cue for k in ("event", "rendererKind", "channel", "particleSystemId")):
                cues.append(cue)
        if cues:
            patch["vfxCues"] = cues
            patch["vfxCueCount"] = len(cues)

    if mobility_calls:
        accepted_modes = {"recall_home", "blink_to_cursor", "blink_to_projectile_impact"}
        mobility = _merged_params(mobility_calls)
        mode = _norm_name(mobility.get("mode"))
        if mode in accepted_modes:
            patch["mobilityMode"] = mode
            if mobility.get("rangeTiles") not in (None, ""):
                patch["mobilityRangeTiles"] = int(max(0, min(80, _num(mobility.get("rangeTiles"), 0) or 0)))
            if mobility.get("cooldownTicks") not in (None, ""):
                patch["mobilityCooldownTicks"] = int(round(_clamp(mobility.get("cooldownTicks"), "cooldownTicks", 0) or 0))
            patch["mobilitySafeTileOnly"] = bool(mobility.get("safeTileOnly") is not False)

    if alt_use_calls:
        alt = _merged_params(alt_use_calls)
        mode = _norm_name(alt.get("mode"))
        if mode not in {"mobility", "generated_buff", "light", "none"}:
            mode = "none"
        patch["altUseMode"] = mode
        if alt.get("cooldownTicks") not in (None, ""):
            patch["altUseCooldownTicks"] = int(round(_clamp(alt.get("cooldownTicks"), "cooldownTicks", 0) or 0))
        amode = _norm_name(alt.get("mobilityMode") or alt.get("mode"))
        if amode in {"recall_home", "blink_to_cursor"}:
            patch["altMobilityMode"] = amode
            patch["altMobilityRangeTiles"] = int(max(0, min(80, _num(alt.get("rangeTiles"), 0) or 0)))
            patch["altMobilitySafeTileOnly"] = bool(alt.get("safeTileOnly") is not False)
        if isinstance(alt.get("generatedBuff"), dict) and int(_num(alt.get("generatedBuff", {}).get("durationTicks"), 0) or 0) > 0:
            patch["altGeneratedBuff"] = alt.get("generatedBuff")
        elif mode == "light":
            alt_strengths = [_clamp(c.get("strength"), "lightStrength", 0) for c in light_calls if c.get("strength") not in (None, "")]
            alt_strengths = [s for s in alt_strengths if s is not None]
            strength = max(alt_strengths) if alt_strengths else 0
            colors = [str(c.get("lightColorName") or c.get("color") or "").strip() for c in light_calls if str(c.get("lightColorName") or c.get("color") or "").strip()]
            duration = _clamp(alt.get("durationTicks"), "durationTicks") if alt.get("durationTicks") not in (None, "") else None
            if strength > 0 and duration is not None and duration > 0:
                patch["altGeneratedBuff"] = {
                    "durationTicks": int(round(duration)),
                    "emitLightStrength": round(max(0, min(1.5, strength)), 3),
                    "lightColorName": (colors[0] if colors else str(patch.get("primaryColorName") or ""))[:32],
                }

    if hold_effect_calls:
        hold = _merged_params(hold_effect_calls)
        if hold.get("lightStrength") not in (None, ""):
            patch["holdLightStrength"] = round(max(0, min(1.5, _num(hold.get("lightStrength"), 0) or 0)), 3)
        color = str(hold.get("lightColorName") or hold.get("color") or "").strip()
        if color:
            patch["holdLightColorName"] = color[:32]
        if isinstance(hold.get("generatedBuff"), dict) and int(_num(hold.get("generatedBuff", {}).get("durationTicks"), 0) or 0) > 0:
            patch["holdGeneratedBuff"] = hold.get("generatedBuff")


    if use_affordance_calls:
        ua = _merged_params(use_affordance_calls)
        for src, out, lo, hi in [
            ("itemScale", "itemScale", 0.55, 1.55),
            ("holdoutOffsetX", "holdoutOffsetX", -80, 80),
            ("holdoutOffsetY", "holdoutOffsetY", -80, 80),
        ]:
            if ua.get(src) not in (None, ""):
                val = max(lo, min(hi, _num(ua.get(src), 0) or 0))
                patch[out] = int(round(val)) if out.startswith("holdout") else round(val, 3)
        for src, out in [("autoReuse", "autoReuse"), ("useTurn", "useTurn"), ("channelUse", "channelUse")]:
            if src in ua:
                patch[out] = bool(ua.get(src))
        enum_fields = {
            "heldVisibility": {"show_item", "hide_item", "show_projectile", "show_both"},
            "releaseTiming": {"instant", "early", "mid_swing", "on_contact", "on_release"},
            "handPose": {"short_weapon", "two_hand", "overhead", "throwing", "staff", "held_out", "none"},
        }
        for field, allowed in enum_fields.items():
            value = _norm_name(ua.get(field))
            if value in allowed:
                patch[field] = value
        if ua.get("initialOffsetPx") not in (None, ""):
            patch["initialOffsetPx"] = int(round(max(-64, min(64, _num(ua.get("initialOffsetPx"), 0) or 0))))

    if consumption_calls:
        cb = _merged_params(consumption_calls)
        if cb.get("consumeChancePercent") not in (None, ""):
            value = _num(cb.get("consumeChancePercent"), None)
            if value is not None:
                patch["consumeChancePercent"] = int(round(max(0, min(100, value))))

    if ammo_behavior_calls:
        ammo = _merged_params(ammo_behavior_calls)
        ammo_for = _norm_name(ammo.get("ammoFor") or ammo.get("kind"))
        if ammo_for in {"arrow", "arrows", "bullet", "bullets", "empty", "none"}:
            patch["ammoFor"] = "" if ammo_for in {"empty", "none"} else ammo_for
            if ammo_for not in {"empty", "none"}:
                patch.setdefault("kind", "ammo")
                patch.setdefault("consumable", True)

    if use_condition_calls:
        cond = _merged_params(use_condition_calls)
        mode = _norm_name(cond.get("mode"))
        if mode in {"grounded", "not_wet", "life_above", "mana_above"}:
            patch["useConditionMode"] = mode
            if cond.get("minLife") not in (None, ""):
                patch["useConditionMinLife"] = int(round(_clamp(cond.get("minLife"), "minLife", 0) or 0))
            if cond.get("minMana") not in (None, ""):
                patch["useConditionMinMana"] = int(round(_clamp(cond.get("minMana"), "minMana", 0) or 0))

    apply_accessory_calls(patch, accessory_calls)
    apply_armor_calls(patch, armor_calls, itemstats)

    # Primary numeric mapping.
    for src, mapping in [
        (shoot, {"rangeTiles": "rangeTiles", "lifetimeTicks": "lifetimeTicks", "shotCount": "shotCount", "spreadRadians": "spreadRadians", "pierce": "pierce", "extraUpdates": "extraUpdates", "homingStrength": "homingStrength", "beamWidthPx": "beamWidthPx", "beamChargeTicks": "beamChargeTicks", "chargeTicks": "chargeTicks", "chargePowerMultiplier": "chargePowerMultiplier", "sentryAttackIntervalTicks": "sentryAttackIntervalTicks", "sentryTargetRangeTiles": "sentryTargetRangeTiles", "sentryLifetimeTicks": "sentryLifetimeTicks", "secondaryDamageMultiplier": "secondaryDamageMultiplier", "secondaryLifetimeTicks": "secondaryLifetimeTicks", "immunityCooldown": "immunityCooldown", "useTimeTicks": "useTimeTicks", "useAnimationTicks": "useAnimationTicks", "speed": "speed"}),
        (hit, {"aoeRadiusTiles": "aoeRadiusTiles", "chainCount": "chainCount", "count": "splitCount", "pullStrength": "pullStrength", "secondaryDamageMultiplier": "secondaryDamageMultiplier", "secondaryLifetimeTicks": "secondaryLifetimeTicks"}),
        (itemstats, {"useTimeTicks": "useTimeTicks", "useAnimationTicks": "useAnimationTicks", "knockback": "knockback", "manaCost": "manaCost", "craftYield": "craftYield"}),
    ]:
        for k, outk in mapping.items():
            if k in src and src.get(k) not in (None, "") and outk not in patch and outk in NUMERIC_LIMITS:
                v = _clamp(src.get(k), outk)
                if v is not None:
                    patch[outk] = _intish(outk, v)

    pull_strength = float(patch.get("pullStrength") or 0.0)
    pull_mode = _enum(hit.get("pullMode"), {"none", "target_to_owner", "owner_to_target", "target_to_projectile"}, "none") or "none"
    if pull_strength > 0.0 and pull_mode != "none":
        patch["pullMode"] = pull_mode
    else:
        if pull_strength > 0.0:
            patch["pullDemotedReason"] = "pullStrength_requires_explicit_pullMode"
            patch["pullStrength"] = 0.0
        patch["pullMode"] = "none"

    if patch.get("runtimeFamily") == "overhead_barrage" and shoot.get("delayTicks") not in (None, ""):
        value = _clamp(shoot.get("delayTicks"), "delayTicks")
        if value is not None:
            patch["delayTicks"] = _intish("delayTicks", value)

    # Hit behavior: the first authored hit effect is primary. A sentry call may
    # author the non-recursive shot effect directly because deploy_sentry owns its shot contract.
    if patch.get("runtimeFamily") == "sentry":
        reject_recursive_sentry_onhit(shoot.get("onHit"))
    onhit = _enum(hit.get("onHit"), ONHITS, None)
    if not onhit and patch.get("runtimeFamily") == "sentry":
        onhit = _enum(shoot.get("onHit"), ONHITS, None)
    if onhit:
        patch["onHit"] = onhit
    debuff_hint = str(hit.get("debuffHint") or "").strip()
    if debuff_hint:
        patch["debuffHint"] = debuff_hint[:80]
    if hit.get("debuffTime") not in (None, ""):
        value = _num(hit.get("debuffTime"), None)
        if value is not None:
            patch["debuffTime"] = int(max(30, min(600, value)))

    # Primary onHit child budget/demotion is owned by secondary module so maxChild*
    # has a single owner path immediately before secondary projectile calls.
    apply_primary_onhit_child_gates(patch, hit)

    # Real secondary damaging projectiles live in one small owner module.
    # This keeps trigger/lifecycle rules out of the already-large main compiler.
    apply_secondary_projectile_calls(patch, secondary_calls)


    # Do not fill authored primary-action mechanics. Missing delivery/movement/
    # cadence/range/lifetime/speed fields are validation errors and go back to
    # the LLM repair loop instead of becoming code-designed gameplay.
    patch.setdefault("effect", "none" if not particle_calls or int(_num(patch.get("dustSpawnDenom"), 0) or 0) <= 0 else "dust")
    if not particle_calls:
        patch.setdefault("dustSpawnDenom", 0)
        patch.setdefault("burstDustCap", 0)
    patch.setdefault("onHit", "none")
    patch.setdefault("aoeRadiusTiles", 0)
    patch["aoeDamageRadiusPx"] = project_aoe_radius_tiles_to_damage_pixels(patch["aoeRadiusTiles"])
    if "pierce" in patch:
        patch["projectileHitBudget"] = project_authored_pierce_to_runtime_hit_budget(patch["pierce"])
    patch.setdefault("useTimeTicks", int(_clamp(_first_non_empty(itemstats.get("useTimeTicks"), shoot.get("useTimeTicks")), "useTimeTicks", 24) or 24))
    patch.setdefault("useAnimationTicks", int(_clamp(_first_non_empty(itemstats.get("useAnimationTicks"), shoot.get("useAnimationTicks"), patch.get("useTimeTicks")), "useAnimationTicks", patch.get("useTimeTicks", 24)) or patch.get("useTimeTicks", 24)))
    if authored_result_kind in {"armor", "accessory", "ammo"}:
        # These DTO families have no authored use action.  Their final item timing is
        # intentionally fixed at 10/10 downstream; compile the same technical value so
        # provenance cannot disagree with the executable wire.
        patch["useTimeTicks"] = 10
        patch["useAnimationTicks"] = 10
    patch.setdefault("extraUpdates", 0)
    patch.setdefault("homingStrength", 0)
    if trail_calls:
        patch.setdefault("trailLength", int(max([_clamp(t.get("trailLength"), "trailLength", 0) or 0 for t in trail_calls] or [0])))
    else:
        patch.setdefault("trailLength", 4 if particle_calls else 0)

    for field in ["projectileShape", "projectileMotion", "projectileTrail", "projectileImpact", "weaponFamily", "projectileFamily", "ammoKind", "sentryPlacement", "secondaryProjectileShape"]:
        val = shoot.get(field) or rp.get(field)
        if val not in (None, ""):
            patch[field] = str(val)

    # Audio is authored as exact acoustic catalog ids. Unknown or missing ids remain
    # absent so validation can target the same author; the compiler is never a composer.
    if shoot:
        raw_use_sound = shoot.get("soundUseCatalogId")
        raw_impact_sound = shoot.get("soundImpactCatalogId")
        use_sound = normalize_sound_catalog_id(raw_use_sound, impact=False)
        impact_sound = normalize_sound_catalog_id(raw_impact_sound, impact=True)
        rejected_sound_ids: list[dict[str, str]] = []
        if raw_use_sound not in (None, "") and not use_sound:
            rejected_sound_ids.append({"field": "soundUseCatalogId", "value": str(raw_use_sound)[:80], "reason": "unknown_exact_catalog_id"})
        if raw_impact_sound not in (None, "") and not impact_sound:
            rejected_sound_ids.append({"field": "soundImpactCatalogId", "value": str(raw_impact_sound)[:80], "reason": "unknown_exact_catalog_id"})
        if use_sound:
            patch["soundUseCatalogId"] = use_sound
        if impact_sound:
            patch["soundImpactCatalogId"] = impact_sound
        if use_sound or impact_sound:
            patch["soundCatalogSource"] = SOUND_CATALOG_SOURCE
        explicit_color = normalize_runtime_color(patch.get("primaryColorName"))
        if explicit_color:
            patch["primaryColorName"] = explicit_color
        if rejected_sound_ids:
            patch["rejectedSoundCatalogIds"] = rejected_sound_ids
        if shoot.get("soundVolume") not in (None, ""):
            patch["soundVolume"] = round(float(_clamp(shoot.get("soundVolume"), "soundVolume", 0.85) or 0.85), 3)
        if shoot.get("soundPitch") not in (None, ""):
            patch["soundPitch"] = round(float(_clamp(shoot.get("soundPitch"), "soundPitch", 0.0) or 0.0), 3)
        if shoot.get("soundPitchVariance") not in (None, ""):
            patch["soundPitchVariance"] = round(float(_clamp(shoot.get("soundPitchVariance"), "soundPitchVariance", 0.18) or 0.0), 3)

    patch["runtimePlanAuthored"] = True
    apply_overhead_barrage_contract(patch)
    apply_charge_release_contract(patch)
    apply_sentry_contract(patch)
    return {k: v for k, v in patch.items() if v not in (None, "")}

__all__ = [
    'TERRARIA_TILE_SIZE_PX',
    'project_aoe_radius_tiles_to_damage_pixels',
    'project_authored_pierce_to_runtime_hit_budget',
    'compile_runtime_plan_to_genome_patch',
]

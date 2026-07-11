from __future__ import annotations

from typing import Any

from infini_local.core.runtime_archetypes import compile_runtime_archetype_to_attack_patch
from infini_local.core.runtime_overhead_barrage_policy import apply_overhead_barrage_contract
from infini_local.core.runtime_charge_release_policy import apply_charge_release_contract
from infini_local.core.runtime_sentry_policy import apply_sentry_contract, reject_recursive_sentry_onhit
from infini_local.core.runtime_authoring.common import _clamp, _enum, _intish, _norm_name, _num
from infini_local.core.runtime_authoring.normalize import _compile_state_meter_calls, _compile_triggered_action_calls, normalize_runtime_plan_inplace, runtime_plan
from infini_local.core.runtime_executor_vocabulary import EFFECTS, MOVEMENTS, ONHITS
from infini_local.core.runtime_family_policy import CANONICAL_RUNTIME_FAMILIES as RUNTIME_FAMILIES
from infini_local.core.runtime_color_policy import normalize_runtime_color, runtime_color_for_effect
from infini_local.core.sound_catalog import (
    SOUND_CATALOG_SOURCE,
    default_impact_sound_id,
    default_use_sound_id,
    normalize_sound_catalog_id,
)
from infini_local.core.runtime_authoring.schema import NUMERIC_LIMITS, _runtime_family_affordances
from infini_local.core.runtime_authoring.vocabulary import DELIVERIES
from infini_local.core.runtime_authoring.secondary import apply_secondary_projectile_calls
from infini_local.core.runtime_authoring.semantics import (
    _apply_armor_slot_budget,
    _parent_grounded_onhit,
    _truthy,
    light_repair_runtime_family_from_fields,
)
from infini_local.core.runtime_authoring.structural import _first_non_empty, _merged_params, _recover_rejected_primary_as_swing_secondary, _select_primary_shoot_call, all_calls

def compile_runtime_plan_to_genome_patch(data: dict[str, Any]) -> dict[str, Any]:
    normalize_runtime_plan_inplace(data)
    rp = runtime_plan(data)
    if not rp:
        return {}
    shoots = all_calls(rp, "shoot_projectile")
    hits = all_calls(rp, "apply_on_hit_effect")
    particle_calls = all_calls(rp, "spawn_contact_particles")
    secondary_calls = all_calls(rp, "spawn_secondary_projectiles")
    trail_calls = all_calls(rp, "leave_trail_or_field")
    use_effect_calls = all_calls(rp, "apply_player_effect_on_use")
    tool_calls = all_calls(rp, "tool_capability")
    light_calls = all_calls(rp, "emit_light")
    vfx_cue_calls = all_calls(rp, "visual_effect_cue")
    mobility_calls = all_calls(rp, "mobility_effect")
    alt_use_calls = all_calls(rp, "set_alt_use_mode")
    hold_effect_calls = all_calls(rp, "hold_item_effect")
    extractinator_calls = all_calls(rp, "extractinator_output")
    use_affordance_calls = all_calls(rp, "use_affordance")
    consumption_calls = all_calls(rp, "consumption_behavior")
    ammo_behavior_calls = all_calls(rp, "ammo_behavior")
    use_condition_calls = all_calls(rp, "use_condition")
    accessory_calls = all_calls(rp, "accessory_effect")
    armor_calls = all_calls(rp, "armor_effect")
    state_meter_calls = all_calls(rp, "state_meter")
    triggered_action_calls = all_calls(rp, "triggered_action")
    itemstats_calls = all_calls(rp, "set_item_stats")
    shoot, rejected_primary = _select_primary_shoot_call(shoots) if shoots else ({}, [])
    hit = _merged_params(hits) if hits else {}
    itemstats = _merged_params(itemstats_calls) if itemstats_calls else {}
    patch: dict[str, Any] = {}
    authored_result_kind = _norm_name(itemstats.get("resultKind") or rp.get("resultKind"))
    if authored_result_kind in {"weapon", "ammo", "consumable_weapon", "tool", "accessory", "armor", "potion", "material", "furniture", "generic"}:
        patch["kind"] = authored_result_kind
    norm = rp.get("_normalization") if isinstance(rp.get("_normalization"), dict) else {}
    if isinstance(norm.get("rejectedEngineCalls"), list) and norm.get("rejectedEngineCalls"):
        patch["rejectedEngineCalls"] = norm.get("rejectedEngineCalls")[:16]

    # Primary executable action: one primary family only.  Incompatible extra
    # primary calls stay visible in provenance/debug and never override final fields.
    recovered_primary_secondary = _recover_rejected_primary_as_swing_secondary(shoot, rejected_primary, shoots)
    secondary_from_rejected_primary = bool(recovered_primary_secondary)
    if recovered_primary_secondary:
        secondary_calls = [*secondary_calls, recovered_primary_secondary]
    if rejected_primary:
        patch["rejectedPrimaryCalls"] = rejected_primary[:8]
    if recovered_primary_secondary:
        patch["recoveredPrimaryConflictAsSecondary"] = {
            "sourceIndex": recovered_primary_secondary.get("_index"),
            "mode": "swing_on_hit_secondary",
            "projectileShape": recovered_primary_secondary.get("projectileShape"),
            "count": recovered_primary_secondary.get("count"),
        }

    parent_onhit, parent_onhit_source = _parent_grounded_onhit(data)
    if parent_onhit and _norm_name(hit.get("onHit")) in {"", "none"}:
        # Preserve parent-authored elemental mechanics for combat outputs without
        # routing from prompt words.  E.g. FlamingArrow + Torch should keep burn.
        hit["onHit"] = parent_onhit
        hit.setdefault("debuffHint", parent_onhit_source)
        patch["parentMechanicPreserved"] = {"kind": "onHit", "value": parent_onhit, "sourceTag": parent_onhit_source}

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
    repair_reason = ""
    if shoots and runtime_family == "none":
        # v0.4.30: tiny repair for weaker models.  This never reads prose and never
        # invents a family from names; it only accepts one unambiguous family signal.
        runtime_family, repair_reason = light_repair_runtime_family_from_fields(shoot)
    if shoots and runtime_family == "none":
        patch["runtimeContractError"] = "primary_attack_requires_runtimeFamily"
    else:
        patch["runtimeFamily"] = runtime_family
        if repair_reason and repair_reason != "authored_runtimeFamily":
            patch["runtimeFamilyRepair"] = repair_reason
        patch.update(_runtime_family_affordances(runtime_family, patch.get("weaponFamily") or shoot.get("weaponFamily"), patch.get("delivery") or shoot.get("delivery")))

    # Aggregate pure VFX calls. This is still not gameplay child logic.
    particle_effects: list[str] = []
    particle_amount = 0.0
    particle_scale = 0.0
    particle_materials: list[str] = []
    for pc in particle_calls:
        eff = _enum(pc.get("effect"), EFFECTS, None)
        if eff and eff != "none":
            particle_effects.append(eff)
        particle_amount += _num(pc.get("amount"), 0) or 0
        particle_scale = max(particle_scale, _num(pc.get("scale"), 0) or 0)
        if pc.get("material") not in (None, ""):
            particle_materials.append(str(pc.get("material"))[:40])
    effect = _enum(_first_non_empty(*particle_effects, shoot.get("effect")), EFFECTS, None)
    if particle_calls and not particle_effects:
        effect = "none"
    if effect:
        patch["effect"] = effect
    if particle_calls:
        patch["burstDustCap"] = int(round(max(0, min(NUMERIC_LIMITS["burstDustCap"][1], particle_amount))))
        # v0.4.13: C# distinguishes effect=none from mundane dust via DustSpawnDenom.
        # effectCode 0 is shared by none/dust for old compatibility, so denom=0 means literally no ambient dust.
        if particle_amount <= 0 or effect in {None, "none"}:
            patch["dustSpawnDenom"] = 0
            patch["burstDustCap"] = 0
        else:
            # Higher authored amount = more frequent, but still bounded; no WhiteTorch fallback in runtime.
            patch["dustSpawnDenom"] = int(max(2, min(12, round(10 - min(8, particle_amount / 5.0)))))
        if particle_scale:
            patch["vfxParticleScale"] = max(0.0, min(2.0, round(particle_scale, 3)))
        if particle_materials:
            # Human/debug lineage only; C# can ignore this safely.
            patch["vfxMaterial"] = ", ".join(dict.fromkeys(particle_materials))[:80]

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
        # Preserve visual field dimensions for debug/VFX only under non-runtime keys.
        for field, out_field in [("fieldLifetimeTicks", "vfxFieldLifetimeTicks"), ("fieldRadiusTiles", "vfxFieldRadiusTiles")]:
            raw_vals = [_clamp(t.get(field), field) for t in trail_calls if t.get(field) not in (None, "")]
            raw_vals = [v for v in raw_vals if v is not None]
            if raw_vals:
                patch[out_field] = _intish(field, max(raw_vals))
        if rejected_trails:
            patch["rejectedTrailCalls"] = rejected_trails[:8]

    # Author-preserved state/trigger intents. These are not semantic routers and do not
    # execute unsupported gameplay by themselves; they are compact contract data for
    # lineage/future runtime wiring, while concrete engineCalls still carry immediate effects.
    runtime_state: dict[str, Any] = {}
    meters = _compile_state_meter_calls(state_meter_calls)
    if meters:
        runtime_state["stateMeters"] = meters
    triggered, rejected_triggered = _compile_triggered_action_calls(triggered_action_calls)
    if triggered:
        runtime_state["triggeredActions"] = triggered
    if rejected_triggered:
        patch.setdefault("rejectedEngineCalls", [])
        patch["rejectedEngineCalls"] = (patch.get("rejectedEngineCalls") or []) + rejected_triggered[:8]
    if runtime_state:
        runtime_state["executionStatus"] = "preserved_contract_not_gameplay_executor"
        patch["runtimeState"] = runtime_state

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
            if bt and bt > 0:
                extra_buffs.append({"buffCode": int(round(bt)), "buffTime": int(round(tm or 60 * 30))})
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
    if generated_buff:
        generated_buff.setdefault("durationTicks", int(patch.get("buffTime") or 60 * 30))
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

    if light_calls:
        strengths = [_clamp(c.get("strength"), "lightStrength", 0) for c in light_calls if c.get("strength") not in (None, "")]
        strengths = [s for s in strengths if s is not None]
        if strengths:
            patch["runtimeLightStrength"] = round(max(strengths), 3)
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
        patch["lightCallCount"] = len(light_calls)

    if vfx_cue_calls:
        allowed_events = {"travel", "active", "tick", "hit", "kill", "expire", "while_held", "while_equipped", "on_use", "on_alt_use"}
        allowed_renderers = {"projectileAfterimage", "spriteStampTrail", "historyRibbon", "tipTrail", "ghostArc", "wavyStrip", "beamLine", "fieldPulse", "orbitingMotes", "actorAfterimage", "impactRing", "impactSprite", "childMotes", "lightCue", "soundCue"}
        allowed_channels = {"motionTrail", "coreGlow", "ambientParticles", "impactShape", "impactParticles", "decaySmoke", "light", "sound"}
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
        mode = _norm_name(alt.get("mode")) or "mobility"
        patch["altUseMode"] = mode[:32]
        amode = _norm_name(alt.get("mobilityMode") or alt.get("mode"))
        if amode in {"recall_home", "blink_to_cursor"}:
            patch["altMobilityMode"] = amode
            patch["altMobilityRangeTiles"] = int(max(0, min(80, _num(alt.get("rangeTiles"), 0) or 0)))
            patch["altMobilityCooldownTicks"] = int(round(_clamp(alt.get("cooldownTicks"), "cooldownTicks", 0) or 0))
            patch["altMobilitySafeTileOnly"] = bool(alt.get("safeTileOnly") is not False)
        if isinstance(alt.get("generatedBuff"), dict):
            patch["altGeneratedBuff"] = alt.get("generatedBuff")
        elif mode == "light":
            alt_strengths = [_clamp(c.get("strength"), "lightStrength", 0) for c in light_calls if c.get("strength") not in (None, "")]
            alt_strengths = [s for s in alt_strengths if s is not None]
            strength = max(alt_strengths) if alt_strengths else 0
            colors = [str(c.get("lightColorName") or c.get("color") or "").strip() for c in light_calls if str(c.get("lightColorName") or c.get("color") or "").strip()]
            if strength > 0:
                patch["altGeneratedBuff"] = {
                    "durationTicks": int(round(_clamp(alt.get("durationTicks"), "durationTicks", 8 * 60) or 8 * 60)),
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
        if isinstance(hold.get("generatedBuff"), dict):
            patch["holdGeneratedBuff"] = hold.get("generatedBuff")

    if extractinator_calls:
        ex = _merged_params(extractinator_calls)
        rt = _clamp(ex.get("resultType"), "resultType", 0) if ex.get("resultType") not in (None, "") else 0
        st = _clamp(ex.get("stack"), "stack", 1) if ex.get("stack") not in (None, "") else 1
        if rt and rt > 0:
            patch["extractinatorOutputItemType"] = int(round(rt))
            patch["extractinatorOutputStack"] = int(round(st or 1))

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
        for src, out in [("autoReuse", "autoReuse"), ("useTurn", "useTurn"), ("channelUse", "channelUse"), ("drawDuringUse", "drawDuringUse")]:
            if src in ua:
                patch[out] = bool(ua.get(src))
        enum_fields = {
            "useFantasy": {"throw", "stab", "swing", "slam", "drink", "crush", "plant", "channel", "equip", "place"},
            "heldVisibility": {"show_item", "hide_item", "show_projectile", "show_both"},
            "releaseTiming": {"instant", "early", "mid_swing", "on_contact", "on_release"},
            "handPose": {"short_weapon", "two_hand", "overhead", "throwing", "staff", "held_out", "none"},
            "spawnStyle": {"from_hand", "at_tip", "centered", "impact_only", "world_anchor"},
            "rotationMode": {"face_velocity", "spin", "fixed", "swing_locked", "random"},
            "trailMode": {"none", "afterimage", "dust", "sprite_stamp", "ribbon"},
            "projectileSizePolicy": {"authored", "inherit_parent_floor", "inherit_parent_max"},
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
            patch["consumeChancePercent"] = int(round(max(0, min(100, _num(cb.get("consumeChancePercent"), 100) or 100))))

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

    if accessory_calls:
        acc = _merged_params(accessory_calls)
        accessory: dict[str, Any] = {"enabled": True}
        if acc.get("archetype") not in (None, ""):
            accessory["archetype"] = _norm_name(acc.get("archetype"))[:32]
        for src, out, lo, hi, integer in [
            ("defense", "defense", 0, 20, True),
            ("maxLife", "maxLife", 0, 100, True),
            ("maxMana", "maxMana", 0, 100, True),
            ("lifeRegen", "lifeRegen", 0, 20, True),
            ("manaRegen", "manaRegen", 0, 20, True),
            ("movementSpeed", "movementSpeed", 0, 1.0, False),
            ("maxRunSpeed", "maxRunSpeed", 0, 2.0, False),
            ("jumpSpeed", "jumpSpeed", 0, 4.0, False),
            ("genericDamage", "genericDamage", 0, 0.4, False),
            ("meleeDamage", "meleeDamage", 0, 0.4, False),
            ("rangedDamage", "rangedDamage", 0, 0.4, False),
            ("magicDamage", "magicDamage", 0, 0.4, False),
            ("summonDamage", "summonDamage", 0, 0.4, False),
            ("genericCrit", "genericCrit", 0, 20, False),
            ("attackSpeed", "attackSpeed", 0, 0.4, False),
            ("knockback", "knockback", 0, 2.0, False),
            ("minionSlots", "minionSlots", 0, 2, True),
            ("sentrySlots", "sentrySlots", 0, 2, True),
            ("manaCostReduction", "manaCostReduction", 0, 0.4, False),
            ("ammoSaveChance", "ammoSaveChance", 0, 0.5, False),
            ("aggro", "aggro", -400, 400, True),
            ("endurance", "endurance", 0, 0.2, False),
            ("armorPenetration", "armorPenetration", 0, 40, False),
            ("lightStrength", "lightStrength", 0, 1.5, False),
        ]:
            raw = acc.get(src)
            if raw in (None, ""):
                continue
            val = max(lo, min(hi, _num(raw, 0) or 0))
            accessory[out] = int(round(val)) if integer else round(float(val), 3)
        for src, out in [("fallDamageImmune", "fallDamageImmune"), ("lavaImmune", "lavaImmune"), ("waterWalk", "waterWalk")]:
            if src in acc:
                accessory[out] = bool(acc.get(src) is not False)
        color = str(acc.get("lightColorName") or acc.get("color") or "").strip()
        if color:
            accessory["lightColorName"] = color[:32]
        patch["accessory"] = accessory
        patch["kind"] = "accessory"
        patch["maxStack"] = 1

    if armor_calls or _norm_name(itemstats.get("resultKind")) == "armor":
        arm = _merged_params(armor_calls) if armor_calls else {}
        armor: dict[str, Any] = {"enabled": True}
        slot = _norm_name(arm.get("armorSlot") or itemstats.get("armorSlot") or arm.get("slot"))
        armor["slot"] = slot if slot in {"head", "body", "legs"} else "body"
        if arm.get("setKey") not in (None, ""):
            armor["setKey"] = str(arm.get("setKey"))[:64]
        if arm.get("archetype") not in (None, ""):
            armor["archetype"] = _norm_name(arm.get("archetype"))[:32]
        for src, out, lo, hi, integer in [
            ("defense", "defense", 0, 80, True),
            ("maxLife", "maxLife", 0, 100, True),
            ("maxMana", "maxMana", 0, 100, True),
            ("lifeRegen", "lifeRegen", 0, 20, True),
            ("manaRegen", "manaRegen", 0, 20, True),
            ("movementSpeed", "movementSpeed", 0, 1.0, False),
            ("maxRunSpeed", "maxRunSpeed", 0, 2.0, False),
            ("jumpSpeed", "jumpSpeed", 0, 4.0, False),
            ("genericDamage", "genericDamage", 0, 0.4, False),
            ("meleeDamage", "meleeDamage", 0, 0.4, False),
            ("rangedDamage", "rangedDamage", 0, 0.4, False),
            ("magicDamage", "magicDamage", 0, 0.4, False),
            ("summonDamage", "summonDamage", 0, 0.4, False),
            ("genericCrit", "genericCrit", 0, 20, False),
            ("attackSpeed", "attackSpeed", 0, 0.4, False),
            ("knockback", "knockback", 0, 2.0, False),
            ("minionSlots", "minionSlots", 0, 2, True),
            ("sentrySlots", "sentrySlots", 0, 2, True),
            ("manaCostReduction", "manaCostReduction", 0, 0.4, False),
            ("ammoSaveChance", "ammoSaveChance", 0, 0.5, False),
            ("aggro", "aggro", -400, 400, True),
            ("endurance", "endurance", 0, 0.2, False),
            ("armorPenetration", "armorPenetration", 0, 40, False),
            ("whipRange", "whipRange", 0, 1.5, False),
            ("summonTagDamage", "summonTagDamage", 0, 0.75, False),
            ("lightStrength", "lightStrength", 0, 1.5, False),
            ("setBonusGenericDamage", "setBonusGenericDamage", 0, 0.4, False),
            ("setBonusMeleeDamage", "setBonusMeleeDamage", 0, 0.4, False),
            ("setBonusRangedDamage", "setBonusRangedDamage", 0, 0.4, False),
            ("setBonusMagicDamage", "setBonusMagicDamage", 0, 0.4, False),
            ("setBonusSummonDamage", "setBonusSummonDamage", 0, 0.4, False),
            ("setBonusGenericCrit", "setBonusGenericCrit", 0, 20, False),
            ("setBonusMovementSpeed", "setBonusMovementSpeed", 0, 1.0, False),
            ("setBonusLifeRegen", "setBonusLifeRegen", 0, 20, True),
            ("setBonusManaRegen", "setBonusManaRegen", 0, 20, True),
            ("setBonusMinionSlots", "setBonusMinionSlots", 0, 2, True),
            ("setBonusSentrySlots", "setBonusSentrySlots", 0, 2, True),
            ("setBonusManaCostReduction", "setBonusManaCostReduction", 0, 0.4, False),
            ("setBonusAmmoSaveChance", "setBonusAmmoSaveChance", 0, 0.5, False),
            ("setBonusAggro", "setBonusAggro", -400, 400, True),
            ("setBonusEndurance", "setBonusEndurance", 0, 0.2, False),
            ("setBonusArmorPenetration", "setBonusArmorPenetration", 0, 40, False),
        ]:
            raw = arm.get(src, itemstats.get(src))
            if raw in (None, ""):
                continue
            val = max(lo, min(hi, _num(raw, 0) or 0))
            armor[out] = int(round(val)) if integer else round(float(val), 3)
        for src, out in [("fallDamageImmune", "fallDamageImmune"), ("lavaImmune", "lavaImmune"), ("waterWalk", "waterWalk")]:
            if src in arm:
                armor[out] = bool(arm.get(src) is not False)
        for src, out in [("lightColorName", "lightColorName"), ("color", "lightColorName"), ("setBonusText", "setBonusText")]:
            if arm.get(src) not in (None, "") and out not in armor:
                armor[out] = str(arm.get(src))[:120 if out == "setBonusText" else 32]
        _apply_armor_slot_budget(armor)
        patch["armor"] = armor
        patch["kind"] = "armor"
        patch["maxStack"] = 1
        patch["damage"] = 0

    # Primary numeric mapping.
    for src, mapping in [
        (shoot, {"rangeTiles": "rangeTiles", "lifetimeTicks": "lifetimeTicks", "shotCount": "shotCount", "spreadRadians": "spreadRadians", "pierce": "pierce", "extraUpdates": "extraUpdates", "homingStrength": "homingStrength", "beamWidthPx": "beamWidthPx", "beamChargeTicks": "beamChargeTicks", "chargeTicks": "chargeTicks", "chargePowerMultiplier": "chargePowerMultiplier", "sentryAttackIntervalTicks": "sentryAttackIntervalTicks", "sentryTargetRangeTiles": "sentryTargetRangeTiles", "sentryLifetimeTicks": "sentryLifetimeTicks", "secondaryLifetimeTicks": "secondaryLifetimeTicks", "immunityCooldown": "immunityCooldown", "useTimeTicks": "useTimeTicks", "useAnimationTicks": "useAnimationTicks", "speed": "speed", "reliability": "reliability", "selfLockTicks": "selfLockTicks", "missPunish": "missPunish"}),
        (hit, {"aoeRadiusTiles": "aoeRadiusTiles", "chainCount": "chainCount", "count": "splitCount", "pullStrength": "pullStrength"}),
        (itemstats, {"useTimeTicks": "useTimeTicks", "useAnimationTicks": "useAnimationTicks", "knockback": "knockback", "manaCost": "manaCost", "craftYield": "craftYield"}),
    ]:
        for k, outk in mapping.items():
            if k in src and src.get(k) not in (None, "") and outk not in patch and outk in NUMERIC_LIMITS:
                v = _clamp(src.get(k), outk)
                if v is not None:
                    patch[outk] = _intish(outk, v)

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
            try:
                patch["debuffTime"] = int(max(15, min(360, float(hit.get("debuffTime")))))
            except Exception:
                patch["debuffTime"] = 90
        else:
            patch["debuffTime"] = 90

    # Some explicit on-hit effects spawn gameplay children in the C# runtime.
    # Give them a child budget only when the LLM actually requested an executable count.
    if onhit in {"chain", "lightning_arc"}:
        # For chain-like effects, generic params.count means chain hops, not split shards.
        existing_split_for_count = int(_num(patch.get("splitCount"), 0) or 0)
        if int(_num(patch.get("chainCount"), 0) or 0) <= 0 and existing_split_for_count > 0:
            patch["chainCount"] = existing_split_for_count
            patch["splitCount"] = 0
        chain_count = int(_num(patch.get("chainCount"), 0) or 0)
        if chain_count > 0:
            patch.setdefault("maxChildProjectiles", int(max(1, min(48, chain_count + 1))))
            patch.setdefault("maxChildDepth", 1)
        else:
            patch["onHitDemotedReason"] = f"{onhit}_requires_count_gt_0"
            patch["onHit"] = "none"
            onhit = "none"
    if onhit in {"mini_missiles", "vortex_spawn", "radial_beams", "starburst", "overhead_barrage", "spore_cloud"}:
        effect_count = int(_num(patch.get("splitCount"), 0) or 0)
        if effect_count <= 0:
            patch["onHitDemotedReason"] = f"{onhit}_requires_count_gt_0"
            patch["onHit"] = "none"
            onhit = "none"
        else:
            patch.setdefault("maxChildProjectiles", int(max(1, min(48, effect_count))))
            patch.setdefault("maxChildDepth", 1)

    # Real secondary damaging projectiles live in one small owner module.
    # This keeps trigger/lifecycle rules out of the already-large main compiler.
    apply_secondary_projectile_calls(
        patch,
        secondary_calls,
        secondary_from_rejected_primary=secondary_from_rejected_primary,
    )


    # Executable defaults: only fill execution slots after the LLM chose engine calls.
    if shoot:
        patch.setdefault("delivery", "shoot")
        patch.setdefault("movement", "straight")
        patch.setdefault("shotCount", 1)
        patch.setdefault("pierce", 0)
        patch.setdefault("rangeTiles", 45)
        patch.setdefault("lifetimeTicks", 90)
        patch.setdefault("spreadRadians", 0)
        patch.setdefault("speed", 8.0)
    patch.setdefault("effect", "none" if not particle_calls or int(_num(patch.get("dustSpawnDenom"), 0) or 0) <= 0 else "dust")
    if not particle_calls:
        patch.setdefault("dustSpawnDenom", 0)
        patch.setdefault("burstDustCap", 0)
    patch.setdefault("onHit", "none")
    patch.setdefault("aoeRadiusTiles", 0)
    patch.setdefault("useTimeTicks", int(_clamp(_first_non_empty(itemstats.get("useTimeTicks"), shoot.get("useTimeTicks")), "useTimeTicks", 24) or 24))
    patch.setdefault("useAnimationTicks", int(_clamp(_first_non_empty(itemstats.get("useAnimationTicks"), shoot.get("useAnimationTicks"), patch.get("useTimeTicks")), "useAnimationTicks", patch.get("useTimeTicks", 24)) or patch.get("useTimeTicks", 24)))
    patch.setdefault("reliability", 1.0)
    patch.setdefault("selfLockTicks", 0)
    patch.setdefault("missPunish", 0)
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

    # Audio is authored as exact acoustic catalog ids, never inferred from item names,
    # tooltip prose, weapon taxonomy, projectile shape or material words.  Invalid ids
    # stay visible in provenance while the finite mechanic-based fallback remains safe.
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
        patch["soundUseCatalogId"] = use_sound or default_use_sound_id(patch.get("runtimeFamily"), patch.get("effect"), patch.get("delivery"))
        patch["soundImpactCatalogId"] = impact_sound or default_impact_sound_id(patch.get("onHit"), patch.get("effect"))
        patch["soundCatalogSource"] = SOUND_CATALOG_SOURCE
        patch["primaryColorName"] = normalize_runtime_color(patch.get("primaryColorName"), runtime_color_for_effect(patch.get("effect")))
        if rejected_sound_ids:
            patch["rejectedSoundCatalogIds"] = rejected_sound_ids
        if shoot.get("soundVolume") not in (None, ""):
            patch["soundVolume"] = round(float(_clamp(shoot.get("soundVolume"), "soundVolume", 0.85) or 0.85), 3)
        if shoot.get("soundPitch") not in (None, ""):
            patch["soundPitch"] = round(float(_clamp(shoot.get("soundPitch"), "soundPitch", 0.0) or 0.0), 3)
        if shoot.get("soundPitchVariance") not in (None, ""):
            patch["soundPitchVariance"] = round(float(_clamp(shoot.get("soundPitchVariance"), "soundPitchVariance", 0.18) or 0.0), 3)

    patch["runtimePlanAuthored"] = True
    patch, _archetype_report = compile_runtime_archetype_to_attack_patch(data, patch)
    apply_overhead_barrage_contract(patch)
    apply_charge_release_contract(patch)
    apply_sentry_contract(patch)
    return {k: v for k, v in patch.items() if v not in (None, "")}

__all__ = ['compile_runtime_plan_to_genome_patch']

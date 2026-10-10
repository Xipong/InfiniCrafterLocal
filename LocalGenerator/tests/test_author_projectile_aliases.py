"""Fresh projectile Author choices preserve existing executor inputs and provenance."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from infini_local.core.runtime_authoring import (
    CAPABILITY_REGISTRY, apply_repair_patch, build_runtime_repair_scope,
    compile_runtime_program, filter_repair_patch_scope, validate_runtime_program,
    validate_runtime_wire,
)
from infini_local.core.runtime_authoring.capability_registry import MOVEMENT_OPCODE
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.qa.capability_witnesses import build_capability_witness


def selected(document, fn=None):
    return next(row for row in document["runtimeProgram"]["calls"]
                if (row["fn"] == fn if fn else row["id"] == "witness_call"))


def compiled_entity(document, call):
    wire = compile_runtime_program(document)
    assert validate_runtime_wire(wire)["ok"]
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    assert audit_compiler_receipts(receipts, authored_document=document, final_document=wire)["ok"]
    assert audit_compiler_receipts(receipts, final_document=wire)["ok"]
    return wire, next(row for row in wire["runtimeProgram"]["entities"] if row["id"] == call["target"])


@pytest.mark.parametrize("immunity,mode,cooldown", [
    ("owner_shared", "owner", -1), ("once_per_npc", "local", -1),
    ({"localCooldown": 0}, "local", 0), ({"localCooldown": 1}, "local", 1),
    ({"localCooldown": 600}, "local", 600),
])
@pytest.mark.parametrize("updates", [1, 2, 6])
def test_immunity_and_update_rate_are_exact_independent_choices(immunity, mode, cooldown, updates):
    document = build_capability_witness("set_projectile_collision")
    call = selected(document)
    call["params"].update(immunity=immunity, updatesPerTick=updates, pierce=-1)
    wire, entity = compiled_entity(document, call)
    assert entity["collision"] == {
        "tileCollide": True, "ignoreWater": False, "bounceCount": 0, "pierce": -1,
        "extraUpdates": updates - 1, "npcImmunityMode": mode, "localNpcHitCooldownTicks": cooldown,
    }
    assert entity["spawn"]["speedPxPerTick"] == 8  # no update-rate rescaling
    relevant = [r for r in wire["runtimeContract"]["finalWireReceipts"] if r.get("callId") == call["id"]]
    assert len([r for r in relevant if ".params.immunity" in r["authoredPath"]]) == 2
    assert any(r.get("authoredPath", "").endswith(".updatesPerTick") and r["value"] == updates - 1 for r in relevant)


@pytest.mark.parametrize("name,value", [
    ("immunity", None), ("immunity", "local"), ("immunity", {}),
    ("immunity", {"localCooldown": -1}), ("immunity", {"localCooldown": 601}),
    ("immunity", {"localCooldown": True}), ("immunity", {"localCooldown": 1.5}),
    ("immunity", {"localCooldown": 2, "mode": "local"}),
    ("updatesPerTick", 0), ("updatesPerTick", 7), ("updatesPerTick", True),
    ("updatesPerTick", 1.5),
])
def test_collision_rejects_ambiguous_choices_and_noninteger_updates(name, value):
    document = build_capability_witness("set_projectile_collision")
    selected(document)["params"][name] = value
    assert not validate_runtime_program(document)["ok"]
    with pytest.raises(ValueError):
        compile_runtime_program(document)


@pytest.mark.parametrize("anchor,wire_anchor", [
    ("activation_origin", "item_use_origin"), ("owner_center", "owner_center"),
    ("cursor", "cursor"), ("ground_at_cursor", "ground_at_cursor"),
])
@pytest.mark.parametrize("height,delay", [(None, 0), (1, 0), (7.25, 19), (80, 600)])
def test_spawn_position_keeps_all_anchors_height_delay_aim_and_ids(anchor, wire_anchor, height, delay):
    document = build_capability_witness("configure_spawn")
    call = selected(document)
    call["params"].update(position=({"at": anchor} if height is None else {
        "above": anchor, "heightTiles": height, "activationDelayTicks": delay,
    }), aim="velocity", offsetPx=-37)
    wire, entity = compiled_entity(document, call)
    assert entity["spawn"]["placement"] == wire_anchor
    assert entity["spawn"]["overTarget"] == {"heightTiles": height or 0, "delayTicks": delay}
    assert entity["spawn"]["aim"] == "velocity" and entity["spawn"]["offsetPx"] == -37
    assert entity["id"] == call["target"]
    relevant = [r for r in wire["runtimeContract"]["finalWireReceipts"] if r.get("callId") == call["id"]]
    assert len([r for r in relevant if ".params.position" in r["authoredPath"]]) == 3


@pytest.mark.parametrize("position", [
    {}, {"at": "above_cursor"}, {"at": "cursor", "activationDelayTicks": 1},
    {"at": "cursor", "above": "cursor", "heightTiles": 3, "activationDelayTicks": 0},
    {"above": "cursor", "heightTiles": 0, "activationDelayTicks": 0},
    {"above": "cursor", "heightTiles": 3},
    {"above": "cursor", "heightTiles": 3, "activationDelayTicks": True},
])
def test_spawn_position_rejects_ambiguous_missing_and_unreviewed_delay_variants(position):
    document = build_capability_witness("configure_spawn")
    selected(document)["params"]["position"] = position
    assert not validate_runtime_program(document)["ok"]


@pytest.mark.parametrize("fn,name,wire_name,lo,hi", [
    ("damage_area_on_event", "radiusTiles", "radiusPx", 8, 768),
    ("move_proximity_missile", "triggerRadiusTiles", "proximityRadiusPx", 4, 512),
])
def test_tile_radii_cover_exactly_every_old_integer_pixel_radius(fn, name, wire_name, lo, hi):
    spec = CAPABILITY_REGISTRY[fn].params[name]
    assert spec.multiple_of == 1 / 16
    assert [spec.to_wire(pixels / 16) for pixels in range(lo, hi + 1)] == list(range(lo, hi + 1))
    for pixels in (lo, lo + 1, 127, hi - 1, hi):
        document = build_capability_witness(fn)
        call = selected(document)
        call["params"][name] = pixels / 16
        _, entity = compiled_entity(document, call)
        output = entity["events"][0] if fn == "damage_area_on_event" else entity["movement"]["params"]
        assert output[wire_name] == pixels and type(output[wire_name]) is int
    for value in ((lo - 1) / 16, (hi + 1) / 16, lo / 16 + 1 / 32, True):
        selected(document)["params"][name] = value
        assert not validate_runtime_program(document)["ok"]


@pytest.mark.parametrize("when", ["on_hit", {"everyTicks": 6}, {"everyTicks": 3600}])
def test_owner_pull_uses_exact_old_action_and_ignores_no_authored_radius(when):
    document = build_capability_witness("pull_owner_to_event_target")
    call = selected(document)
    call["params"].update(when=when, strength=3.125, delayTicks=37)
    wire, entity = compiled_entity(document, call)
    event = entity["events"][0]
    assert event == {
        "id": "witness_call", "action": "pull_on_event", "actionCode": 5,
        "event": "on_hit" if isinstance(when, str) else "periodic", "mode": "owner_to_target",
        "radiusTiles": 1, "strength": 3.125, "delayTicks": 37,
        **({"periodTicks": when["everyTicks"]} if isinstance(when, dict) else {}),
    }
    relevant = [r for r in wire["runtimeContract"]["finalWireReceipts"] if r.get("callId") == call["id"]]
    for literal in ("action", "actionCode", "mode", "radiusTiles"):
        receipt = next(r for r in relevant if r["finalPath"].endswith("." + literal))
        assert receipt["authoredPath"].endswith(".fn") and receipt["status"] == "technical_projection"
    hostile = deepcopy(document)
    selected(hostile)["params"]["radiusTiles"] = 37
    assert not validate_runtime_program(hostile)["ok"]
    npc = build_capability_witness("pull_on_event")
    selected(npc)["params"]["mode"] = "owner_to_target"
    assert not validate_runtime_program(npc)["ok"]


@pytest.mark.parametrize("mutation", ["discriminator", "missing", "duplicate", "source"])
def test_owner_pull_discriminator_receipts_bind_the_exact_existing_executor(mutation):
    document = build_capability_witness("pull_owner_to_event_target")
    wire, entity = compiled_entity(document, selected(document))
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    action = next(row for row in receipts if row.get("callId") == "witness_call"
                  and row["finalPath"].endswith(".action"))
    if mutation == "discriminator":
        # Even a mutually consistent different existing opcode/name pair is
        # not the projection of the explicitly selected owner-pull capability.
        entity["events"][0].update(action="damage_area_on_event", actionCode=3)
        action["value"] = "damage_area_on_event"
        next(row for row in receipts if row.get("callId") == "witness_call"
             and row["finalPath"].endswith(".actionCode"))["value"] = 3
    elif mutation == "missing":
        receipts.remove(action)
    elif mutation == "duplicate":
        receipts.append(deepcopy(action))
    else:
        action["authoredPath"] = action["authoredPath"].removesuffix(".fn") + ".params.strength"
    for source in (None, document):
        report = audit_compiler_receipts(receipts, authored_document=source, final_document=wire)
        assert not report["ok"]
        assert any("fixed wire literal" in row["reason"] for row in report["violations"])


@pytest.mark.parametrize("fn", ["spawn_entity_on_event", "pull_on_event", "pull_owner_to_event_target"])
@pytest.mark.parametrize("when", [None, {}, "periodic", {"everyTicks": 5}, {"everyTicks": 3601},
                                 {"everyTicks": 6.5}, {"everyTicks": True}, {"everyTicks": 6, "event": "on_hit"}])
def test_periodic_trigger_requires_one_explicit_integer_interval(fn, when):
    document = build_capability_witness(fn)
    selected(document)["params"]["when"] = when
    assert not validate_runtime_program(document)["ok"]


def test_root_spawn_fields_are_omittable_only_for_exact_child_kind():
    document = build_capability_witness("spawn_entity_on_event")
    spawn = next(row for row in document["runtimeProgram"]["calls"]
                 if row["fn"] == "configure_spawn" and row["target"] == "witness_child")
    spawn["params"].pop("count")
    spawn["params"].pop("spreadRadians")
    original = deepcopy(document)
    wire, entity = compiled_entity(document, spawn)
    assert document == original
    assert entity["spawn"]["count"] == 1 and entity["spawn"]["spreadRadians"] == 0
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    assert {r["authoredPath"].rsplit(".", 1)[-1] for r in receipts
            if r.get("callId") == spawn["id"] and r["status"] == "declared_neutral_omission"} == {"count", "spreadRadians"}
    # A free projectile can be reached by a child event and a root binding.
    # Neither producer reachability nor current count permits a kind heuristic.
    child = next(e for e in document["runtimeProgram"]["entities"] if e["id"] == "witness_child")
    child["kind"] = "free_projectile"
    for root_binding in (False, True):
        if root_binding:
            binding = deepcopy(document["runtimeProgram"]["bindings"][0])
            binding.update(id="alternate_child", input="alternate_use")
            binding["usePolicy"]["action"]["targetId"] = "witness_child"
            document["runtimeProgram"]["bindings"].append(binding)
        errors = validate_runtime_program(document)["errors"]
        assert {r["path"].rsplit(".", 1)[-1] for r in errors if r["code"] == "missing_dependency_param"} == {"count", "spreadRadians"}
    assert not audit_compiler_receipts(receipts, authored_document=document, final_document=wire)["ok"]
    forged_wire = deepcopy(wire)
    next(e for e in forged_wire["runtimeProgram"]["entities"] if e["id"] == "witness_child")["kind"] = "free_projectile"
    assert not audit_compiler_receipts(receipts, final_document=forged_wire)["ok"]


@pytest.mark.parametrize("movement", ["move_straight", "move_gravity_arc", "move_boomerang", "move_returning_glaive", "move_flail_tether"])
@pytest.mark.parametrize("tile_collide", [False, True])
def test_bounce_omission_is_limited_to_exact_inactive_consumer_branches(movement, tile_collide):
    document = build_capability_witness(movement)
    collision = selected(document, "set_projectile_collision")
    collision["params"].update(tileCollide=tile_collide, bounceCount=17)
    _, explicit = compiled_entity(document, collision)
    assert explicit["collision"]["bounceCount"] == 17
    collision["params"].pop("bounceCount")
    allowed = not tile_collide or movement in {"move_boomerang", "move_returning_glaive", "move_flail_tether"}
    assert validate_runtime_program(document)["ok"] is allowed
    if allowed:
        _, entity = compiled_entity(document, collision)
        assert entity["collision"]["bounceCount"] == 0
    else:
        with pytest.raises(ValueError):
            compile_runtime_program(document)


@pytest.mark.parametrize("new_tile", [False, True])
def test_repair_reactivating_collision_requires_an_explicit_bounce_choice(new_tile):
    document = build_capability_witness("move_straight")
    collision = selected(document, "set_projectile_collision")
    collision["params"].pop("bounceCount")
    collision["params"]["tileCollide"] = "invalid_boolean"
    report = validate_runtime_program(document)
    scope = build_runtime_repair_scope(document, report["errors"])
    candidate = deepcopy(collision)
    candidate["params"].update(tileCollide=new_tile, bounceCount=7, pierce=99)
    filtered, audit = filter_repair_patch_scope(document, {"note": "choose collision", "callsUpsert": [candidate]}, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(document, filtered)
    result = selected(repaired, "set_projectile_collision")["params"]
    assert result["pierce"] == collision["params"]["pierce"]
    assert result["bounceCount"] == 7  # exact missing leaf was a current deterministic error
    assert validate_runtime_program(repaired)["ok"]


def test_omitted_bounce_stays_absent_during_unrelated_repair():
    document = build_capability_witness("move_straight")
    collision = selected(document, "set_projectile_collision")
    collision["params"].update(tileCollide=False, pierce=101)
    collision["params"].pop("bounceCount")
    scope = build_runtime_repair_scope(document, validate_runtime_program(document)["errors"])
    candidate = deepcopy(collision)
    candidate["params"].update(pierce=3, bounceCount=7, tileCollide=True)
    filtered, audit = filter_repair_patch_scope(document, {"note": "repair pierce", "callsUpsert": [candidate]}, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(document, filtered)
    result = selected(repaired, "set_projectile_collision")["params"]
    assert result["tileCollide"] is False and "bounceCount" not in result
    assert result["pierce"] == 3 and validate_runtime_program(repaired)["ok"]


@pytest.mark.parametrize("delete_motion", ["witness_call", "other_motion"])
@pytest.mark.parametrize("author_bounce", [False, True])
def test_repair_resolves_movement_conflict_before_conditional_bounce_omission(delete_motion, author_bounce):
    document = build_capability_witness("move_boomerang")
    collision = selected(document, "set_projectile_collision")
    collision["params"].pop("bounceCount")
    collision["params"]["tileCollide"] = True
    motion = selected(document)
    document["runtimeProgram"]["calls"].append({
        "id": "other_motion", "fn": "move_straight", "target": motion["target"], "params": {},
    })
    errors = validate_runtime_program(document)["errors"]
    assert {row["code"] for row in errors} == {"exclusive_component_conflict"}
    scope = build_runtime_repair_scope(document, errors)
    assert next(row["paths"] for row in scope["fieldPermissions"]["calls"]
                if row["id"] == collision["id"]) == ["params.bounceCount"]
    candidate = deepcopy(collision)
    candidate["params"].update(pierce=99, **({"bounceCount": 7} if author_bounce else {}))
    filtered, audit = filter_repair_patch_scope(document, {
        "note": "keep one chosen movement", "callsUpsert": [candidate], "callIdsDelete": [delete_motion],
    }, scope)
    missing_new_choice = delete_motion == "witness_call" and not author_bounce
    assert audit["ok"] is not missing_new_choice, audit
    repaired = apply_repair_patch(document, filtered)
    result = selected(repaired, "set_projectile_collision")["params"]
    assert result["pierce"] == collision["params"]["pierce"]
    if delete_motion == "other_motion":
        assert "bounceCount" not in result
        if author_bounce:
            assert any(row["reason"] == "inactive_omission_stays_frozen" for row in audit["ignoredChanges"])
    elif author_bounce:
        assert result["bounceCount"] == 7
    else:
        assert any(row.get("actual", {}).get("code") == "missing_dependency_param" for row in audit["errors"])
        assert {row["code"] for row in validate_runtime_program(repaired)["errors"]} == {"missing_dependency_param"}
        with pytest.raises(ValueError):
            compile_runtime_program(repaired)
        return
    _, entity = compiled_entity(repaired, selected(repaired, "set_projectile_collision"))
    assert entity["collision"]["bounceCount"] == (7 if delete_motion == "witness_call" else 0)


@pytest.mark.parametrize("fn,broken,value,frozen_key,hostile", [
    ("set_projectile_collision", {"immunity": {"localCooldown": 601}}, {"immunity": {"localCooldown": 19}}, "pierce", 99),
    ("pull_on_event", {"when": {"everyTicks": 5}}, {"when": {"everyTicks": 19}}, "strength", 4),
    ("configure_spawn", {"position": {"above": "cursor", "heightTiles": 81, "activationDelayTicks": 37}},
     {"position": {"above": "owner_center", "heightTiles": 19, "activationDelayTicks": 2}}, "count", 12),
])
def test_nested_repair_changes_only_the_broken_leaf(fn, broken, value, frozen_key, hostile):
    document = build_capability_witness(fn)
    call = selected(document)
    call["params"].update(deepcopy(broken))
    errors = validate_runtime_program(document)["errors"]
    scope = build_runtime_repair_scope(document, errors)
    paths = next(row["paths"] for row in scope["fieldPermissions"]["calls"] if row["id"] == call["id"])
    leaf = {"set_projectile_collision": "immunity.localCooldown", "pull_on_event": "when.everyTicks",
            "configure_spawn": "position.heightTiles"}[fn]
    assert paths == ["params." + leaf]
    candidate = deepcopy(call)
    candidate["params"].update(deepcopy(value), **{frozen_key: hostile})
    filtered, audit = filter_repair_patch_scope(document, {"note": "repair exact leaf", "callsUpsert": [candidate]}, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(document, filtered)
    actual = selected(repaired)["params"]
    assert actual[frozen_key] == call["params"][frozen_key]
    if fn == "configure_spawn":
        assert actual["position"] == {"above": "cursor", "heightTiles": 19, "activationDelayTicks": 37}
    assert validate_runtime_program(repaired)["ok"]


@pytest.mark.parametrize("fn", ["spawn_over_target", "move_bounce"])
def test_retired_author_call_is_absent_from_schema_prompt_repair_but_wire_opcode_remains(fn):
    from infini_local.core.runtime_authoring import compact_capability_catalog, capability_provider_union
    from infini_local.pipelines.llm_authoring_pipeline import build_gameplay_repair_dossier
    assert fn not in {row["fn"] for row in compact_capability_catalog()}
    assert fn not in {row["properties"]["fn"]["const"] for row in capability_provider_union()}
    document = build_capability_witness("move_gravity_arc")
    selected(document)["fn"] = fn
    assert not validate_runtime_program(document)["ok"]
    scope = build_runtime_repair_scope(document, validate_runtime_program(document)["errors"])
    assert fn not in scope["create"]["calls"]["allowedFns"]
    dossier = build_gameplay_repair_dossier(document, {}, {}, {}, {}, failure_report=validate_runtime_program(document))
    for section in ("blockerCapabilities", "supportingCapabilities", "existingBrokenCapabilityCards"):
        assert fn not in {row["fn"] for row in dossier[section]}
    assert MOVEMENT_OPCODE["move_bounce"] == 6 and MOVEMENT_OPCODE["move_gravity_arc"] == 2


def test_frozen_wire_and_receipts_survive_without_accepting_old_author_paths():
    path = Path(__file__).with_name("fixtures") / "projectile_retained_wire.json"
    corpus = json.loads(path.read_text())
    assert corpus["sourceHead"] == "a3d5950"
    for row in corpus["cases"]:
        wire = row["wire"]
        before = json.dumps(wire, sort_keys=True)
        receipts = wire["runtimeContract"]["finalWireReceipts"]
        assert validate_runtime_wire(wire)["ok"], row["fn"]
        report = audit_compiler_receipts(receipts, final_document=wire)
        assert report["ok"], (row["fn"], report)
        assert json.dumps(wire, sort_keys=True) == before
        broken = deepcopy(receipts)
        next(r for r in broken if r.get("callId") == "witness_call" and ".params." in r["authoredPath"])["authoredPath"] += "_unknown"
        assert not audit_compiler_receipts(broken, final_document=wire)["ok"]


@pytest.mark.parametrize("fn", ["move_bounce", "spawn_over_target"])
def test_retained_capability_evidence_cannot_admit_a_second_author_grammar(fn):
    corpus = json.loads((Path(__file__).with_name("fixtures") / "projectile_retained_wire.json").read_text())
    saved = next(row["wire"] for row in corpus["cases"] if row["fn"] == fn)
    parameters = [row for row in saved["runtimeContract"]["finalWireReceipts"]
                  if row.get("callId") == "witness_call" and row.get("status") == "delivered"]
    assert audit_compiler_receipts(parameters)["ok"]
    source_index = int(parameters[0]["authoredPath"].split("calls[")[1].split("]")[0])
    params = {}
    for row in parameters:
        name = row["authoredPath"].split(".params.")[1]
        params[name] = row["value"]
    source_calls = [None] * source_index + [{"id": "witness_call", "fn": fn, "target": "old", "params": params}]
    report = audit_compiler_receipts(parameters, authored_document={"runtimeProgram": {"calls": source_calls}})
    assert not report["ok"]
    assert any(row["reason"] == "retained wire capability is not a current Author source" for row in report["violations"])

@pytest.mark.parametrize("attack", ["source-targets", "receipt-owners"])
def test_actual_collision_alias_binds_source_target_to_exact_wire_owner(attack):
    document = build_capability_witness("spawn_entity_on_event")
    calls = [r for r in document["runtimeProgram"]["calls"] if r["fn"] == "set_projectile_collision"]
    assert len(calls) == 2
    for cooldown, call in enumerate(calls, 10):
        call["params"]["immunity"] = {"localCooldown": cooldown}
    wire = compile_runtime_program(document)
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    assert audit_compiler_receipts(receipts, authored_document=document, final_document=wire)["ok"]
    if attack == "source-targets":
        calls[0]["target"], calls[1]["target"] = calls[1]["target"], calls[0]["target"]
        assert validate_runtime_program(document)["ok"]
    else:
        entities = wire["runtimeProgram"]["entities"]
        indices = [next(i for i, e in enumerate(entities) if e["id"] == c["target"]) for c in calls]
        for row in receipts:
            if row.get("callId") in {c["id"] for c in calls}:
                a, b = (f"entities[{i}]" for i in indices)
                row["finalPath"] = row["finalPath"].replace(a, "OWNER_SWAP").replace(b, a).replace("OWNER_SWAP", b)
        a, b = indices
        entities[a]["collision"], entities[b]["collision"] = entities[b]["collision"], entities[a]["collision"]
    assert not audit_compiler_receipts(receipts, authored_document=document, final_document=wire)["ok"]


@pytest.mark.parametrize("attack", ["cooldown-domain", "hybrid-variant", "missing-literal", "duplicate", "spawn-domain"])
@pytest.mark.parametrize("source_available", [False, True])
def test_actual_typed_alias_receipts_require_one_complete_valid_projection(attack, source_available):
    fn = "configure_spawn" if attack == "spawn-domain" else "set_projectile_collision"
    document = build_capability_witness(fn)
    call = selected(document)
    if fn == "configure_spawn":
        call["params"]["position"] = {"above": "cursor", "heightTiles": 1, "activationDelayTicks": 0}
    else:
        call["params"]["immunity"] = {"localCooldown": 19}
    wire = compile_runtime_program(document)
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    entity = next(e for e in wire["runtimeProgram"]["entities"] if e["id"] == call["target"])
    if attack == "spawn-domain":
        entity["spawn"]["overTarget"]["heightTiles"] = 0.5
        next(r for r in receipts if r.get("authoredPath", "").endswith(".position.heightTiles"))["value"] = 0.5
    elif attack == "cooldown-domain":
        entity["collision"]["localNpcHitCooldownTicks"] = 601
        next(r for r in receipts if r.get("authoredPath", "").endswith(".immunity.localCooldown"))["value"] = 601
    else:
        row = next(r for r in receipts if r.get("callId") == call["id"] and r["finalPath"].endswith(".npcImmunityMode"))
        if attack == "hybrid-variant":
            entity["collision"]["npcImmunityMode"] = row["value"] = "owner"
        elif attack == "missing-literal":
            receipts.remove(row)
        else:
            receipts.append(deepcopy(row))
    assert not audit_compiler_receipts(receipts, authored_document=document if source_available else None,
                                       final_document=wire)["ok"]


@pytest.mark.parametrize("missing", [False, True])
def test_retained_spawn_outputs_keep_their_separate_exact_capability_owner(missing):
    corpus = json.loads((Path(__file__).with_name("fixtures") / "projectile_retained_wire.json").read_text())
    wire = deepcopy(next(row["wire"] for row in corpus["cases"] if row["fn"] == "spawn_over_target"))
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    if missing:
        receipts[:] = [r for r in receipts if not (r.get("fn") == "spawn_over_target"
                                                   and r["finalPath"].endswith(".overTarget.heightTiles"))]
    before = deepcopy(wire)
    assert audit_compiler_receipts(receipts, final_document=wire)["ok"] is not missing
    assert wire == before

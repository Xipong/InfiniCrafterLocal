"""Fresh projectile Author choices preserve existing executor inputs and provenance."""
import json
from copy import deepcopy
from pathlib import Path

import pytest
from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY, MOVEMENT_OPCODE
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
from infini_local.core.runtime_authoring.repair.filter import filter_repair_patch_scope
from infini_local.core.runtime_authoring.repair.scope import build_runtime_repair_scope
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.qa.capability_witnesses import build_capability_witness


def selected(document, fn=None):
    return next(row for row in document["runtimeProgram"]["calls"]
                if (row["fn"] == fn if fn else row["id"] == "witness_call"))


def compiled_entity(document, call):
    wire = compile_runtime_program(document)
    assert validate_runtime_wire(wire)["ok"]
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    return wire, next(row for row in wire["runtimeProgram"]["entities"] if row["id"] == call["target"])


# Each immunity branch and the update-rate endpoints have distinct witnesses;
# crossing every cooldown with every update rate only repeats these projections.
@pytest.mark.parametrize("immunity,mode,cooldown,updates", [
    ("owner_shared", "owner", -1, 6),
    ("once_per_npc", "local", -1, 2),
    ({"localCooldown": 0}, "local", 0, 1),
    ({"localCooldown": 37}, "local", 37, 6),
    ({"localCooldown": 600}, "local", 600, 2),
])
def test_immunity_and_update_rate_are_exact_independent_choices(immunity, mode, cooldown, updates):
    document = build_capability_witness("projectile_collision")
    call = selected(document)
    call["params"].update(immunity=immunity, updatesPerTick=updates, pierce=-1)
    wire, entity = compiled_entity(document, call)
    assert entity["collision"] == {
        "tileCollide": True, "ignoreWater": False, "bounceCount": 0, "bounceSpeedRetention": 1, "pierce": -1,
        "extraUpdates": updates - 1, "npcImmunityMode": mode, "localNpcHitCooldownTicks": cooldown,
    }
    assert entity["spawn"]["speedPxPerTick"] == pytest.approx(8 / updates)  # world speed is lowered at the same-target update rate
    relevant = [r for r in wire["runtimeContract"]["finalWireReceipts"] if r.get("callId") == call["id"]]
    immunity_rows = [r for r in relevant if ".params.immunity" in r["authoredPath"]]
    assert len(immunity_rows) == 2
    for removed in immunity_rows:
        for source in (None, document):
            assert not audit_compiler_receipts([r for r in wire["runtimeContract"]["finalWireReceipts"] if r is not removed],
                                               authored_document=source, final_document=wire)["ok"]
            forged = deepcopy(wire["runtimeContract"]["finalWireReceipts"])
            forged[wire["runtimeContract"]["finalWireReceipts"].index(removed)]["value"] = "forged"
            assert not audit_compiler_receipts(forged, authored_document=source, final_document=wire)["ok"]
    assert any(r.get("authoredPath", "").endswith(".updatesPerTick") and r["value"] == updates - 1 for r in relevant)


@pytest.mark.parametrize("name,value", [
    ("immunity", None), ("immunity", "local"), ("immunity", {}),
    ("immunity", {"localCooldown": -1}), ("immunity", {"localCooldown": 601}),
    ("immunity", {"localCooldown": True}), ("immunity", {"localCooldown": 1.5}),
    ("immunity", {"localCooldown": 2, "mode": "local"}),
    ("immunity", {"localCooldown": 10, "owner": True}),
    ("updatesPerTick", 0), ("updatesPerTick", 7), ("updatesPerTick", True),
    ("updatesPerTick", 1.5),
])
def test_collision_rejects_ambiguous_choices_and_noninteger_updates(name, value):
    document = build_capability_witness("projectile_collision")
    selected(document)["params"][name] = value
    assert not validate_runtime_program(document)["ok"]
    with pytest.raises(ValueError):
        compile_runtime_program(document)


# Every anchor is exercised in both structural variants. Height and delay use
# the same independent leaf projectors for every anchor: distribute their
# minimum/interior/maximum witnesses instead of crossing every pair again.
@pytest.mark.parametrize("anchor,wire_anchor,height,delay", [
    ("activation_origin", "item_use_origin", None, 0),
    ("activation_origin", "item_use_origin", 1, 0),
    ("owner_center", "owner_center", None, 0),
    ("owner_center", "owner_center", 7.25, 19),
    ("cursor", "cursor", None, 0),
    ("cursor", "cursor", 80, 600),
    ("ground_at_cursor", "ground_at_cursor", None, 0),
    ("ground_at_cursor", "ground_at_cursor", 7.25, 19),
    ("native_resting_spot", "native_resting_spot", None, 0),
    ("native_resting_spot", "native_resting_spot", 80, 600),
])
def test_spawn_position_keeps_all_anchors_height_delay_aim_and_ids(anchor, wire_anchor, height, delay):
    document = build_capability_witness("spawn")
    call = selected(document)
    call["params"].update(position=({"at": anchor} if height is None else {
        "above": anchor, "heightTiles": height, 'activationDelay': (delay) / 60,
    }), aim="velocity", offsetBlocks=(-37) / 16)
    wire, entity = compiled_entity(document, call)
    assert entity["spawn"]["placement"] == wire_anchor
    assert entity["spawn"]["overTarget"] == {"heightTiles": height or 0, "delayTicks": delay}
    assert entity["spawn"]["aim"] == "velocity" and entity["spawn"]["offsetPx"] == -37
    assert entity["id"] == call["target"]
    relevant = [r for r in wire["runtimeContract"]["finalWireReceipts"] if r.get("callId") == call["id"]]
    assert len([r for r in relevant if ".params.position" in r["authoredPath"]]) == 3


@pytest.mark.parametrize("position", [
    {}, {"at": "above_cursor"}, {"at": "cursor", "activationDelay": 1 / 60},
    {"at": "cursor", "above": "cursor", "heightTiles": 3, "activationDelay": 0},
    {"above": "cursor", "heightTiles": 0, "activationDelay": 0},
    {"above": "cursor", "heightTiles": 3},
    {"above": "cursor", "heightTiles": 3, "activationDelay": True},
])
def test_spawn_position_rejects_ambiguous_missing_and_unreviewed_delay_variants(position):
    document = build_capability_witness("spawn")
    selected(document)["params"]["position"] = position
    assert not validate_runtime_program(document)["ok"]


@pytest.mark.parametrize("fn,name,wire_name,lo,hi", [
    ("damage_nearby_on_event", "radius", "radiusPx", 8, 960),
])
# Each owner retains both bounds, a non-boundary exact pixel, and every
# rejection class. Extra interior pixels repeat the same exact projection.
@pytest.mark.parametrize("case", ["minimum", "next-pixel", "maximum", "below", "above", "off-step", "boolean"])
def test_tile_radius_boundaries_keep_exact_pixel_projection(fn, name, wire_name, lo, hi, case):
    spec = CAPABILITY_REGISTRY[fn].params[name]
    assert (spec.minimum, spec.maximum, spec.multiple_of) == (lo / 16, hi / 16, 1 / 16)
    pixels = {"minimum": lo, "next-pixel": lo + 1,
              "maximum": hi, "below": lo - 1, "above": hi + 1, "off-step": lo + .5, "boolean": 16}[case]
    document = build_capability_witness(fn)
    call = selected(document)
    call["params"][name] = True if case == "boolean" else pixels / 16
    before = deepcopy(document)
    if case in {"below", "above", "off-step", "boolean"}:
        report = validate_runtime_program(document)
        assert not report["ok"] and any(e["path"].endswith(".params." + name) for e in report["errors"])
        with pytest.raises(ValueError, match="runtime program rejected"):
            compile_runtime_program(document)
    else:
        assert type(spec.to_wire(pixels / 16)) is int and spec.to_wire(pixels / 16) == pixels
        _, entity = compiled_entity(document, call)
        output = entity["events"][0] if fn == "damage_nearby_on_event" else entity["movement"]["params"]
        assert output[wire_name] == pixels and type(output[wire_name]) is int
    assert document == before


@pytest.mark.parametrize("when", ["on_hit", "on_crit"])
def test_owner_pull_uses_exact_old_action_and_ignores_no_authored_radius(when):
    document = build_capability_witness("pull_on_event")
    selected(document)["params"] = {"when": "on_hit", "mode": "owner_to_target", "impulseBlocksPerSecond": 7.5}
    call = selected(document)
    call["params"].update(when=when, impulseBlocksPerSecond=11.71875, delay=(37) / 60)
    wire, entity = compiled_entity(document, call)
    event = entity["events"][0]
    assert event == {
        "id": "witness_call", "action": "pull_on_event", "actionCode": 5,
        "event": when, "mode": "owner_to_target", "strength": 3.125, "delayTicks": 37,
    }
    relevant = [r for r in wire["runtimeContract"]["finalWireReceipts"] if r.get("callId") == call["id"]]
    for literal in ("action", "actionCode"):
        receipt = next(r for r in relevant if r["finalPath"].endswith("." + literal))
        assert receipt["authoredPath"].endswith(".fn") and receipt["status"] == "technical_projection"
    hostile = deepcopy(document)
    selected(hostile)["params"]["radius"] = 37
    assert not validate_runtime_program(hostile)["ok"]
    npc = build_capability_witness("pull_on_event")
    selected(npc)["params"]["mode"] = "owner_to_target"
    assert not validate_runtime_program(npc)["ok"]


@pytest.mark.parametrize("mutation", ["discriminator", "missing", "duplicate", "source"])
def test_owner_pull_discriminator_receipts_bind_the_exact_existing_executor(mutation):
    document = build_capability_witness("pull_on_event")
    selected(document)["params"] = {"when": "on_hit", "mode": "owner_to_target", "impulseBlocksPerSecond": 7.5}
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
        action["authoredPath"] = action["authoredPath"].removesuffix(".fn") + ".params.impulseBlocksPerSecond"
    for source in (None, document):
        report = audit_compiler_receipts(receipts, authored_document=source, final_document=wire)
        assert not report["ok"]
        assert any("fixed wire literal" in row["reason"] for row in report["violations"])


# The shared event-trigger schema owns malformed interval shapes. Other
# consumers keep a routed negative sentinel rather than copying the full matrix.
@pytest.mark.parametrize("fn,when", [
    *(pytest.param("spawn_on_event", when, id="spawn-" + label) for label, when in (
        ("null", None), ("empty", {}), ("bare-periodic", "periodic"),
        ("below", {"everySeconds": 5 / 60}), ("above", {"everySeconds": 3601 / 60}),
        ("rounds-below-minimum", {"everySeconds": 5.49 / 60}), ("boolean", {"everySeconds": True}),
        ("extra-field", {"everySeconds": 0.1, "event": "on_hit"}),
    )),
    pytest.param("pull_on_event", {"everySeconds": 5 / 60}, id="pull-interval-bound"),
    pytest.param("pull_on_event", {"everySeconds": 0.1, "event": "on_hit"}, id="owner-pull-extra-field"),
])
def test_periodic_trigger_requires_one_explicit_integer_interval(fn, when):
    document = build_capability_witness(fn)
    selected(document)["params"]["when"] = when
    assert not validate_runtime_program(document)["ok"]


def test_root_spawn_fields_are_omittable_only_for_exact_child_kind():
    document = build_capability_witness("spawn_on_event")
    spawn = next(row for row in document["runtimeProgram"]["calls"]
                 if row["fn"] == "spawn" and row["target"] == "witness_child")
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
            binding["action"]["targetId"] = "witness_child"
            document["runtimeProgram"]["bindings"].append(binding)
        errors = validate_runtime_program(document)["errors"]
        assert {r["path"].rsplit(".", 1)[-1] for r in errors if r["code"] == "missing_dependency_param"} == {"count", "spreadRadians"}
    assert not audit_compiler_receipts(receipts, authored_document=document, final_document=wire)["ok"]
    forged_wire = deepcopy(wire)
    next(e for e in forged_wire["runtimeProgram"]["entities"] if e["id"] == "witness_child")["kind"] = "free_projectile"
    assert not audit_compiler_receipts(receipts, final_document=forged_wire)["ok"]


@pytest.mark.parametrize("movement", ["move_straight", "accelerate_y", "return_when", "seek"])
@pytest.mark.parametrize("tile_collide", [False, True])
def test_bounce_omission_is_limited_to_exact_inactive_consumer_branches(movement, tile_collide):
    document = build_capability_witness(movement)
    collision = selected(document, "projectile_collision")
    collision["params"].update(tileCollide=tile_collide, bounceCount=17)
    _, explicit = compiled_entity(document, collision)
    assert explicit["collision"]["bounceCount"] == 17
    collision["params"].pop("bounceCount")
    allowed = not tile_collide
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
    collision = selected(document, "projectile_collision")
    collision["params"].pop("bounceCount")
    collision["params"]["tileCollide"] = "invalid_boolean"
    report = validate_runtime_program(document)
    scope = build_runtime_repair_scope(document, report["errors"])
    candidate = deepcopy(collision)
    candidate["params"].update(tileCollide=new_tile, bounceCount=7, pierce=99)
    filtered, audit = filter_repair_patch_scope(document, {"note": "choose collision", "callsUpsert": [candidate]}, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(document, filtered)
    result = selected(repaired, "projectile_collision")["params"]
    assert result["pierce"] == collision["params"]["pierce"]
    assert result["bounceCount"] == 7  # exact missing leaf was a current deterministic error
    assert validate_runtime_program(repaired)["ok"]


def test_omitted_bounce_stays_absent_during_unrelated_repair():
    document = build_capability_witness("move_straight")
    collision = selected(document, "projectile_collision")
    collision["params"].update(tileCollide=False, pierce=101)
    collision["params"].pop("bounceCount")
    scope = build_runtime_repair_scope(document, validate_runtime_program(document)["errors"])
    candidate = deepcopy(collision)
    candidate["params"].update(pierce=3, bounceCount=7, tileCollide=True)
    filtered, audit = filter_repair_patch_scope(document, {"note": "repair pierce", "callsUpsert": [candidate]}, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(document, filtered)
    result = selected(repaired, "projectile_collision")["params"]
    assert result["tileCollide"] is False and "bounceCount" not in result
    assert result["pierce"] == 3 and validate_runtime_program(repaired)["ok"]


@pytest.mark.parametrize("delete_motion", ["witness_call", "other_motion"])
@pytest.mark.parametrize("author_bounce", [False, True])
def test_repair_movement_conflict_cannot_invent_an_active_collision_choice(delete_motion, author_bounce):
    document = build_capability_witness("move_straight")
    collision = selected(document, "projectile_collision")
    collision["params"].pop("bounceCount")
    collision["params"]["tileCollide"] = True
    motion = selected(document)
    document["runtimeProgram"]["calls"].append({
        "id": "other_motion", "fn": "move_straight", "target": motion["target"],
    })
    errors = validate_runtime_program(document)["errors"]
    assert {row["code"] for row in errors} == {"exclusive_component_conflict", "duplicate_single_component", "missing_dependency_param"}
    scope = build_runtime_repair_scope(document, errors)
    assert next(row["paths"] for row in scope["fieldPermissions"]["calls"]
                if row["id"] == collision["id"]) == ["params.bounceCount"]
    candidate = deepcopy(collision)
    candidate["params"].update(pierce=99, **({"bounceCount": 7} if author_bounce else {}))
    filtered, audit = filter_repair_patch_scope(document, {
        "note": "keep one movement and choose collision", "callsUpsert": [candidate], "callIdsDelete": [delete_motion],
    }, scope)
    assert audit["ok"] is author_bounce, audit
    repaired = apply_repair_patch(document, filtered)
    result = selected(repaired, "projectile_collision")["params"]
    assert result["pierce"] == collision["params"]["pierce"]
    if author_bounce:
        _, entity = compiled_entity(repaired, selected(repaired, "projectile_collision"))
        assert entity["collision"]["bounceCount"] == result["bounceCount"] == 7
    else:
        assert "bounceCount" not in result
        assert {row["code"] for row in validate_runtime_program(repaired)["errors"]} == {"missing_dependency_param"}
        with pytest.raises(ValueError):
            compile_runtime_program(repaired)


@pytest.mark.parametrize("fn,broken,value,frozen_key,hostile", [
    ("projectile_collision", {"immunity": {"localCooldown": 601}}, {"immunity": {"localCooldown": 19}}, "pierce", 99),
    ("pull_on_event", {"when": {"everySeconds": 5 / 60}}, {"when": {"everySeconds": 19 / 60}}, "impulseBlocksPerSecond", 15),
    ("spawn", {"position": {"above": "cursor", "heightTiles": 81, "activationDelay": 37 / 60}},
     {"position": {"above": "owner_center", "heightTiles": 19, "activationDelay": 2 / 60}}, "count", 12),
])
def test_nested_repair_changes_only_the_broken_leaf(fn, broken, value, frozen_key, hostile):
    document = build_capability_witness(fn)
    call = selected(document)
    call["params"].update(deepcopy(broken))
    errors = validate_runtime_program(document)["errors"]
    scope = build_runtime_repair_scope(document, errors)
    paths = next(row["paths"] for row in scope["fieldPermissions"]["calls"] if row["id"] == call["id"])
    leaf = {"projectile_collision": "immunity.localCooldown", "pull_on_event": "when.everySeconds",
            "spawn": "position.heightTiles"}[fn]
    assert paths == ["params." + leaf]
    if fn == "projectile_collision":
        assert any(e["code"] == "shape_maximum" and e["path"].endswith(".immunity.localCooldown") for e in errors)
    candidate = deepcopy(call)
    candidate["params"].update(deepcopy(value), **{frozen_key: hostile})
    filtered, audit = filter_repair_patch_scope(document, {"note": "repair exact leaf", "callsUpsert": [candidate]}, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(document, filtered)
    actual = selected(repaired)["params"]
    assert actual[frozen_key] == call["params"][frozen_key]
    if fn == "spawn":
        assert actual["position"] == {"above": "cursor", "heightTiles": 19, "activationDelay": 37 / 60}
    assert validate_runtime_program(repaired)["ok"]


@pytest.mark.parametrize("fn", ["spawn_over_target", "move_bounce", "move_gravity_arc", "move_orbit",
                                  "move_boomerang", "move_proximity_missile", "channel_beam", "charge_then_release"])
def test_retired_author_call_is_absent_from_schema_prompt_and_repair(fn):
    from infini_local.core.runtime_authoring.registry_views import capability_provider_union, compact_capability_catalog
    from infini_local.pipelines.author.request import build_gameplay_repair_dossier
    if fn in CAPABILITY_REGISTRY:
        assert CAPABILITY_REGISTRY[fn].author_visible is False
        with pytest.raises(KeyError, match=fn):
            build_capability_witness(fn)
    assert fn not in {row["fn"] for row in compact_capability_catalog()}
    assert fn not in {row["properties"]["fn"]["const"] for row in capability_provider_union()}
    document = build_capability_witness("move_straight")
    selected(document)["fn"] = fn
    assert not validate_runtime_program(document)["ok"]
    scope = build_runtime_repair_scope(document, validate_runtime_program(document)["errors"])
    assert fn not in scope["create"]["calls"]["allowedFns"]
    dossier = build_gameplay_repair_dossier(document, {}, {}, failure_report=validate_runtime_program(document))
    for section in ("blockerCapabilities", "supportingCapabilities", "existingBrokenCapabilityCards"):
        assert fn not in {row["fn"] for row in dossier[section]}
    assert "move_bounce" not in MOVEMENT_OPCODE and MOVEMENT_OPCODE["move_gravity_arc"] == 2


def test_frozen_retired_receipts_are_negative_evidence_without_rewriting_bytes():
    path = Path(__file__).with_name("fixtures") / "projectile_retained_wire.json"
    corpus = json.loads(path.read_text())
    assert corpus["sourceHead"] == "a3d5950"
    for row in corpus["cases"]:
        wire = row["wire"]
        before = json.dumps(wire, sort_keys=True)
        receipts = wire["runtimeContract"]["finalWireReceipts"]
        assert not validate_runtime_wire(wire)["ok"], row["fn"]
        report = audit_compiler_receipts(receipts, final_document=wire)
        assert not report["ok"], (row["fn"], report)
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
    assert not audit_compiler_receipts(parameters)["ok"]
    source_index = int(parameters[0]["authoredPath"].split("calls[")[1].split("]")[0])
    params = {}
    for row in parameters:
        name = row["authoredPath"].split(".params.")[1]
        params[name] = row["value"]
    source_calls = [None] * source_index + [{"id": "witness_call", "fn": fn, "target": "old", "params": params}]
    source = {"runtimeProgram": {"calls": source_calls}}
    missing_schema = audit_compiler_receipts(parameters, authored_document=source)
    assert not missing_schema["ok"]
    assert missing_schema["violations"][0]["reason"] == "source provenance requires the sole current Author grammar"
    from infini_local.core.runtime_authoring.capability_registry import RUNTIME_PROGRAM_SCHEMA
    report = audit_compiler_receipts(parameters, authored_document={
        "runtimeProgram": {"schema": RUNTIME_PROGRAM_SCHEMA, "calls": source_calls},
    })
    assert not report["ok"]
    assert any(row["reason"] == "compiler receipt used an undeclared input or output field" for row in report["violations"])


@pytest.mark.parametrize("attack", ["cooldown-domain", "hybrid-variant", "missing-literal", "duplicate", "foreign-source", "spawn-domain"])
@pytest.mark.parametrize("source_available", [False, True])
def test_actual_typed_alias_receipts_require_one_complete_valid_projection(attack, source_available):
    fn = "spawn" if attack == "spawn-domain" else "projectile_collision"
    document = build_capability_witness(fn)
    call = selected(document)
    if fn == "spawn":
        call["params"]["position"] = {"above": "cursor", "heightTiles": 1, 'activationDelay': (0) / 60}
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
        elif attack == "foreign-source":
            row["authoredPath"] += ".foreign"
        else:
            receipts.append(deepcopy(row))
    assert not audit_compiler_receipts(receipts, authored_document=document if source_available else None,
                                       final_document=wire)["ok"]


@pytest.mark.parametrize("missing", [False, True])
def test_retired_spawn_receipt_owner_is_refused_even_with_complete_outputs(missing):
    corpus = json.loads((Path(__file__).with_name("fixtures") / "projectile_retained_wire.json").read_text())
    wire = deepcopy(next(row["wire"] for row in corpus["cases"] if row["fn"] == "spawn_over_target"))
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    if missing:
        receipts[:] = [r for r in receipts if not (r.get("fn") == "spawn_over_target"
                                                   and r["finalPath"].endswith(".overTarget.heightTiles"))]
    before = deepcopy(wire)
    assert not audit_compiler_receipts(receipts, final_document=wire)["ok"]
    assert wire == before


@pytest.mark.parametrize("delay", [0, 2])
def test_hit_pull_to_entity_retains_explicit_mode_and_delay(delay):
    document = build_capability_witness("pull_on_event")
    call = selected(document)
    call["params"].update(when="on_hit", mode="target_to_entity", impulseBlocksPerSecond=7.5, radius=10, delay=(delay) / 60)
    assert validate_runtime_program(document)["ok"]
    wire, entity = compiled_entity(document, call)
    event = entity["events"][0]
    assert event["event"] == "on_hit" and event["mode"] == "target_to_entity"
    assert event["strength"] == 2 and event["radiusTiles"] == 10 and event["delayTicks"] == delay
    assert audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"],
                                   authored_document=document, final_document=wire)["ok"]

@pytest.mark.parametrize("fn", ["configure_placeable", "move_bounce", "spawn_over_target", "chain_damage_on_event"])
def test_retired_internal_capabilities_have_no_receipt_owner(fn):
    assert fn not in CAPABILITY_REGISTRY


def test_reserved_movement_six_is_refused_without_renumbering_current_codes():
    document = build_capability_witness("move_straight")
    wire = compile_runtime_program(document)
    wire.pop("runtimeContract")
    entity = next(e for e in wire["runtimeProgram"]["entities"] if "movement" in e)
    entity["movement"].update(code=6, name="")
    assert not validate_runtime_wire(wire)["ok"]
    assert MOVEMENT_OPCODE["move_forward_then_retract"] == 19
    assert MOVEMENT_OPCODE["move_front_hand"] == 20


@pytest.mark.parametrize("current,retired", [("place_tile", "configure_placeable"),
                                           ("damage_nearby_on_event", "chain_damage_on_event")])
def test_retired_receipt_owner_cannot_authenticate_current_mechanics(current, retired):
    document = build_capability_witness(current)
    wire = compile_runtime_program(document)
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    assert audit_compiler_receipts(receipts, final_document=wire)["ok"]
    for row in receipts:
        if row.get("callId") == "witness_call":
            row["fn"] = retired
    assert not audit_compiler_receipts(receipts, final_document=wire)["ok"]


@pytest.mark.parametrize("value,accepted", [
    (0.0000625, True), (4.5 / 16, True), (32, True),
    (0, False), (32.0001, False), (True, False), (None, False),
])
def test_independent_proximity_radius_uses_float_pixels_not_retired_integer_lattice(value, accepted):
    fn = "proximity_action"
    spec = CAPABILITY_REGISTRY[fn].params["triggerRadiusBlocks"]
    assert (spec.minimum, spec.maximum, spec.multiple_of) == (0.0000625, 32, None)
    document = build_capability_witness(fn)
    call = selected(document)
    call["params"]["triggerRadiusBlocks"] = value
    before = deepcopy(document)
    report = validate_runtime_program(document)
    assert report["ok"] is accepted, report
    if accepted:
        wire, entity = compiled_entity(document, call)
        assert entity["proximity"]["triggerRadiusPx"] == value * 16
        assert "homing" not in entity and "seek" not in entity
        rows = [r for r in wire["runtimeContract"]["finalWireReceipts"]
                if r.get("callId") == call["id"] and r["authoredPath"].endswith(".params.triggerRadiusBlocks")]
        assert len(rows) == 1 and rows[0]["value"] == value * 16
        assert rows[0]["finalPath"].endswith(".proximity.triggerRadiusPx")
    else:
        assert any(e["path"].endswith(".params.triggerRadiusBlocks") for e in report["errors"])
        with pytest.raises(ValueError):
            compile_runtime_program(document)
    assert document == before


@pytest.mark.parametrize("pixels,accepted", [(4, True), (5, True), (512, True), (3, False), (513, False), (4.5, False), (True, False)])
def test_retained_proximity_opcode_keeps_its_integer_pixel_domain(pixels, accepted):
    # Explicit saved-wire control, not a compiler/importer for retired Author calls.
    wire = compile_runtime_program(build_capability_witness("move_straight"))
    wire.pop("runtimeContract")
    entity = next(e for e in wire["runtimeProgram"]["entities"] if "movement" in e)
    entity["movement"] = {"name": "move_proximity_missile", "code": 13,
                          "params": {"rangeTiles": 20, "homingStrength": 0.1, "proximityRadiusPx": pixels}}
    before = deepcopy(wire)
    assert validate_runtime_wire(wire)["ok"] is accepted
    assert wire == before

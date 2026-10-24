"""Current Author units and the unchanged saved-runtime boundary, without fixture adapters."""
from copy import deepcopy
from typing import Any

import pytest

from infini_local.core.runtime_authoring.capability_registry import (
    CAPABILITY_REGISTRY, RUNTIME_PROGRAM_SCHEMA,
)
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire


def call(fn, params, target="body", ident=None):
    return {"id": ident or fn, "fn": fn, "target": target, "params": params}


def item_document():
    return {"name": "Clock", "category": "consumable", "runtimeProgram": {
        "apiVersion": "infini.runtime-program.v5", "schema": "infini.runtime-program.authoring.v6",
        "primaryEntityId": "body", "entities": [{"id": "body", "kind": "item_body"}],
        "bindings": [{"id": "use", "input": "primary_use", "action": {
            "kind": "apply_item_effects"}, "stackCost": 0, "contactDamage": False}],
        "calls": [call("configure_item_stats", {"damage": 0, "damageClass": "generic",
            "knockback": 0, "useTimeSeconds": 0.025,
            "useAnimationSeconds": 0.025, "manaCost": 0, "rarity": 0,
            "valueCopper": 0, "maxStack": 1, "craftYield": 1, "widthPx": 16,
            "heightPx": 16, "scale": 1}),
            call("configure_item_use", {"useStyle": "hold_up", "autoReuse": False,
                "useTurn": False, "hideUseGraphic": False, "disableMeleeHitbox": True, "channel": False}),
            call("apply_vanilla_buff_on_use", {"buffId": 1, "durationSeconds": 1.5})],
    }}


def test_seconds_lower_to_world_ticks_without_mutating_author():
    assert RUNTIME_PROGRAM_SCHEMA == "infini.runtime-program.authoring.v6"
    source = item_document()
    before = deepcopy(source)
    report = validate_runtime_program(source)
    assert report["ok"], report
    wire = compile_runtime_program(source)
    assert wire["gameplay"]["useTime"] == 2  # 1.5 ticks: ties up, not bankers rounding.
    assert wire["gameplay"]["extraBuffs"][0]["buffTime"] == 90
    assert source == before
    assert validate_runtime_wire(wire)["ok"]
    source["runtimeProgram"]["schema"] = "infini.runtime-program.authoring.v5"
    assert not validate_runtime_program(source)["ok"]


def test_projection_metadata_and_target_update_context():
    spec = CAPABILITY_REGISTRY["move_gravity_arc"].params["accelerationYBlocksPerSecondSquared"]
    assert spec.to_wire(900, updates_per_tick=2) == 1
    card = spec.wire_projection_card()
    assert card["predecessorNames"] == ["accelY"]
    assert card["updatesPerTickPower"] == 2
    assert card["wireMinimum"] == -2 and card["wireMaximum"] == 2
    with pytest.raises(ValueError, match="updatesPerTick"):
        spec.to_wire(900)


def projectile_document(updates=2):
    source = item_document()
    program = source["runtimeProgram"]
    program["primaryEntityId"] = "shot"
    program["entities"].append({"id": "shot", "kind": "free_projectile"})
    program["bindings"][0]["action"] = {"kind": "spawn_entity", "targetId": "shot"}
    program["calls"] = program["calls"][:2] + [
        call("configure_spawn", {"velocity": {"constantSpeedBlocksPerSecond": 120},
            "count": 1, "spreadRadians": 0, "offsetBlocks": 0.5,
            "aim": "cursor", "position": {"above": "activation_origin", "heightTiles": 2,
                "activationDelaySeconds": 0.025}}, "shot"),
        call("set_projectile_lifetime", {"lifetimeSeconds": 2.5}, "shot"),
        call("set_projectile_hitbox", {"widthPx": 16, "heightPx": 16, "drawScale": 1, "hitboxScale": 1}, "shot"),
        call("set_projectile_collision", {"tileCollide": False, "ignoreWater": False,
            "pierce": 1, "updatesPerTick": updates, "immunity": {"localCooldown": 10}}, "shot"),
        call("set_projectile_damage", {"damageClass": "generic", "damage": 10, "knockback": 1, "ownerHitCheck": False}, "shot"),
        call("move_gravity_arc", {"accelerationYBlocksPerSecondSquared": 900}, "shot"),
    ]
    return source


def test_contextual_projectile_projection_and_strict_source_audit():
    from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
    source = projectile_document()
    report = validate_runtime_program(source)
    assert report["ok"], report
    wire = compile_runtime_program(source)
    shot = next(e for e in wire["runtimeProgram"]["entities"] if e["id"] == "shot")
    assert shot["spawn"]["speedPxPerTick"] == 16
    assert shot["spawn"]["offsetPx"] == 8
    assert shot["spawn"]["overTarget"]["delayTicks"] == 2
    assert shot["lifetimeTicks"] == 150
    assert shot["movement"]["params"]["gravityPerTick"] == 1
    assert shot["collision"]["extraUpdates"] == 1
    assert shot["collision"]["localNpcHitCooldownTicks"] == 10
    assert validate_runtime_wire(wire)["ok"]
    rows = wire["runtimeContract"]["finalWireReceipts"]
    assert audit_compiler_receipts(rows, authored_document=source, final_document=wire)["ok"]
    predecessor = deepcopy(rows)
    for row in predecessor:
        if "authoredPath" not in row:
            continue
        row["authoredPath"] = (row["authoredPath"]
            .replace("accelerationYBlocksPerSecondSquared", "accelY")
            .replace("constantSpeedBlocksPerSecond", "constantSpeedPxPerUpdate")
            .replace("lifetimeSeconds", "lifetimeTicks")
            .replace("activationDelaySeconds", "activationDelayTicks")
            .replace("offsetBlocks", "offsetPx")
            .replace("useTimeSeconds", "useTimeTicks")
            .replace("useAnimationSeconds", "useAnimationTicks"))
    before_audit = deepcopy(predecessor)
    assert audit_compiler_receipts(predecessor, final_document=wire)["ok"]
    assert predecessor == before_audit
    assert not audit_compiler_receipts(predecessor, authored_document=source, final_document=wire)["ok"]


@pytest.mark.parametrize("seconds", [0, 0.001, 10.01])
def test_seconds_engine_bounds_and_nonzero_collapse_are_refused(seconds):
    source = item_document()
    source["runtimeProgram"]["calls"][0]["params"]["useTimeSeconds"] = seconds
    before = deepcopy(source)
    assert not validate_runtime_program(source)["ok"]
    assert source == before


@pytest.mark.parametrize("updates", range(1, 7))
def test_full_predecessor_speed_and_acceleration_range_remains_reachable(updates):
    cap = CAPABILITY_REGISTRY["configure_spawn"].params["velocity"]
    speed = cap.alternatives[0].properties["constantSpeedBlocksPerSecond"]
    gravity = CAPABILITY_REGISTRY["move_gravity_arc"].params["accelerationYBlocksPerSecondSquared"]
    for spec, engines in ((speed, (0, 80)), (gravity, (-2, 0, 2))):
        for engine in engines:
            author = spec.from_wire(engine, updates_per_tick=updates)
            assert spec.minimum <= author <= spec.maximum
            assert spec.to_wire(author, updates_per_tick=updates) == engine
            assert spec.consumer_value_error(author, updates_per_tick=updates) is None
            assert spec.matches_scalar_projection(engine)


@pytest.mark.parametrize("fn,params,member,expected", [
    ("set_projectile_turn_modifier", {"turnRadiansPerSecond": 12, "startDelaySeconds": 0.025, "durationSeconds": 0.5},
        "turnModifier", {"turnRadiansPerUpdate": 0.1, "startDelayTicks": 2, "durationTicks": 30}),
    ("set_projectile_speed_modifier", {"speedMultiplierPerUpdate": 1.1, "maxSpeedBlocksPerSecond": 120,
        "startDelaySeconds": 0, "durationSeconds": 0.5}, "speedModifier", {"maxSpeed": 16, "durationTicks": 30}),
    ("set_projectile_hitbox_curve", {"startScale": 1, "endScale": 2, "startDelaySeconds": 0.025,
        "durationSeconds": 0.5, "mirrorToSprite": False, "curve": "linear"}, "hitboxCurve", {"startDelayTicks": 2, "durationTicks": 30}),
])
def test_modifier_wire_stays_in_engine_domains(fn, params, member, expected):
    source = projectile_document()
    source["runtimeProgram"]["calls"].append(call(fn, params, "shot"))
    report = validate_runtime_program(source)
    assert report["ok"], report
    wire = compile_runtime_program(source)
    shot = next(e for e in wire["runtimeProgram"]["entities"] if e["id"] == "shot")
    for key, value in expected.items():
        assert shot[member][key] == pytest.approx(value)
    report = validate_runtime_wire(wire)
    assert report["ok"], report
    stripped = deepcopy(wire)
    stripped.pop("runtimeContract")
    assert validate_runtime_wire(stripped)["ok"]


def world_leaves(spec):
    if spec.alternatives:
        for variant in spec.alternatives:
            yield from world_leaves(variant)
    elif spec.properties:
        for leaf in spec.properties.values():
            yield from world_leaves(leaf)
    elif spec.wire_kind:
        yield spec


def test_all_declared_engine_endpoints_remain_reachable_for_every_target_clock():
    for cap in CAPABILITY_REGISTRY.values():
        for root in cap.params.values():
            for spec in world_leaves(root):
                for endpoint in (spec.minimum, spec.maximum):
                    if endpoint is not None:
                        assert any(spec.consumer_value_error(endpoint, updates_per_tick=clock) is None
                                   for clock in range(1, 7)), (cap.name, endpoint)
                for updates in range(1, 7):
                    if spec.wire_updates_power:
                        # The model-facing clock card must expose admissible
                        # endpoints too, not only the fixture inverse below.
                        for endpoint in spec.contextual_author_bounds(updates_per_tick=updates).values():
                            if endpoint is not None:
                                assert spec.consumer_value_error(endpoint, updates_per_tick=updates) is None, (cap.name, updates, endpoint)
                    for engine in (spec.wire_minimum, spec.wire_maximum):
                        if engine is None:
                            continue
                        value = spec.from_wire(engine, updates_per_tick=updates)
                        assert spec.minimum <= value <= spec.maximum, (cap.name, spec.predecessor_names, value)
                        assert spec.consumer_value_error(value, updates_per_tick=updates) is None, (cap.name, spec.predecessor_names, updates, engine, value)
                        assert spec.matches_scalar_projection(engine), (cap.name, spec.predecessor_names, engine)


def test_author_cards_explain_human_constraints_without_saved_receipt_or_engine_tables():
    import json
    card = CAPABILITY_REGISTRY["configure_spawn"].author_prompt_card()
    text = json.dumps(card)
    assert "predecessorNames" not in text
    assert "wireMinimum" not in text
    assert "constantSpeedPxPerUpdate" not in text
    speed = CAPABILITY_REGISTRY["configure_spawn"].params["velocity"].alternatives[0].properties["constantSpeedBlocksPerSecond"]
    assert speed.author_projection_card()["boundsAtUpdatesPerTick1To6"][5][1] == 1800
    assert CAPABILITY_REGISTRY["set_projectile_collision"].params["updatesPerTick"].wire_projection_card()["offset"] == -1


def test_half_tick_rounding_is_up_only_at_the_actual_tie():
    import math
    spec = CAPABILITY_REGISTRY["configure_item_stats"].params["useTimeSeconds"]
    tie = 1 / 120
    assert spec.to_wire(tie) == 1
    assert spec.to_wire(math.nextafter(tie, 0)) == 0
    assert spec.consumer_value_error(math.nextafter(tie, 0)) is not None
    assert spec.to_wire(math.nextafter(tie, math.inf)) == 1
    assert spec.to_wire(0.025) == 2


def test_hit_target_world_geometry_uses_blocks_but_keeps_algorithm_counters():
    geometry = CAPABILITY_REGISTRY["spawn_entity_from_hit_target"].params["geometry"]
    assert geometry.properties["clearanceBlocks"].to_wire(1.5) == 24
    assert geometry.properties["beforePositionJitterRadiusBlocks"].to_wire(2) == 32
    assert "clearancePx" not in geometry.properties
    assert "beforePositionJitterRadiusPx" not in geometry.properties
    counter = geometry.properties["initialIgnoreCountdownUpdates"]
    assert not counter.wire_kind and counter.kind == "integer"


def test_child_velocity_uses_the_child_clock_including_nested_distributions():
    source = projectile_document()
    program = source["runtimeProgram"]
    program["entities"].append({"id": "child", "kind": "child_projectile"})
    child_calls = []
    for original in program["calls"]:
        if original["target"] != "shot":
            continue
        child = deepcopy(original)
        child["id"] += "_child"
        child["target"] = "child"
        if child["fn"] == "set_projectile_collision":
            child["params"]["updatesPerTick"] = 4
        elif child["fn"] == "configure_spawn":
            child["params"]["velocity"] = {"disk": {"maxSpeedBlocksPerSecond": 120}}
        child_calls.append(child)
    program["calls"].extend(child_calls)
    program["calls"].append(call("spawn_entity_on_event", {"when": {"everySeconds": 0.1},
        "entity": "child", "count": 1, "spreadRadians": 0, "damageBasis": "authored_child",
        "knockbackBasis": "authored_child", "damageMultiplier": 1, "delaySeconds": 0.025}, "shot"))
    report = validate_runtime_program(source)
    assert report["ok"], report
    wire = compile_runtime_program(source)
    entities = {e["id"]: e for e in wire["runtimeProgram"]["entities"]}
    assert entities["shot"]["spawn"]["speedPxPerTick"] == 16
    assert entities["child"]["spawn"]["velocityDistribution"]["maxSpeedPxPerUpdate"] == 8
    assert entities["child"]["movement"]["params"]["gravityPerTick"] == 0.25
    assert entities["shot"]["events"][0]["periodTicks"] == 6
    assert entities["shot"]["events"][0]["delayTicks"] == 2
    report = validate_runtime_wire(wire)
    assert report["ok"], report


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "wrong_target", "bad_counter"])
def test_context_never_defaults_missing_or_ambiguous_target_clocks(mutation):
    source = projectile_document()
    calls = source["runtimeProgram"]["calls"]
    collision = next(c for c in calls if c["fn"] == "set_projectile_collision")
    if mutation == "missing":
        calls.remove(collision)
    elif mutation == "duplicate":
        duplicate = deepcopy(collision)
        duplicate["id"] += "_duplicate"
        calls.append(duplicate)
    elif mutation == "wrong_target":
        collision["target"] = "body"
    else:
        collision["params"]["updatesPerTick"] = 2.5
    before = deepcopy(source)
    assert not validate_runtime_program(source)["ok"]
    assert source == before


@pytest.mark.parametrize("updates,accepted", [(1, False), (6, True)])
def test_full_human_speed_range_is_contextually_bounded_not_globally_shrunk(updates, accepted):
    source = projectile_document(updates)
    spawn = next(c for c in source["runtimeProgram"]["calls"] if c["fn"] == "configure_spawn")
    spawn["params"]["velocity"] = {"constantSpeedBlocksPerSecond": 1800}
    assert validate_runtime_program(source)["ok"] is accepted


@pytest.mark.parametrize("old,new", [("useTimeTicks", "useTimeSeconds"), ("useAnimationTicks", "useAnimationSeconds")])
def test_predecessor_leaf_names_are_not_fresh_author_aliases(old, new):
    source = item_document()
    params = source["runtimeProgram"]["calls"][0]["params"]
    params[old] = params.pop(new)
    assert not validate_runtime_program(source)["ok"]


def test_non_time_integer_lattices_and_float32_signed_neutrals_remain_exact():
    import math
    offset = CAPABILITY_REGISTRY["configure_spawn"].params["offsetBlocks"]
    regen = CAPABILITY_REGISTRY["configure_accessory"].params["lifeRegenHpPerSecond"]
    gravity = CAPABILITY_REGISTRY["move_gravity_arc"].params["accelerationYBlocksPerSecondSquared"]
    with pytest.raises(ValueError, match="non-integral"):
        offset.to_wire(0.01)
    with pytest.raises(ValueError, match="non-integral"):
        regen.to_wire(0.3)
    assert offset.to_wire(1 / 16) == 1
    assert math.copysign(1, gravity.to_wire(-0.0, updates_per_tick=6)) == -1
    assert gravity.consumer_value_error(-0.0, updates_per_tick=6) is None
    assert gravity.consumer_value_error(1e-320, updates_per_tick=6) is not None


@pytest.mark.parametrize("mutation", ["missing_value", "bad_counter"])
def test_unresolved_clock_does_not_make_valid_world_values_repairable(mutation):
    from infini_local.core.runtime_authoring.repair_scope import build_runtime_repair_scope
    source = projectile_document()
    collision = next(c for c in source["runtimeProgram"]["calls"] if c["fn"] == "set_projectile_collision")
    if mutation == "missing_value":
        del collision["params"]["updatesPerTick"]
    else:
        collision["params"]["updatesPerTick"] = False
    before = deepcopy(source)
    report = validate_runtime_program(source)
    assert not report["ok"]
    assert all(row["code"] != "consumer_representability" for row in report["errors"]), report
    scope = build_runtime_repair_scope(source, report["errors"])
    assert scope["fieldPermissions"]["calls"] == [{
        "id": collision["id"], "paths": ["params.updatesPerTick"]}]
    assert source == before


@pytest.mark.parametrize("retain_receipts", [True, False])
def test_authentic_pre_v6_compiler_wire_remains_readable(retain_receipts):
    """Frozen d288982 compiler output, captured before any unit-migration edits.

    This is an offline capability witness, not a provider response or a promise
    that its image-less intermediate is a fully delivered visual asset.
    Never regenerate this fixture with the current Author/compiler.
    """
    import json
    from pathlib import Path
    path = Path(__file__).with_name("fixtures") / "author_v5_world_unit_wire.json"
    original_bytes = path.read_bytes()
    wire = json.loads(original_bytes)
    assert any(row.get("authoredPath", "").endswith(".params.accelY")
               for row in wire["runtimeContract"]["finalWireReceipts"])
    if not retain_receipts:
        del wire["runtimeContract"]
    before = deepcopy(wire)
    report = validate_runtime_wire(wire)
    assert report["ok"], report
    assert wire == before and path.read_bytes() == original_bytes


def test_saved_predecessor_omission_keeps_its_exact_integer_zero_domain():
    import json
    from pathlib import Path
    path = Path(__file__).with_name("fixtures") / "author_v5_omitted_jump_wire.json"
    wire = json.loads(path.read_bytes())  # Actual pre-v6 compiler, optional jump absent.
    before = deepcopy(wire)
    rows = [r for r in wire["runtimeContract"]["finalWireReceipts"]
            if r.get("authoredPath", "").endswith(".params.jumpSpeedBonusPxPerTick")]
    assert rows and all(r["status"] == "declared_neutral_omission"
                        and type(r["value"]) is int and r["value"] == 0 for r in rows)
    assert validate_runtime_wire(wire)["ok"]
    assert wire == before
    # The legacy token is not granted to a fresh/current source path.
    for row in wire["runtimeContract"]["finalWireReceipts"]:
        row["authoredPath"] = row.get("authoredPath", "").replace(
            "jumpSpeedBonusPxPerTick", "jumpSpeedBonusBlocksPerSecond")
    assert not validate_runtime_wire(wire)["ok"]

def test_converted_native_float_rates_reject_float32_nonzero_collapse():
    def leaves(spec):
        if spec.alternatives:
            for variant in spec.alternatives:
                yield from leaves(variant)
        elif spec.kind == "object":
            for child in spec.properties.values():
                yield from leaves(child)
        else:
            yield spec
    selected = [leaf for cap in CAPABILITY_REGISTRY.values() for root in cap.params.values()
                for leaf in leaves(root) if leaf.wire_kind == "number"
                and leaf.consumer_storage != "float64"
                and (leaf.wire_minimum is None or leaf.wire_minimum <= 0)
                and (leaf.wire_maximum is None or leaf.wire_maximum > 0)]
    assert selected
    for spec in selected:
        n = 2 if spec.requires_update_context else None
        assert spec.to_wire(1e-48, updates_per_tick=n) != 0
        assert spec.consumer_value_error(1e-48, updates_per_tick=n) is not None, spec
        assert spec.consumer_value_error(0.0, updates_per_tick=n) is None, spec


def test_spiral_underflow_is_refused_at_author_leaf_without_mutation():
    source = projectile_document(2)
    source["runtimeProgram"]["calls"][-1] = call(
        "move_spiral", {"turnRadiansPerSecond": 1e-45}, "shot")
    before = deepcopy(source)
    report = validate_runtime_program(source)
    assert not report["ok"]
    assert any(row["code"] == "consumer_representability"
               and row["path"].endswith(".params.turnRadiansPerSecond")
               for row in report["errors"])
    assert source == before


@pytest.mark.parametrize("fn,param,bound_name,bare_outside_accepted", [
    ("set_projectile_homing_modifier", "maxTurnRadiansPerSecond", "minimum", False),
    ("set_projectile_homing_modifier", "maxTurnRadiansPerSecond", "maximum", False),
    ("pull_on_event", "impulseBlocksPerSecond", "minimum", True),
    ("pull_owner_to_event_target", "impulseBlocksPerSecond", "minimum", True),
])
def test_native_float32_engine_endpoints_survive_without_accepting_outside_single(fn, param, bound_name, bare_outside_accepted):
    import struct
    spec = CAPABILITY_REGISTRY[fn].params[param]
    original_bound = getattr(spec, "wire_" + bound_name)
    stored = struct.unpack("!f", struct.pack("!f", original_bound))[0]
    assert spec.matches_scalar_projection(stored)
    assert spec.consumer_value_error(stored, wire_value=True) is None
    bits = struct.unpack("!I", struct.pack("!f", stored))[0]
    upward = bound_name == "maximum"
    adjacent_bits = bits + (1 if (stored > 0) == upward else -1)
    outside = struct.unpack("!f", struct.pack("!I", adjacent_bits))[0]
    assert not spec.matches_scalar_projection(outside)

    # Native serialization has no compiler sidecar: exercise the actual saved
    # wire reader too, not just the scalar helper that feeds receipt admission.
    import re
    from infini_local.qa.capability_witnesses import build_capability_witness
    source = build_capability_witness(fn)
    authored_call = next(c for c in source["runtimeProgram"]["calls"] if c["fn"] == fn)
    authored_call["params"][param] = spec.from_wire(
        original_bound, updates_per_tick=1 if spec.requires_update_context else None)
    wire = compile_runtime_program(source)
    paths = [r["finalPath"] for r in wire["runtimeContract"]["finalWireReceipts"]
             if r.get("fn") == fn and r.get("authoredPath", "").endswith(".params." + param)]
    assert paths
    del wire["runtimeContract"]
    def set_native_value(value):
        for path in paths:
            tokens = re.findall(r"[^.\[\]]+", path.removeprefix("$."))
            owner: Any = wire
            for token in tokens[:-1]:
                owner = owner[int(token)] if isinstance(owner, list) else owner[token]
            owner[tokens[-1]] = value
    set_native_value(stored)
    assert validate_runtime_wire(wire)["ok"]
    set_native_value(outside)
    # Actual predecessor-reader comparison confirms that bare pull event wire
    # retains its older 0..4 domain. Do not shrink it to the narrower .01 Author
    # / receipt threshold while fixing native Single endpoints.
    assert validate_runtime_wire(wire)["ok"] is bare_outside_accepted

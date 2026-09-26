"""Declared full-Author omissions are not inferred mechanics or Repair edits."""
from copy import deepcopy
from itertools import product

import pytest

from infini_local.core.runtime_authoring import (
    compile_runtime_program, validate_runtime_program, validate_runtime_wire,
    CAPABILITY_REGISTRY,
)
from infini_local.qa.capability_witnesses import build_capability_witness


def _call(doc, fn):
    return next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == fn)


def _wire_payload(doc):
    wire = compile_runtime_program(doc)
    assert validate_runtime_wire(wire)["ok"]
    return {key: wire[key] for key in ("runtimeProgram", "gameplay", "accessory", "armor")}


@pytest.mark.parametrize("damage_class", ["melee", "ranged", "magic", "summon", "default"])
def test_mana_omission_is_explicit_zero_for_every_damage_class(damage_class):
    explicit = build_capability_witness("configure_item_stats")
    params = _call(explicit, "configure_item_stats")["params"]
    params.update(damageClass=damage_class, manaCost=0)
    sparse = deepcopy(explicit)
    del _call(sparse, "configure_item_stats")["params"]["manaCost"]
    before = deepcopy(sparse)
    report = validate_runtime_program(sparse)
    assert report["ok"], report["errors"]
    assert _wire_payload(sparse) == _wire_payload(explicit)
    assert sparse == before, "compilation must preserve the original sparse Author object"
    paid = deepcopy(explicit)
    _call(paid, "configure_item_stats")["params"]["manaCost"] = 7
    assert _wire_payload(paid)["gameplay"]["manaCost"] == 7


@pytest.mark.parametrize("bad", [None, False, "0", -1, 501])
def test_present_invalid_mana_is_not_replaced_by_neutral(bad):
    doc = build_capability_witness("configure_item_stats")
    _call(doc, "configure_item_stats")["params"]["manaCost"] = bad
    assert not validate_runtime_program(doc)["ok"]
    with pytest.raises(ValueError):
        compile_runtime_program(doc)


@pytest.mark.parametrize("x,y", list(product([None, 0, -96, 96], repeat=2)))
def test_holdout_axes_are_independently_optional_without_losing_the_other_axis(x, y):
    sparse = build_capability_witness("configure_item_use")
    params = _call(sparse, "configure_item_use")["params"]
    for name, value in (("holdoutOffsetX", x), ("holdoutOffsetY", y)):
        if value is None:
            params.pop(name)
        else:
            params[name] = value
    explicit = deepcopy(sparse)
    _call(explicit, "configure_item_use")["params"].update(
        holdoutOffsetX=0 if x is None else x, holdoutOffsetY=0 if y is None else y,
    )
    report = validate_runtime_program(sparse)
    assert report["ok"], report["errors"]
    assert _wire_payload(sparse) == _wire_payload(explicit)


@pytest.mark.parametrize("original_mana,patch_mana", [(9, None), (None, 12)])
def test_repair_omission_is_no_change_and_valid_absence_stays_frozen(original_mana, patch_mana):
    from infini_local.core.runtime_authoring import (
        apply_repair_patch, build_runtime_repair_scope, filter_repair_patch_scope,
    )
    doc = build_capability_witness("configure_item_stats")
    call = _call(doc, "configure_item_stats")
    call["params"]["damage"] = -1
    if original_mana is None:
        call["params"].pop("manaCost")
    else:
        call["params"]["manaCost"] = original_mana
    errors = validate_runtime_program(doc)["errors"]
    scope = build_runtime_repair_scope(doc, errors)
    fixed = deepcopy(call)
    fixed["params"]["damage"] = 20
    if patch_mana is None:
        fixed["params"].pop("manaCost", None)
    else:
        fixed["params"]["manaCost"] = patch_mana
    filtered, audit = filter_repair_patch_scope(doc, {"callsUpsert": [fixed], "note": "repair damage only"}, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(doc, filtered)
    assert _call(repaired, "configure_item_stats")["params"].get("manaCost") == original_mana
    assert _wire_payload(repaired)["gameplay"]["manaCost"] == (0 if original_mana is None else original_mana)


def test_serialized_author_and_repair_distinguish_neutral_omission_from_no_change():
    import json
    from infini_local.pipelines.llm_authoring_pipeline import (
        build_initial_author_request, build_gameplay_repair_dossier,
    )
    _, user, _ = build_initial_author_request({}, {}, {}, {}, "omission-proof", model_name="test-model")
    catalog = json.loads(user)["runtimeCapabilityContract"]["catalog"]
    cards = {c["fn"]: c for c in catalog["capabilities"]}
    for fn, params in DECLARED.items():
        for name, neutral in params.items():
            assert cards[fn]["params"][name]["optional"] is True
            assert cards[fn]["params"][name]["default"] == neutral
    guide = catalog["fieldGuide"]["paramNotation"]
    assert "default" in guide and "full Author" in guide and "not universal" in guide
    doc = build_capability_witness("configure_item_stats")
    _call(doc, "configure_item_stats")["params"]["damage"] = -1
    dossier = build_gameplay_repair_dossier(doc, {}, {}, {}, {}, failure_report=validate_runtime_program(doc))
    rules = " ".join(json.loads(json.dumps(dossier))["rules"])
    assert "omission means no change" in rules


BUFF_NEUTRALS = {
    "miningSpeedMultiplier": 1,
    "oreSenseEnabled": False,
    "moveSpeedBonusFactor": 0,
    "jumpSpeedBonusPxPerTick": 0,
    "manaRegenBonusPoints": 0,
    "lifeRegenHpPerSecond": 0,
}


@pytest.mark.parametrize("present", list(product([False, True], repeat=len(BUFF_NEUTRALS))))
def test_all_buff_omission_combinations_preserve_selected_light_and_exact_wire(present):
    explicit = build_capability_witness("apply_generated_buff_on_use")
    _call(explicit, "apply_generated_buff_on_use")["params"].update(BUFF_NEUTRALS)
    sparse = deepcopy(explicit)
    params = _call(sparse, "apply_generated_buff_on_use")["params"]
    for name, keep in zip(BUFF_NEUTRALS, present):
        if not keep:
            params.pop(name)
    assert _wire_payload(sparse) == _wire_payload(explicit)


@pytest.mark.parametrize("active,value", [
    ("miningSpeedMultiplier", 1.5), ("oreSenseEnabled", True),
    ("moveSpeedBonusFactor", -0.25), ("jumpSpeedBonusPxPerTick", 1),
    ("manaRegenBonusPoints", 3), ("lifeRegenHpPerSecond", 1.5),
])
def test_one_explicit_buff_effect_survives_with_all_other_modifiers_omitted(active, value):
    sparse = build_capability_witness("apply_generated_buff_on_use")
    params = _call(sparse, "apply_generated_buff_on_use")["params"]
    params["lightStrength"] = 0
    for name in BUFF_NEUTRALS:
        params.pop(name)
    params[active] = value
    explicit = deepcopy(sparse)
    complete = _call(explicit, "apply_generated_buff_on_use")["params"]
    for name, neutral in BUFF_NEUTRALS.items():
        complete.setdefault(name, neutral)
    assert _wire_payload(sparse) == _wire_payload(explicit)


@pytest.mark.parametrize("present", list(product([False, True], repeat=len(BUFF_NEUTRALS))))
def test_jointly_absent_or_neutral_modifiers_cannot_create_an_inert_buff(present):
    doc = build_capability_witness("apply_generated_buff_on_use")
    params = _call(doc, "apply_generated_buff_on_use")["params"]
    params.update(BUFF_NEUTRALS, lightStrength=0)
    for name, keep in zip(BUFF_NEUTRALS, present):
        if not keep:
            params.pop(name)
    report = validate_runtime_program(doc)
    assert not report["ok"]
    assert any(e["code"] == "inert_component" for e in report["errors"])
    with pytest.raises(ValueError):
        compile_runtime_program(doc)


DECLARED = {
    "configure_item_stats": {"manaCost": 0},
    "configure_item_use": {"holdoutOffsetX": 0, "holdoutOffsetY": 0},
    "apply_generated_buff_on_use": BUFF_NEUTRALS,
}


def test_only_the_reviewed_parameter_allowlist_has_declared_neutral_defaults():
    from infini_local.core.runtime_authoring.program_schema import strict_schema_errors
    actual = {fn: {name: spec.default for name, spec in cap.params.items() if spec.default is not None}
              for fn, cap in CAPABILITY_REGISTRY.items() if any(s.default is not None for s in cap.params.values())}
    assert actual == DECLARED
    for fn, values in actual.items():
        for name, value in values.items():
            spec = CAPABILITY_REGISTRY[fn].params[name]
            assert not spec.required and spec.neutral == value
            assert type(spec.neutral) is type(value)
            assert not strict_schema_errors(value, spec.schema())


@pytest.mark.parametrize("fn,param", [(fn, p) for fn, params in DECLARED.items() for p in params])
def test_declared_optional_keeps_its_present_type_range_and_wire_mapping(fn, param):
    spec = CAPABILITY_REGISTRY[fn].params[param]
    for bad in (None, "missing", False if spec.kind != "boolean" else 0):
        doc = build_capability_witness(fn)
        _call(doc, fn)["params"][param] = bad
        assert not validate_runtime_program(doc)["ok"], (fn, param, bad)
    values = [False, True] if spec.kind == "boolean" else [spec.minimum, spec.maximum]
    for value in values:
        doc = build_capability_witness(fn)
        call = _call(doc, fn)
        call["params"][param] = value
        wire = compile_runtime_program(doc)
        report = validate_runtime_wire(wire)
        assert report["ok"], report["errors"]
        receipts = [r for r in wire["runtimeContract"]["finalWireReceipts"]
                    if r.get("callId") == call["id"] and r.get("authoredPath", "").endswith(".params." + param)]
        assert receipts and all(r["status"] == "delivered" and r["value"] == spec.to_wire(value) for r in receipts)


@pytest.mark.parametrize("fn,names", [
    ("apply_generated_buff_on_use", ("lightStrength", "lightColor")),
    ("restore_resources_on_use", ("healLife", "healMana")),
    ("configure_tool", ("pickPower", "axePowerTooltipPercent", "hammerPower", "miningSpeedScale")),
    ("set_projectile_collision", ("npcImmunityMode", "localNpcHitCooldownEngineUnits")),
    ("move_boomerang", ("returnAfterTicks", "returnSpeed")),
])
def test_unaudited_or_coupled_groups_do_not_gain_optional_permissions(fn, names):
    for present in product([False, True], repeat=len(names)):
        doc = build_capability_witness(fn)
        params = _call(doc, fn)["params"]
        for name, keep in zip(names, present):
            if not keep:
                params.pop(name)
        assert validate_runtime_program(doc)["ok"] is all(present), (fn, present)


def test_channel_dependency_remains_explicit_despite_other_neutral_omissions():
    doc = build_capability_witness("channel_beam")
    params = _call(doc, "configure_item_use")["params"]
    params.pop("holdoutOffsetX")
    params.pop("holdoutOffsetY")
    assert validate_runtime_program(doc)["ok"]
    params["channel"] = False
    report = validate_runtime_program(doc)
    assert not report["ok"]
    assert any(e["code"] == "missing_item_capability_param" for e in report["errors"])


def test_sparse_buff_still_requires_its_executable_binding():
    doc = build_capability_witness("apply_generated_buff_on_use")
    params = _call(doc, "apply_generated_buff_on_use")["params"]
    for name in BUFF_NEUTRALS:
        params.pop(name)
    doc["runtimeProgram"]["bindings"] = []
    report = validate_runtime_program(doc)
    assert not report["ok"]
    assert any(e["code"] == "missing_binding_dependency" for e in report["errors"])

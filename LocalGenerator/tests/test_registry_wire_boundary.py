"""Indexed strict-wire diagnostics, executable buffs, delivery refusal and cache quarantine."""

from copy import deepcopy
import copy
import re
import pytest
from infini_local.core.runtime_authoring import compile_runtime_program, validate_runtime_program, validate_runtime_wire
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.web.vfx_debug_routes import _sample_data
from infini_local.core.runtime_authoring.capability_registry import RUNTIME_PROGRAM_API_VERSION
from infini_local.core.vfx_manifest import _compile_manifest
from infini_local.storage.world_storage import sanitize_recipe_for_delivery, is_deliverable_recipe_payload


@pytest.fixture
def wire():
    data = _sample_data()
    assert validate_runtime_wire(data)["ok"] is True
    return data


@pytest.mark.parametrize(
    "path,value,code,insert",
    [
        pytest.param(("runtimeProgram", "entities", 0), v, "required_object", True, id="entity-row-" + label)
        for label, v in (("null", None), ("boolean", False), ("integer", 0), ("text", "broken"), ("array", []), ("array-text", ["broken"]))
    ]
    + [
        pytest.param(("runtimeProgram", "bindings", 0, "id"), v, "required_id", False, id="binding-id-" + label)
        for label, v in (("null", None), ("empty", ""), ("whitespace", "   "), ("integer", 7), ("array", []))
    ]
    + [
        pytest.param(("runtimeProgram", "entities", 1, "controller", "code"), v, "unsupported_opcode", False, id="controller-" + label)
        for label, v in (("array", []), ("object", {}), ("array-integer", [1]))
    ]
    + [
        pytest.param(
            ("gameplay",) + (("generatedBuff",) if field == "durationTicks" else ()) + (field,),
            v,
            "invalid_integer",
            False,
            id=field + "-" + label,
        )
        for field in ("healLife", "healMana", "durationTicks")
        for label, v in (
            ("null", None),
            ("false", False),
            ("true", True),
            ("fractional", 1.5),
            ("numeric-text", "3"),
            ("text", "broken"),
            ("object", {}),
            ("array", []),
        )
    ],
)
def test_wire_diagnostics_preserve_json_type_original_index_and_source(wire, path, value, code, insert):
    target = wire
    if path[0] == "gameplay":
        wire.setdefault("gameplay", {})["healLife"] = 20
    for part in path[:-1]:
        target = target.setdefault(part, {}) if isinstance(target, dict) else target[part]
    if insert:
        target.insert(path[-1], value)
    else:
        target[path[-1]] = value
    before = deepcopy(wire)
    expected = "$" + "".join(f"[{p}]" if isinstance(p, int) else "." + p for p in path)
    report = validate_runtime_wire(wire)
    assert report["ok"] is False
    assert any(e["path"] == expected and e["code"] == code for e in report["errors"]), report
    assert wire == before


@pytest.mark.parametrize(
    "mutation,path,code",
    [
        pytest.param(
            "mixed-row", "$.runtimeProgram.entities[2].movement.code", "unsupported_opcode", id="original-index-after-malformed-row"
        ),
        pytest.param("extra-body", "$.runtimeProgram.entities", "item_body_count", id="multiple-item-bodies"),
        pytest.param("duplicate-binding", "$.runtimeProgram.bindings[1].id", "duplicate_id", id="same-id-distinct-inputs"),
    ],
)
def test_wire_cross_row_identity_constraints(wire, mutation, path, code):
    runtime = wire["runtimeProgram"]
    if mutation == "mixed-row":
        runtime["entities"].insert(0, None)
        runtime["entities"][2]["movement"]["code"] = -1
    elif mutation == "extra-body":
        extra = deepcopy(runtime["entities"][0])
        extra["id"] = "extra_item"
        runtime["entities"].append(extra)
    else:
        extra = deepcopy(runtime["bindings"][0])
        extra["input"] = "alternate_use"
        runtime["bindings"].append(extra)
    report = validate_runtime_wire(wire)
    assert not report["ok"]
    assert any(e["path"] == path and e["code"] == code for e in report["errors"])


def _wire():
    data = compile_runtime_program(build_capability_witness("apply_generated_buff_on_use"))
    data.pop("runtimeContract")
    data["gameplay"]["generatedBuff"]["emitLightStrength"] = 0.25
    return data


MALFORMED_BUFF_FIELDS = [
    ("jumpBoost", "broken"),
    ("lifeRegen", True),
    ("miningSpeedMultiplier", 0),
    ("oreSenseRadiusTiles", 2),
    ("durationTicks", 21601),
    ("durationTicks", 1.0),
    ("manaRegen", 1.0),
    ("lifeRegen", 1.0),
    ("oreSenseRadiusTiles", True),
    ("movementSpeed", -0.6),
    ("jumpBoost", 9),
    ("manaRegen", 121),
    ("lifeRegen", 121),
    ("emitLightStrength", 2),
    ("lightColorName", "broken"),
    ("lightColorName", None),
    ("jumpBoost", float("inf")),
    ("jumpBoost", 10**1000),
    ("miningSpeedMultiplier", None),
    ("extra", 1),
    ("jumpBoost", 1e-50),
    ("miningSpeedMultiplier", 1.000000001),
]
FORGED_EFFECT_FIELDS = [
    ("oreSenseRadiusTiles", "true"),
    ("jumpBoost", "1"),
    ("miningSpeedMultiplier", float("nan")),
    ("emitLightStrength", float("nan")),
    ("lifeRegen", True),
    ("lifeRegen", 1.5),
    ("lifeRegen", 10**1000),
    ("miningSpeedMultiplier", 0),
    ("emitLightStrength", -0.25),
    ("jumpBoost", -1),
]


@pytest.mark.parametrize(
    "field,value,active,accepted,dependency",
    [
        pytest.param(field, value, True, False, False, id="active-light-" + field + "-" + str(i))
        for i, (field, value) in enumerate(MALFORMED_BUFF_FIELDS)
    ]
    + [
        pytest.param(field, value, False, False, True, id="forged-effect-" + field + "-" + str(i))
        for i, (field, value) in enumerate(FORGED_EFFECT_FIELDS)
    ]
    + [
        pytest.param(field, 1, True, True, False, id="json-integer-" + field)
        for field in ("miningSpeedMultiplier", "jumpBoost", "movementSpeed", "emitLightStrength", "lifeRegen", "oreSenseRadiusTiles")
    ],
)
def test_generated_buff_fields_cannot_hide_or_forge_executable_effect(field, value, active, accepted, dependency):
    data = _wire()
    buff = data["gameplay"]["generatedBuff"]
    if not active:
        buff.update(
            miningSpeedMultiplier=1, oreSenseRadiusTiles=0, movementSpeed=0, jumpBoost=0, manaRegen=0, lifeRegen=0, emitLightStrength=0
        )
    buff[field] = value
    before = deepcopy(data)
    report = validate_runtime_wire(data)
    assert report["ok"] is accepted, report
    if not accepted:
        assert any(e["path"] == "$.gameplay.generatedBuff." + field for e in report["errors"])
    if dependency:
        assert any(e["code"] == "binding_dependency" for e in report["errors"])
    assert data == before


@pytest.mark.parametrize(
    "effect,value,wire_key,wire_value",
    [
        pytest.param(*r, id=r[0] + "-" + str(r[1]))
        for r in (
            ("miningSpeedMultiplier", 1.5, "miningSpeedMultiplier", 1.5),
            ("lightStrength", 0.25, "emitLightStrength", 0.25),
            ("oreSenseEnabled", True, "oreSenseRadiusTiles", 1),
            ("moveSpeedBonusPercent", 20, "movementSpeed", 0.2),
            ("jumpSpeedBonusPxPerTick", 1, "jumpBoost", 1),
            ("manaRegenBonusPoints", 1, "manaRegen", 1),
            ("lifeRegenHpPerSecond", 0.5, "lifeRegen", 1),
            ("moveSpeedBonusPercent", -25, "movementSpeed", -0.25),
            ("manaRegenBonusPoints", 3, "manaRegen", 3),
            ("lifeRegenHpPerSecond", 1.5, "lifeRegen", 3),
            ("moveSpeedBonusPercent", 10, "movementSpeed", 0.1),
            ("jumpSpeedBonusPxPerTick", 0.5, "jumpBoost", 0.5),
        )
    ],
)
@pytest.mark.parametrize("sparse", [False, True], ids=["explicit-neutrals", "omitted-neutrals"])
def test_single_buff_effect_is_not_inert_and_sparse_wire_is_exact(effect, value, wire_key, wire_value, sparse):
    source = build_capability_witness("apply_generated_buff_on_use")
    params = next(c["params"] for c in source["runtimeProgram"]["calls"] if c["fn"] == "apply_generated_buff_on_use")
    neutrals = {
        "miningSpeedMultiplier": 1,
        "oreSenseEnabled": False,
        "moveSpeedBonusPercent": 0,
        "jumpSpeedBonusPxPerTick": 0,
        "manaRegenBonusPoints": 0,
        "lifeRegenHpPerSecond": 0,
    }
    params.update(neutrals, lightStrength=0, lightColor="white")
    assert any(e["code"] == "inert_component" for e in validate_runtime_program(source)["errors"])
    params[effect] = value
    explicit = compile_runtime_program(source)
    if sparse:
        for key in neutrals:
            if key != effect:
                params.pop(key)
    wire = compile_runtime_program(source)
    assert wire["gameplay"]["generatedBuff"][wire_key] == wire_value
    assert {k: wire[k] for k in ("runtimeProgram", "gameplay", "accessory", "armor")} == {
        k: explicit[k] for k in ("runtimeProgram", "gameplay", "accessory", "armor")
    }
    assert validate_runtime_wire(wire)["ok"]


@pytest.mark.parametrize("change", ["white-color-only", "red-color-only", "no-duration", "empty-color", "missing-color", "sparse"])
def test_generated_buff_dependency_and_legacy_absence(change):
    data = _wire()
    buff = data["gameplay"]["generatedBuff"]
    if change.endswith("color-only"):
        buff.update(emitLightStrength=0, lightColorName=change.split("-")[0])
    elif change == "no-duration":
        buff.update(durationTicks=0, oreSenseRadiusTiles=1)
    elif change == "empty-color":
        buff["lightColorName"] = ""
    elif change == "missing-color":
        buff.pop("lightColorName")
    else:
        data["gameplay"]["generatedBuff"] = {"durationTicks": 60, "jumpBoost": 1}
    before = deepcopy(data)
    report = validate_runtime_wire(data)
    assert report["ok"] is (change == "sparse")
    if change.endswith("color-only") or change == "no-duration":
        assert any(e["code"] == "binding_dependency" for e in report["errors"])
    assert data == before


@pytest.mark.parametrize("mutation,error_path,code", [
    pytest.param("entity_row", "$.runtimeProgram.entities[0]", "required_object", id="entity_row"),
    pytest.param("extra_body", "$.runtimeProgram.entities", "item_body_count", id="extra_body"),
    pytest.param("binding_id", "$.runtimeProgram.bindings[0].id", "required_id", id="binding_id"),
    pytest.param("controller_code", "$.runtimeProgram.entities[1].controller.code", "unsupported_opcode", id="controller_code"),
    pytest.param("heal_value", "$.gameplay.healLife", "invalid_integer", id="heal_value"),
    pytest.param("buff_duration", "$.gameplay.generatedBuff.durationTicks", "invalid_integer", id="buff_duration"),
])
def test_rejected_wire_is_quarantined_by_real_cache_lookup(tmp_path, monkeypatch, wire, mutation, error_path, code):
    from infini_local.pipelines import visual_delivery_gate
    from infini_local.pipelines.combine_pipeline import _cached_payload_report, combine_cache_lookup
    from infini_local.qa.live_no_image_fixture import hydrate_no_image_fixture_assets, write_no_image_fixture_png
    from infini_local.storage import world_recipe_runtime, world_storage

    monkeypatch.setattr(world_recipe_runtime, "WORLD_RECIPES_DIR", tmp_path)
    monkeypatch.setattr(visual_delivery_gate, "SPRITE_DIR", tmp_path)
    monkeypatch.setattr(visual_delivery_gate, "WORLD_RECIPES_DIR", tmp_path)
    payload = {"worldId": "audit-world", "itemA": {"type": 1}, "itemB": {"type": 2}}
    key, cached = combine_cache_lookup(payload)
    assert cached is None
    hydrate_no_image_fixture_assets(wire, write_no_image_fixture_png(tmp_path / "cache-control.png"))
    wire["vfxManifest"] = _compile_manifest(wire, {
        "effectMagnitude": 0.0, "visualBudgetClass": "tiny",
        "motif": {"element": "neutral", "shapeLanguage": "none", "motionLanguage": "none",
                  "paletteRole": "primary", "rhythm": 1.0, "chaos": 0.0}, "slots": [],
    }, key)
    assert _cached_payload_report(wire)["ok"]
    path = world_storage.world_recipe_file(tmp_path, "audit-world", key)
    world_storage.write_world_recipe_cache(tmp_path, "test", key, "audit-world", wire)
    valid_cached = combine_cache_lookup(payload)[1]
    assert isinstance(valid_cached, dict)
    assert valid_cached["runtimeProgram"] == wire["runtimeProgram"]
    assert path.exists()
    runtime = wire["runtimeProgram"]
    if mutation == "entity_row":
        runtime["entities"].insert(0, None)
    elif mutation == "extra_body":
        extra = copy.deepcopy(runtime["entities"][0])
        extra["id"] = "extra_item"
        runtime["entities"].append(extra)
    elif mutation == "binding_id":
        runtime["bindings"][0]["id"] = ""
    elif mutation == "heal_value":
        wire.setdefault("gameplay", {})["healLife"] = "broken"
    elif mutation == "buff_duration":
        wire.setdefault("gameplay", {})["generatedBuff"] = {"durationTicks": "broken"}
    else:
        runtime["entities"][1]["controller"]["code"] = []
    report = validate_runtime_wire(wire)
    assert not report["ok"]
    assert any(e["path"] == error_path and e["code"] == code for e in report["errors"])
    world_storage.atomic_write_json(path, wire)
    original = path.read_bytes()

    assert combine_cache_lookup(payload) == (key, None)
    assert not path.exists()
    reasons = list((path.parent.parent / "invalid").glob("*.reason.json"))
    assert len(reasons) == 1
    reason = world_storage.read_json_file(reasons[0])
    assert isinstance(reason, dict)
    assert reason["reason"] == "low_level_runtime_contract_invalid"
    assert reason["details"]["errors"] == [{"path": "$", "message": "payload is not deliverable"}]
    assert (reasons[0].parent / reason["payloadFile"]).read_bytes() == original


@pytest.mark.parametrize(
    "field,value",
    [
        ("jumpBoost", "broken"),
        ("lifeRegen", True),
        ("miningSpeedMultiplier", 0),
        ("oreSenseRadiusTiles", 2),
    ],
)
def test_a7_storage_delivery_gate_rejects_malformed_neighbour(field, value):
    delivery = sanitize_recipe_for_delivery(_wire())
    delivery.update(id="receipt_probe", name="Receipt probe", schemaVersion=5, runtimeApiVersion=RUNTIME_PROGRAM_API_VERSION)
    # The positive control is a complete compiled empty VFX manifest, not only
    # a schema marker. This observer isolates the malformed buff neighbour.
    delivery["vfxManifest"] = _compile_manifest(
        delivery,
        {
            "effectMagnitude": 0.0,
            "visualBudgetClass": "tiny",
            "motif": {
                "element": "neutral",
                "shapeLanguage": "none",
                "motionLanguage": "none",
                "paletteRole": "primary",
                "rhythm": 1.0,
                "chaos": 0.0,
            },
            "slots": [],
        },
        "receipt_probe",
    )
    assert is_deliverable_recipe_payload(delivery)
    delivery["gameplay"]["generatedBuff"][field] = value
    assert not is_deliverable_recipe_payload(delivery)


@pytest.mark.parametrize("bad", [None, [], 0, "buff"])
def test_present_malformed_buff_object_is_not_hidden_by_healing(bad):
    wire = _wire()
    wire["gameplay"]["healLife"] = 10
    wire["gameplay"]["generatedBuff"] = bad
    report = validate_runtime_wire(wire)
    assert not report["ok"]
    assert any(e["path"] == "$.gameplay.generatedBuff" for e in report["errors"])


@pytest.mark.parametrize(
    "bad",
    [
        None,
        [],
        1,
        False,
        "row",
        {},
        {"fn": []},
        {"authoredPaths": 7},
        {"authoredPaths": "path"},
        {"authoredPaths": [None]},
        {"finalPath": []},
        {"status": None},
        {"callId": {}},
        {"lowererId": True},
        {"authoredPath": 0},
    ],
)
def test_malformed_rows_have_original_index_in_direct_and_wire_audits(bad):
    source = build_capability_witness("configure_item_stats")
    wire = compile_runtime_program(source)
    rows = wire["runtimeContract"]["finalWireReceipts"]
    index = len(rows)
    rows.append(deepcopy(bad))
    for authored in (None, source):
        report = audit_compiler_receipts(rows, authored_document=authored, final_document=wire)
        assert not report["ok"]
        assert any(
            v.get("receiptIndex") == index and v.get("path", "").startswith(f"$.runtimeContract.finalWireReceipts[{index}]")
            for v in report["violations"]
        )
    report = validate_runtime_wire(wire)
    assert not report["ok"]
    assert any(v.get("receiptIndex") == index for v in report["technicalLowering"]["violations"])


@pytest.mark.parametrize("field", ["finalPath", "authoredPath", "authoredPaths"])
@pytest.mark.parametrize("bad_index", ["9" * 4301, "-1", "1.0", "not_an_index"], ids=["oversized", "negative", "fractional", "text"])
@pytest.mark.parametrize("with_source", [False, True])
def test_malformed_path_indices_are_indexed_violations(field, bad_index, with_source):
    source = build_capability_witness("configure_item_stats")
    wire = compile_runtime_program(source)
    rows = wire["runtimeContract"]["finalWireReceipts"]
    if field == "authoredPath":
        bad = deepcopy(next(row for row in rows if row.get("fn") == "configure_item_stats"))
        bad[field] = re.sub(r"\[\d+\]", f"[{bad_index}]", bad[field], count=1)
    else:
        bad = deepcopy(rows[0])
        if field == "finalPath":
            bad[field] = f"runtimeProgram.entities[{bad_index}].id"
        else:
            bad[field][1] = f"runtimeProgram.entities[{bad_index}].id"
    # A preceding malformed row must not shift the original receipt index.
    rows.append(None)
    index = len(rows)
    rows.append(bad)
    report = audit_compiler_receipts(rows, authored_document=source if with_source else None, final_document=wire)
    assert not report["ok"]
    assert any(
        v.get("receiptIndex") == index and v.get("path", "").startswith(f"$.runtimeContract.finalWireReceipts[{index}]")
        for v in report["violations"]
    )
    report = validate_runtime_wire(wire)
    assert not report["ok"]
    assert any(v.get("receiptIndex") == index for v in report["technicalLowering"]["violations"])

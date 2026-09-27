"""Generated buff precision is a consumer constraint, not author quantization."""
from copy import deepcopy

import pytest

from infini_local.core.runtime_authoring import CAPABILITY_REGISTRY, compile_runtime_program, validate_runtime_program
from infini_local.qa.capability_witnesses import build_capability_witness

FN = "apply_generated_buff_on_use"


def buff_document(name, value, companion):
    doc = build_capability_witness(FN)
    params = next(c["params"] for c in doc["runtimeProgram"]["calls"] if c["fn"] == FN)
    params.update(miningSpeedMultiplier=1, lightStrength=0, oreSenseEnabled=False,
                  moveSpeedBonusFactor=0, jumpSpeedBonusPxPerTick=0,
                  manaRegenBonusPoints=0, lifeRegenHpPerSecond=0)
    params[name] = value
    if companion == "ore":
        params["oreSenseEnabled"] = True
    elif companion == "healing":
        doc["runtimeProgram"]["calls"].append({"id": "healing", "fn": "restore_resources_on_use",
            "target": next(c["target"] for c in doc["runtimeProgram"]["calls"] if c["fn"] == FN),
            "params": {"healLife": 1, "healMana": 0, "usesPotionRules": False}})
    return doc


@pytest.mark.parametrize("companion", ["sole", "ore", "healing"])
@pytest.mark.parametrize("name,value", [("miningSpeedMultiplier", 1.000000001),
    ("miningSpeedMultiplier", 0.999999999), ("moveSpeedBonusFactor", 1e-50),
    ("moveSpeedBonusFactor", -1e-50), ("jumpSpeedBonusPxPerTick", 1e-50), ("lightStrength", 1e-50)])
def test_non_neutral_float32_collapse_is_rejected_at_exact_leaf(name, value, companion):
    doc = buff_document(name, value, companion)
    before = deepcopy(doc)
    report = validate_runtime_program(doc)
    assert not report["ok"]
    assert any(e["code"] == "consumer_representability" and e["path"].endswith(".params." + name)
               for e in report["errors"]), report
    assert doc == before


def test_consumer_error_is_registered_for_conditional_repair():
    from infini_local.core.runtime_authoring import VALIDATION_ERROR_CODES, REPAIR_VALIDATION_ERROR_CODES, REPAIR_ERROR_POLICY
    assert "consumer_representability" in VALIDATION_ERROR_CODES
    assert "consumer_representability" in REPAIR_VALIDATION_ERROR_CODES
    assert REPAIR_ERROR_POLICY["consumer_representability"]["llmRepairable"] is True


def test_consumer_collapse_repair_changes_only_the_exact_param():
    from infini_local.core.runtime_authoring import build_runtime_repair_scope, filter_repair_patch_scope, apply_repair_patch
    from infini_local.pipelines.llm_authoring_pipeline import build_initial_author_request, build_gameplay_repair_dossier
    import json
    doc = buff_document("miningSpeedMultiplier", 1.000000001, "ore")
    source = next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == FN)
    candidate = deepcopy(source)
    candidate["params"].update(miningSpeedMultiplier=1.0005, durationTicks=21600)
    report = validate_runtime_program(doc)
    scope = build_runtime_repair_scope(doc, report["errors"])
    patch = {"note": "exact consumer repair", "realizationReplacement": deepcopy(doc["realization"]),
             "callsUpsert": [candidate]}
    filtered, audit = filter_repair_patch_scope(doc, patch, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(doc, filtered)
    assert validate_runtime_program(repaired)["ok"]
    actual = next(c for c in repaired["runtimeProgram"]["calls"] if c["fn"] == FN)
    assert actual["params"] == dict(source["params"], miningSpeedMultiplier=1.0005)
    assert compile_runtime_program(repaired)["gameplay"]["generatedBuff"]["miningSpeedMultiplier"] == 1.0005
    _, author_packet, _ = build_initial_author_request({}, {}, {}, {}, "precision", model_name="test-model")
    repair_packet = json.dumps(build_gameplay_repair_dossier(doc, {}, {}, {}, {}, failure_report=report))
    for packet in (author_packet, repair_packet):
        assert 'consumerConstraint' in packet and 'nonneutral_must_remain_nonneutral' in packet


@pytest.mark.parametrize("companion", ["sole", "ore", "healing"])
@pytest.mark.parametrize("name,value", [("miningSpeedMultiplier", 1.0005),
    ("miningSpeedMultiplier", 0.9995), ("moveSpeedBonusFactor", .0005),
    ("moveSpeedBonusFactor", -.0005), ("jumpSpeedBonusPxPerTick", .0005),
    ("lightStrength", .0005), ("moveSpeedBonusFactor", 1e-40)])
def test_representable_small_buff_is_not_quantized(name, value, companion):
    doc = buff_document(name, value, companion)
    assert validate_runtime_program(doc)["ok"]
    wire = compile_runtime_program(doc)
    spec = CAPABILITY_REGISTRY[FN].params[name]
    assert wire["gameplay"]["generatedBuff"][spec.wire_name or name] == value


def test_consumer_constraint_is_model_visible_without_changing_bounds():
    cap = CAPABILITY_REGISTRY[FN]
    for name in ("miningSpeedMultiplier", "moveSpeedBonusFactor", "jumpSpeedBonusPxPerTick", "lightStrength"):
        spec = cap.params[name]
        constraint = cap.author_prompt_card()["params"][name]["consumerConstraint"]
        assert constraint == spec.schema()["x-infini-consumerConstraint"]
        assert constraint["storage"] == "float32"
        assert constraint["neutral"] == spec.neutral
        assert constraint["rule"] == "nonneutral_must_remain_nonneutral"
    assert cap.params["moveSpeedBonusFactor"].minimum == -.5


@pytest.mark.parametrize("name", ["manaRegenBonusPoints", "lifeRegenHpPerSecond"])
def test_discrete_regen_domain_and_exact_neutrals_remain_valid(name):
    for integer in range(121):
        value = integer / 2 if name == "lifeRegenHpPerSecond" else integer
        doc = buff_document(name, value, "ore")
        assert validate_runtime_program(doc)["ok"]
        wire = compile_runtime_program(doc)
        spec = CAPABILITY_REGISTRY[FN].params[name]
        assert wire["gameplay"]["generatedBuff"][spec.wire_name] == integer
        for continuous in ("miningSpeedMultiplier", "moveSpeedBonusFactor", "jumpSpeedBonusPxPerTick", "lightStrength"):
            param = CAPABILITY_REGISTRY[FN].params[continuous]
            assert param.consumer_value_error(param.neutral) is None


@pytest.mark.parametrize("name,value,accepted", [
    ("miningSpeedMultiplier", 1 + 2**-23, True),
    ("miningSpeedMultiplier", 1 - 2**-24, True),
    ("miningSpeedMultiplier", 1 + 2**-24, False),
    ("miningSpeedMultiplier", 1 - 2**-25, False),
    ("moveSpeedBonusFactor", 2**-149, True),
    ("moveSpeedBonusFactor", -(2**-149), True),
    ("moveSpeedBonusFactor", 2**-150, False),
    ("moveSpeedBonusFactor", -(2**-150), False),
])
def test_ieee754_round_to_even_neutral_boundary(name, value, accepted):
    report = validate_runtime_program(buff_document(name, value, "ore"))
    assert report["ok"] is accepted, report

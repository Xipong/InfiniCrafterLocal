from infini_local.core import runtime_authoring as ra
from infini_local.pipelines.llm_authoring_prompt import engine_runtime_capability_contract_for_llm
from infini_local.pipelines.parent_context_cards import raw_parent_card_for_llm


def _compile(engine_calls):
    data = {"runtimePlan": {"engineCalls": engine_calls}}
    patch = ra.compile_runtime_plan_to_genome_patch(data)
    data["debug"] = {}
    data["gameplay"] = {}
    return patch


def _check_golden_magic_mirror_boots_authors_mobility_and_accessory():
    patch = _compile([
        {"fn": "mobility_effect", "params": {"mode": "blink_to_cursor", "rangeTiles": 32, "cooldownTicks": 900}},
        {"fn": "accessory_effect", "params": {"archetype": "mobility", "stats": {"movementSpeed": 0.12, "fallDamageImmune": True}}},
    ])
    assert patch["mobilityMode"] == "blink_to_cursor"
    assert patch["accessory"]["enabled"] is True
    assert patch["accessory"]["movementSpeed"] > 0
    assert patch["accessory"]["fallDamageImmune"] is True


def _check_golden_spelunker_style_contract_does_not_add_ore_visual_executor():
    card = engine_runtime_capability_contract_for_llm({}, {}, {})
    semantics = card["semanticRules"]
    assert any("ore" in rule.lower() and "diagnostic" in rule.lower() for rule in semantics)
    text = str(card)
    assert "accessory_effect" in text
    assert "extractinator_output" not in text


def _check_generated_parent_card_enrichment_keeps_utility_and_accessory_identity():
    parent = {
        "name": "Generated Lumen Band",
        "generatedData": {
            "gameplay": {"kind": "accessory", "holdLightStrength": 0.6, "extractinatorOutputItemType": 75},
            "accessory": {"enabled": True, "archetype": "utility", "movementSpeed": 0.08, "lightStrength": 0.4},
            "attack": {"enabled": False},
            "generatedParentSummary": {"name": "Generated Lumen Band", "visualIdentity": "brass ring with star light"},
        },
    }
    card = raw_parent_card_for_llm(parent)
    gp = card["raw"]["generatedParent"]
    assert gp["gameplay"]["kind"] == "accessory"
    assert gp["gameplay"]["holdLightStrength"] == 0.6
    assert "extractinatorOutputItemType" not in gp["gameplay"]
    assert gp["accessory"]["enabled"] is True
    assert gp["accessory"]["lightStrength"] == 0.4
    assert gp["summary"]["visualIdentity"] == "brass ring with star light"

# Coarse test bundle: the checks below used to be separate pytest items.
# Keeping them as helper checks cuts collection/runtime noise while preserving
# the same assertions inside one scenario-level contract per file.
def _run_coarse_contracts(tmp_path):
    import inspect as _inspect
    import pytest as _pytest

    for _name in [
    '_check_golden_magic_mirror_boots_authors_mobility_and_accessory',

    '_check_golden_spelunker_style_contract_does_not_add_ore_visual_executor',
    '_check_generated_parent_card_enrichment_keeps_utility_and_accessory_identity'
    ]:
        _fn = globals()[_name]
        _sig = _inspect.signature(_fn)
        _kwargs = {}
        if "tmp_path" in _sig.parameters:
            _case_dir = tmp_path / _name
            _case_dir.mkdir(parents=True, exist_ok=True)
            _kwargs["tmp_path"] = _case_dir
        if "monkeypatch" in _sig.parameters:
            with _pytest.MonkeyPatch.context() as _mp:
                _kwargs["monkeypatch"] = _mp
                _fn(**_kwargs)
        else:
            _fn(**_kwargs)


def test_runtime_golden_recipes_contract_coarse_contract(tmp_path):
    _run_coarse_contracts(tmp_path)

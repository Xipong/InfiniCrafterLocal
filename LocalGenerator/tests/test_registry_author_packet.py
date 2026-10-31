"""The serialized Author packet exposes the canonical shape, units and construction grammar."""

from __future__ import annotations
from infini_local.core.runtime_authoring.capability_registry import (
    CAPABILITY_REGISTRY, BINDING_ACTION_REGISTRY, ENTITY_KIND_REGISTRY,
    EVENT_KIND_REGISTRY, author_parameter_shape,
)
from prompt_packet_helpers import request_dossier, dossier_text, expand_catalog_targets
import copy
import json
import pytest
from repair_test_helpers import offline_builder, repair_with_response, assert_repaired_source

from infini_local.core.runtime_authoring.capability_registry import INPUT_KIND_REGISTRY
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.capability_registry import runtime_authoring_prompt_field_guide
from infini_local.core.runtime_authoring.program_schema import binding_schema, strict_schema_errors
from infini_local.pipelines.author.item_contract import author_item_response_schema, author_item_provider_response_schema, author_item_prompt_shape_card, author_item_repair_prompt_shape_card, author_item_repair_response_schema, project_provider_author_item_to_local
from infini_local.pipelines.author.prompt import (
    PLANNER_PROMPT_LIMIT_CHARS,
    PLANNER_PROMPT_MIN_HEADROOM_CHARS,
    planner_prompt_usability_report,
)
from infini_local.pipelines.author.request import build_initial_author_request
from infini_local.pipelines.author import request as pipeline
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture


def _assert_catalog_delivery(catalog, capabilities=CAPABILITY_REGISTRY):
    """Compare delivered metadata to its typed owners, including multiplicity.

    Inventory order is not gameplay order. Parameter arrays and schema branches
    inside each card keep their literal identity. Editorial overlays may evolve;
    they cannot replace any field owned by the registry.
    """
    from test_author_request_compaction import _expand_constraint_references

    inventories = (
        ("capabilities", "fn", [cap.author_prompt_card() for cap in capabilities.values() if cap.author_visible]),
        ("entityKinds", "kind", [row.prompt_card() for row in ENTITY_KIND_REGISTRY.values()]),
        ("inputs", "input", [row.prompt_card() for row in INPUT_KIND_REGISTRY.values()]),
        ("bindingActions", "action", [row.prompt_card() for row in BINDING_ACTION_REGISTRY.values()]),
        ("events", "event", [row.author_prompt_card() for row in EVENT_KIND_REGISTRY.values()]),
    )
    for group, identity, expected in inventories:
        actual = _expand_constraint_references(catalog[group], catalog["fieldGuide"]["consumerConstraints"])
        actual = expand_catalog_targets(actual, catalog["fieldGuide"]["targetKindSets"])
        actual = [{key: value for key, value in row.items() if key != "constructionMeaning"} for row in actual]
        assert sorted(actual, key=lambda row: row[identity]) == sorted(expected, key=lambda row: row[identity]), group

    # A reference must identify a complete literal parameter of the right owner,
    # not another reference or merely a similarly named parameter.
    cards = {row["fn"]: row for row in catalog["capabilities"]}
    for fn, card in cards.items():
        for name, param in card["params"].items():
            if "paramRef" in param:
                owner, leaf = param["paramRef"].split(".")
                assert leaf == name
                assert capabilities[owner].params[leaf] == capabilities[fn].params[name]
                assert "paramRef" not in cards[owner]["params"][leaf]
    canonical = runtime_authoring_prompt_field_guide()
    canonical["types"] = {name: author_parameter_shape(schema) for name, schema in canonical["types"].items()}
    assert {key: catalog["fieldGuide"][key] for key in canonical} == canonical
    from infini_local.core.runtime_authoring.terraria_vocabulary import (
        DAMAGE_CLASS_MEANINGS, DAMAGE_CLASS_TOKENS,
        ITEM_USE_STYLE_MEANINGS, ITEM_USE_STYLE_TMODLOADER_NAMES, ITEM_USE_STYLE_TOKENS,
    )
    for key, tokens, meanings in (
        ("damageClass", DAMAGE_CLASS_TOKENS, DAMAGE_CLASS_MEANINGS),
        ("itemUseStyle", ITEM_USE_STYLE_TOKENS, ITEM_USE_STYLE_MEANINGS),
    ):
        vocabulary = catalog["fieldGuide"][key]
        assert vocabulary["builtInTokens"] == list(tokens)
        assert vocabulary["meaningByToken"] == dict(meanings)
        assert set(meanings) == set(tokens)
    assert set(ITEM_USE_STYLE_TMODLOADER_NAMES) == set(cards["item_use"]["params"]["useStyle"]["enum"])


@pytest.mark.parametrize("fixture_name", ["fishing_platform_tool", "workbench_blade"])
def test_coherence_advice_preserves_explicit_useful_placement_and_nonplacement(monkeypatch, fixture_name):
    from infini_local.core.runtime_authoring.compiler import compile_runtime_program
    from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire

    monkeypatch.setattr('infini_local.core.llm_config.LLM_RESPONSE_FORMAT_MODE', "json_object")
    item = build_runtime_fixture(fixture_name)
    before = copy.deepcopy(item)
    compiled_before = compile_runtime_program(item)
    # Constructing the new advisory packet must neither edit an existing design
    # nor turn guidance into a validator prohibition or deterministic selection.
    request, user, _ = build_initial_author_request(item, {}, "preserve-design", model_name="offline-test")
    assert dossier_text(request) == user
    prepared = pipeline._prepare_parsed_author_item(item, response_format=request["response_format"])
    assert prepared == before and item == before
    assert validate_runtime_program(prepared)["ok"]
    compiled_after = compile_runtime_program(prepared)
    assert validate_runtime_wire(compiled_after)["ok"]
    assert compiled_after == compiled_before
    placement = [row for row in prepared["runtimeProgram"]["bindings"] if row["action"]["kind"] == "place_item"]
    if fixture_name == "fishing_platform_tool":
        assert placement == [{
            "id": "alternate_place", "input": "alternate_use",
            "action": {"kind": "place_item", "placementCallId": "platform_result"},
        }]
        assert next(row["params"] for row in prepared["runtimeProgram"]["calls"] if row["id"] == "platform_result") == {
            "tileId": 19, "placeStyle": 0,
        }
    else:
        assert placement == []


def test_format_repair_with_coherence_advice_preserves_existing_placement(monkeypatch):
    monkeypatch.setattr('infini_local.core.llm_config.LLM_RESPONSE_FORMAT_MODE', "json_object")
    item = build_runtime_fixture("fishing_platform_tool")
    before = copy.deepcopy(item)
    content = json.dumps(item)
    _, recipe_context, _ = build_initial_author_request({}, {}, "syntax-only", model_name="offline-test")
    requests = []

    def respond(request, **kwargs):
        requests.append(request)
        return {"choices": [{"message": {"content": content}}]}

    monkeypatch.setattr(pipeline, "llm_chat_json", respond)
    prepared, raw = pipeline._repair_malformed_author_json(
        malformed_raw_text=content[:-1] + ",}", parse_error=ValueError("trailing comma"),
        original_recipe_context=recipe_context, model_name="offline-test",
    )
    context = request_dossier(requests[0])
    assert "concept" not in context["requiredJsonShape"], "syntax repair is not a second design request"
    assert context["malformedRawText"] == content[:-1] + ",}"
    assert prepared == before and item == before and raw == content


def test_scoped_repair_does_not_use_coherence_advice_to_remove_valid_placement(monkeypatch):
    item = build_runtime_fixture("fishing_platform_tool")
    before = copy.deepcopy(item)
    stats = _stats(item)
    stats["params"]["damage"] = -1
    replacement = copy.deepcopy(stats)
    replacement["params"]["damage"] = 8
    patch = {
        "note": "Repair only invalid damage", "realizationReplacement": copy.deepcopy(item["realization"]),
        "callsUpsert": [replacement], "bindingIdsDelete": ["alternate_place"], "callIdsDelete": ["platform_result"],
    }
    repaired, request = repair_with_response(monkeypatch, item, patch, "json_object")
    context = request_dossier(request)
    assert "concept" not in context["requiredJsonShape"]
    assert repaired["debug"]["gameplayRepairFilterAudit"]["ignoredChanges"]
    assert_repaired_source(repaired, before)
    assert _stats(item)["params"]["damage"] == -1, "repair does not mutate its input"


def test_author_shape_card_and_schema_share_public_members():
    card = author_item_prompt_shape_card()
    schema = author_item_response_schema()
    assert set(card["root"]) == set(schema["properties"])
    assert set(card["root"]) - set(schema["required"]) == {"concept", "realization"}
    assert isinstance(card["concept"], str)
    assert set(card["realization"]) == {"description", "selfEvaluation"}
    assert set(schema["required"]) == {"name", "category", "runtimeProgram"}
    assert {row["input"] for row in card["runtimeProgram"]["bindings"]} == set(INPUT_KIND_REGISTRY)
    assert all(not strict_schema_errors(row, binding_schema()) for row in card["runtimeProgram"]["bindings"])
    repair_card = author_item_repair_prompt_shape_card()
    assert set(repair_card) == set(author_item_repair_response_schema()["properties"])


@pytest.mark.parametrize("mode,rich", [
    pytest.param("json_schema", True, id="schema-generated-parent"),
    pytest.param("json_object", False, id="json-native-parent"),
    pytest.param("off", True, id="unconstrained-generated-parent"),
])
def test_author_packet_guide_and_prompt_budget_keep_registry_reachable(monkeypatch, rich, mode):
    from infini_local.pipelines.context.cards import raw_parent_card_for_llm
    from test_source_unit_guidance import _serialized_chat_request

    monkeypatch.setattr('infini_local.core.llm_config.LLM_RESPONSE_FORMAT_MODE', mode)
    a = build_runtime_fixture("held_and_deployed") if rich else {"id": "a", "name": "A", "damage": 10, "useTime": 20}
    b = a if rich else {"id": "b", "name": "B", "damage": 20, "useTime": 30}
    before = copy.deepcopy((a, b))
    request, text, _ = build_initial_author_request(a, b, "budget-proof", model_name="offline-test")
    assert (request["response_format"] or {}).get("type") == (None if mode == "off" else mode)
    assert dossier_text(request) == text
    # Observe the actual HTTP JSON, after provider preparation and serialization.
    packet = _serialized_chat_request(monkeypatch, request)
    assert packet["messages"] == request["messages"]
    assert packet.get("response_format") == request["response_format"]
    assert len(text) <= PLANNER_PROMPT_LIMIT_CHARS - PLANNER_PROMPT_MIN_HEADROOM_CHARS
    delivered = request_dossier(packet, declaration=request)
    assert delivered["parents"] == {key: {"packet": raw_parent_card_for_llm(parent)}
                                    for key, parent in zip(("A", "B"), before)}
    assert (a, b) == before
    assert delivered["requiredJsonShape"] == author_item_prompt_shape_card()
    catalog = delivered["runtimeCapabilityContract"]["catalog"]
    _assert_catalog_delivery(catalog)
    visible = {cap.name for cap in CAPABILITY_REGISTRY.values() if cap.author_visible}
    assert {row["fn"] for row in catalog["capabilities"]} == visible
    assert len(catalog["capabilities"]) == len(visible)
    if mode == "json_schema":
        variants = packet["response_format"]["json_schema"]["schema"]["properties"]["runtimeProgram"]["properties"]["calls"]["items"]["anyOf"]
        assert {row["properties"]["fn"]["const"] for row in variants} == visible
        assert len(variants) == len(visible)
    report = planner_prompt_usability_report(a, b, "budget-proof")
    assert report["ok"] and report["headroom"] >= PLANNER_PROMPT_MIN_HEADROOM_CHARS
    assert report["limit"] == PLANNER_PROMPT_LIMIT_CHARS
    assert report["visibleCapabilities"] == len(visible)
    assert report["missingCapabilities"] == report["extraCapabilities"] == []
    assert report["containsWeaponMacro"] is False and report["containsFamilyRouter"] is False


@pytest.mark.parametrize("defect", ["missing", "duplicate", "wrong-bound"])
def test_catalog_delivery_oracle_accepts_reordering_and_rejects_loss(monkeypatch, defect):
    """Negative controls prevent a dict/set conversion from hiding lost data."""
    monkeypatch.setattr('infini_local.core.llm_config.LLM_RESPONSE_FORMAT_MODE', "json_object")
    request, _, _ = build_initial_author_request({}, {}, "delivery-control", model_name="offline")
    catalog = request_dossier(request)["runtimeCapabilityContract"]["catalog"]
    for group in ("capabilities", "entityKinds", "inputs", "bindingActions", "events"):
        catalog[group].reverse()
    _assert_catalog_delivery(catalog)
    cards = catalog["capabilities"]
    if defect == "missing":
        cards.pop()
    elif defect == "duplicate":
        cards.append(copy.deepcopy(cards[0]))
    else:
        stats = next(row for row in cards if row["fn"] == "item_stats")
        stats["params"]["damage"]["max"] += 1
    with pytest.raises(AssertionError):
        _assert_catalog_delivery(catalog)


def test_rewording_canonical_cards_reaches_author_and_repair_without_changing_mechanics(monkeypatch):
    """A safe editorial change must propagate without requiring test rewrites."""
    from dataclasses import replace
    import infini_local.core.runtime_authoring.capability_registry as registry
    from infini_local.core.runtime_authoring.compiler import compile_runtime_program
    from infini_local.pipelines.author import prompt
    from test_source_unit_guidance import _serialized_chat_request
    from infini_local.qa.capability_witnesses import build_capability_witness

    monkeypatch.setattr('infini_local.core.llm_config.LLM_RESPONSE_FORMAT_MODE', "json_schema")
    source = build_capability_witness("item_stats")
    before = copy.deepcopy(source)
    wire = compile_runtime_program(source)
    provider_schema = author_item_provider_response_schema()
    cap = registry.CAPABILITY_REGISTRY["item_stats"]
    summary = "Item statistics in revised player language."
    meaning = "Mana points requested by the item's native use."
    changed = replace(cap, summary=summary, params={**cap.params, "manaCost": replace(cap.params["manaCost"], description=meaning)})
    registry_copy = {**registry.CAPABILITY_REGISTRY, cap.name: changed}
    for owner in (registry, prompt, pipeline):
        monkeypatch.setattr(owner, "CAPABILITY_REGISTRY", registry_copy)

    request, _, _ = build_initial_author_request({}, {}, "editorial-control", model_name="offline")
    delivered = request_dossier(_serialized_chat_request(monkeypatch, request), declaration=request)
    catalog = delivered["runtimeCapabilityContract"]["catalog"]
    _assert_catalog_delivery(catalog, registry_copy)
    card = next(row for row in catalog["capabilities"] if row["fn"] == cap.name)
    assert card["does"] == summary and card["params"]["manaCost"]["meaning"] == meaning
    assert author_item_provider_response_schema() == provider_schema
    assert compile_runtime_program(source) == wire and source == before

    # Real scoped Repair must receive the revised canonical card while refusing
    # a response that tries to change valid neighboring mechanics.
    stats = _stats(source)
    stats["params"]["damage"] = True
    correction = copy.deepcopy(_stats(before))
    correction["params"]["manaCost"] = 19
    repaired, repair_request = repair_with_response(monkeypatch, source, {
        "note": "Fix invalid damage only", "callsUpsert": [correction],
    }, "json_schema")
    repair = request_dossier(_serialized_chat_request(monkeypatch, repair_request), declaration=repair_request)
    assert repair["existingBrokenCapabilityCards"] == [changed.prompt_card()]
    assert repair["repairScope"]["fieldPermissions"]["calls"] == [{"id": stats["id"], "paths": ["params.damage"]}]
    assert repaired["debug"]["gameplayRepairFilterAudit"]["ignoredChanges"]
    assert_repaired_source(repaired, before)


@pytest.mark.parametrize("pick_power", [0, 50], ids=["inactive-tool-keeps-light", "active-tool-keeps-light"])
def test_tool_applicability_does_not_rewrite_authored_composition(pick_power):
    from infini_local.core.runtime_authoring.compiler import compile_runtime_program
    from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
    from infini_local.qa.capability_witnesses import build_capability_witness

    doc = build_capability_witness("tool_stats")
    tool = next(row for row in doc["runtimeProgram"]["calls"] if row["fn"] == "tool_stats")
    tool["params"].update(pickPower=pick_power, axePower=0, hammerPower=0, miningSpeedMultiplier=2)
    light = copy.deepcopy(next(row for row in build_capability_witness("held_light")["runtimeProgram"]["calls"] if row["fn"] == "held_light"))
    light["id"] = "independent_light"
    doc["runtimeProgram"]["calls"].append(light)
    before = copy.deepcopy(doc)
    wire = compile_runtime_program(doc)
    assert validate_runtime_wire(wire)["ok"]
    assert wire["gameplay"]["pickPower"] == pick_power
    assert wire["gameplay"]["miningSpeedScale"] == 2
    assert wire["gameplay"]["holdLightStrength"] > 0
    assert doc == before


# Each case owns one serialized field's complete consumer explanation.
# Phrase clauses are assertions on that one field, not separate setup/requests.

def _stats(item):
    return next(row for row in item["runtimeProgram"]["calls"] if isinstance(row, dict) and row["fn"] == "item_stats")


def _response_format():
    return {"type": "json_schema", "json_schema": {"schema": author_item_provider_response_schema()}}


@pytest.mark.parametrize(
    "mode,wrapper,omitted",
    [
        pytest.param("json_schema", True, True, id="schema-declared-nullable"),
        pytest.param("json_object", True, False, id="plain-json"),
        pytest.param("off", True, False, id="no-format"),
        pytest.param("json_schema", False, False, id="schema-without-nullable-wrapper"),
    ],
)
def test_nullable_projection_requires_actual_schema_and_preserves_invalid_neighbours(mode, wrapper, omitted):
    item = build_runtime_fixture("workbench_blade")
    _stats(item)["params"].update(manaCost=None, notARegisteredParameter=None, damage=None)
    item["runtimeProgram"]["calls"].insert(0, None)
    before = copy.deepcopy(item)
    response_format = _response_format() if mode == "json_schema" else ({"type": mode} if mode != "off" else None)
    if mode == "json_schema" and not wrapper:
        variants = response_format["json_schema"]["schema"]["properties"]["runtimeProgram"]["properties"]["calls"]["items"]["anyOf"]
        variant = next(r for r in variants if r["properties"]["fn"]["const"] == "item_stats")
        params = variant["properties"]["params"]["properties"]
        params["manaCost"] = params["manaCost"]["anyOf"][0]
    projected = project_provider_author_item_to_local(item, response_format=response_format)
    assert pipeline._prepare_parsed_author_item(item, response_format=response_format) == projected
    params = _stats(projected)["params"]
    assert ("manaCost" not in params) is omitted
    assert params["notARegisteredParameter"] is None and params["damage"] is None
    assert projected["runtimeProgram"]["calls"][0] is None and len(projected["runtimeProgram"]["calls"]) == len(
        item["runtimeProgram"]["calls"]
    )
    assert item == before and not validate_runtime_program(projected)["ok"]
    if mode == "off":
        assert pipeline._prepare_parsed_author_item(item) == before


@pytest.mark.parametrize(
    "mode,actual,malformed",
    [
        pytest.param(mode, actual, False, id=mode + "-effective-" + (actual or "off"))
        for mode, actual in (
            ("json_schema", "json_schema"),
            ("json_object", "json_object"),
            ("off", ""),
            ("json_schema", "json_object"),
            ("json_schema", ""),
        )
    ]
    + [pytest.param("json_schema", "json_schema", True, id="schema-format-repair")],
)
def test_author_entrypoint_uses_effective_format_preserves_raw_and_carries_mode_to_repair(monkeypatch, mode, actual, malformed):
    item = build_runtime_fixture("workbench_blade")
    _stats(item)["params"]["manaCost"] = None
    content = json.dumps(item)
    raw = content[:-1] + ",}" if malformed else content
    responses = iter([raw, content] if malformed else [content])
    requests = []

    def respond(request, **kwargs):
        requests.append(request)
        return {"choices": [{"message": {"content": next(responses)}}], "_debug": {"responseFormatType": actual}}

    offline_builder(monkeypatch, mode, respond)
    result = pipeline.try_llm_plan({}, {}, "nullable-test")
    assert result is not None
    assert ("manaCost" not in _stats(result)["params"]) is (actual == "json_schema")
    assert validate_runtime_program(result)["ok"] is (actual == "json_schema")
    assert result["debug"]["llmRawOutput"] == raw[:12000]
    assert [r["_infini_stage"] for r in requests] == (["planner", "author_repair"] if malformed else ["planner"])
    if malformed:
        assert result["debug"]["gameplayFormatRepairRawOutput"] == content[:12000]


@pytest.mark.parametrize(
    "source_schema,mode,actual,accepted",
    [
        pytest.param(*r, id=("schema" if r[0] else "plain") + "-" + r[1] + "-" + str(i))
        for i, r in enumerate(
            (
                (True, "json_schema", "json_schema", True),
                (False, "json_object", "json_object", True),
                (False, "off", "", True),
                (False, "json_schema", "json_object", True),
                (False, "json_schema", None, False),
            )
        )
    ],
)
def test_format_repair_preserves_source_contract_without_mode_upgrade(monkeypatch, source_schema, mode, actual, accepted):
    from infini_local.core.errors import PlannerUnavailable

    monkeypatch.setattr('infini_local.core.llm_config.LLM_RESPONSE_FORMAT_MODE', mode)
    item = build_runtime_fixture("workbench_blade")
    _stats(item)["params"]["manaCost"] = None
    content = json.dumps(item)
    response = {"choices": [{"message": {"content": content}}]}
    if actual is not None:
        response["_debug"] = {"responseFormatType": actual}
    monkeypatch.setattr(pipeline, "llm_chat_json", lambda *a, **kw: response)
    args = {
        "malformed_raw_text": content[:-1] + ",}",
        "parse_error": ValueError("trailing comma"),
        "original_recipe_context": "{}",
        "model_name": "offline-test",
        "source_response_format": _response_format() if source_schema else None,
    }
    if not accepted:
        with pytest.raises(PlannerUnavailable, match="changed recoverable authored fields"):
            pipeline._repair_malformed_author_json(**args)
    else:
        prepared, raw = pipeline._repair_malformed_author_json(**args)
        assert ("manaCost" not in _stats(prepared)["params"]) is source_schema
        assert raw == content


@pytest.mark.parametrize(
    "mode,actual,mana,variant",
    [
        pytest.param("json_schema", "json_schema", None, "nullable", id="schema-preserves-omission"),
        pytest.param("json_schema", "json_schema", 7, "nullable", id="schema-preserves-present-sibling"),
        pytest.param("json_schema", "json_object", 7, "nullable", id="effective-plain-json-refuses-null-scaffolding")
    ]
    + [
        pytest.param("json_object", None, 7, "invalid-frozen-mana", id="filter-before-final-range-validation"),
        pytest.param("json_schema", None, 7, None, id="null-realization"),
        pytest.param("json_schema", None, 7, {}, id="empty-realization"),
        pytest.param("json_schema", None, 7, {"description": "incomplete"}, id="incomplete-realization"),
    ],
)
def test_repair_entrypoint_preserves_frozen_semantics_raw_and_optional_realization(monkeypatch, mode, actual, mana, variant):
    from infini_local.core.errors import PlannerUnavailable
    from infini_local.core.runtime_authoring.program_schema import strict_repair_shape_report

    item = build_runtime_fixture("workbench_blade")
    stats = _stats(item)
    if mana is None:
        stats["params"].pop("manaCost", None)
    else:
        stats["params"]["manaCost"] = mana
    stats["params"]["damage"] = -1
    replacement = copy.deepcopy(stats)
    replacement["params"].update(damage=42, manaCost=-1 if variant == "invalid-frozen-mana" else None)
    shape_guard = not isinstance(variant, str)
    patch = {
        "note": "Repair damage",
        "realizationReplacement": variant if shape_guard else copy.deepcopy(item["realization"]),
        "callsUpsert": [replacement],
    }
    if variant == "nullable":
        patch["metadataPatch"] = None
    if variant == "invalid-frozen-mana":
        assert not strict_repair_shape_report(patch)["ok"]
    response = {"choices": [{"message": {"content": json.dumps(patch)}}]}
    if actual is not None:
        response["_debug"] = {"responseFormatType": actual}
    offline_builder(monkeypatch, mode, lambda *a, **kw: response)
    args = (item, {}, {}, "repair-contract")
    if variant == "nullable" and actual != "json_schema":
        with pytest.raises(PlannerUnavailable):
            pipeline.repair_author_item_after_failure(*args, failure_report=validate_runtime_program(item))
    else:
        result = pipeline.repair_author_item_after_failure(*args, failure_report=validate_runtime_program(item))
        assert validate_runtime_program(result)["ok"] and _stats(result)["params"]["damage"] == 42
        assert ("manaCost" in _stats(result)["params"]) is (mana is not None)
        if shape_guard:
            expected = copy.deepcopy(item)
            _stats(expected)["params"]["damage"] = 42
            if variant is not None:
                expected["realization"] = variant
            assert {k: v for k, v in result.items() if k != "debug"} == expected
        if mana is not None:
            assert _stats(result)["params"]["manaCost"] == mana
        if variant == "nullable":
            assert result["debug"]["gameplayRepairRawPatch"] == patch

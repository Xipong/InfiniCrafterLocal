
from prompt_packet_helpers import expand_catalog_targets, request_dossier

"""Real builder admission, no provider calls or synthetic responses."""
import copy
import json
from typing import Any

import pytest
from infini_local.core import llm_config
from infini_local.core.runtime_authoring.registry_views import compact_capability_catalog
from infini_local.pipelines.author.prompt import PLANNER_PROMPT_LIMIT_CHARS, PLANNER_PROMPT_MIN_HEADROOM_CHARS
from infini_local.pipelines.author.request import build_initial_author_request
from test_author_request_compaction import _expand_constraint_references
from test_source_unit_guidance import _serialized_chat_request


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
def test_literal_source_tooltip_context_fits_without_clipping(monkeypatch, mode):
    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", mode)
    literal = "literal source context " + "Ж" * 1000
    source = {
        "id": 2322, "name": "Mining Potion", "sourceMod": "Terraria", "internalName": "MiningPotion",
        "fullName": "Terraria/MiningPotion", "damage": 0, "buffType": 104, "buffTime": 21600,
        "tooltipLines": [literal] * 12,
        "tooltipSource": {"source": "Lang.GetTooltip", "fullName": "Terraria/MiningPotion", "language": "ru-RU", "status": "observed_literal"},
    }
    before = copy.deepcopy(source)
    request, user, _ = build_initial_author_request(source, source, "headroom", model_name="offline")
    payload = json.loads(user)
    for label in ("A", "B"):
        assert payload["parents"][label]["packet"]["raw"]["item"]["tooltipLines"] == source["tooltipLines"]
    assert request_dossier(request) == payload
    assert len(user) <= PLANNER_PROMPT_LIMIT_CHARS - PLANNER_PROMPT_MIN_HEADROOM_CHARS
    sent = _serialized_chat_request(monkeypatch, request)
    assert request_dossier(sent, declaration=request) == payload
    assert sent["messages"] == request["messages"]
    catalog = payload["runtimeCapabilityContract"]["catalog"]
    expanded = _expand_constraint_references(catalog["capabilities"], catalog["fieldGuide"]["consumerConstraints"])
    expanded = expand_catalog_targets(expanded, catalog["fieldGuide"]["targetKindSets"])
    assert [{key: value for key, value in card.items() if key != "constructionMeaning"}
            for card in expanded] == compact_capability_catalog()
    assert source == before


def test_fresh_cards_share_only_exact_parameter_metadata_and_dead_negative_clauses():
    from dataclasses import replace

    from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
    from infini_local.core.runtime_authoring.parameter_contract import RequirementSpec
    from infini_local.core.runtime_authoring.registry_views import runtime_authoring_prompt_field_guide

    before = {name: cap.audit_card() for name, cap in CAPABILITY_REGISTRY.items()}
    catalog = compact_capability_catalog()
    cards = {card["fn"]: card for card in catalog}
    guide = runtime_authoring_prompt_field_guide()
    assert len(cards) == len(catalog), "each visible capability is delivered exactly once"
    assert set(cards) == {name for name, cap in CAPABILITY_REGISTRY.items() if cap.author_visible}
    references = []
    for name, card in cards.items():
        cap = CAPABILITY_REGISTRY[name]
        assert set(card["params"]) == set(cap.params)
        for param, row in card["params"].items():
            if "paramRef" not in row:
                continue
            assert set(row) == {"paramRef"}
            fn, leaf = row["paramRef"].split(".")
            assert fn in cards and leaf == param
            assert "paramRef" not in cards[fn]["params"][leaf], "one direct lookup, not a reference chain"
            assert CAPABILITY_REGISTRY[fn].params[leaf] == cap.params[param]
            references.append((name, param))
        expected = []
        for rule in before[name].get("requires", []):
            rule = copy.deepcopy(rule)
            if rule["kind"] == "present_param_forbids_capability" and not CAPABILITY_REGISTRY[rule["capability"]].author_visible:
                continue
            if rule["kind"] == "capability_absent":
                rule["anyOf"] = [fn for fn in rule["anyOf"] if CAPABILITY_REGISTRY[fn].author_visible]
                if not rule["anyOf"]:
                    continue
            if rule.get("target") == "same_target":
                rule.pop("target")
            if "equals" in rule and rule["equals"] is None:
                rule.pop("equals")
            expected.append(rule)
        assert card.get("requires", []) == expected, name
    assert references
    assert guide["requirementNotation"]["omittedMetadata"] == {"target": "same_target", "equals": None}
    # A reference to an unknown/unregistered function is not proved unreachable.
    unknown = RequirementSpec("present_param_forbids_capability", capability="future_function", param="count")
    changed = replace(CAPABILITY_REGISTRY["spawn"], requirements=(unknown,))
    assert changed.author_prompt_card()["requires"][0]["capability"] == "future_function"
    assert before == {name: cap.audit_card() for name, cap in CAPABILITY_REGISTRY.items()}


@pytest.mark.parametrize("field,value", [("maximum", 9.0), ("units", "distinct units"),
                                         ("description", "Distinct consumer meaning")])
def test_shared_parameter_reference_never_hides_a_different_fact(field, value):
    from dataclasses import replace

    from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY

    cap = CAPABILITY_REGISTRY["apply_status_on_event"]
    assert cap.author_prompt_card()["params"]["delay"] == {
        "paramRef": "generated_buff_on_event.delay"}
    changed = replace(cap, params={**cap.params, "delay": replace(cap.params["delay"], **{field: value})})
    row = changed.author_prompt_card()["params"]["delay"]
    assert "paramRef" not in row
    key = {"maximum": "max", "description": "meaning", "units": "units"}[field]
    assert row[key] == value


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
def test_provider_cards_recover_all_canonical_parameter_facts(monkeypatch, mode):
    from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY

    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", mode)
    source = {"name": "literal zero/null source", "damage": 0, "generatedData": {
        "gameplay": {"damage": 0, "generatedBuff": {"movementSpeed": 0, "lifeRegen": None}},
        "accessory": {"movementSpeed": 0, "lifeRegen": None, "waterWalk": False},
        "armor": {"movementSpeed": 0, "lifeRegen": None, "setBonusLifeRegen": 0},
        "runtimeProgram": {"entities": [], "bindings": [], "calls": []},
    }}
    before = copy.deepcopy(source)
    request, user, _ = build_initial_author_request(source, source, "canonical-card-parity", model_name="offline")
    sent = _serialized_chat_request(monkeypatch, request)
    packet = request_dossier(sent, declaration=request)
    for label in ("A", "B"):
        raw = packet["parents"][label]["packet"]["raw"]
        assert raw["item"]["damage"] == 0
        for key, value in source["generatedData"].items():
            assert raw["generatedParent"][key] == value
    assert source == before
    catalog = packet["runtimeCapabilityContract"]["catalog"]
    guide = catalog["fieldGuide"]
    expanded: Any = _expand_constraint_references(catalog["capabilities"], guide["consumerConstraints"])
    cards: dict[str, dict[str, Any]] = {row["fn"]: row for row in expanded}
    seconds_primer = "World duration (seconds); shared nearest-tick rounding applies. Native consumer: "
    checked = 0
    shared = 0

    def normalize_meanings(value: Any) -> Any:
        if isinstance(value, dict):
            result = {key: child.removeprefix(seconds_primer)
                    if key in {"meaning", "description"} and isinstance(child, str)
                    else normalize_meanings(child) for key, child in value.items()}
            units = value.get("units", value.get("x-infini-units"))
            if isinstance(units, str):
                for key in ("meaning", "description"):
                    if isinstance(result.get(key), str):
                        result[key] = result[key].removeprefix(f"Author units: {units}. Native consumer: ")
            properties = result.get("properties")
            if isinstance(properties, dict) and len(properties) == 1:
                child = next(iter(properties.values()))
                if isinstance(child, dict) and result.get("description") == child.get("description"):
                    result.pop("description", None)
            return result
        if isinstance(value, list):
            return [normalize_meanings(child) for child in value]
        return value

    def resolve_param(fn: str, param: str) -> dict[str, Any]:
        row = copy.deepcopy(cards[fn]["params"][param])
        if "paramRef" in row:
            owner, leaf = row["paramRef"].split(".")
            assert "paramRef" not in cards[owner]["params"][leaf]
            row = copy.deepcopy(cards[owner]["params"][leaf])
            fn = owner
        if fn == "armor" and "meaning" not in row:
            row["meaning"] = resolve_param("accessory", param)["meaning"]
        return row

    def expected_shape(schema):
        names = {"description": "meaning", "minimum": "min", "maximum": "max",
                 "x-infini-units": "units", "x-infini-reference": "reference",
                 "x-infini-neutral": "neutral", "x-infini-consumerConstraint": "consumerConstraint",
                 "x-infini-authorProjection": "projectionConstraints"}
        result = {names.get(k, k): copy.deepcopy(v) for k, v in schema.items()
                  if k not in {"x-infini-semanticType", "required", "properties", "oneOf"}}
        if "properties" in schema:
            result["properties"] = {k: {**expected_shape(v), **({"optional": True} if k not in schema.get("required", []) else {})}
                                    for k, v in schema["properties"].items()}
        if "oneOf" in schema:
            result["oneOf"] = [expected_shape(v) for v in schema["oneOf"]]
        return result

    for fn, delivered_card in cards.items():
        card = expand_catalog_targets([delivered_card], guide["targetKindSets"])[0]
        cap = CAPABILITY_REGISTRY[fn]
        source = cap.audit_card()
        for key in ("fn", "does", "targets", "exclusiveGroup", "acceptedEvents", "emitsEvents",
                    "positionOwnership", "multiplicity", "maxPerTarget", "budget"):
            if key in cap.prompt_card():
                assert card[key] == source[key], (fn, key)
        if cap.effect_groupable:
            assert card["effectGroups"] == {"$ref": "#/fieldGuide/effectGroups"}
            assert guide["effectGroups"] == source["effectGroups"]
        for param, original in source["params"].items():
            row = resolve_param(fn, param)
            spec = cap.params[param]
            if spec.shared_type:
                annotations = {key: original[key] for key in ("default", "neutral", "omissionAllowedOnlyWhen") if key in original}
                assert row == {"typeRef": spec.shared_type, **({"optional": True} if not spec.required else {}), **annotations}
                expanded_shape = copy.deepcopy(guide["types"][spec.shared_type])
                if "default" in row:
                    expanded_shape["default"] = row["default"]
                if "neutral" in row:
                    expanded_shape["neutral"] = row["neutral"]
                assert expanded_shape == expected_shape(original["shape"]) == expected_shape(spec.schema())
                assert original["meaning"] == guide["types"][spec.shared_type]["meaning"]
                shared += 1
                continue
            expected = normalize_meanings(copy.deepcopy(original))
            expected.pop("required", None)
            expected.pop("semanticType", None)  # Existing documented presentation-only omission.
            if not spec.required:
                expected["optional"] = True
            for suffix, units in (("Seconds", "seconds"), ("Tiles", "blocks (tiles)"),
                                  ("Px", "pixels"), ("Radians", "radians")):
                if param.endswith(suffix) and spec.units == units:
                    expected.pop("units", None)
                    break
            if fn == "armor" and param.startswith("setBonus"):
                expected["meaning"] = expected["meaning"].removeprefix(guide["setBonusParamPrefix"])
            shape = expected.get("shape")
            if isinstance(shape, dict) and shape.get("description") == expected["meaning"]:
                shape.pop("description")
            if "shape" in expected:
                expected.update(expected_shape(expected.pop("shape")))
            # Exact deep equality includes every nested bound, enum, unit,
            # reference, ordering relation, omission rule, neutral and projection.
            assert row == expected, (fn, param)
            checked += 1
    assert checked + shared == sum(len(cap.params) for cap in CAPABILITY_REGISTRY.values() if cap.author_visible)
    assert checked and shared
    assert request_dossier(request) == json.loads(user) == packet


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
def test_retired_loaded_status_vocabulary_never_reaches_author_or_changes_literal_sources(monkeypatch, mode):
    """An old producer's global registry is not an Author effect vocabulary."""
    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", mode)
    entries = [{"id": n, "fullName": f"ContextFixture/RegisteredStatus{n}"} for n in range(1, 2049)]
    source = {
        "name": "Bounded native reference context",
        "tooltipLines": ["literal source " + "Ж" * 1000] * 12,
        "loadedBuffIdentitiesRaw": {"source": "native_loaded_buff_registry", "complete": False, "entries": entries},
    }
    before = copy.deepcopy(source)
    request, text, _ = build_initial_author_request(source, source, "retired-identities", model_name="offline")
    sent = _serialized_chat_request(monkeypatch, request)
    packet = request_dossier(sent, declaration=request)
    assert "statusIdentityChoices" not in packet["runtimeCapabilityContract"]
    assert "RegisteredStatus2048" not in json.dumps(sent)
    assert "loadedBuffIdentitiesRaw" not in json.dumps(sent)
    for side in ("A", "B"):
        assert packet["parents"][side]["packet"]["raw"]["item"]["tooltipLines"] == source["tooltipLines"]
    assert len(packet["runtimeCapabilityContract"]["catalog"]["capabilities"]) == len(compact_capability_catalog())
    assert len(text) <= PLANNER_PROMPT_LIMIT_CHARS - PLANNER_PROMPT_MIN_HEADROOM_CHARS
    assert source == before


def test_author_budget_is_the_authorized_300k_for_complete_attack_source_context():
    assert PLANNER_PROMPT_LIMIT_CHARS == 300_000


def test_shared_target_kind_sets_preserve_every_exact_capability_domain():
    _, text, _ = build_initial_author_request({}, {}, "target-kind-sharing", model_name="offline")
    catalog = json.loads(text)["runtimeCapabilityContract"]["catalog"]
    sets = catalog["fieldGuide"].get("targetKindSets", {})
    assert sets
    expected = {card["fn"]: card["targets"] for card in compact_capability_catalog()}
    for card in catalog["capabilities"]:
        targets = sets[card["targetsRef"]] if "targetsRef" in card else card["targets"]
        assert targets == expected[card["fn"]]
        assert ("targets" in card) != ("targetsRef" in card)


@pytest.mark.parametrize("extra_room", [None, 31], ids=["declared-limit", "changed-limit"])
def test_decimal_character_guard_accepts_exact_boundary_and_rejects_next_unicode_character(monkeypatch, extra_room):
    from infini_local.pipelines.author import prompt

    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", "json_object")
    _, initial, _ = build_initial_author_request({}, {}, "", model_name="offline")
    if extra_room is not None:
        monkeypatch.setattr(prompt, "PLANNER_PROMPT_LIMIT_CHARS", len(initial) + extra_room)
    limit = prompt.PLANNER_PROMPT_LIMIT_CHARS
    key = "Ж" * (limit - len(initial))
    before = copy.deepcopy(key)
    request, text, _ = build_initial_author_request({}, {}, key, model_name="offline")
    assert len(text) == limit
    assert len(text.encode("utf-8")) > limit
    assert request_dossier(request)["recipeKey"] == key == before
    with pytest.raises(ValueError):
        build_initial_author_request({}, {}, key + "Ж", model_name="offline")

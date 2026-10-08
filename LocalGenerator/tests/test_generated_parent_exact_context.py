"""Exact accepted parent facts at card and serialized offline stage boundaries."""
from __future__ import annotations

import copy

import pytest

from infini_local.core.runtime_authoring import compile_runtime_program, validate_runtime_wire
from infini_local.pipelines.parent_context_cards import raw_parent_card_for_llm
from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.storage.world_storage import sanitize_recipe_for_delivery


@pytest.mark.parametrize("capability", [
    "apply_generated_buff_on_use", "apply_vanilla_buff_on_use", "move_player_on_use",
    "add_hold_light", "configure_tool", "configure_item_contact_hitbox",
    "configure_accessory", "configure_armor", "damage_area_on_event", "spawn_entity_on_event",
])
def test_card_preserves_complete_accepted_mechanics(capability):
    data = sanitize_recipe_for_delivery(compile_runtime_program(build_capability_witness(capability)))
    data["id"] = "exact-accepted-parent"
    assert validate_runtime_wire(data)["ok"]
    parent = {"name": "literal source", "generatedData": data}
    before = copy.deepcopy(parent)
    card = raw_parent_card_for_llm(parent)["raw"]["generatedParent"]
    assert card["gameplay"] == data["gameplay"]
    assert card["accessory"] == data["accessory"]
    assert card["armor"] == data["armor"]
    expected_runtime = copy.deepcopy(data["runtimeProgram"])
    for entity in expected_runtime["entities"]:
        entity.pop("visual", None)
    assert card["runtimeProgram"] == expected_runtime
    assert card["id"] == data["id"]
    from infini_local.pipelines.llm_authoring_pipeline import build_initial_author_request
    import json
    request, user, _ = build_initial_author_request(parent, parent, {}, {}, "complete-parent", model_name="offline-test-model")
    packet = json.loads(user)
    assert json.loads(request["messages"][1]["content"]) == packet
    assert packet["parents"]["A"]["packet"]["raw"]["generatedParent"] == card
    assert packet["parents"]["B"]["packet"]["raw"]["generatedParent"] == card
    assert parent == before
    card["gameplay"]["damage"] = -1
    card["runtimeProgram"]["bindings"][0]["usePolicy"]["stackCost"] = 999
    card["accessory"]["enabled"] = "mutated detached card"
    assert parent == before


def _accepted_appearance_parent():
    from infini_local.pipelines import visual_generation_pipeline as visual
    from test_low_level_three_stage_pipeline import _visual_kit

    data = compile_runtime_program(build_capability_witness("move_straight"))
    kit = _visual_kit(data)
    kit["item"].update(
        prompt="Literal cyan gel inside red liquid, in a glass flask.",
        silhouette="Rounded bottle with a narrow neck and cork.",
        visualIdentity="cyan gel contained in red liquid",
        palette=["translucent cyan gel", "deep red liquid"],
        grip={"normalizedX": 0.5, "normalizedY": 0.29},
        preferredCanvasSize=64, renderSizePx=26, forwardAngleDegrees=-90,
        inventoryScale=1.25, worldScale=0.75,
    )
    for entity in kit["entities"]:
        if entity["visualProjectRef"] == "item":
            entity.update({key: kit["item"][key] for key in ("prompt", "silhouette", "visualIdentity")})
        if entity["entityId"] != data["runtimeProgram"]["itemEntityId"]:
            entity.update(
                assetMode="baked_sprite", visualProjectRef="entity", scale=1.5,
                prompt="one literal cyan bead", silhouette="one round bead",
                visualIdentity="detached cyan bead", preferredCanvasSize=32,
                renderSizePx=12, forwardAngleDegrees=0,
            )
    accepted, errors = visual._validate_kit(
        kit, [entity["id"] for entity in data["runtimeProgram"]["entities"]],
        data["runtimeProgram"]["itemEntityId"],
    )
    assert accepted is not None, errors
    delivered = sanitize_recipe_for_delivery(visual._apply_kit(data, accepted))
    delivered.update(id="literal-parent-definition", recipeKey="literal-parent-recipe")
    return {"name": "opaque identity", "generatedData": delivered}


def test_visual_card_preserves_exact_accepted_appearance_with_entity_provenance():
    parent = _accepted_appearance_parent()
    before = copy.deepcopy(parent)
    data = parent["generatedData"]
    author_card = raw_parent_card_for_llm(parent)["raw"]["generatedParent"]
    card = raw_parent_card_for_llm(parent, include_visual_reference=True)["raw"]["generatedParent"]
    expected_visual = {key: data["visual"][key] for key in (
        "imagePrompt", "negativePrompt", "palette", "preferredCanvasSize", "renderSizePx",
        "forwardAngleDegrees", "inventoryScale", "worldScale", "grip",
    )}
    assert card["visual"] == expected_visual
    for source, projected in zip(data["runtimeProgram"]["entities"], card["runtimeProgram"]["entities"]):
        assert projected["id"] == source["id"]
        assert projected["kind"] == source["kind"]
        assert projected["visual"] == {key: value for key, value in source["visual"].items()
                                       if key not in ("spritePath", "spriteUrl", "spriteStatus", "spriteTechnicalScore")}
    assert card["id"] == data["id"]
    assert card["recipeKey"] == data["recipeKey"]
    assert "visual" not in author_card
    assert all("visual" not in entity for entity in author_card["runtimeProgram"]["entities"])
    mechanics_only = copy.deepcopy(card)
    mechanics_only.pop("visual")
    for entity in mechanics_only["runtimeProgram"]["entities"]:
        entity.pop("visual")
    assert mechanics_only == author_card
    assert parent == before
    card["visual"]["grip"]["normalizedY"] = 0.99
    card["visual"]["palette"].append("mutated detached palette")
    card["runtimeProgram"]["entities"][0]["visual"]["silhouette"] = "mutated detached silhouette"
    assert parent == before


@pytest.mark.parametrize("format_mode", ["json_schema", "json_object"])
def test_serialized_visual_director_repair_keep_exact_parent_facts(monkeypatch, format_mode):
    import json
    import socket
    from collections import deque
    from infini_local.pipelines import visual_generation_pipeline as visual
    from test_low_level_three_stage_pipeline import _visual_kit

    def denied(*args, **kwargs):
        raise AssertionError("offline test forbids network")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr("infini_local.pipelines.llm_transport.LLM_RESPONSE_FORMAT_MODE", format_mode)
    monkeypatch.setattr(visual, "USE_LLM", True)
    monkeypatch.setattr(visual, "VISUAL_DIRECTOR_LLM", True)
    monkeypatch.setattr(visual, "resolve_llm_model", lambda: "offline-test-model")
    monkeypatch.setattr(visual, "trace_stage_request", lambda *a, **k: None)
    parent = _accepted_appearance_parent()
    child = compile_runtime_program(build_capability_witness("apply_generated_buff_on_use"))
    before = copy.deepcopy((parent, child))
    chosen = _visual_kit(child)
    broken = copy.deepcopy(chosen)
    broken["item"]["inventoryScale"] = 99
    responses = deque([broken, {
        "schema": visual.VISUAL_REPAIR_PATCH_SCHEMA,
        "itemPatch": {"inventoryScale": chosen["item"]["inventoryScale"]},
        "entitiesUpsert": [], "entityIdsDelete": [], "entityIndicesDelete": [],
        "animationPlan": None, "note": "exact invalid scale only",
    }])
    requests = []

    def provider_stub(request, **kwargs):
        requests.append(copy.deepcopy(request))
        return {"choices": [{"message": {"content": json.dumps(responses.popleft())}}]}

    monkeypatch.setattr(visual, "llm_chat_json", provider_stub)
    result = visual.apply_visual_director(child, parent, parent, {}, {})
    assert len(requests) == 2 and not responses
    assert result["visualKit"] == chosen
    director, repair = [json.loads(request["messages"][1]["content"]) for request in requests]
    expected = raw_parent_card_for_llm(parent, include_visual_reference=True)
    assert director["parents"] == repair["parentFactsReadOnly"] == {
        "parentA": {"packet": expected}, "parentB": {"packet": expected},
    }
    assert repair["repairScope"]["fieldPermissions"]["itemPaths"] == ["inventoryScale"]
    assert parent == before[0]
    assert {key: value for key, value in child.items() if key != "debug"} == before[1]
    assert result["gameplay"] == child["gameplay"]


def test_real_author_builder_preserves_present_accepted_parent_without_visuals(monkeypatch):
    import json
    from infini_local.pipelines import llm_authoring_pipeline as author

    # Sparse wire control proves presence/absence semantics independently from
    # complete compiler witnesses and the frozen-corpus replay; nothing is clipped.
    data = {
        "id": "source-definition", "recipeKey": "source-recipe",
        "gameplay": {"generatedBuff": {"durationTicks": 360, "jumpBoost": 1.5}},
        "runtimeProgram": {
            "apiVersion": "infini.runtime-program.v5", "schema": "infini.runtime-program.wire.v3",
            "itemEntityId": "body", "primaryEntityId": "body", "primaryOwner": "item_body",
            "entities": [{"id": "body", "kind": "item_body", "events": [], "visualRole": "inventory_item",
                          "visual": {"role": "inventory_item", "visualIdentity": "Visual-only literal", "scale": 1.25}}],
            "itemUse": {"configured": True, "useStyle": "drink_liquid"},
            "bindings": [{"id": "drink", "input": "primary_use", "role": "primary", "usePolicy": {
                "action": {"kind": "apply_item_effects", "targetId": "body"},
                "stackCost": 1, "contactDamage": False,
            }}],
        },
        "visual": {"palette": ["cyan", "red"], "renderSizePx": 26},
    }
    assert validate_runtime_wire(data)["ok"]
    parent = {"name": "literal", "generatedData": data}
    before = copy.deepcopy(parent)
    request, user, _ = author.build_initial_author_request(parent, {}, {}, {}, "exact-parent", model_name="offline-test-model")
    packet = json.loads(user)["parents"]["A"]["packet"]
    assert json.loads(request["messages"][1]["content"])["parents"]["A"]["packet"] == packet
    assert packet == raw_parent_card_for_llm(parent)
    assert packet["raw"]["generatedParent"]["gameplay"] == data["gameplay"]
    assert packet["raw"]["generatedParent"]["id"] == "source-definition"
    assert "Visual-only literal" not in user
    assert "palette" not in json.dumps(packet)
    assert parent == before


@pytest.mark.parametrize("status,lines", [
    ("observed_literal", ["  Телепортирует вас домой  ", "", "\tДословная строка\n"]),
    ("refused_line_bound", []),
    ("refused_character_bound", []),
])
def test_literal_tooltip_source_survives_real_author_visual_repair(monkeypatch, status, lines):
    import json
    import socket
    from infini_local.pipelines import llm_authoring_pipeline as author
    from infini_local.pipelines import visual_generation_pipeline as visual

    def denied(*args, **kwargs):
        raise AssertionError("offline test forbids network")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr("infini_local.pipelines.llm_transport.LLM_RESPONSE_FORMAT_MODE", "json_object")
    monkeypatch.setattr(visual, "resolve_llm_model", lambda: "offline-test-model")
    monkeypatch.setattr(visual, "trace_stage_request", lambda *a, **k: None)
    parent = {
        "name": "literal source", "fullName": "Terraria/RecallPotion",
        "tooltipLines": lines, "tooltipSource": {
            "source": "Lang.GetTooltip", "fullName": "Terraria/RecallPotion",
            "language": "ru-RU", "status": status,
        },
    }
    before = copy.deepcopy(parent)
    request, user, _ = author.build_initial_author_request(parent, {}, {}, {}, "literal-tooltip", model_name="offline-test-model")
    author_packet = json.loads(user)["parents"]["A"]["packet"]
    assert json.loads(request["messages"][1]["content"])["parents"]["A"]["packet"] == author_packet
    captured = []

    def provider_stub(request, **kwargs):
        captured.append(copy.deepcopy(request))
        return {"choices": [{"message": {"content": "{}"}}]}

    monkeypatch.setattr(visual, "llm_chat_json", provider_stub)
    data = compile_runtime_program(build_capability_witness("apply_generated_buff_on_use"))
    visual._request_visual_kit(data, parent, {}, {}, {})
    visual._request_visual_kit(data, parent, {}, {}, {}, repair_errors=[], previous={}, repair_scope={})
    packets = [author_packet,
               json.loads(captured[0]["messages"][1]["content"])["parents"]["parentA"]["packet"],
               json.loads(captured[1]["messages"][1]["content"])["parentFactsReadOnly"]["parentA"]["packet"]]
    for packet in packets:
        assert packet["raw"]["item"]["tooltipLines"] == lines
        assert packet["raw"]["item"]["tooltipSource"] == parent["tooltipSource"]
    detached = raw_parent_card_for_llm(parent)
    detached["raw"]["item"]["tooltipLines"].append("detached")
    detached["raw"]["item"]["tooltipSource"]["language"] = "changed"
    assert parent == before


@pytest.mark.parametrize("runtime", [None, []])
def test_visual_projection_keeps_independent_source_when_runtime_is_unknown(runtime):
    parent = {"name": "literal", "generatedData": {
        "id": "old-source-definition", "runtimeProgram": runtime,
        "visual": {"palette": ["literal red"], "grip": {"normalizedX": 0.0, "normalizedY": 1.0}},
    }}
    before = copy.deepcopy(parent)
    card = raw_parent_card_for_llm(parent, include_visual_reference=True)["raw"]["generatedParent"]
    assert card["visual"] == parent["generatedData"]["visual"]
    assert card["runtimeProgram"] == {}
    assert "gameplay" not in card and "accessory" not in card and "armor" not in card
    assert "visual" not in raw_parent_card_for_llm(parent)["raw"]["generatedParent"]
    assert parent == before


@pytest.mark.parametrize("surface", ["directProjectileRaw", "effectiveProjectileRaw"])
def test_verified_motion_reference_is_exact_in_author_visual_repair(monkeypatch, surface):
    import json
    from infini_local.pipelines import llm_authoring_pipeline as author
    from infini_local.pipelines import visual_generation_pipeline as visual
    from infini_local.pipelines.parent_context_pipeline import compact_projectile_profile

    observation = {
        "source": "verified_native_AI_001_reference", "fullName": "Terraria/WoodenArrowFriendly",
        "sourceMethodSha256": "5ce22f6374b8b786ee332454aa0bb136ebd20c57520929b41fe4f328dca56d9b",
        "firstGravityUpdate": 15, "verticalVelocityIncrementPerUpdate": 0.1,
        "maxDownwardVelocityPxPerUpdate": 16,
        "units": "velocity in pixels/projectile update; start counts native AI invocations",
        "scope": "Native dry initial flight with default AI state; not collision/liquid/global-mod behavior. Read-only reference, not inherited execution. Generated move_gravity_arc starts immediately and is not an exact delayed native-AI replica. Author chooses the trajectory explicitly.",
    }
    source = {"type": 1, "sourceMod": "Terraria", "internalName": "WoodenArrowFriendly",
              "fullName": "Terraria/WoodenArrowFriendly", "arrow": True, "motionReference": observation}
    before = copy.deepcopy(source)
    compact = compact_projectile_profile(source)
    assert compact["motionReference"] == observation
    compact["motionReference"]["scope"] = "mutated detached reference"
    assert source == before
    without = {key: value for key, value in source.items() if key != "motionReference"}
    assert "motionReference" not in compact_projectile_profile(without)
    parent = {"name": "literal source", surface: source}
    parent_before = copy.deepcopy(parent)
    _, user, _ = author.build_initial_author_request(parent, {}, {}, {}, "source-motion", model_name="offline-test-model")
    monkeypatch.setattr(visual, "resolve_llm_model", lambda: "offline-test-model")
    monkeypatch.setattr(visual, "trace_stage_request", lambda *a, **k: None)
    monkeypatch.setattr("infini_local.pipelines.llm_transport.LLM_RESPONSE_FORMAT_MODE", "json_object")
    requests = []

    def provider_stub(request, **kwargs):
        requests.append(copy.deepcopy(request))
        return {"choices": [{"message": {"content": "{}"}}]}

    monkeypatch.setattr(visual, "llm_chat_json", provider_stub)
    child = compile_runtime_program(build_capability_witness("move_straight"))
    visual._request_visual_kit(child, parent, {}, {}, {})
    visual._request_visual_kit(child, parent, {}, {}, {}, repair_errors=[], previous={}, repair_scope={})
    packets = [json.loads(user)["parents"]["A"]["packet"],
               json.loads(requests[0]["messages"][1]["content"])["parents"]["parentA"]["packet"],
               json.loads(requests[1]["messages"][1]["content"])["parentFactsReadOnly"]["parentA"]["packet"]]
    key = "directProjectile" if surface == "directProjectileRaw" else "effectiveProjectile"
    for packet in packets:
        assert packet["raw"][key]["motionReference"] == observation
    assert parent == parent_before


def test_projectile_dedupe_does_not_erase_distinct_motion_observations():
    base = {"type": 1, "internalName": "literal", "sourceMod": "Terraria", "width": 10, "height": 10}
    reference = {"source": "verified native", "scope": "literal source scope", "firstGravityUpdate": 15}
    for direct_ref in (None, {**reference, "firstGravityUpdate": 0}):
        direct = copy.deepcopy(base)
        if direct_ref is not None:
            direct["motionReference"] = direct_ref
        effective = {**base, "motionReference": reference}
        parent = {"name": "literal source", "directProjectileRaw": direct, "effectiveProjectileRaw": effective}
        before = copy.deepcopy(parent)
        card = raw_parent_card_for_llm(parent)
        assert card["raw"]["effectiveProjectile"]["motionReference"] == reference
        assert parent == before

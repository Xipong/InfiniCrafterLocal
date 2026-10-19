
from prompt_packet_helpers import request_dossier, dossier_text
"""Actual Author packets keep registry mechanics without contradictory global prose."""
from copy import deepcopy
import json

import pytest

from infini_local.core import llm_config
from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY, compact_capability_catalog
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.pipelines import llm_authoring_pipeline as author
from infini_local.pipelines.parent_context_cards import raw_parent_card_for_llm
from infini_local.qa.capability_witnesses import build_capability_witness
from test_author_request_compaction import _expand_constraint_references


def _stationary_periodic_shooter(pool=None):
    doc = build_capability_witness("target_and_fire")
    calls = doc["runtimeProgram"]["calls"]
    controller = next(row for row in calls if row["fn"] == "target_and_fire")
    calls.remove(controller)
    root, child = controller["target"], controller["params"]["shotEntity"]
    calls.append({"id": "periodic_shot", "fn": "spawn_entity_on_event", "target": root, "params": {
        "when": {'everySeconds': (30) / 60}, "entity": child, "count": 1, "spreadRadians": 0.0,
        "damageBasis": "authored_child", "knockbackBasis": "authored_child", "damageMultiplier": 1.0,
        'delaySeconds': (0) / 60,
    }})
    if pool is not None:
        calls.append({"id": "descendant_pool", "fn": "set_descendant_concurrency", "target": root,
                      "params": {"maxActive": pool}})
    return doc, root, child


@pytest.mark.parametrize("mode", ["json_object", "json_schema", "off"])
def test_serialized_initial_packet_preserves_registry_and_source_without_repeated_global_blocks(monkeypatch, mode):
    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", mode)
    parents = ({"name": "Native source", "useAmmo": 97},
               {"name": "Generated source", "generatedData": compile_runtime_program(build_capability_witness("configure_weapon_ammo"))})
    before = deepcopy(parents)
    request, user, system = author.build_initial_author_request(*parents, "consistency", model_name="offline")
    assert dossier_text(request) == user
    assert (request["response_format"] or {}).get("type") == (None if mode == "off" else mode)
    packet = json.loads(user)
    assert parents == before
    assert packet["parents"] == {key: {"packet": raw_parent_card_for_llm(parent)}
                                 for key, parent in zip(("A", "B"), parents)}
    assert "gameplayAuthoringStages" not in packet
    assert set(packet["runtimeCapabilityContract"]) == {"catalog", "technicalNotes"}
    assert "forbidden" not in packet["requiredJsonShape"]
    assert "runtimeProgram alone defines executable gameplay" in system
    priority = " ".join(packet["priorityHeader"])
    assert "ammo" not in priority.casefold()  # Deleted obsolete ban, no replacement paragraph.
    assert "No ammo-consuming weapon capability exists" not in user
    assert "stationary contact, not a firing turret" not in user
    catalog = packet["runtimeCapabilityContract"]["catalog"]
    cards = {row["fn"]: row for row in catalog["capabilities"]}
    expanded = _expand_constraint_references(
        {fn: {key: value for key, value in card.items() if key != "constructionMeaning"}
         for fn, card in cards.items()}, catalog["fieldGuide"]["consumerConstraints"])
    assert expanded == {row["fn"]: row for row in compact_capability_catalog()}
    # Ammo semantics stay on the existing canonical cards in every transport mode.
    assert "selected ammo projectile AI is not copied" in cards["configure_weapon_ammo"]["does"]
    assert "does not configure a weapon to consume ammo" in cards["configure_vanilla_ammo_item"]["does"]
    assert "whole generated item (not ammo" in catalog["fieldGuide"]["stackCost"]
    assert "explicit card default" in catalog["fieldGuide"]["paramNotation"]
    assert "A neutral annotation alone" not in catalog["fieldGuide"]["sourceValues"]
    assert all("constructionMeaning" not in row for row in catalog["inputs"]
               if row["input"] in ("primary_use", "alternate_use"))
    assert all("constructionMeaning" not in row for row in catalog["events"]
               if row["event"] in ("on_use", "on_expire"))
    budget = packet["runtimeProgramInvariants"]["graphAndSpawnBudget"]
    assert all(phrase in budget for phrase in ("static sum", "default lifetime allowance does not replenish",
               "set_descendant_concurrency", "replenishable live-slot pool", "ancestor limits"))


@pytest.mark.parametrize("pool", [None, 3])
def test_stationary_periodic_shooter_is_admitted_without_targeting_controller(pool):
    doc, root_id, child_id = _stationary_periodic_shooter(pool)
    before = deepcopy(doc)
    assert not any(row["fn"] == "target_and_fire" for row in doc["runtimeProgram"]["calls"])
    assert validate_runtime_program(doc)["ok"]
    wire = compile_runtime_program(doc)
    assert validate_runtime_wire(wire)["ok"]
    assert doc == before
    root = next(row for row in wire["runtimeProgram"]["entities"] if row["id"] == root_id)
    assert root["kind"] == "stationary_projectile"
    assert "controller" not in root and "targeting" not in root
    assert [(row["event"], row["action"], row["periodTicks"], row["entityId"])
            for row in root["events"]] == [("periodic", "spawn_entity_on_event", 30, child_id)]
    if pool is None:
        assert "descendantMaxActive" not in root["spawn"]
    else:
        assert root["spawn"]["descendantMaxActive"] == pool
    # Concurrency changes runtime occupancy, not the static graph/depth ceilings.
    for row in doc["runtimeProgram"]["calls"]:
        if row["id"] == "periodic_shot":
            row["params"]["entity"] = root_id
    assert not validate_runtime_program(doc)["ok"]


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
def test_actual_scoped_repair_explains_stationary_shooting_without_changing_permissions(monkeypatch, mode):
    from test_repair_gameplay_contract import _offline_gameplay_repair

    doc, _, _ = _stationary_periodic_shooter(pool=3)
    correction = deepcopy(next(row for row in doc["runtimeProgram"]["calls"] if row["id"] == "descendant_pool"))
    next(row for row in doc["runtimeProgram"]["calls"] if row["id"] == "descendant_pool")["params"]["maxActive"] = 0
    repaired, dossier = _offline_gameplay_repair(monkeypatch, doc, {
        "note": "Correct only invalid concurrent capacity", "realizationReplacement": doc["realization"],
        "callsUpsert": [correction],
    }, mode)
    truth = dossier["runtimeExecutionTruth"]["entityTopology"]
    assert "periodic spawn_entity_on_event can shoot" in truth
    assert "target_and_fire separately provides NPC acquisition" in truth
    assert "not a firing turret/sentry" not in truth
    assert dossier["repairScope"]["fieldPermissions"]["calls"] == [
        {"id": "descendant_pool", "paths": ["params.maxActive"]}]
    card = next(row for row in dossier["existingBrokenCapabilityCards"] if row["fn"] == "set_descendant_concurrency")
    assert card == CAPABILITY_REGISTRY["set_descendant_concurrency"].prompt_card()
    assert validate_runtime_wire(compile_runtime_program(repaired))["ok"]

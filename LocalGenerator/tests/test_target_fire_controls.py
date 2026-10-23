"""Composable targeting controls preserve exact author choices and frozen neighbors."""
from copy import deepcopy
import pytest
from test_sentry_targeting_contract import _fixture, _targeting
from repair_test_helpers import provider_roundtrip
from infini_local.pipelines import author_item_contract as contract
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.core.runtime_authoring.repair_scope import build_runtime_repair_scope, filter_repair_patch_scope
from infini_local.core.runtime_authoring.program_schema import apply_repair_patch

FILTER = dict(minimumRangeTiles=2, coneRadians=1.2, coneDirection="projectile_velocity", bossFilter="boss_only", minimumHealthRatio=.2, maximumHealthRatio=.6)

def accepted(options):
    doc, call = _fixture(**options)
    before = deepcopy(doc)
    assert validate_runtime_program(doc)["ok"]
    restored = provider_roundtrip(doc, {"type": "json_schema", "json_schema": {"schema": contract.author_item_provider_response_schema()}})
    wire = compile_runtime_program(restored)
    assert validate_runtime_wire(wire)["ok"]
    assert {key: _targeting(wire)[key] for key in options} == options
    assert wire["runtimeContract"]["technicalLoweringAudit"]["ok"]
    assert doc == before
    return doc, call, wire

def rejected(options, bad):
    doc, call, wire = accepted(options)
    wire.pop("runtimeContract")
    for key, value in bad.items():
        broken = deepcopy(doc); call_bad = next(c for c in broken["runtimeProgram"]["calls"] if c["id"] == call["id"])
        call_bad["params"][key] = value
        assert not validate_runtime_program(broken)["ok"]
        delivered = deepcopy(wire); _targeting(delivered)[key] = value
        assert not validate_runtime_wire(delivered)["ok"]
        scope = build_runtime_repair_scope(broken, validate_runtime_program(broken)["errors"])
        candidate = deepcopy(call); candidate["params"]["count"] = 3
        patch, audit = filter_repair_patch_scope(broken, {"callsUpsert": [candidate], "note": "repair exact target leaf"}, scope)
        assert apply_repair_patch(broken, patch) == doc
        assert audit["ignoredChanges"]

def test_filter_joint_delivery_rejection_and_frozen_repair():
    rejected(FILTER, dict(minimumRangeTiles=121, coneRadians=-1, coneDirection="guessed", bossFilter=None, minimumHealthRatio=-.1, maximumHealthRatio=1.1))
    doc, call = _fixture(**{**FILTER, "minimumHealthRatio": .8})
    assert not validate_runtime_program(doc)["ok"]


def test_priority_and_manual_target_delivery_rejection_repair():
    for priority in ("distance", "lowest_health", "highest_health", "closest_to_owner", "facing_alignment"):
        accepted({**FILTER, "targetPriority": priority, "targetPolicy": "player_assigned_only"})
    rejected({"targetPriority": "lowest_health", "targetPolicy": "player_assigned_only"}, {"targetPriority": "boss_name", "targetPolicy": "automatic_guess"})


def test_predictive_aim_exact_delivery_scope_and_child_handoff_requirement():
    options = dict(aimMode="velocity_lead", leadSeconds=.5, maximumLeadTiles=4)
    doc, call = _fixture(**options)
    child = next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "configure_spawn" and c["target"] == call["params"]["shotEntity"])
    child["params"]["aim"] = "velocity"
    assert validate_runtime_program(doc)["ok"]
    wire = compile_runtime_program(doc)
    assert validate_runtime_wire(wire)["ok"]
    child["params"]["aim"] = "cursor"
    assert not validate_runtime_program(doc)["ok"]
    # Repair owns the incompatible selector, while the authored child and valid
    # lead horizon stay frozen. A lead option is not unconditional create support.
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    assert scope["create"]["calls"]["allowed"] is False
    candidate, child_candidate = deepcopy(call), deepcopy(child)
    candidate["params"].update(aimMode="direct", leadSeconds=1.5)
    child_candidate["params"]["aim"] = "velocity"
    patch, audit = filter_repair_patch_scope(doc,
        {"callsUpsert": [candidate, child_candidate], "note": "repair lead selector only"}, scope)
    repaired = apply_repair_patch(doc, patch)
    expected = deepcopy(doc)
    next(c for c in expected["runtimeProgram"]["calls"] if c["id"] == call["id"])["params"]["aimMode"] = "direct"
    assert repaired == expected
    assert validate_runtime_program(repaired)["ok"]
    assert audit["ignoredChanges"]
    wire.pop("runtimeContract")
    next(e for e in wire["runtimeProgram"]["entities"] if e["id"] == call["params"]["shotEntity"])["spawn"]["aim"] = "cursor"
    assert not validate_runtime_wire(wire)["ok"]
    rejected(dict(aimMode="direct", leadSeconds=.5, maximumLeadTiles=4), dict(aimMode="guessed", leadSeconds=2.1, maximumLeadTiles=-1))

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

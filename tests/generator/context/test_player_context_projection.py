"""Player scope reaches real requests without a counter-only diagnostic envelope."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import re

import pytest

from infini_local.pipelines.context.mechanics_context import _author_source_graph


def _producer_scope():
    source = (Path(__file__).resolve().parents[3]
              / "mod/InfiniCrafterLocal/Common/Services/Generation/GeneratorClient.SourceGraph.Export.cs")
    match = re.search(r'\["scope"\] = "([^"\r\n]+)"', source.read_text(encoding="utf-8"))
    assert match is not None
    return match[1]


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("with_mechanics_source", [False, True])
@pytest.mark.parametrize("unknown_field", [False, True])
def test_player_scope_without_diagnostic_envelope_in_production_requests(
        monkeypatch, mode, with_mechanics_source, unknown_field):
    from infini_local.core import llm_config
    from infini_local.core.runtime_authoring.validator import validate_runtime_program
    from infini_local.pipelines.author.request import build_initial_author_request, build_gameplay_repair_dossier
    from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
    from prompt_packet_helpers import expand_native_source_references, request_dossier
    from repair_test_helpers import repair_with_response, assert_delivery

    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", mode)
    scope = _producer_scope()
    qualification = "Unlinked player effects are outside parent mechanics, not proven inactive."
    assert scope.count(qualification) == 1
    graph = {"source": "parent_reachable_compiled_source_graph", "version": 1,
             "nodes": [], "scope": scope, "unresolved": ["player_context_dependency_unresolved"]}
    if unknown_field:
        graph["diagnosticSecretMarker"] = "not for Author"
    parent = {"name": "Source-scoped parent", "parentSourceGraph": graph}
    if with_mechanics_source:
        parent["directProjectileRaw"] = {"type": 31, "mechanicsSource": {
            "source": "native_mechanics_source", "version": 1, "identity": {"type": 31},
            "records": [], "unresolved": []}}
    before = copy.deepcopy(parent)
    request, _, _ = build_initial_author_request(parent, {}, "offline", model_name="offline")
    assert request["response_format"]["type"] == mode
    author = expand_native_source_references(request_dossier(json.loads(json.dumps(request))))

    doc = build_runtime_fixture("workbench_blade")
    stats = next(row for row in doc["runtimeProgram"]["calls"] if row["fn"] == "item_stats")
    stats["params"].pop("manaCost")
    good = copy.deepcopy(doc)
    incoming = copy.deepcopy(stats)
    incoming["params"]["knockback"] = 5.0
    stats["params"]["damage"] = -1
    broken = copy.deepcopy(doc)
    report = validate_runtime_program(doc)
    assert not report["ok"]
    baseline = build_gameplay_repair_dossier(doc, {}, {}, failure_report=report)
    repaired, request = repair_with_response(monkeypatch, doc,
        {"note": "correct only invalid damage", "callsUpsert": [incoming]}, mode, parents=(parent, {}))
    repair = expand_native_source_references(request_dossier(json.loads(json.dumps(request))))
    assert repair["repairScope"] == baseline["repairScope"]
    assert repair["acceptedItemContext"]["runtimeProgram"] == broken["runtimeProgram"]
    assert repaired["runtimeProgram"] == good["runtimeProgram"]
    assert repaired["debug"]["gameplayRepairFilterAudit"]["ignoredChanges"]
    assert validate_runtime_program(repaired)["ok"]
    assert_delivery(repaired)

    for raw in [author["parents"]["A"]["packet"]["raw"], repair["parents"]["a"]["packet"]["raw"]]:
        projected = raw["item"]["parentSourceGraph"]
        assert projected["scope"] == scope
        assert projected["unresolved"] == graph["unresolved"]
        assert "externalPlayerContext" not in json.dumps(raw)
        assert "unlinkedHookCount" not in json.dumps(raw)
        assert "diagnosticSecretMarker" not in json.dumps(raw)
        if unknown_field:
            assert projected["transportOmissions"]["unknownFieldCount"] == 1
        else:
            assert "transportOmissions" not in projected
    assert doc == broken and parent == before


def test_retired_player_counter_uses_existing_unknown_field_policy():
    graph = {"source": "parent_reachable_compiled_source_graph", "version": 1, "nodes": [],
             "unresolved": ["player_context_dependency_unresolved"],
             "externalPlayerContext": {"unlinkedHookCount": 2, "scope": "old capture diagnostic"}}
    before = copy.deepcopy(graph)
    projected = _author_source_graph(graph)
    assert projected is not None
    assert "externalPlayerContext" not in projected
    assert projected["unresolved"] == graph["unresolved"]
    assert projected["transportOmissions"]["unknownFieldCount"] == 1
    assert graph == before

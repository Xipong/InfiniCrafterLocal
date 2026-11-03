"""Literal outgoing timing guidance and frozen leaf-local Gameplay Repair."""
from copy import deepcopy
import json

import pytest

from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.pipelines.author import request as author
from prompt_packet_helpers import request_dossier
from repair_test_helpers import provider_roundtrip, repair_with_response
from test_modifier_timing_windows import CASES, document
from test_source_unit_guidance import _repair_request, _serialized_chat_request


def _timing_card(card):
    """Assert the public decision, not parity between two registry projections."""
    rule, = [row for row in card["requires"] if row["kind"] == "timing_pair_or_window"]
    assert rule["allowAbsent"] is True
    assert (rule["param"], rule["otherParam"], rule["anyOf"]) == (
        "startDelay", "duration", ["window"])
    window = card["params"]["window"]
    assert window.get("default") == window.get("neutral") == {"phase": "always"}
    for key in ("startDelay", "duration", "window"):
        assert not card["params"][key].get("required", False)


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("stage", ["Author", "Repair"])
@pytest.mark.parametrize("fn,member,author_leaf,wire_leaf,value", CASES)
def test_actual_cards_advertise_unrestricted_default_and_conditional_pair(
    monkeypatch, mode, stage, fn, member, author_leaf, wire_leaf, value,
):
    monkeypatch.setattr('infini_local.core.llm_config.LLM_RESPONSE_FORMAT_MODE', mode)
    if stage == "Author":
        request, _, _ = author.build_initial_author_request({}, {}, "unrestricted-timing", model_name="offline")
        sent = _serialized_chat_request(monkeypatch, request)
        catalog = request_dossier(sent, declaration=request)["runtimeCapabilityContract"]["catalog"]
        card, = [row for row in catalog["capabilities"] if row["fn"] == fn]
        # Actual outgoing schema accepts historical timing and nullable transport
        # restores exact sparse Author source, without injecting timing fields.
        for form in ("omitted", "pair", "window", "intersection"):
            source, _ = document(fn, form)
            # Exercise the public required envelope; witness-only diagnostic
            # concept/realization metadata is not part of this timing fixture.
            source = {key: source[key] for key in ("name", "category", "runtimeProgram")}
            before = deepcopy(source)
            restored = provider_roundtrip(source, sent["response_format"])
            assert validate_runtime_program(restored)["ok"]
            assert restored == before and source == before
    else:
        broken, call = document(fn, "omitted")
        call["params"][author_leaf] = -99999
        request, _ = _repair_request(monkeypatch, mode, {}, broken)
        sent = _serialized_chat_request(monkeypatch, request)
        repair = request_dossier(sent, declaration=request)
        card, = repair["existingBrokenCapabilityCards"]
        assert card["fn"] == fn
        assert repair["repairScope"]["fieldPermissions"]["calls"] == [
            {"id": call["id"], "paths": ["params." + author_leaf]}]
    _timing_card(card)


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("form", ["omitted", "pair", "window"])
@pytest.mark.parametrize("fn,member,author_leaf,wire_leaf,value", CASES)
def test_numeric_repair_cannot_fill_or_rewrite_accepted_timing_in_actual_packets(
    monkeypatch, mode, form, fn, member, author_leaf, wire_leaf, value,
):
    source, call = document(fn, form)
    call["params"][author_leaf] = value
    expected = deepcopy(source)
    assert validate_runtime_program(expected)["ok"]
    call["params"][author_leaf] = -99999
    frozen = json.dumps(source, sort_keys=True)
    hostile = deepcopy(call)
    hostile["params"].update({author_leaf: value, "startDelay": 7,
                              "duration": 8, "window": {"phase": "outbound"}})
    incoming = {
        "note": "Fix only the numeric leaf; hostile timing fill/rewrite/delete must be ignored",
        "callsUpsert": [hostile],
        "callParamKeysDelete": [{"callId": call["id"], "key": key}
                                for key in ("startDelay", "duration", "window")],
    }
    repaired, request = repair_with_response(monkeypatch, source, incoming, mode)
    sent = _serialized_chat_request(monkeypatch, request)
    dossier = request_dossier(sent, declaration=request)
    assert dossier["repairScope"]["fieldPermissions"]["calls"] == [
        {"id": call["id"], "paths": ["params." + author_leaf]}]

    assert repaired["debug"]["gameplayRepairFilterAudit"]["ignoredChanges"]
    assert json.dumps({key: val for key, val in repaired.items() if key != "debug"}, sort_keys=True) == json.dumps(expected, sort_keys=True)
    assert json.dumps(source, sort_keys=True) == frozen
    final = compile_runtime_program(repaired)
    baseline = compile_runtime_program(expected)
    assert validate_runtime_wire(final)["ok"]
    assert final["runtimeProgram"] == baseline["runtimeProgram"]
    entity = next(row for row in final["runtimeProgram"]["entities"] if row["id"] == call["target"])
    component = entity[member]
    if form == "omitted":
        assert component["window"] == {"phase": "always"}
        assert "startDelayTicks" not in component and "durationTicks" not in component
    elif form == "pair":
        assert (component["startDelayTicks"], component["durationTicks"]) == (30, 60)
    else:
        assert component["window"] == {"phase": "always", "clock": "active", "startDelayTicks": 15, "durationTicks": 120}

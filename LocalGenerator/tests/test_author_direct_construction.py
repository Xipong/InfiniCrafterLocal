"""Contract for construction guidance in the serialized single-response Author packet."""
import json

from infini_local.pipelines.llm_authoring_pipeline import build_initial_author_request


def test_direct_construction_is_local_without_checklist_or_draft_loop(monkeypatch):
    monkeypatch.setattr("infini_local.pipelines.llm_transport.LLM_RESPONSE_FORMAT_MODE", "json_object")
    a = {"id": "blade", "name": "Blade", "damage": 7, "useTime": 20}
    b = {"id": "bench", "name": "Workbench", "createTile": 18, "useTime": 15}
    request, user, _ = build_initial_author_request(a, b, a, b, "blade+bench", model_name="gemini-2.5-flash")
    assert request["messages"][1]["content"] == user
    payload = json.loads(user)
    assert "selfCheck" not in payload
    assert "structureCheck" not in payload["runtimeProgramInvariants"]
    assert "realizationExecutionTruth" not in payload["runtimeProgramInvariants"]
    catalog = payload["runtimeCapabilityContract"]["catalog"]
    assert "requiredComponents" in catalog["entityKinds"][0]
    assert "paramNotation" in catalog["fieldGuide"]
    assert "referenceRules" in catalog["fieldGuide"]
    assert "on_use" in {row["event"] for row in catalog["events"]}
    assert "charge_then_release" in {row["fn"] for row in catalog["capabilities"]}
    assert "selfEvaluation" in payload["diagnosticReport"]
    for phrase in ("Before answering", "Check each", "Walk every", "draft-reject", "second design pass"):
        assert phrase.lower() not in user.lower()
    assert "concept" in user and "realization" in user

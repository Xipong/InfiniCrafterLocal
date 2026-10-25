
from prompt_packet_helpers import request_dossier, dossier_text
"""Serialized Author/Repair keep each construction rule at its owning guide."""
from copy import deepcopy
import json

import pytest

from infini_local.core import llm_config
from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.pipelines import llm_authoring_pipeline as author
from infini_local.pipelines.author_item_contract import RUNTIME_ROW_SHAPE_RULE
from infini_local.qa.capability_witnesses import build_capability_witness


@pytest.mark.parametrize("mode", ["json_schema", "json_object", "off"])
def test_serialized_author_keeps_spelling_once_and_preserves_mechanical_guides(monkeypatch, mode):
    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", mode)
    request, user, system = author.build_initial_author_request({}, {}, "owners", model_name="offline")
    assert dossier_text(request) == user
    packet = json.loads(user)
    catalog = packet["runtimeCapabilityContract"]["catalog"]
    guide = catalog["fieldGuide"]
    shapes = guide["rowShapes"]
    assert shapes == RUNTIME_ROW_SHAPE_RULE
    assert all(shapes.count(phrase) == 1 for phrase in (
        "one explicit id/fn/target/params envelope", "Fixed binding literals may be explicit or omitted",
        "place_item stackCost=1 and contactDamage=false", "hold/equipped stackCost=0 and contactDamage=false",
        "item-body-only action targetId=the exact unique declared item_body id",
        "Projectile action targets remain explicit", "placementCallId is required for place_item and forbidden for other actions",
    ))
    assert "Write id, fn, target and params for every new call" not in user
    assert "write fixed stackCost" not in user.casefold()
    assert "may be explicit or omitted" not in guide["bindingTarget"]
    assert "stackConsumeChancePercent" not in shapes
    assert "only with stackCost=1 outside placement" in guide["stackCost"]
    assert "omission retains the existing 100 percent debit" in guide["stackCost"]
    assert all(phrase in guide["bindingTarget"] for phrase in (
        "entity-kind allowlist", "contactDamage=true", "primaryEntityId", "disableMeleeHitbox=false",
        "no ammo category", "Item.noMelee", "configure_item_stats.damage", "set_projectile_damage",
    ))
    assert "runtimeProgram alone defines executable gameplay" in system
    header = " ".join(packet["priorityHeader"])
    assert "weapon archetype for execution" in header
    assert "Deterministic code never infers gameplay" in header
    assert "author every mechanic explicitly in runtimeProgram" in header
    assert "source tempo when available" in header
    assert "aiStyle" not in header and "Catalog membership" not in header
    motion = guide["projectileMotion"]
    assert all(phrase in motion for phrase in (
        "aiStyle do not execute native AI", "domain knowledge is not a verified source measurement",
        "independent choices", "none implies channel, collision policy or lifetime", "legal when deliberate",
    ))


@pytest.mark.parametrize("mode", ["json_schema", "json_object", "off"])
def test_serialized_overlays_keep_only_facts_missing_from_canonical_cards(monkeypatch, mode):
    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", mode)
    _, user, _ = author.build_initial_author_request({}, {}, "overlays", model_name="offline")
    catalog = json.loads(user)["runtimeCapabilityContract"]["catalog"]
    placed = next(row for row in catalog["capabilities"] if row["fn"] == "present_placed_item_sprite")
    assert all(fact in placed["constructionMeaning"] for fact in (
        "16x16/256 cells max", "post-place actors or visual callbacks are refused",
    ))
    canonical = CAPABILITY_REGISTRY["present_placed_item_sprite"].author_prompt_card()
    assert placed["does"] == canonical["does"]
    assert placed["requires"] == canonical["requires"]
    assert placed["params"]["placementCallId"] == canonical["params"]["placementCallId"]
    assert "existing full-frame root PNG" in placed["does"]
    assert "Absent call retains native presentation" in placed["does"]
    free = next(row for row in catalog["entityKinds"] if row["kind"] == "free_projectile")
    assert "requiredComponents" not in free["constructionMeaning"]
    assert free["requiredComponents"] and free["positionRequirement"]
    assert all(phrase in free["constructionMeaning"] for phrase in (
        "independent projectiles", "not a singleton", "batch count", "hold binding does not spawn again",
    ))


@pytest.mark.parametrize("mode", ["json_schema", "json_object", "off"])
def test_actual_repair_request_keeps_shape_guidance_without_duplicate_mechanical_prose(monkeypatch, mode):
    source = build_capability_witness("configure_item_stats")
    call = next(row for row in source["runtimeProgram"]["calls"] if row["fn"] == "configure_item_stats")
    call["params"]["damage"] = True
    before = deepcopy(source)
    requests = []

    class CapturedRequest(BaseException):
        """Stop at the real provider seam without a paid call or a synthetic repair."""

    def capture(request, **kwargs):
        requests.append(deepcopy(request))
        raise CapturedRequest()

    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", mode)
    for name, value in dict(
        USE_LLM=True, resolve_llm_model=lambda: "offline", llm_chat_json=capture,
        trace_event=lambda *args, **kwargs: None, trace_stage_request=lambda *args, **kwargs: None,
        llm_reasoning_system_suffix=lambda *args, **kwargs: "",
        apply_llm_common_options=lambda request, **kwargs: request,
    ).items():
        monkeypatch.setattr(author, name, value)
    with pytest.raises(CapturedRequest):
        author.repair_author_item_after_failure(source, {}, {}, "owners", failure_report=validate_runtime_program(source))
    assert source == before and len(requests) == 1
    request = requests[0]
    assert (request["response_format"] or {}).get("type") == (None if mode == "off" else mode)
    dossier = request_dossier(request)
    assert dossier["rules"].count(RUNTIME_ROW_SHAPE_RULE) == 1
    assert "may be explicit or omitted" not in dossier["runtimeExecutionTruth"]["units"]["bindingTarget"]
    assert "write fixed stackCost" not in " ".join(dossier["rules"]).casefold()
    assert "omission means no change" in " ".join(dossier["rules"])
    assert "preserve unchanged required fields and accepted optional values or absences" in " ".join(dossier["rules"])
    assert dossier["repairScope"]["fieldPermissions"]["calls"] == [{"id": call["id"], "paths": ["params.damage"]}]
    assert dossier["existingBrokenCapabilityCards"] == [CAPABILITY_REGISTRY["configure_item_stats"].prompt_card()]

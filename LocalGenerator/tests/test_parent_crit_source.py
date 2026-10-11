"""Native base crit reaches Author without becoming a generated stat default."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import re
import socket

import pytest

from infini_local.pipelines import llm_authoring_pipeline as author
from infini_local.pipelines import llm_transport
from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.core.runtime_authoring import compile_runtime_program


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("parent crit tests must stay offline")
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


def test_native_csharp_crit_projection_uses_only_request_normalized_item():
    # Static source regression, not a substitute for EngineRuntimeChecks.ParentCrit.
    from tools.check_csharp_contracts import method_body, stripped

    source = (Path(__file__).resolve().parents[2] /
              "ModSources/InfiniCrafterLocal/Common/Services/GeneratorClient.cs").read_text()
    wire = stripped(method_body(source, "ToWireItem"))
    assert re.search(r"\bcrit\s*=\s*craftItem\.crit\b", wire), "real native craft snapshot drops base Item.crit"
    assert wire.index("CraftIdentityItem(item, existing)") < wire.index("crit = craftItem.crit")
    assert not re.search(r"\bcrit\s*=\s*item\.crit\b", wire), "consumed item's prefix must not bias source crit"
    for method in ("FingerprintFromItem", "RuntimeFactsFromItem"):
        assert re.search(r"\bcrit\s*=\s*item\.crit\b", stripped(method_body(source, method)))
    assert "GetWeaponCrit" not in wire, "player-effective crit is not base recipe identity"


@pytest.mark.parametrize("mode", ["json_schema", "json_object", "off"])
@pytest.mark.parametrize("crit", [0, 4, 29])
@pytest.mark.parametrize("surface", ["top_level", "fingerprint"])
def test_native_crit_reaches_actual_author_message_unchanged(monkeypatch, mode, crit, surface):
    monkeypatch.setattr(llm_transport, "LLM_RESPONSE_FORMAT_MODE", mode)
    parent = {"name": "native base crit source", "damage": 40, "damageClass": "ranged"}
    parent.update({"crit": crit} if surface == "top_level" else {"fingerprint": {"crit": crit}})
    before = copy.deepcopy(parent)
    request, user, _ = author.build_initial_author_request(parent, {}, {}, {}, "native-base-crit", model_name="offline-test-model")
    if mode == "off":
        assert request["response_format"] is None
    else:
        assert request["response_format"]["type"] == mode
    assert request["messages"][1]["content"] == user
    packet = json.loads(user)
    assert packet["parents"]["A"]["packet"]["raw"]["item"]["crit"] == crit
    assert "crit" not in packet["parents"]["B"]["packet"]["raw"]["item"]
    assert parent == before


@pytest.mark.parametrize("mode", ["json_schema", "json_object", "off"])
def test_source_crit_is_not_confused_with_generated_equipment_bonus(monkeypatch, mode):
    monkeypatch.setattr(llm_transport, "LLM_RESPONSE_FORMAT_MODE", mode)
    data = compile_runtime_program(build_capability_witness("configure_accessory"))
    data["accessory"]["genericCrit"] = 17.0
    parent = {"name": "generated equipped bonus source", "crit": 0, "generatedData": data}
    before = copy.deepcopy(parent)
    request, _, _ = author.build_initial_author_request(parent, {}, {}, {}, "generated-crit-separation", model_name="offline-test-model")
    raw = json.loads(request["messages"][1]["content"])["parents"]["A"]["packet"]["raw"]
    assert raw["item"]["crit"] == 0
    assert raw["generatedParent"]["accessory"]["genericCrit"] == 17.0
    assert raw["generatedParent"]["gameplay"] == data["gameplay"]
    assert "crit" not in raw["generatedParent"]["gameplay"]
    assert parent == before

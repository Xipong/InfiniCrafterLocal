"""Native base crit reaches Author without becoming a generated stat default."""
from __future__ import annotations

from prompt_packet_helpers import request_dossier, dossier_text

import copy
import json
import socket

import pytest

from infini_local.core import llm_config
from infini_local.pipelines import llm_authoring_pipeline as author
from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.core.runtime_authoring.compiler import compile_runtime_program


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("parent crit tests must stay offline")
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)




# Parent projection runs before response-format selection. Cover every source
# surface/value boundary once, then retain delivery through both other formats.
@pytest.mark.parametrize("mode,crit,surface", [
    ("json_schema", crit, surface)
    for surface in ("top_level", "fingerprint") for crit in (0, 4, 29)
] + [
    ("json_object", 29, "fingerprint"),
    ("off", 0, "top_level"),
])
def test_native_crit_reaches_actual_author_message_unchanged(monkeypatch, mode, crit, surface):
    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", mode)
    parent = {"name": "native base crit source", "damage": 40, "damageClass": "ranged"}
    parent.update({"crit": crit} if surface == "top_level" else {"fingerprint": {"crit": crit}})
    before = copy.deepcopy(parent)
    request, user, _ = author.build_initial_author_request(parent, {}, "native-base-crit", model_name="offline-test-model")
    if mode == "off":
        assert request["response_format"] is None
    else:
        assert request["response_format"]["type"] == mode
    assert dossier_text(request) == user
    packet = json.loads(user)
    assert packet["parents"]["A"]["packet"]["raw"]["item"]["crit"] == crit
    assert "crit" not in packet["parents"]["B"]["packet"]["raw"]["item"]
    assert parent == before


@pytest.mark.parametrize("mode", ["json_schema", "json_object", "off"])
def test_source_crit_is_not_confused_with_generated_equipment_bonus(monkeypatch, mode):
    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", mode)
    data = compile_runtime_program(build_capability_witness("accessory"))
    data["accessory"]["genericCrit"] = 17.0
    parent = {"name": "generated equipped bonus source", "crit": 0, "generatedData": data}
    before = copy.deepcopy(parent)
    request, _, _ = author.build_initial_author_request(parent, {}, "generated-crit-separation", model_name="offline-test-model")
    raw = request_dossier(request)["parents"]["A"]["packet"]["raw"]
    assert raw["item"]["crit"] == 0
    assert raw["generatedParent"]["accessory"]["genericCrit"] == 17.0
    assert raw["generatedParent"]["gameplay"] == data["gameplay"]
    assert "crit" not in raw["generatedParent"]["gameplay"]
    assert parent == before

"""The VFX designer sees accepted mechanics, never just its textual summary."""
from __future__ import annotations

import copy
import json

import pytest

from infini_local.core import vfx_manifest as vfx
from infini_local.core.runtime_authoring import compile_runtime_program
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture


@pytest.mark.parametrize("repair", [False, True])
@pytest.mark.parametrize("fixture", [
    "workbench_blade", "umbrella_grenade", "door_on_chain", "returning_potion",
    "fishing_platform_tool", "shield_and_disc", "held_and_deployed", "equipment_tool_combat",
])
def test_actual_vfx_packet_contains_exact_read_only_runtime_mechanics(repair, fixture):
    data = compile_runtime_program(build_runtime_fixture(fixture))
    # Compare the actual compiler projection, not a guessed second mechanics DTO.
    entity = data["runtimeProgram"]["entities"][0]
    entity["visual"] = {"spritePath": "private-local-path.png", "prompt": "not mechanical"}
    original = copy.deepcopy(data)
    expected = copy.deepcopy(data["runtimeProgram"])
    for row in expected["entities"]:
        row.pop("visual", None)
    sent = []

    def capture(_system, user, *args, **kwargs):
        sent.append(json.loads(kwargs["messages"][1]["content"]) if repair else json.loads(json.dumps(user)))
        return {}

    packet = vfx._prompt_packet(data, None, None)
    if repair:
        vfx._request(capture, packet, repair_errors=[{"path": "$.slots[0].alpha", "message": "invalid"}],
                     previous={"slots": []}, repair_scope={"fieldPermissions": {"slots": []}})
    else:
        vfx._request(capture, packet)
    assert sent[0].get("acceptedRuntimeProgramReadOnly") == expected
    assert "private-local-path.png" not in json.dumps(sent[0])
    assert data == original
    packet["acceptedRuntimeProgramReadOnly"]["entities"][0]["lifetimeTicks"] = 999
    assert data == original


def test_empty_mechanical_context_does_not_invent_entities_or_parameters():
    packet = vfx._prompt_packet({}, None, None)
    assert packet.get("acceptedRuntimeProgramReadOnly") == {}

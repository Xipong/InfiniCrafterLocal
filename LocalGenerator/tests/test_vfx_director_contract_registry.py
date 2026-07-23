from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

import pytest

from infini_local.core.vfx_director_contract import (
    VFX_NUMERIC_FIELDS,
    VFX_RENDERER_RULES,
    VFX_SLOT_ENUM_FIELDS,
    VFX_TOP_ENUM_FIELDS,
    _vfx_director_validation_report,
    vfx_director_required_json_shape,
    vfx_director_surface,
)
from infini_local.core.vfx_director_prompt import build_vfx_director_prompt


def test_vfx_surface_and_prompt_shape_match_pre_migration_baseline() -> None:
    expected = json.loads(
        (
            Path(__file__).resolve().parent
            / "fixtures"
            / "vfx_director_contract_surface_v1.json"
        ).read_text(encoding="utf-8")
    )
    actual = {
        "schema": "infini.vfx-director-contract-surface.v1",
        "surface": vfx_director_surface(),
        "requiredJsonShape": vfx_director_required_json_shape(),
    }
    assert actual == expected
    prompt_shape = build_vfx_director_prompt(
        None,
        None,
        {},
        actual["surface"],
        {"slots": [2, 6]},
    )["requiredJsonShape"]
    assert prompt_shape == actual["requiredJsonShape"]


def test_vfx_field_contracts_are_closed_unique_and_well_bounded() -> None:
    slot_names = [field.name for field in VFX_SLOT_ENUM_FIELDS]
    surface_keys = [field.surface_key for field in VFX_SLOT_ENUM_FIELDS]
    numeric_names = [field.name for field in VFX_NUMERIC_FIELDS]
    assert len(slot_names) == len(set(slot_names)) == 11
    assert len(surface_keys) == len(set(surface_keys)) == 11
    assert len(numeric_names) == len(set(numeric_names)) == 15
    assert {field.name for field in VFX_TOP_ENUM_FIELDS} == {"visualBudgetClass"}
    assert all(field.values and len(field.values) == len(set(field.values)) for field in VFX_SLOT_ENUM_FIELDS)
    assert all(field.minimum < field.maximum for field in VFX_NUMERIC_FIELDS)
    assert set(VFX_RENDERER_RULES) == {"soundCue", "lightCue"}


def test_vfx_field_contracts_are_frozen() -> None:
    with pytest.raises(FrozenInstanceError):
        VFX_SLOT_ENUM_FIELDS[0].name = "renamed"  # type: ignore[misc]
    with pytest.raises(TypeError):
        VFX_RENDERER_RULES["soundCue"] = {}  # type: ignore[index]


def test_vfx_validator_consumes_registry_ranges_and_renderer_rules() -> None:
    slot: dict[str, Any] = {
        field.name: field.values[0]
        for field in VFX_SLOT_ENUM_FIELDS
    }
    for field in VFX_NUMERIC_FIELDS:
        if field.name == "effectMagnitude" or not field.required:
            continue
        slot[field.name] = field.minimum
    payload = {
        "effectMagnitude": 2.0,
        "visualBudgetClass": VFX_TOP_ENUM_FIELDS[0].values[0],
        "slots": [slot],
    }
    report = _vfx_director_validation_report(payload, max_slots=2)
    assert report["valid"] is True
    assert any(
        warning.get("path") == "effectMagnitude"
        and warning.get("clamped") == 1.0
        for warning in report["warnings"]
    )

    sound_slot = dict(slot, rendererKind="soundCue", channel="light", lane="primary")
    invalid = _vfx_director_validation_report(
        {**payload, "effectMagnitude": 1.0, "slots": [sound_slot]},
        max_slots=2,
    )
    assert invalid["valid"] is False
    assert {
        error.get("path")
        for error in invalid["errors"]
        if error.get("error") == "renderer_field_mismatch"
    } == {"slots[0].channel", "slots[0].lane"}

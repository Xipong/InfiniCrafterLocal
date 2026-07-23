from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from infini_local.core.boundary_models import (
    VisualKitBoundary,
    canonical_visual_kit_view,
)
from infini_local.core.visual_role_contracts import (
    VISUAL_BAKED_ROLE_CONTRACTS,
    VISUAL_BAKED_ROLE_PROMPT_FIELDS,
    VISUAL_FORBIDDEN_BAKED_ASSET_KEYS,
    VISUAL_ROLE_CONTRACTS,
    VISUAL_ROLE_CONTRACT_BY_NAME,
    visual_director_role_fields,
)
from infini_local.pipelines.visual_director_contract import (
    visual_director_output_contract,
    visual_kit_response_schema,
)


def test_visual_role_surface_matches_pre_migration_baseline() -> None:
    expected = json.loads(
        (
            Path(__file__).resolve().parent
            / "fixtures"
            / "visual_director_contract_surface_v1.json"
        ).read_text(encoding="utf-8")
    )
    actual = {
        "schema": "infini.visual-director-contract-surface.v1",
        "outputContract": visual_director_output_contract(),
        "providerSchema": visual_kit_response_schema(),
    }
    assert actual == expected
    assert actual["outputContract"]["roleFields"] == visual_director_role_fields()


def test_visual_roles_are_unique_and_reference_real_visual_kit_fields() -> None:
    roles = [contract.role for contract in VISUAL_ROLE_CONTRACTS]
    prompt_fields = [contract.prompt_field for contract in VISUAL_ROLE_CONTRACTS]
    assert roles == ["item", "projectile", "impact", "child", "field", "equip_overlay"]
    assert len(roles) == len(set(roles)) == 6
    assert len(prompt_fields) == len(set(prompt_fields)) == 6
    assert set(prompt_fields) <= set(VisualKitBoundary.model_fields)
    assert [contract.role for contract in VISUAL_BAKED_ROLE_CONTRACTS] == [
        "projectile", "impact", "child", "field", "equip_overlay"
    ]
    assert dict(VISUAL_BAKED_ROLE_PROMPT_FIELDS) == {
        contract.role: contract.prompt_field
        for contract in VISUAL_BAKED_ROLE_CONTRACTS
    }
    assert VISUAL_FORBIDDEN_BAKED_ASSET_KEYS == ("item", "vfx")


def test_visual_role_capabilities_are_frozen_and_projectile_local() -> None:
    projectile = VISUAL_ROLE_CONTRACT_BY_NAME["projectile"]
    assert projectile.reuse_item_sprite_allowed is True
    assert projectile.distinct_from_item_allowed is True
    assert all(
        not contract.reuse_item_sprite_allowed
        and not contract.distinct_from_item_allowed
        for contract in VISUAL_BAKED_ROLE_CONTRACTS
        if contract.role != "projectile"
    )
    with pytest.raises(FrozenInstanceError):
        projectile.role = "renamed"  # type: ignore[misc]
    with pytest.raises(TypeError):
        VISUAL_ROLE_CONTRACT_BY_NAME["new"] = projectile  # type: ignore[index]


def test_visual_boundary_consumes_role_capability_flags() -> None:
    projectile = canonical_visual_kit_view({
        "itemIconPrompt": "item",
        "projectileSpritePrompt": "same body",
        "bakedAssets": {
            "projectile": {
                "mode": "reuse_item_sprite",
                "reason": "same authored body",
            },
        },
    })
    assert projectile["bakedAssets"]["projectile"]["mode"] == "reuse_item_sprite"

    with pytest.raises(ValueError, match="projectile role"):
        canonical_visual_kit_view({
            "itemIconPrompt": "item",
            "impactSpritePrompt": "impact",
            "bakedAssets": {
                "impact": {
                    "mode": "reuse_item_sprite",
                    "reason": "invalid",
                },
            },
        })


def test_visual_boundary_aggregates_schema_and_role_errors_for_one_repair() -> None:
    with pytest.raises(ValueError) as captured:
        canonical_visual_kit_view({
            "artDirection": "unknown duplicate style owner",
            "itemIconPrompt": "spider fang staff",
            "childSpritePrompt": "venom bolt",
            "bakedAssets": {
                "child": {
                    "mode": "baked_sprite",
                    "reason": "distinct child body",
                    "distinctFromItem": True,
                },
            },
        })

    message = str(captured.value)
    assert "artDirection" in message
    assert "distinctFromItem is valid only for the projectile role" in message

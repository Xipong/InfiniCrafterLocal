from __future__ import annotations

from pathlib import Path
import re

from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
from infini_local.core.runtime_authoring.program_schema import (
    author_item_repair_schema,
    author_item_response_schema,
)
from infini_local.pipelines.author_item_contract import author_item_prompt_shape_card
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture


ROOT = Path(__file__).resolve().parents[2]
CS = ROOT / "ModSources" / "InfiniCrafterLocal"


def _read(path: str) -> str:
    return (CS / path).read_text("utf-8", errors="ignore")


def _contains_key(value: object, forbidden: str) -> bool:
    if isinstance(value, dict):
        return forbidden in value or any(_contains_key(child, forbidden) for child in value.values())
    if isinstance(value, list):
        return any(_contains_key(child, forbidden) for child in value)
    return False


def test_generated_item_author_and_repair_surfaces_forbid_tooltips() -> None:
    author = author_item_response_schema()
    repair = author_item_repair_schema()
    card = author_item_prompt_shape_card()

    assert "tooltip" not in author["properties"]
    assert "tooltip" not in author["required"]
    assert "tooltip" not in repair["properties"]["metadataPatch"]["properties"]
    assert "tooltip" not in card["root"]
    fixture = build_runtime_fixture("workbench_blade")
    assert not _contains_key(fixture, "tooltip")
    # Negative control: checking only the top-level dict would miss authored
    # tooltip fields hidden in metadata or nested runtime entities.
    assert _contains_key({"runtimeProgram": {"entities": [{"tooltip": "invented"}]}}, "tooltip")


def test_generated_item_wire_and_runtime_have_no_authored_tooltip_renderer() -> None:
    model = _read("Common/Models/GeneratedItemData.Model.cs")
    normalize = _read("Common/Models/GeneratedItemData.Normalize.cs")
    serialization = _read("Common/Models/GeneratedItemData.cs")
    item = _read("Content/Items/GeneratedItem.cs")

    assert "public string Tooltip" not in model
    assert "Tooltip =" not in serialization
    assert ".Tooltip" not in normalize
    assert "ModifyTooltips" not in item
    assert "TooltipLine" not in item


def test_generated_armor_has_no_model_authored_set_bonus_tooltip_text() -> None:
    armor = CAPABILITY_REGISTRY["configure_armor"]
    compiler = (ROOT / "LocalGenerator/infini_local/core/runtime_authoring/compiler.py").read_text("utf-8")
    model = _read("Common/Models/GeneratedItemData.Model.cs")
    item = _read("Content/Items/GeneratedItem.cs")

    assert "setBonusText" not in armor.params
    assert '"setBonusText"' not in compiler
    assert "SetBonusText" not in model
    assert "player.setBonus" not in item


def test_exported_contract_artifacts_match_the_no_tooltip_and_impact_contracts() -> None:
    schemas = ROOT / "contracts" / "schemas"
    for name in (
        "runtime_program_author.schema.json",
        "author_item_response.schema.json",
        "author_item_repair.schema.json",
        "capability_inventory.generated.json",
        "technical_lowering.generated.json",
    ):
        source = (schemas / name).read_text("utf-8")
        assert '"tooltip"' not in source
        assert "setBonusText" not in source

    for name in ("visual_runtime_entities.schema.json", "visual_repair_patch.schema.json"):
        source = (schemas / name).read_text("utf-8")
        assert "impactPrompt" not in source
        assert "impactNegativePrompt" not in source

    for name in ("vfx_runtime_events.schema.json", "vfx_repair_patch.schema.json"):
        source = (schemas / name).read_text("utf-8")
        assert "spritePrompt" in source
        assert "spriteNegativePrompt" in source


def test_generated_proxy_localization_blocks_do_not_define_even_empty_tooltips() -> None:
    localization = ROOT / "ModSources" / "InfiniCrafterLocal" / "Localization"
    proxy_names = ("GeneratedItem", "GeneratedHeadArmor", "GeneratedBodyArmor", "GeneratedLegsArmor")
    for file_name in ("en-US_Mods.InfiniCrafterLocal.hjson", "ru-RU_Mods.InfiniCrafterLocal.hjson"):
        source = (localization / file_name).read_text("utf-8")
        for proxy_name in proxy_names:
            blocks = re.findall(rf"{proxy_name}:\s*\{{([^}}]*)\}}", source)
            assert blocks, f"missing localization block {proxy_name} in {file_name}"
            assert all("Tooltip" not in block for block in blocks)
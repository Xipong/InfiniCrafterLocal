"""Independent JSON Schema checks for the actual transmitted VFX contracts."""
from __future__ import annotations

# pyright: reportPrivateUsage=false
import copy

from jsonschema import Draft202012Validator
import pytest

from infini_local.core.runtime_authoring import strict_schema_errors
from tests.test_vfx_material_contract import _asset, _data, _sent, _with_asset


@pytest.mark.parametrize("repair", [False, True])
@pytest.mark.parametrize("asset_id,valid", [
    ("leaf", True), ("Glow", True), ("glow", True), ("x" * 48, True),
    ("leaf\n", False), ("leaf\r\n", False), ("leaf\u2028", False),
    ("leaf\u2029", False), ("", False), ("x" * 49, False),
    ("../leaf", False), (" leaf", False),
])
def test_standard_schema_and_local_gate_agree_on_exact_asset_ids(repair: bool, asset_id: str, valid: bool) -> None:
    packet = _sent(_data(), repair)
    schema = packet["outputSchema"]
    Draft202012Validator.check_schema(schema)
    asset_schema = schema["properties"]["assetsUpsert" if repair else "assets"]["items"]
    row = _asset(asset_id)
    assert Draft202012Validator(asset_schema).is_valid(row) is valid
    assert (not strict_schema_errors(row, asset_schema)) is valid
    slots = schema["properties"]["slotsUpsert" if repair else "slots"]["items"]
    selector_schema = slots["properties"]["element"]["properties"]["texture"]
    selector = {"source": "asset", "assetId": asset_id}
    assert Draft202012Validator(selector_schema).is_valid(selector) is valid
    assert (not strict_schema_errors(selector, selector_schema)) is valid
    if repair:
        # Read the actual serialized Repair packet, not a rebuilt helper schema.
        deletions = schema["properties"]["assetIdsDelete"]
        assert Draft202012Validator(deletions).is_valid([asset_id]) is valid
        assert (not strict_schema_errors([asset_id], deletions)) is valid
        patch = {"schema": schema["properties"]["schema"]["const"],
                 "note": "delete exact diagnosed asset id", "assetIdsDelete": [asset_id]}
        assert Draft202012Validator(schema).is_valid(patch) is valid
        assert (not strict_schema_errors(patch, schema)) is valid


def test_standard_schema_accepts_complete_authored_asset_composition_without_rewriting() -> None:
    data = _data()
    authored = _with_asset(data)
    before = copy.deepcopy(authored)
    schema = _sent(data, False)["outputSchema"]
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(authored)
    assert authored == before

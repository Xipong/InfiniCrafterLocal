"""Exact test-only reversal of #12 notation/provenance; frozen archives stay untouched."""
from copy import deepcopy
import hashlib
import json


def historical_equipment_inventory_wire(document):
    """Reverse only the six additive accessory paths in the registry inventory.

    This is diagnostic metadata, not omitted-default materialization: historical
    gameplay and receipts must contain none of these newly authorable leaves.
    Complete before/after roster digests pin ordering and every retained path.
    """
    added = ("accessory.iceSkate", "accessory.noKnockback", "accessory.fireWalk",
             "accessory.accRunSpeed", "accessory.rocketBoots", "accessory.wireVision")
    assert all(path.split(".", 1)[1] not in document["accessory"] for path in added)
    assert not any(row.get("finalPath") in added
                   for row in document["runtimeContract"]["finalWireReceipts"])
    projected = deepcopy(document)
    lowerers = projected["runtimeContract"]["technicalLoweringAudit"]["lowerers"]
    matches = [row for row in lowerers if row["id"] == "item_fields_to_tml_projection"]
    assert len(matches) == 1
    outputs = matches[0]["outputs"]

    def digest(paths):
        return hashlib.sha256(json.dumps(paths, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()

    assert len(outputs) == 148
    assert digest(outputs) == "98fe8cbef7787c5ae896ec50642a0e3ec55f0c73c522bcb04bd8308e5413fc8f"
    start = outputs.index("accessory.waterWalk") + 1
    assert outputs[start:start + len(added)] == list(added)
    assert outputs[start + len(added)] == "armor.enabled"
    del outputs[start:start + len(added)]
    assert len(outputs) == 142
    assert digest(outputs) == "dd625b6afd3cf3b5d15ec7d0c4645cd7538f2d1b323494c9f574445bab032274"
    return projected


def historical_item_alias_wire(document):
    projected = deepcopy(document)
    contract = projected["runtimeContract"]
    rows = contract["finalWireReceipts"]
    for row in list(rows):
        if row.get("fn") == "configure_item_use" and row["authoredPath"].endswith(".params.customHeldSprite"):
            assert row["status"] == "delivered" and row["value"] in ("immediate", "on_release")
            assert row["finalPath"] in ("gameplay.releaseTiming", "runtimeProgram.itemUse.releaseTiming")
            row["authoredPath"] = row["authoredPath"].removesuffix("customHeldSprite") + "heldSpriteVisibilityHint"
    placement_calls = {row["callId"] for row in rows if row.get("fn") == "configure_tile_placement"}
    for call_id in placement_calls:
        selected = [row for row in rows if row.get("callId") == call_id]
        assert len(selected) == 3
        inactive = next(row for row in selected if row["finalPath"].endswith(".wallId"))
        assert inactive["status"] == "technical_projection" and inactive["value"] == -1
        assert inactive["authoredPath"].endswith(".fn")
        inactive["status"] = "delivered"
        inactive["authoredPath"] = inactive["authoredPath"].removesuffix("fn") + "params.wallId"
        for row in selected:
            assert row["fn"] == "configure_tile_placement"
            row["fn"] = "configure_placeable"
        positions = [i for i, row in enumerate(rows) if row.get("callId") == call_id]
        ordered = [next(row for row in selected if row["finalPath"].endswith("." + field))
                   for field in ("tileId", "wallId", "placeStyle")]
        for i, row in zip(positions, ordered):
            rows[i] = row
    stats = contract["validation"]["stats"]
    stats["capabilitiesUsed"] = sorted("configure_placeable" if fn == "configure_tile_placement" else fn
                                       for fn in stats["capabilitiesUsed"])
    return projected

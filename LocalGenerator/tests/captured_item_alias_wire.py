"""Exact test-only reversal of #12 notation/provenance; frozen archives stay untouched."""
from copy import deepcopy


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

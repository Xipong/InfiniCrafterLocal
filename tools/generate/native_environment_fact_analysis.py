"""Literal scene-flag source shapes only; never execute native/mod hooks.

Facts describe local code branches, not the whole method or the current world.
Opaque instructions and unknown branch shapes are not interpreted.
"""
from __future__ import annotations


def aura_branches(code):
    """Read tile-type/frame comparisons ending in a direct true scene setter."""
    records = []
    for n in range(len(code) - 8):
        head = code[n:n + 5]
        if not (head[0].op == "ldloca" and head[1].op == "call"
                and head[1].arg[0] == "Terraria.Tile.get_type"
                and head[2].op == "ldind.u2" and head[3].op == "const"
                and head[4].op == "bne" and head[4].arg > head[4].offset):
            continue
        end = head[4].arg
        block = [i for i in code[n + 5:] if i.offset < end]
        if len(block) < 3 or [(i.op, i.arg) for i in block[-3:-1]] != [("ldarg", 0), ("const", 1)]:
            continue
        call = block[-1]
        if call.op != "call" or not call.arg[0].startswith("Terraria.SceneMetrics.set_Has"):
            continue
        guards, body, valid = [], block[:-3], True
        if len(body) % 5:
            continue
        for at in range(0, len(body), 5):
            a, b, c, d, e = body[at:at + 5]
            comparisons = {"bge": "less_than", "bgt": "less_or_equal", "blt": "greater_or_equal", "ble": "greater_than"}
            if not (a.op == "ldloca" and a.arg == head[0].arg and b.op == "call"
                    and b.arg[0] in ("Terraria.Tile.get_frameX", "Terraria.Tile.get_frameY")
                    and c.op == "ldind.i2" and d.op == "const" and e.op in comparisons and e.arg == end):
                valid = False
                break
            guards.append({"field": b.arg[0].split("get_")[1], "comparison": comparisons[e.op], "value": d.arg})
        start = head[0].offset
        # A branch from outside cannot bypass a recognized predicate.
        for ins in code:
            targets = ins.arg if ins.op == "switch" else [ins.arg] if ins.op.startswith("b") and isinstance(ins.arg, int) else []
            if not start <= ins.offset < end and any(start < target < end for target in targets):
                valid = False
        if valid:
            records.append({"tileId": head[3].arg, "sceneFlag": call.arg[0].split("set_")[1],
                "tileFrameConditions": guards, "sourceBranchOffset": head[4].offset})
    return records


def scene_regen_additions(code):
    """Exact local-player + scene predicate followed by one literal addition."""
    out = {}
    for n in range(len(code) - 14):
        b = code[n:n + 15]
        expected = ["ldarg", "ldfld", "ldsfld", "bne", "ldsfld", "call", "brfalse",
                    "ldarg", "ldarg", "ldfld", "const", "add", "stfld"]
        b = b[:13]
        if [i.op for i in b] != expected:
            continue
        if not (b[0].arg == 0 and b[1].arg == "Terraria.Entity.whoAmI"
                and b[2].arg == "Terraria.Main.myPlayer" and b[3].arg == b[6].arg
                and b[4].arg == "Terraria.Main.SceneMetrics" and b[5].arg[0].startswith("Terraria.SceneMetrics.get_Has")
                and b[7].arg == b[8].arg == 0 and b[9].arg == "Terraria.Player.lifeRegen"
                and b[10].op == "const"):
            continue
        # stfld remains a raw token in the common decoder. The generator resolves
        # that token before this recognizer; no unknown write is accepted.
        if b[12].arg != "Terraria.Player.lifeRegen" or b[3].arg != code[n + 13].offset:
            continue
        start, end = b[0].offset, code[n + 13].offset
        if any(not start <= ins.offset < end and any(start < target < end for target in
                (ins.arg if ins.op == "switch" else [ins.arg] if ins.op.startswith("b") and isinstance(ins.arg, int) else []))
                for ins in code):
            continue
        out[b[5].arg[0].split("get_")[1]] = {"field": "Player.lifeRegen", "add": b[10].arg,
            "condition": "local_player_and_scene_flag", "units": "native_life_regen_counter_units",
            "scope": "one native addition before other regeneration, debuff and mod processing; not final HP per second"}
    return out


# These are audited SOURCE PROGRAM certificates, not per-item or family tables.
# Their complete IL was checked against the installed binary (not API reference
# assemblies). Unknown methods never acquire the declared arithmetic merely by
# containing a getter/call name. Whole-module SHA/MVID additionally cover every
# dependent getter, metadata initializer, and GetTileData overload.
PLACEMENT_SOURCE_CERTIFICATES = {
    "TileObject.Place": "905f016285cf638e62a56185c18d786e7879e186933326dbd61c64303712988e",
    "TileObjectData.CalculatePlacementStyle": "9992280a8aba8d0a97caf0cb1ac83c8ec59215bc86d7690c03cc494db0ddef69",
    "TileObjectData.Initialize": "8f30db7f3197e38bb489bbc6eff27100c19a3ae39d3b869effc4cabe7499edec",
    "TileObjectData.GetTileData": "47222b188e6c6fa05447e61acaa1f30fb22680e1a0eb1574f32ee0d6f9ea191b",
}


def certified_placement_mapping(certificates: dict[str, str]) -> dict[str, object]:
    """Exact audited IL program; no broad claim of arbitrary C# interpretation.

    Offsets use dncil body coordinates, including the 12-byte method header.
    Runtime reads current native metadata only; it does not execute Place,
    CanPlace, item defaults or equipment hooks to create these observations.
    """
    if any(certificates.get(name) != sha for name, sha in PLACEMENT_SOURCE_CERTIFICATES.items()):
        raise ValueError("Unsupported native placement source program")
    return {
        "algorithm": "TileObject.Place_metadata_frames_v1",
        "sourceMethods": list(PLACEMENT_SOURCE_CERTIFICATES),
        "sourceMethodCertificates": dict(PLACEMENT_SOURCE_CERTIFICATES),
        "placementStyle": "style * StyleMultiplier + Style + max(random, 0)",
        "styleWrap": "if StyleWrapLimit > 0: line = placementStyle / StyleWrapLimit * StyleLineSkip; placementStyle %= StyleWrapLimit; else line = 0",
        "baseFrameX": "CoordinateFullWidth * (placementStyle if StyleHorizontal else line)",
        "baseFrameY": "CoordinateFullHeight * (line if StyleHorizontal else placementStyle)",
        "tileCellFrameX": "baseFrameX + column * (CoordinateWidth + CoordinatePadding)",
        "tileCellFrameY": "baseFrameY + sum(CoordinateHeights[row] + CoordinatePadding for preceding rows)",
        "sourceIlOffsets": {"calculatePlacementStyle": [12, 39], "placementBaseFrames": [190, 311], "placementCellFrames": [552, 698]},
        "scope": "Conditional newly placed empty-cell frames under current native TileObjectData. No placement success, world state, wiring changes, random styles, custom placement hooks or generated gameplay is inferred. Each admitted variant retains its alternate index and matching cell frames. Only current vanilla default item tile/style pairs are admitted.",
    }

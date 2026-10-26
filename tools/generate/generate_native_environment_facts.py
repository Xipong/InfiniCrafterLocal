"""Generate conditional scene references from nonexecuted native source shapes."""
from __future__ import annotations

import argparse
import json
import hashlib
import uuid
from pathlib import Path

from generate_native_hit_status import decode
from native_environment_fact_analysis import aura_branches, scene_regen_additions, certified_placement_mapping

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "ModSources/InfiniCrafterLocal/Common/Services/Generation/NativeEnvironmentFactsCatalog.g.cs"
REPORT = ROOT / "contracts/reports/native_environment_sources.generated.json"


def placement_sources(path: Path):
    """Read method bodies/identity from metadata; do not load the assembly."""
    import dnfile
    from dncil.cil.body import CilMethodBody
    from dncil.cil.body.reader import CilMethodBodyReaderBytes

    pe = dnfile.dnPE(str(path))
    methods = [("Terraria", "TileObject", "Place"),
        ("Terraria.ObjectData", "TileObjectData", "CalculatePlacementStyle"),
        ("Terraria.ObjectData", "TileObjectData", "Initialize"),
        ("Terraria.ObjectData", "TileObjectData", "GetTileData")]
    version = pe.net.mdtables.Assembly.rows[0]
    for namespace, owner, method in methods:
        native = next(m.row for t in pe.net.mdtables.TypeDef
            if str(t.TypeNamespace) == namespace and str(t.TypeName) == owner
            for m in t.MethodList if str(m.row.Name) == method)
        body = CilMethodBody(CilMethodBodyReaderBytes(pe.get_data(native.Rva, 100_000)))
        yield {"method": owner + "." + method, "overloadIndex": 0,
            "assemblyVersion": ".".join(str(getattr(version, k)) for k in ("MajorVersion", "MinorVersion", "BuildNumber", "RevisionNumber")),
            "sourceMethodSha256": hashlib.sha256(pe.get_data(native.Rva + body.header_size, body.code_size)).hexdigest(),
            "sourceModuleVersionId": str(uuid.UUID(bytes_le=pe.net.mdtables.Module.rows[0].Mvid.value)),
            "assemblySha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def extract(path):
    sources = []
    methods = [("SceneMetrics", "ScanAndExportToMain", 0), ("Player", "UpdateLifeRegen", 0),
        ("Player", "ApplyBannerOffenseBuff", 1), ("Player", "ApplyBannerDefenseBuff", 1),
        ("Player", "HasNPCBannerBuff", 0)]
    decoded = {}
    for owner, method, index in methods:
        data = decode(path, owner, method, "Terraria.ID.TileID", allow_opaque=True, overload_index=index)
        decoded[owner + "." + method] = data[0]
        sources.append({"method": owner + "." + method, "overloadIndex": index,
            "assemblyVersion": data[3], "sourceMethodSha256": data[4], "sourceModuleVersionId": data[6], "assemblySha256": data[5]})
    auras = aura_branches(decoded["SceneMetrics.ScanAndExportToMain"])
    regen = scene_regen_additions(decoded["Player.UpdateLifeRegen"])
    for row in auras:
        if row["sceneFlag"] in regen:
            row["regenerationComponent"] = regen[row["sceneFlag"]]
    # Certify the exact banner operation rather than guessing meanings from field names.
    for suffix, stat, normal, expert in [("Offense", ".HitModifiers.TargetDamageMultiplier", "NormalDamageDealt", "ExpertDamageDealt"),
            ("Defense", ".HurtModifiers.IncomingDamageMultiplier", "NormalDamageReceived", "ExpertDamageReceived")]:
        code = decoded["Player.ApplyBanner" + suffix + "Buff"]
        names = [i.arg[0] if i.op == "call" else i.arg for i in code]
        required = ["Terraria.Player.HasNPCBannerBuff", ".Sets.BannerStrength", "Terraria.Item.BannerToItem",
                    stat, "Terraria.Main.get_expertMode", ".BannerEffect." + normal, ".BannerEffect." + expert,
                    "Terraria.ModLoader.MultipliableFloat.op_Multiply"]
        if not all(name in names for name in required):
            raise ValueError("Unrecognized banner operation: " + suffix)
        # Whole operation is straight-line except guard and difficulty selection.
        if [i.op for i in code] != ["ldarg", "ldarg", "call", "brtrue", "ret", "ldsfld", "ldarg", "call", "ldelem", "stloc", "ldarg", "ldflda", "dup", "ldobj", "call", "brtrue", "ldloc", "ldfld", "br", "ldloc", "ldfld", "call", "stobj", "ret"]:
            raise ValueError("Changed banner control flow: " + suffix)
        if ([i.arg[0] for i in code if i.op == "call"] != [required[0], required[2], required[4], required[7]]
                or [i.arg for i in code if i.op == "ldfld"] != [required[5], required[6]]
                or code[3].arg != code[5].offset or code[15].arg != code[19].offset
                or code[18].arg != code[21].offset
                or [(i.op, i.arg) for i in code[:2]] != [("ldarg", 0), ("ldarg", 1)]
                or code[6].arg != 1 or code[10].arg != 2):
            raise ValueError("Changed banner operand or gate: " + suffix)
    sources.extend(placement_sources(path))
    mapping = certified_placement_mapping({s["method"]: s["sourceMethodSha256"] for s in sources})
    return {"sources": sources, "auras": auras, "placementMapping": mapping}


def render(data):
    lines = ["// Generated by tools/generate/generate_native_environment_facts.py; do not hand-edit.",
        "using System.Collections.Generic;", "namespace InfiniCrafterLocal.Common.Services;", "internal static class NativeEnvironmentFactsCatalog", "{",
        '    internal const string AssemblySha256 = "' + data["sources"][0]["assemblySha256"] + '";',
        '    internal const string ModuleVersionId = "' + data["sources"][0]["sourceModuleVersionId"] + '";',
        "    internal static readonly Dictionary<string, string> Certificates = new()", "    {"]
    for source in data["sources"]:
        lines.append('        ["' + source["method"] + '"] = "' + source["sourceMethodSha256"] + ':' + source["sourceModuleVersionId"] + '",')
    lines += ["    };", '    internal const string PlacementMappingJson = """' + json.dumps(data["placementMapping"], separators=(",", ":")) + '""";', '    internal const string AuraJson = """' + json.dumps(data["auras"], separators=(",", ":")) + '""";', "}", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assembly", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    data = extract(args.assembly)
    products = {OUTPUT: render(data), REPORT: json.dumps({"schema": "infini.native-environment-sources.v1", **data}, indent=2) + "\n"}
    for path, contents in products.items():
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != contents:
                raise SystemExit("stale native environment facts: " + str(path))
        else:
            path.write_text(contents, encoding="utf-8")
    print(len(data["auras"]), "conditional tile aura branches")


if __name__ == "__main__":
    main()

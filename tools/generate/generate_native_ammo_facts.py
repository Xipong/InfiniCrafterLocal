"""Generate ammo source observations from exact native method IL, without loading it."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from generate_native_hit_status import decode
from native_ammo_fact_analysis import ammo_method_facts, default_ammo_selection, item_type_mentions

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "ModSources/InfiniCrafterLocal/Common/Services/Generation/NativeAmmoFactsCatalog.g.cs"
REPORT = ROOT / "contracts/reports/native_ammo_sources.generated.json"


def hook_dispatch_trace(path):
    """Read direct dispatcher call sites from this exact assembly, not tML docs."""
    import dnfile
    from dncil.cil.body import CilMethodBody
    from dncil.cil.body.reader import CilMethodBodyReaderBytes
    pe = dnfile.dnPE(str(path))
    owners = {id(m.row): str(t.TypeNamespace) + "." + str(t.TypeName)
              for t in pe.net.mdtables.TypeDef for m in t.MethodList}
    rows = []
    for owner, names in (("Terraria.ModLoader.ItemLoader", ("PickAmmo", "ModifyShootStats", "Shoot")),
                         ("Terraria.ModLoader.CombinedHooks", ("ModifyShootStats", "Shoot"))):
        for name in names:
            method = next(m for m in pe.net.mdtables.MethodDef if owners[id(m)] == owner and str(m.Name) == name)
            body = CilMethodBody(CilMethodBodyReaderBytes(pe.get_data(method.Rva, 100_000)))
            calls = []
            for ins in body.instructions:
                if ins.opcode.name not in ("call", "callvirt"):
                    continue
                token = ins.operand.value
                if token >> 24 == 6:
                    member = pe.net.mdtables.MethodDef.rows[(token & 0xffffff) - 1]
                    target_owner = owners[id(member)]
                elif token >> 24 == 10:
                    member = pe.net.mdtables.MemberRef.rows[(token & 0xffffff) - 1]
                    target = member.Class.row
                    target_owner = str(getattr(target, "TypeNamespace", "")) + "." + str(getattr(target, "TypeName", ""))
                else:
                    continue
                if target_owner in ("Terraria.ModLoader.ModItem", "Terraria.ModLoader.GlobalItem", "Terraria.ModLoader.ItemLoader", "Terraria.ModLoader.PlayerLoader"):
                    calls.append(target_owner + "." + str(member.Name))
            rows.append({"method": owner + "." + name,
                         "sourceMethodSha256": hashlib.sha256(pe.get_data(method.Rva + body.header_size, body.code_size)).hexdigest(),
                         "directHookCalls": calls,
                         "scope": "Direct call-site source order; conditional skips and per-entity hook iteration do not imply all hooks execute"})
    return rows


def native_ammo_category_literals(path):
    """Read only literal static field initializers; no .cctor execution."""
    import dnfile
    from dncil.cil.body import CilMethodBody
    from dncil.cil.body.reader import CilMethodBodyReaderBytes
    pe = dnfile.dnPE(str(path))
    owner = next(t for t in pe.net.mdtables.TypeDef if str(t.TypeNamespace) == "Terraria.ID" and str(t.TypeName) == "AmmoID")
    method = next(m.row for m in owner.MethodList if str(m.row.Name) == ".cctor")
    body = CilMethodBody(CilMethodBodyReaderBytes(pe.get_data(method.Rva, 10000)))
    values = {}
    for literal, store in zip(body.instructions, body.instructions[1:]):
        if not literal.opcode.name.startswith("ldc.i4") or store.opcode.name != "stsfld":
            continue
        op = literal.opcode.name
        value = literal.operand if op in ("ldc.i4", "ldc.i4.s") else -1 if op.endswith(".m1") else int(op.rsplit(".", 1)[1])
        field = pe.net.mdtables.Field.rows[(store.operand.value & 0xffffff) - 1]
        values["Terraria.ID.AmmoID." + str(field.Name)] = value
    return values


def extract(path):
    sources = []
    trace = hook_dispatch_trace(path)
    categories = native_ammo_category_literals(path)
    *_, lookup_sha, _, lookup_module = decode(path, "Player", "PickAmmo_TryFindingSpecificMatches", allow_opaque=True)
    for method, overload in (("PickAmmo", 1), ("ItemCheck_Shoot", 0)):
        code, _, _, version, sha, assembly_sha, module = decode(path, "Player", method, "Terraria.ID.ItemID", allow_opaque=True, overload_index=overload)
        selection = default_ammo_selection(code, categories) if method == "PickAmmo" else None
        if selection is not None:
            selection["specificMatchLookupCertificate"] = lookup_sha + ":" + lookup_module
        sources.append({"method": "Player." + method, "sourceMethodSha256": sha,
                        "sourceModuleVersionId": module, "assemblyVersion": version,
                        "assemblySha256": assembly_sha,
                        "itemTypeMentions": item_type_mentions(code, 1 if method == "PickAmmo" else 2),
                        "defaultProjectileSelection": selection,
                        "scope": "Literal item-type projectile rewrites and explicit native item-branch spawn arguments only. The initial selection chain and live table lookup are certified separately; ambient/player/projectile-set rewrites, branch admission, hooks and actual shot outcome remain unknown.",
                        "hookDispatchTrace": trace if method == "PickAmmo" else [],
                        "sourceStageCallSites": [{"method": ins.arg[0], "sourceCallIlOffset": ins.offset} for ins in code
                                                 if ins.op == "call" and ins.arg[0] in ("Terraria.Player.PickAmmo", "Terraria.ModLoader.ItemLoader.PickAmmo", "Terraria.ModLoader.CombinedHooks.ModifyShootStats", "Terraria.ModLoader.CombinedHooks.Shoot")],
                        "records": ammo_method_facts(code, method)})
    return sources


def render(sources):
    lines = ["// Generated by tools/generate/generate_native_ammo_facts.py; do not hand-edit.",
             "using System.Collections.Generic;", "namespace InfiniCrafterLocal.Common.Services;",
             "internal static class NativeAmmoFactsCatalog", "{",
             "    internal static readonly Dictionary<string, Dictionary<int, string>> Sources = new()", "    {"]
    for s in sorted(sources, key=lambda s: s["method"] + s["sourceMethodSha256"]):
        key = s["method"] + ":" + s["sourceMethodSha256"] + ":" + s["sourceModuleVersionId"]
        lines += [f'        ["{key}"] = new()', "        {"]
        for row in s["records"]:
            lines.append(f'            [{row["itemId"]}] = """{json.dumps(row, separators=(",", ":"))}""",')
        lines += ["        },"]
    lines += ["    };", "    internal static readonly Dictionary<string, string> Selection = new()", "    {"]
    for s in sorted(sources, key=lambda s: s["method"] + s["sourceMethodSha256"]):
        key = s["method"] + ":" + s["sourceMethodSha256"] + ":" + s["sourceModuleVersionId"]
        baseline = {"itemTypeMentions": s["itemTypeMentions"], "defaultProjectileSelection": s["defaultProjectileSelection"], "hookDispatchTrace": s["hookDispatchTrace"], "sourceStageCallSites": s["sourceStageCallSites"]}
        lines.append(f'        ["{key}"] = """{json.dumps(baseline, separators=(",", ":"))}""",')
    return "\n".join(lines + ["    };", "}", ""])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assembly", type=Path, action="append", required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    sources = [s for path in args.assembly for s in extract(path)]
    products = {OUTPUT: render(sources), REPORT: json.dumps({"schema": "infini.native-ammo-sources.v1", "sources": sources}, indent=2) + "\n"}
    for path, text in products.items():
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                raise SystemExit("stale ammo source facts: " + str(path))
        else:
            path.write_text(text, encoding="utf-8")
    for s in sources:
        print(s["method"], len(s["records"]), "bounded source records")


if __name__ == "__main__":
    main()

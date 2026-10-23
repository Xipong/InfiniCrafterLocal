"""Regenerate certified source facts from official tModLoader assemblies.

Analysis dependencies (developer-only): dnfile==0.18.0 dncil==1.0.2.
No assembly is loaded/executed. Supply every supported release with --assembly.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import uuid
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from native_hit_status_analysis import Instruction, analyze

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "ModSources/InfiniCrafterLocal/Common/Services/Generation/NativeHitStatusCatalog.g.cs"
REPORT = ROOT / "contracts/reports/native_hit_status_sources.generated.json"


def read_compressed(data, offset):
    lead = data[offset]
    if lead < 0x80:
        return lead, offset + 1
    if lead < 0xC0:
        return ((lead & 0x3F) << 8) | data[offset + 1], offset + 2
    return ((lead & 0x1F) << 24) | int.from_bytes(data[offset + 1:offset + 4], "big"), offset + 4


def decode(path):
    import dnfile
    from dncil.cil.body import CilMethodBody
    from dncil.cil.body.reader import CilMethodBodyReaderBytes

    pe = dnfile.dnPE(str(path))
    owners = {}
    for type_ in pe.net.mdtables.TypeDef:
        owner = str(type_.TypeNamespace) + "." + str(type_.TypeName)
        for member in [*type_.FieldList, *type_.MethodList]:
            owners[id(member.row)] = owner

    def member(token):
        table = {4: "Field", 6: "MethodDef", 10: "MemberRef"}.get(token >> 24)
        if not table:
            raise ValueError("unsupported member token")
        row = getattr(pe.net.mdtables, table).rows[(token & 0xFFFFFF) - 1]
        owner = owners.get(id(row))
        if owner is None:
            type_ = row.Class.row
            owner = str(type_.TypeNamespace) + "." + str(type_.TypeName)
        return owner + "." + str(row.Name), row

    def constants(owner):
        result = {}
        for c in pe.net.mdtables.Constant:
            field = c.Parent.row
            if owners.get(id(field)) != owner:
                continue
            raw = c.Value.value
            if len(raw) not in (2, 4):
                continue
            value = int.from_bytes(raw, "little", signed=True)
            result[str(field.Name)] = value
        return result

    projectile_ids = constants("Terraria.ID.ProjectileID")
    buff_ids = constants("Terraria.ID.BuffID")
    method = next(m.row for t in pe.net.mdtables.TypeDef
                  if str(t.TypeNamespace) == "Terraria" and str(t.TypeName) == "Projectile"
                  for m in t.MethodList if str(m.row.Name) == "StatusNPC")
    body = CilMethodBody(CilMethodBodyReaderBytes(pe.get_data(method.Rva, 100_000)))
    if body.exception_handlers:
        raise ValueError("exception handlers are outside supported native subset")
    instructions = []
    for ins in body.instructions:
        op, arg = ins.opcode.name, ins.operand
        if op.startswith("ldc.i4"):
            arg = arg if op in ("ldc.i4", "ldc.i4.s") else int(op.rsplit(".", 1)[1])
            op = "const"
        elif op == "ldc.r4":
            op = "const"
        elif op.startswith(("ldarg.", "ldloc.", "stloc.")):
            base, suffix = op.rsplit(".", 1)
            op, arg = base, arg.index if suffix == "s" else int(suffix)
        elif op in ("ldfld", "ldsfld"):
            arg = member(arg.value)[0]
        elif op in ("call", "callvirt"):
            name, row = member(arg.value)
            sig = row.Signature.value
            if sig[0] & 0x10:
                raise ValueError("generic method outside supported subset")
            count, ret_offset = read_compressed(sig, 1)
            arg = (name, count, bool(sig[0] & 0x20), sig[ret_offset] != 1)
            op = "call"
        elif op.startswith("ldelem."):
            op = "ldelem"
        elif op.startswith("conv."):
            op = "conv"
        elif op.startswith("bne.un"):
            op = "bne"
        elif op.endswith(".s"):
            op = op[:-2]
        instructions.append(Instruction(ins.offset, op, arg))
    assembly = pe.net.mdtables.Assembly.rows[0]
    version = ".".join(str(getattr(assembly, key)) for key in ("MajorVersion", "MinorVersion", "BuildNumber", "RevisionNumber"))
    raw = pe.get_data(method.Rva + body.header_size, body.code_size)
    return instructions, projectile_ids, buff_ids, version, hashlib.sha256(raw).hexdigest(), hashlib.sha256(path.read_bytes()).hexdigest(), str(uuid.UUID(bytes_le=pe.net.mdtables.Module.rows[0].Mvid.value))


def extract(path):
    instructions, projectile_ids, buff_ids, version, method_hash, assembly_hash, module_id = decode(path)
    projectile_names = {value: name for name, value in projectile_ids.items() if name not in ("Count", "None")}
    buff_names = {value: name for name, value in buff_ids.items() if name not in ("Count", "None")}
    records, exclusions, covered_sites = [], [], set()
    for type_ in range(max(projectile_names) + 1):
        if type_ not in projectile_names:
            continue
        try:
            result = analyze(instructions, type_)
        except (ValueError, IndexError) as error:
            raise ValueError(f"unrecognized native method for projectile {type_}: {error}") from error
        effects = result["effects"]
        for effect in effects:
            if effect["buffId"] not in buff_names:
                raise ValueError("status ID missing from loaded vanilla BuffID constants")
            effect["buffName"] = buff_names[effect["buffId"]]
            covered_sites.add(effect["ilOffset"])
        # Every type is processed; only types with proved facts need runtime rows.
        if effects:
            records.append({"projectileId": type_, "projectileName": projectile_names[type_], "effects": effects})
        for excluded in result["excludedSites"]:
            exclusions.append({"projectileId": type_, **excluded})
    sites = {i.offset for i in instructions if i.op == "call" and i.arg[0] == "Terraria.NPC.AddBuff"}
    counts = Counter(x["reason"] for x in exclusions)
    return {
        "assemblyVersion": version, "assemblySha256": assembly_hash, "moduleVersionId": module_id, "sourceMethodSha256": method_hash,
        "scope": "Unconditional vanilla Projectile.StatusNPC NPC.AddBuff requests only; not final applied buffs, item hooks, player/PvP hits, child AI or mod hooks.",
        "analyzedProjectileTypes": len(projectile_names), "coveredProjectileTypes": len(records),
        "coveredProjectileEffects": sum(len(r["effects"]) for r in records),
        "totalMethodAddBuffSites": len(sites), "coveredMethodAddBuffSites": len(covered_sites),
        "uncoveredMethodAddBuffOffsets": sorted(sites - covered_sites),
        "excludedTypeSiteCounts": dict(sorted(counts.items())), "records": records,
    }


def render(sources):
    lines = ["// Generated by tools/generate/generate_native_hit_status.py; do not hand-edit.",
             "using System.Collections.Generic;", "using Terraria.ID;", "",
             "namespace InfiniCrafterLocal.Common.Services;", "", "internal static class NativeHitStatusCatalog", "{",
             "    internal sealed record Fact(int BuffId, string BuffName, int MinimumTicks, int MaximumTicks, int StepTicks, int IlOffset);",
             "    internal static readonly Dictionary<string, Dictionary<int, Fact[]>> Sources = new()", "    {"]
    for source in sorted(sources, key=lambda s: s["sourceMethodSha256"]):
        lines += [f'        ["{source["sourceMethodSha256"]}:{source["moduleVersionId"]}"] = new()', "        {"]
        for record in source["records"]:
            lines.append(f'            [ProjectileID.{record["projectileName"]}] = new Fact[] {{')
            for fact in record["effects"]:
                lines.append(f'                new(BuffID.{fact["buffName"]}, "{fact["buffName"]}", {fact["durationTicksMin"]}, {fact["durationTicksMax"]}, {fact["durationTicksStep"]}, {fact["ilOffset"]}),')
            lines.append("            },")
        lines += ["        },"]
    lines += ["    };", "}", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assembly", type=Path, action="append", required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    sources = sorted([extract(p) for p in args.assembly], key=lambda s: s["sourceMethodSha256"])
    products = {OUTPUT: render(sources), REPORT: json.dumps({"schema": "infini.native-hit-status-sources.v1", "sources": sources}, indent=2) + "\n"}
    for path, contents in products.items():
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != contents:
                raise SystemExit("stale generated source facts: " + str(path))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(contents, encoding="utf-8")
    for source in sources:
        print(json.dumps({k: v for k, v in source.items() if k not in ("records", "uncoveredMethodAddBuffOffsets")}))


if __name__ == "__main__":
    main()

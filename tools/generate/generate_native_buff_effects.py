"""Generate parent-local native buff effect fragments from certified IL.

Developer-only dnfile/dncil reader; never loads assemblies or executes hooks.
No BuffID family/name tables: identity constants only label the derived rows.
"""
from __future__ import annotations

import argparse
import copy
import json
from collections import Counter
from pathlib import Path

from generate_native_hit_status import decode
from native_buff_effect_analysis import buff_type_branches, npc_dot_fragments, npc_defense_fragments, npc_regen_unit_evidence, pairs

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "ModSources/InfiniCrafterLocal/Common/Services/Generation/NativeBuffEffectCatalog.g.cs"
REPORT = ROOT / "contracts/reports/native_buff_effect_sources.generated.json"
METHODS = (("Player", "UpdateBuffs"), ("NPC", "UpdateNPC_BuffSetFlags"),
           ("NPC", "UpdateNPC_BuffFlagsReset"), ("NPC", "UpdateNPC_BuffApplyDOTs"),
           ("NPC", "GetIncomingStrikeModifiers"))
SCOPE = ("Read-only native source operation fragments, not inherited execution or a complete buff implementation. "
         "Each fragment requires control to reach its certified test; unresolved enclosing guards remain required. "
         "Boolean assignments describe flags only, not their full gameplay effect. Numeric writes are contributions, "
         "not guaranteed final stats/damage. Other native paths, downstream AI, admission/immunity, duration refresh, "
         "equipment/world interactions and mod hooks remain unknown. No tooltip is used as semantic evidence.")
UNITS = {
    "boolean_flag_only": "Literal native flag assignment; downstream behavior is not implied.",
    "native_member_units": "Signed addition in the named member's native storage units, not a percentage or final stat; no conversion inferred.",
    "dimensionless_factor": "Multiply the named member's current native value by this factor at this source site, not a final effective-stat guarantee.",
    "native_lifeRegen_units": "Signed NPC.lifeRegen contribution after clearing positive regen. Optional unitEvidence proves a local accumulator/HP relation; nominalHpLossPerSecondAt60Updates explicitly assumes 60 updates/s, not proved scheduling or final HP loss. Other contributions, target immortality, routing and hooks still apply.",
    "defense_points": "Hit-local StatModifier.Flat defense-point contribution; not a persistent NPC.defense mutation or a guaranteed final defense/damage delta.",
    "native_operator_argument": "Literal second argument of the named binary operator; first argument is the current named member value, and the result is stored back. Operator implementation/components are not expanded. Do not interpret Additive as final multiplicative damage or infer final stat/damage from the operator name.",
}


def metadata(path):
    import dnfile
    pe = dnfile.dnPE(str(path))
    signatures = {b"\x06\x02": "boolean", b"\x06\x08": "int32", b"\x06\x0c": "float32", b"\x06\x0d": "float64",
                  b"\x06\x1d\x02": "boolean_array"}
    fields = {str(t.TypeNamespace) + "." + str(t.TypeName) + "." + str(f.row.Name): signatures[f.row.Signature.value]
              for t in pe.net.mdtables.TypeDef for f in t.FieldList if f.row.Signature.value in signatures}
    fields.update({str(t.TypeNamespace) + "." + str(t.TypeName) + "." + str(f.row.Name): "value_type"
                   for t in pe.net.mdtables.TypeDef for f in t.FieldList if f.row.Signature.value.startswith(b"\x06\x11")})
    incoming = next(m.row for t in pe.net.mdtables.TypeDef if str(t.TypeNamespace) == "Terraria" and str(t.TypeName) == "NPC"
                    for m in t.MethodList if str(m.row.Name) == "GetIncomingStrikeModifiers")
    params = {p.row.Sequence: str(p.row.Name) for p in incoming.ParamList}
    if params.get(3) != "ignoreArmorDebuffs":
        raise ValueError("unrecognized NPC defense consumer signature")
    return fields


def cleared_flags(code, field_types):
    """Require the whole reset body to be simple literal instance-field stores."""
    result, p = set(), pairs(code)
    if not p or p[-1] != ("ret", None) or (len(p) - 1) % 3:
        return set()
    for n in range(0, len(p) - 1, 3):
        a, b, c = p[n:n + 3]
        if a != ("ldarg", 0) or b[0] != "const" or c[0] != "stfld":
            return set()
        if field_types.get(c[1]) == "boolean":
            if b[1] == 0:
                result.add(c[1])
            else:
                result.discard(c[1])
    return result


def extract(path):
    fields, codes, methods = metadata(path), {}, []
    for owner, name in METHODS:
        code, _, buffs, version, sha, assembly, module = decode(path, owner, name, allow_opaque=True)
        codes[name] = code
        methods.append({"owner": owner, "name": name, "sourceMethodSha256": sha})
    names = {v: k for k, v in buffs.items() if k not in ("None", "Count")}
    player = buff_type_branches(codes["UpdateBuffs"], "Player", fields)
    flag_rows = buff_type_branches(codes["UpdateNPC_BuffSetFlags"], "NPC", fields)
    clear = cleared_flags(codes["UpdateNPC_BuffFlagsReset"], fields)
    consumers = [("UpdateNPC_BuffApplyDOTs", f) for f in npc_dot_fragments(codes["UpdateNPC_BuffApplyDOTs"], fields)]
    unit_evidence = npc_regen_unit_evidence(codes["UpdateNPC_BuffApplyDOTs"])
    if unit_evidence is not None:
        for _, fragment in consumers:
            for operation in fragment["operations"]:
                operation["unitEvidence"] = unit_evidence
                operation["nominalHpLossPerSecondAt60Updates"] = -operation["value"] * 60 / unit_evidence["accumulatorUnitsPerHealthPoint"]
                operation["nominalRateScope"] = "Conditional unit comparison at 60 native accumulator updates per second, not guaranteed final HP loss; actual cadence, immortality, realLife routing, other contributions and hooks remain applicable."
    consumers += [("GetIncomingStrikeModifiers", f) for f in npc_defense_fragments(codes["GetIncomingStrikeModifiers"], fields)]
    records = {}

    def record(receiver, bid):
        if bid not in names:
            raise ValueError("source branch buff ID missing from native constants")
        key = (receiver, bid)
        if key not in records:
            records[key] = {"receiver": receiver, "buffId": bid, "buffFullName": "Terraria/" + names[bid],
                            "completeness": "unsupported", "fragments": [], "sourceFlags": [],
                            "unsupported": ["other_native_paths_and_mod_hooks_not_decoded", "not_a_final_effect_or_immunity_guarantee"]}
        return records[key]

    for branch in player:
        if branch["operations"]:
            r = record("player", branch["buffId"])
            r["fragments"].append({**branch, "sourceMethod": "Player.UpdateBuffs"})
    for branch in flag_rows:
        r = record("npc", branch["buffId"])
        for op in branch["operations"]:
            if op["storageType"] != "boolean" or op["value"] is not True:
                continue
            r["sourceFlags"].append({**op, "condition": branch["condition"], "sourceMethod": "NPC.UpdateNPC_BuffSetFlags"})
            for method, effect in consumers:
                if effect["flagMember"] != op["nativeMember"] or op["nativeMember"] not in clear:
                    continue
                f = copy.deepcopy(effect)
                f["sourceMethod"] = "NPC." + method
                f["condition"]["flagSetByBuffBranch"] = branch["condition"]
                f["flagResetSourceMethod"] = "NPC.UpdateNPC_BuffFlagsReset"
                r["fragments"].append(f)
        if not r["fragments"]:
            r["unsupported"].append("flag_only_no_supported_numeric_consumer_trace")
    for r in records.values():
        if r["fragments"]:
            r["completeness"] = "partial_native_statement_fragments"
        r["scope"] = SCOPE
        used = {op["units"] for f in r["fragments"] for op in f["operations"]}
        r["sourceUnitDescriptors"] = {unit: UNITS[unit] for unit in sorted(used)}
    return {"assemblyVersion": version, "assemblySha256": assembly, "sourceModuleVersionId": module,
            "methods": methods, "scope": SCOPE, "records": [records[k] for k in sorted(records)],
            "analysis": {"playerLiteralBranches": len(player), "npcLiteralBranches": len(flag_rows),
                         "recognizedDotFlagConsumers": len([f for method, f in consumers if method == "UpdateNPC_BuffApplyDOTs"]),
                         "recognizedDefenseFlagConsumers": len([f for method, f in consumers if method == "GetIncomingStrikeModifiers"]),
                         "unsupportedPlayerBranches": [b for b in player if not b["operations"]],
                         "unsupportedNpcBranches": [b for b in flag_rows if not b["operations"]]}}


def render(sources):
    lines = ["// Generated by tools/generate/generate_native_buff_effects.py; do not hand-edit.",
             "using System.Collections.Generic;", "namespace InfiniCrafterLocal.Common.Services;",
             "internal static class NativeBuffEffectCatalog", "{",
             "    internal sealed record Method(string Owner, string Name, string Sha256);",
             "    internal sealed record Source(Method[] Methods, string CertificateJson, Dictionary<string, string> Records);",
             "    internal static readonly Dictionary<string, Source> Sources = new()", "    {"]
    for source in sources:
        key = source["assemblySha256"] + ":" + source["sourceModuleVersionId"]
        cert = {k: source[k] for k in ("assemblySha256", "sourceModuleVersionId", "methods")}
        lines += [f'        ["{key}"] = new(new Method[] {{']
        for method in source["methods"]:
            lines.append(f'            new("{method["owner"]}", "{method["name"]}", "{method["sourceMethodSha256"]}"),')
        lines += [f'        }}, """{json.dumps(cert, separators=(",", ":"))}""", new()', "        {"]
        for row in source["records"]:
            lines.append(f'            ["{row["receiver"]}:{row["buffId"]}"] = """{json.dumps(row, separators=(",", ":"))}""",')
        lines += ["        }),"]
    return "\n".join(lines + ["    };", "}", ""])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assembly", type=Path, action="append", required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    sources = sorted([extract(p) for p in args.assembly], key=lambda s: s["assemblySha256"])
    products = {OUTPUT: render(sources), REPORT: json.dumps({"schema": "infini.native-buff-effect-sources.v1", "sources": sources}, indent=2) + "\n"}
    for path, text in products.items():
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                raise SystemExit("stale buff effect source facts: " + str(path))
        else:
            path.write_text(text, encoding="utf-8")
    for source in sources:
        print(json.dumps({"assemblySha256": source["assemblySha256"],
                          "records": dict(Counter(r["receiver"] + ":" + r["completeness"] for r in source["records"])),
                          "dotFlagConsumers": source["analysis"]["recognizedDotFlagConsumers"],
                          "defenseFlagConsumers": source["analysis"]["recognizedDefenseFlagConsumers"]}))


if __name__ == "__main__":
    main()

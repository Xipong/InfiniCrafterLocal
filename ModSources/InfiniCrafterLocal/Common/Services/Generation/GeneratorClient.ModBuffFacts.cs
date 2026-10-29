#nullable enable
using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json.Nodes;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Services;

public sealed partial class GeneratorClient
{
    private static JsonObject? CaptureModBuffEffectReference(int id, string receiver)
    {
        if (id < BuffID.Count || id >= BuffLoader.BuffCount || receiver is not ("npc" or "player")) return null;
        try
        {
            ModBuff? buff = BuffLoader.GetBuff(id);
            if (buff is null) return null;
            JsonObject result = InspectModBuffSource(buff.GetType(), receiver);
            result["buffId"] = id;
            result["buffFullName"] = buff.FullName;
            return result;
        }
        catch { return null; }
    }

    private static JsonObject MethodSourceIdentity(MethodBase method) => new()
    {
        ["method"] = method.DeclaringType!.FullName + "." + method.Name,
        ["sourceModuleVersionId"] = method.Module.ModuleVersionId.ToString(),
        ["sourceMethodSha256"] = Convert.ToHexString(SHA256.HashData(method.GetMethodBody()!.GetILAsByteArray()!)).ToLowerInvariant(),
    };

    private static HashSet<int> SourceBranchTargets(List<AmmoIl> code) => new(code.SelectMany(i =>
        i.Op == "switch" && i.Arg is int[] many ? many
        : (i.Op.StartsWith("b") || i.Op.StartsWith("leave")) && i.Arg is int target ? new[] { target } : Array.Empty<int>()));

    private static JsonNode? TypedSourceLiteral(AmmoIl instruction, Type storage)
    {
        if (storage == typeof(bool) && instruction.Op == "const" && instruction.Arg is int boolean && boolean is 0 or 1)
            return JsonValue.Create(boolean == 1);
        if (storage == typeof(int) && instruction.Op == "const" && instruction.Arg is int integer) return JsonValue.Create(integer);
        if (storage == typeof(float) && instruction.Op == "ldc.r4" && instruction.Arg is float single && float.IsFinite(single)) return JsonValue.Create(single);
        if (storage == typeof(double) && instruction.Op == "ldc.r8" && instruction.Arg is double number && double.IsFinite(number)) return JsonValue.Create(number);
        return null;
    }

    private static JsonObject InspectModBuffSource(Type type, string receiver)
    {
        var fragments = new JsonArray();
        var registeredData = new JsonArray();
        var unsupported = new JsonArray("other_statements_helpers_global_hooks_and_downstream_consumers_not_analyzed");
        Type target = receiver == "npc" ? typeof(NPC) : typeof(Player);
        MethodInfo? update = type.GetMethod("Update", new[] { target, typeof(int).MakeByRefType() });
        if (update is not null && update.DeclaringType != typeof(ModBuff))
        {
            try
            {
                var code = ReadAmmoIl(update, preserveStructure: true);
                var targets = SourceBranchTargets(code);
                var operations = new JsonArray();
                for (int n = 0; n < code.Count; n++)
                {
                    if (code[n].Op != "ldarg" || !Equals(code[n].Arg, 1)) continue;
                    int valueAt = n + 1;
                    MethodInfo? helper = null;
                    Type storageOwner = target;
                    if (valueAt < code.Count && code[valueAt].Op == "call" && code[valueAt].Arg is MethodInfo callee
                        && callee.IsStatic && callee.GetParameters().Length == 1 && callee.GetParameters()[0].ParameterType == target
                        && (receiver == "npc" ? typeof(GlobalNPC) : typeof(ModPlayer)).IsAssignableFrom(callee.ReturnType))
                    {
                        helper = callee;
                        storageOwner = callee.ReturnType;
                        valueAt++;
                    }
                    if (valueAt + 1 >= code.Count || code[valueAt + 1].Op != "stfld" || code[valueAt + 1].Arg is not FieldInfo field
                        || field.IsStatic || !field.DeclaringType!.IsAssignableFrom(storageOwner)
                        || code.Skip(n + 1).Take(valueAt + 1 - n).Any(i => targets.Contains(i.Offset))) continue;
                    JsonNode? value = TypedSourceLiteral(code[valueAt], field.FieldType);
                    if (value is null) continue;
                    var operation = new JsonObject
                    {
                        ["nativeMember"] = field.DeclaringType.FullName + "." + field.Name,
                        ["operation"] = "assign", ["value"] = value, ["storageType"] = field.FieldType.FullName,
                        ["units"] = field.FieldType == typeof(bool) ? "boolean_flag_only" : "native_member_units",
                        ["sourceIlOffset"] = code[valueAt + 1].Offset,
                        ["condition"] = "control_must_reach_source_statement",
                    };
                    if (helper is not null)
                    {
                        operation["receiverExpression"] = helper.DeclaringType!.FullName + "." + helper.Name + "(target)";
                        operation["receiverResolution"] = "helper_return_object; helper_body_not_analyzed";
                    }
                    operations.Add(operation);
                }
                if (operations.Count > 0)
                {
                    JsonObject fragment = MethodSourceIdentity(update);
                    fragment["operations"] = operations;
                    fragments.Add(fragment);
                }
                else unsupported.Add("update_outside_literal_field_write_subset");
            }
            catch { unsupported.Add("update_outside_bounded_method_subset"); }
        }
        MethodInfo? setup = type.GetMethod("SetStaticDefaults", Type.EmptyTypes);
        if (setup is not null && setup.DeclaringType != typeof(ModBuff))
        {
            try
            {
                CaptureRegisteredBuffData(setup, registeredData);
                if (registeredData.Count == 8) unsupported.Add("registration_observation_limit_reached");
            }
            catch { unsupported.Add("registration_outside_bounded_method_subset"); }
        }
        return new JsonObject
        {
            ["source"] = "loaded_mod_buff_source_fragments", ["receiver"] = receiver,
            ["completeness"] = fragments.Count + registeredData.Count > 0 ? "partial_source_statements" : "unsupported",
            ["fragments"] = fragments, ["registeredData"] = registeredData, ["unsupported"] = unsupported,
            ["scope"] = "Parent-local compiled source only, no hook execution. Field writes require reaching their statement; helper-return receivers are unresolved. registeredData links this buff's Type-indexed registration to explicit static initializer writes, not current mutable values or proved effect units. Constructor behavior, downstream consumers, scaling, immunity, scheduling, reapplication and final damage remain unknown. Never convert a flag or data-field name into an unconditional gameplay effect."
        };
    }

    private static void CaptureRegisteredBuffData(MethodInfo setup, JsonArray result)
    {
        var code = ReadAmmoIl(setup, preserveStructure: true);
        var targets = SourceBranchTargets(code);
        for (int n = 0; n + 4 < code.Count && result.Count < 8; n++)
        {
            if (code[n].Op != "ldsfld" || code[n].Arg is not FieldInfo registry || !registry.FieldType.IsArray
                || code[n + 1].Op != "ldarg" || !Equals(code[n + 1].Arg, 0)
                || code[n + 2].Op != "call" || code[n + 2].Arg is not MethodInfo index
                || index.DeclaringType != typeof(ModBuff) || index.Name != "get_Type"
                || code[n + 3].Op != "ldsfld" || code[n + 3].Arg is not FieldInfo data
                || data.FieldType != registry.FieldType.GetElementType() || code[n + 4].Op != "stelem.ref"
                || code.Skip(n + 1).Take(4).Any(i => targets.Contains(i.Offset))) continue;
            JsonObject? initializer = CaptureDataInitializer(data);
            if (initializer is null) continue;
            var row = MethodSourceIdentity(setup);
            row["registryMember"] = registry.DeclaringType!.FullName + "." + registry.Name;
            row["index"] = "this_buff.Type";
            row["dataMember"] = data.DeclaringType!.FullName + "." + data.Name;
            row["sourceStoreIlOffset"] = code[n + 4].Offset;
            row["condition"] = "control_must_reach_registration_statement";
            row["initializer"] = initializer;
            result.Add(row);
        }
    }

    private static JsonObject? CaptureDataInitializer(FieldInfo data)
    {
        ConstructorInfo? initializer = data.DeclaringType!.TypeInitializer;
        if (initializer is null) return null;
        var code = ReadAmmoIl(initializer, preserveStructure: true);
        var targets = SourceBranchTargets(code);
        for (int n = 0; n < code.Count; n++)
        {
            if (code[n].Op != "newobj" || code[n].Arg is not ConstructorInfo constructor
                || constructor.DeclaringType != data.FieldType || constructor.GetParameters().Length != 0) continue;
            var writes = new JsonArray();
            int k = n + 1;
            while (k + 2 < code.Count && code[k].Op == "dup" && code[k + 2].Op == "stfld"
                && code[k + 2].Arg is FieldInfo field && field.DeclaringType!.IsAssignableFrom(data.FieldType))
            {
                JsonNode? value = TypedSourceLiteral(code[k + 1], field.FieldType);
                if (value is null) break;
                writes.Add(new JsonObject { ["member"] = field.DeclaringType.FullName + "." + field.Name,
                    ["value"] = value, ["storageType"] = field.FieldType.FullName, ["sourceIlOffset"] = code[k + 2].Offset });
                k += 3;
            }
            if (writes.Count == 0 || k >= code.Count || code[k].Op != "stsfld" || !Equals(code[k].Arg, data)
                || code.Skip(n + 1).Take(k - n).Any(i => targets.Contains(i.Offset))) continue;
            var result = MethodSourceIdentity(initializer);
            result["explicitFieldWrites"] = writes;
            result["sourceStoreIlOffset"] = code[k].Offset;
            return result;
        }
        return null;
    }
}

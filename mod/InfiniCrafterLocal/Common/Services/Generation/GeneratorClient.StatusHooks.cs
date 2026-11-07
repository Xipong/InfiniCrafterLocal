#nullable enable
using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Nodes;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Services;

public sealed partial class GeneratorClient
{
    // Source statements, not hook execution or a second gameplay interpreter.
    // Follow only the current parent's attached hit hooks; never publish the
    // loaded buff registry or infer effects from an item/buff name.
    private static object? WithItemStatusHooks(Item item, object? native)
    {
        var owners = new List<(Type Type, Type Base)>();
        if (item.ModItem is not null) owners.Add((item.ModItem.GetType(), typeof(ModItem)));
        bool rosterComplete = true;
        try { foreach (var global in item.Globals) owners.Add((global.GetType(), typeof(GlobalItem))); }
        catch { rosterComplete = false; }
        return WithStatusHooks(native, owners, rosterComplete);
    }

    private static object? WithProjectileStatusHooks(Projectile projectile, object? native)
    {
        var owners = new List<(Type Type, Type Base)>();
        if (projectile.ModProjectile is not null) owners.Add((projectile.ModProjectile.GetType(), typeof(ModProjectile)));
        bool rosterComplete = true;
        try { foreach (var global in projectile.Globals) owners.Add((global.GetType(), typeof(GlobalProjectile))); }
        catch { rosterComplete = false; }
        return WithStatusHooks(native, owners, rosterComplete);
    }

    private static object? WithStatusHooks(object? native, List<(Type Type, Type Base)> owners, bool rosterComplete)
    {
        var hooks = new JsonArray();
        int omitted = 0;
        foreach (var owner in owners.Distinct())
            foreach (MethodInfo method in owner.Type.GetMethods(BindingFlags.Public | BindingFlags.Instance))
            {
                if (method.Name != "OnHitNPC" || method.DeclaringType == owner.Base
                    || method.GetBaseDefinition().DeclaringType != owner.Base) continue;
                if (hooks.Count >= 16) { omitted++; continue; }
                hooks.Add(InspectStatusHook(method));
            }
        // No hook statement to add. The native reference already excludes mod
        // behavior; an unavailable roster must not fabricate an effect object.
        if (hooks.Count == 0) return native;
        var result = native is null ? new JsonObject { ["source"] = "parent_hit_hook_source_statements" }
            : JsonSerializer.SerializeToNode(native, WireJsonOptions)!.AsObject();
        result["hitHookSource"] = new JsonObject
        {
            ["hooks"] = hooks,
            ["attachedRosterComplete"] = rosterComplete && omitted == 0,
            ["omittedHookCount"] = omitted,
            ["scope"] = "Read-only direct NPC.AddBuff call statements in this parent's attached OnHitNPC overrides. A statement describes arguments IF control reaches its IL offset; it does not prove a per-hit effect or probability. Admission, guards, helper calls, other events, ModPlayer hooks, downstream buff consumers and detours remain unanalyzed. Unknown is not absent. No hooks or ModContent.BuffType methods were executed."
        };
        return result;
    }

    private static JsonObject InspectStatusHook(MethodInfo method)
    {
        var result = new JsonObject
        {
            ["method"] = method.DeclaringType!.FullName + "." + method.Name,
            ["sourceModuleVersionId"] = method.Module.ModuleVersionId.ToString(),
            ["completeness"] = "unsupported",
        };
        try
        {
            byte[] il = method.GetMethodBody()?.GetILAsByteArray() ?? throw new NotSupportedException();
            result["sourceMethodSha256"] = Convert.ToHexString(SHA256.HashData(il)).ToLowerInvariant();
            var code = ReadAmmoIl(method, preserveStructure: true);
            var requests = new JsonArray();
            var unresolved = new JsonArray();
            var targets = new HashSet<int>(code.SelectMany(i => i.Op == "switch" && i.Arg is int[] many ? many
                : (i.Op.StartsWith("b") || i.Op.StartsWith("leave")) && i.Arg is int target ? new[] { target } : Array.Empty<int>()));
            var parameters = method.GetParameters();
            for (int n = 0; n < code.Count; n++)
            {
                if (code[n].Op is not ("call" or "callvirt") || code[n].Arg is not MethodInfo call
                    || call.DeclaringType != typeof(NPC) || call.Name != nameof(NPC.AddBuff)) continue;
                var signature = call.GetParameters();
                AmmoIl? duration = StatusArgumentSource(code, n - 2, targets);
                AmmoIl? flags = StatusArgumentSource(code, n - 1, targets);
                // Exact stack-producing slice, including target and quiet. No
                // edge may enter its interior with different stack values.
                if (signature.Length != 3 || signature[0].ParameterType != typeof(int)
                    || signature[1].ParameterType != typeof(int) || signature[2].ParameterType != typeof(bool)
                    || n < 4 || code[n - 4].Op != "ldarg" || code[n - 4].Arg is not int arg
                    || arg < 1 || arg > parameters.Length || parameters[arg - 1].ParameterType != typeof(NPC)
                    || duration?.Op != "const" || duration.Arg is not int ticks || ticks <= 0
                    || flags?.Op != "const" || flags.Arg is not int quiet || quiet is not (0 or 1)
                    || code.Skip(n - 3).Take(4).Any(i => targets.Contains(i.Offset)))
                { unresolved.Add(code[n].Offset); continue; }
                var identity = ReadStatusBuffIdentity(StatusArgumentSource(code, n - 3, targets));
                if (identity is null) { unresolved.Add(code[n].Offset); continue; }
                identity["receiver"] = "npc";
                identity["targetParameter"] = parameters[arg - 1].Name;
                identity["requestedDurationTicks"] = ticks;
                identity["quiet"] = quiet == 1;
                identity["sourceCallIlOffset"] = code[n].Offset;
                identity["condition"] = "control_must_reach_source_statement";
                if (identity["buffId"] is JsonValue value && value.TryGetValue<int>(out int id))
                    identity["buffEffectReference"] = CaptureNativeBuffEffectReference(id, "npc");
                requests.Add(identity);
            }
            result["requests"] = requests;
            result["unresolvedDirectAddBuffOffsets"] = unresolved;
            result["completeness"] = "partial_source_statements";
        }
        catch { result["reason"] = "method_outside_bounded_direct_call_subset"; }
        return result;
    }

    private static AmmoIl? StatusArgumentSource(List<AmmoIl> code, int index, HashSet<int> targets)
    {
        if (index < 0) return null;
        AmmoIl value = code[index];
        if (value.Op != "ldloc") return value;
        if (targets.Contains(value.Offset)) return null;
        // A local copy is evidence only with a dominating definition in the
        // same straight-line block and no address escape. Do not choose an arm
        // of a phi/ternary or evaluate a helper to invent the missing value.
        for (int n = index - 1; n >= 0; n--)
        {
            AmmoIl prior = code[n];
            if (targets.Contains(prior.Offset) || prior.Op.StartsWith("ldloca") || prior.Op.StartsWith("b")
                || prior.Op.StartsWith("leave") || prior.Op is "switch" or "ret" or "throw") return null;
            if (prior.Op == "stloc" && Equals(prior.Arg, value.Arg))
                return n > 0 && code[n - 1].Op is "const" or "call" ? code[n - 1] : null;
        }
        return null;
    }

    private static JsonObject? ReadStatusBuffIdentity(AmmoIl? instruction)
    {
        if (instruction is null) return null;
        if (instruction.Op == "const" && instruction.Arg is int id && id > 0 && id < BuffLoader.BuffCount)
        {
            string? name = BuffID.Search.ContainsId(id) ? BuffID.Search.GetName(id) : null;
            return new JsonObject { ["buffId"] = id, ["buffFullName"] = id < BuffID.Count && name is not null ? "Terraria/" + name : name };
        }
        if (instruction.Op != "call" || instruction.Arg is not MethodInfo method
            || method.DeclaringType != typeof(ModContent) || method.Name != nameof(ModContent.BuffType)
            || !method.IsGenericMethod || method.GetGenericArguments().Length != 1 || method.GetParameters().Length != 0
            || method.ReturnType != typeof(int))
            return null;
        Type type = method.GetGenericArguments()[0];
        // Resolve by actual registered CLR type, never a guessed numeric ID.
        for (int candidate = BuffID.Count; candidate < BuffLoader.BuffCount; candidate++)
        {
            ModBuff? buff = BuffLoader.GetBuff(candidate);
            if (buff?.GetType() == type)
                return new JsonObject { ["buffId"] = candidate, ["buffFullName"] = buff.FullName };
        }
        return new JsonObject { ["buffClrType"] = type.FullName, ["identityStatus"] = "not_registered_in_current_buff_loader" };
    }
}

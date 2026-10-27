#nullable enable
using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Reflection.Emit;
using System.Security.Cryptography;
using System.Text.Json.Nodes;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Services;

public sealed partial class GeneratorClient
{
    private static readonly Lazy<string?> AmmoPickCertificate = new(() => AmmoMethodCertificate(typeof(Player).GetMethods(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance)
        .Single(m => m.Name == "PickAmmo" && m.GetParameters().Length == 8)));
    private static readonly Lazy<string?> AmmoSpecificMatchCertificate = new(() => {
        var method = typeof(Player).GetMethod("PickAmmo_TryFindingSpecificMatches", BindingFlags.NonPublic | BindingFlags.Instance);
        return method is null ? null : AmmoMethodCertificate(method);
    });

    private static string? AmmoMethodCertificate(MethodInfo method)
    {
        try
        {
            byte[]? il = method.GetMethodBody()?.GetILAsByteArray();
            return il is null ? null : Convert.ToHexString(SHA256.HashData(il)).ToLowerInvariant() + ":" + method.Module.ModuleVersionId;
        }
        catch { return null; }
    }

    // This is metadata inspection, not reflection dispatch or an IL executor.
    // Only explicit bounded source shapes below produce positive hook facts.
    internal static JsonObject CaptureAmmoProjectileSemantics(Item item)
    {
        var stages = new JsonArray();
        var unknowns = new JsonArray("Ammo choice/admission, player equipment, later native projectile-set rewrites and ModPlayer hooks are not evaluated.");
        bool replaced = false, conditional = false, ownDelivery = false, unknownWrite = false;
        foreach (var (method, certificate) in new[] { ("Player.PickAmmo", AmmoPickCertificate.Value), ("Player.ItemCheck_Shoot", ShootFactCertificate.Value) })
        {
            var stage = new JsonObject { ["method"] = method, ["rules"] = new JsonArray(), ["spawnSites"] = new JsonArray() };
            if (certificate is not null && NativeAmmoFactsCatalog.Sources.TryGetValue(method + ":" + certificate, out var catalog))
            {
                stage["sourceMethodSha256"] = certificate.Split(':')[0];
                stage["sourceModuleVersionId"] = certificate.Split(':')[1];
                var baseline = JsonNode.Parse(NativeAmmoFactsCatalog.Selection[method + ":" + certificate])!;
                stage["defaultProjectileSelection"] = baseline["defaultProjectileSelection"]?.DeepClone();
                stage["sourceStageCallSites"] = baseline["sourceStageCallSites"]!.DeepClone();
                if (method == "Player.PickAmmo")
                {
                    var dispatch = baseline["hookDispatchTrace"]!.AsArray();
                    bool verified = dispatch.OfType<JsonObject>().All(row => {
                        string name = row["method"]!.GetValue<string>();
                        Type owner = name.StartsWith("Terraria.ModLoader.ItemLoader.") ? typeof(ItemLoader) : typeof(CombinedHooks);
                        return NativeAttackCertificate(owner, name.Substring(name.LastIndexOf('.') + 1))
                            == row["sourceMethodSha256"]!.GetValue<string>() + ":" + certificate.Split(':')[1];
                    });
                    if (verified) stage["hookDispatchTrace"] = dispatch.DeepClone();
                    else unknowns.Add("Native hook dispatch source certificate differs; generated dispatcher trace withheld.");
                }
                bool mentioned = baseline["itemTypeMentions"]!.AsArray().Any(x => x!.GetValue<int>() == item.type);
                if (item.ModItem is null && mentioned && !catalog.ContainsKey(item.type))
                {
                    stage["status"] = "unmodeled_native_item_branch";
                    unknownWrite = true;
                }
                if (item.ModItem is null && catalog.TryGetValue(item.type, out string? json))
                {
                    var facts = JsonNode.Parse(json)!.AsObject();
                    stage["rules"] = facts["rules"]!.DeepClone();
                    stage["spawnSites"] = facts["spawnSites"]!.DeepClone();
                    stage["spawnOriginSetups"] = facts["spawnOriginSetups"]!.DeepClone();
                    stage["unrecognizedProjectileWriteOffsets"] = facts["unrecognizedProjectileWriteOffsets"]!.DeepClone();
                    foreach (var rule in facts["rules"]!.AsArray().OfType<JsonObject>())
                    {
                        if (rule["whenInputProjectileId"] is null) replaced = true;
                        else conditional = true;
                    }
                    ownDelivery |= facts["spawnSites"]!.AsArray().Count > 0;
                    unknownWrite |= facts["unrecognizedProjectileWriteOffsets"]!.AsArray().Count > 0;
                }
            }
            else
            {
                stage["status"] = "unknown_native_method_certificate";
                unknownWrite = true;
            }
            stages.Add(stage);
        }
        var hooks = new JsonArray();
        if (item.ModItem is not null)
            CaptureAmmoHooks(item.ModItem.GetType(), typeof(ModItem), hooks);
        try
        {
            foreach (var global in item.Globals)
                CaptureAmmoHooks(global.GetType(), typeof(GlobalItem), hooks);
        }
        catch { unknowns.Add("Attached GlobalItem hook roster unavailable; listed hook facts are partial."); }
        bool hookReplace = false, hookConditional = false, hookOwn = false, hookSuppress = false, opaqueHook = false;
        bool certifiedDispatch = stages.OfType<JsonObject>().Any(stage => stage["hookDispatchTrace"] is JsonArray);
        bool globalStopsModShoot = certifiedDispatch && hooks.OfType<JsonObject>().Any(hook =>
            hook["ownerKind"]?.GetValue<string>() == "GlobalItem" && hook["phase"]?.GetValue<string>() == "Shoot"
            && hook["shape"]!.GetValue<string>() is "suppresses_default_shot" or "fixed_projectile_spawn_suppresses_default");
        foreach (var hook in hooks.OfType<JsonObject>())
        {
            if (globalStopsModShoot && hook["ownerKind"]?.GetValue<string>() == "ModItem" && hook["phase"]?.GetValue<string>() == "Shoot") continue;
            string shape = hook["shape"]!.GetValue<string>();
            opaqueHook |= shape == "opaque";
            hookReplace |= shape == "literal_projectile_replacement";
            hookConditional |= shape == "conditional_literal_projectile_replacement";
            hookOwn |= shape == "fixed_projectile_spawn_suppresses_default";
            hookSuppress |= shape == "suppresses_default_shot";
        }
        bool offsetSelection = stages.OfType<JsonObject>().Any(stage =>
            stage["defaultProjectileSelection"]?["categoryOffsetSelectors"] is JsonArray selectors
            && selectors.OfType<JsonObject>().Any(selector => selector["ammoCategoryId"]!.GetValue<int>() == item.useAmmo));
        string relation = opaqueHook ? "unknown_hook_projectile_semantics"
            : hookOwn ? "ignored_replaced_by_hook_projectiles"
            : hookSuppress ? "suppressed_default_shot"
            : hookConditional ? "conditionally_replaced_by_inspected_hook"
            : hookReplace ? "replaced_by_inspected_hook"
            : replaced ? "replaced" : conditional ? "conditionally_replaced"
            : unknownWrite ? "unknown_native_projectile_semantics"
            : offsetSelection ? "native_ammo_table_or_offset_selection"
            : ownDelivery ? "retained_with_native_item_delivery" : "retained_in_default_ammo_path";
        unknowns.Add("Known literal item rules do not certify absence of other native rewrites or a final shot. Native item-specific spawn sites may change origin, count and trajectory even when their projectile argument is retained.");
        unknowns.Add("CanShoot, ammo availability, player hooks and other gameplay gates may change or suppress shooting; source inspection does not execute them.");
        if (offsetSelection)
            unknowns.Add("Verified complete selection chain reads the current specific-match table first, then category offsets or the positive-ammo/default arm. This does not certify later rewrites or a final shot.");
        return new JsonObject {
            ["status"] = "source_inspected", ["ammoProjectileRelation"] = relation,
            ["finalShotOutcome"] = "unknown_without_gameplay_execution",
            ["stages"] = stages, ["hooks"] = hooks, ["unknowns"] = unknowns,
            ["scope"] = "Read-only parent source evidence, never required child mechanics. Retained projectile identity is not a claim of normal direct-arrow delivery. Inventory ammo entries are candidate inputs, not observed fired behavior. Ammo-item damage, speed and knockback remain separate native inputs when projectile identity is replaced; no universal additive final-damage formula is asserted. Author explicitly chooses generated behavior." };
    }

    private static JsonObject BindAmmoCandidateProjectile(Item weapon, AmmoCandidate candidate, JsonObject semantics)
    {
        int input = candidate.Item.shoot, current = input;
        bool changed = false, suppressed = false, opaque = false, known = true;
        var ownSpawns = new HashSet<int>();
        var proofs = new JsonArray();
        void Apply(JsonObject rule, string method)
        {
            if (rule["whenInputProjectileId"] is JsonNode condition && (!known || condition.GetValue<int>() != current)) return;
            if (rule["outputProjectileId"] is not JsonNode output) return;
            current = output.GetValue<int>(); changed = true; known = true;
            proofs.Add(new JsonObject { ["method"] = method, ["rule"] = rule.DeepClone() });
        }
        void Hooks(IEnumerable<JsonObject>? hooks)
        {
            if (hooks is null) return;
            foreach (var hook in hooks)
            {
                string shape = hook["shape"]!.GetValue<string>();
                if (shape is "literal_projectile_replacement" or "conditional_literal_projectile_replacement") Apply(hook, hook["method"]!.GetValue<string>());
                else if (shape == "fixed_projectile_spawn_suppresses_default") { current = hook["projectileId"]!.GetValue<int>(); ownSpawns.Add(current); changed = true; known = true; }
                else if (shape == "suppresses_default_shot") suppressed = true;
                else if (shape == "opaque") opaque = true;
            }
        }
        var stages = semantics["stages"]!.AsArray().OfType<JsonObject>().ToArray();
        foreach (var stage in stages)
        {
            if (stage["method"]!.GetValue<string>() == "Player.PickAmmo")
            {
                if (stage["defaultProjectileSelection"] is not JsonObject selection
                    || selection["specificMatchLookupFirst"]?.GetValue<bool>() != true
                    || AmmoSpecificMatchCertificate.Value != selection["specificMatchLookupCertificate"]?.GetValue<string>())
                    known = false;
                else try
                {
                    if (AmmoID.Sets.SpecificLauncherAmmoProjectileMatches.TryGetValue(weapon.type, out var matches)
                        && matches.TryGetValue(candidate.Item.type, out int matched))
                    {
                        current = matched; changed = true;
                        proofs.Add(new JsonObject { ["method"] = "Player.PickAmmo", ["source"] = "SpecificLauncherAmmoProjectileMatches", ["projectileId"] = matched });
                    }
                    else if (selection["categoryOffsetSelectors"] is JsonArray offsets
                        && offsets.OfType<JsonObject>().Any(selector => selector["ammoCategoryId"]!.GetValue<int>() == weapon.useAmmo))
                    {
                        current = checked(weapon.shoot + input); changed = current != input;
                        proofs.Add(new JsonObject { ["method"] = "Player.PickAmmo", ["source"] = "certified_category_offset", ["projectileId"] = current });
                    }
                    else if (input <= ProjectileID.None)
                    {
                        current = weapon.shoot; changed = current != input;
                        proofs.Add(new JsonObject { ["method"] = "Player.PickAmmo", ["source"] = "certified_retained_weapon_shoot", ["projectileId"] = current });
                    }
                }
                catch { known = false; }
            }
            foreach (var rule in stage["rules"]!.AsArray().OfType<JsonObject>()) Apply(rule, stage["method"]!.GetValue<string>());
            if (stage["method"]!.GetValue<string>() == "Player.PickAmmo") Hooks(CaptureAmmoInputHookReference(candidate.Item)?["hooks"]?.AsArray().OfType<JsonObject>());
        }
        var weaponHooks = semantics["hooks"]!.AsArray().OfType<JsonObject>().ToArray();
        var dispatch = stages.SelectMany(stage => stage["hookDispatchTrace"] is JsonArray rows
            ? rows.OfType<JsonObject>() : Enumerable.Empty<JsonObject>()).ToArray();
        var phases = stages.Where(stage => stage["method"]!.GetValue<string>() == "Player.ItemCheck_Shoot")
            .SelectMany(stage => stage["sourceStageCallSites"] is JsonArray sites ? sites.OfType<JsonObject>() : Enumerable.Empty<JsonObject>())
            .OrderBy(site => site["sourceCallIlOffset"]!.GetValue<int>())
            .Select(site => site["method"]!.GetValue<string>())
            .Where(name => name is "Terraria.ModLoader.CombinedHooks.ModifyShootStats" or "Terraria.ModLoader.CombinedHooks.Shoot")
            .Select(name => name.Substring(name.LastIndexOf('.') + 1)).ToArray();
        bool globalShootStopped = false;
        if (weaponHooks.Length > 0 && phases.Length != 2) opaque = true;
        foreach (string phase in phases)
        {
            var matching = weaponHooks.Where(hook => hook["phase"]?.GetValue<string>() == phase).ToArray();
            if (matching.Length == 0) continue;
            var trace = dispatch.SingleOrDefault(row => row["method"]!.GetValue<string>() == "Terraria.ModLoader.ItemLoader." + phase);
            if (trace?["directHookCalls"] is not JsonArray calls) { opaque = true; continue; }
            foreach (string callback in calls.Select(call => call!.GetValue<string>()))
            {
                string owner = callback.StartsWith("Terraria.ModLoader.GlobalItem.") ? "GlobalItem" : "ModItem";
                if (phase == "Shoot" && owner == "ModItem" && globalShootStopped) continue;
                var owned = matching.Where(hook => hook["ownerKind"]?.GetValue<string>() == owner).ToArray();
                Hooks(owned);
                // Native ItemLoader calls every GlobalItem.Shoot, then admits
                // ModItem.Shoot only when all globals allowed it. Own spawns
                // remain distinct from the ref-projectile being modified.
                if (phase == "Shoot" && owner == "GlobalItem")
                    globalShootStopped |= owned.Any(hook => hook["shape"]!.GetValue<string>() is "suppresses_default_shot" or "fixed_projectile_spawn_suppresses_default");
            }
        }
        if (ownSpawns.Count > 1) opaque = true; // Multiple actual spawns are not one guessed identity.
        if (ownSpawns.Count == 1) { current = ownSpawns.Single(); suppressed = false; known = true; }
        string relation = semantics["ammoProjectileRelation"]!.GetValue<string>();
        bool unconditional = relation is "replaced" or "replaced_by_inspected_hook" or "ignored_replaced_by_hook_projectiles";
        bool retainInput = known && !suppressed && !opaque && !unconditional && current == input;
        var binding = new JsonObject {
            ["candidateSource"] = candidate.Source, ["inventorySlot"] = candidate.InventorySlot,
            ["inputProjectileId"] = input, ["sourceRuleOutputProjectileId"] = suppressed || opaque || !known ? null : current,
            ["includeInputProjectileProfile"] = retainInput,
            ["includeReplacementProjectileProfile"] = changed && known && !suppressed && !opaque && current > ProjectileID.None && current < ProjectileLoader.ProjectileCount,
            ["relation"] = suppressed ? "default_shot_suppressed" : opaque ? "unknown_hook_outcome" : !known ? "unknown_native_ammo_selection" : changed ? "source_rule_projection" : "input_retained_in_supported_source_rules",
            ["matchedSourceRules"] = proofs,
            ["scope"] = "Candidate input bound through supported source rules and current specific-match table only. Ambient player state, opaque hooks and unmodeled native writes are unresolved; not an observed or guaranteed final shot." };
        return binding;
    }

    private static object? SourceReplacementProjectileRaw(int type, Item weapon)
    {
        if (type <= ProjectileID.None || type >= ProjectileLoader.ProjectileCount) return null;
        var raw = System.Text.Json.JsonSerializer.SerializeToNode(ProjectileRawSnapshot(type, weapon.shootSpeed,
            "source_inspected_replacement_projectile_identity_not_final_shot", weapon, -1), WireJsonOptions)?.AsObject();
        raw?.Remove("itemShootSpeed");
        return raw;
    }

    private static void CaptureAmmoHooks(Type type, Type baseType, JsonArray hooks, bool ammoInput = false)
    {
        foreach (string name in ammoInput ? new[] { "PickAmmo" } : new[] { "ModifyShootStats", "Shoot" })
        {
            var declaration = baseType.GetMethod(name, BindingFlags.Instance | BindingFlags.Public)!;
            var method = type.GetMethods(BindingFlags.Instance | BindingFlags.Public).SingleOrDefault(m => m.GetBaseDefinition() == declaration);
            if (method is null || method.DeclaringType == baseType) continue;
            hooks.Add(InspectAmmoHook(method));
        }
    }

    internal static JsonObject? CaptureAmmoInputHookReference(Item ammo)
    {
        var hooks = new JsonArray();
        if (ammo.ModItem is not null) CaptureAmmoHooks(ammo.ModItem.GetType(), typeof(ModItem), hooks, ammoInput: true);
        bool rosterAvailable = true;
        try { foreach (var global in ammo.Globals) CaptureAmmoHooks(global.GetType(), typeof(GlobalItem), hooks, ammoInput: true); }
        catch { rosterAvailable = false; }
        return hooks.Count == 0 ? null : new JsonObject {
            ["hooks"] = hooks, ["attachedGlobalRosterObserved"] = rosterAvailable,
            ["scope"] = "ItemLoader.PickAmmo calls the selected ammo.ModItem then its GlobalItems, not the weapon's ModItem. Candidate-only source inspection; not native ammo selection or a guaranteed final projectile." };
    }

    private sealed record AmmoIl(int Offset, string Op, object? Arg);
    private static readonly Dictionary<short, OpCode> AmmoOpcodes = typeof(OpCodes).GetFields(BindingFlags.Public | BindingFlags.Static)
        .Where(f => f.FieldType == typeof(OpCode)).Select(f => (OpCode)f.GetValue(null)!).ToDictionary(op => op.Value);

    private static List<AmmoIl> ReadAmmoIl(MethodBase method, bool preserveStructure = false)
    {
        var body = method.GetMethodBody();
        byte[] il = body?.GetILAsByteArray() ?? throw new NotSupportedException();
        if (il.Length > 2048 || body!.ExceptionHandlingClauses.Count != 0) throw new NotSupportedException();
        Type[] methodArguments = method is MethodInfo genericMethod ? genericMethod.GetGenericArguments() : Type.EmptyTypes;
        var result = new List<AmmoIl>();
        for (int p = 0; p < il.Length;)
        {
            int offset = p;
            short value = il[p++] == 0xfe ? (short)(0xfe00 | il[p++]) : (short)il[offset];
            var opcode = AmmoOpcodes[value];
            string op = opcode.Name!;
            object? arg = null;
            switch (opcode.OperandType)
            {
                case OperandType.InlineNone: break;
                case OperandType.ShortInlineI: arg = (int)(sbyte)il[p++]; break;
                case OperandType.InlineI: arg = BitConverter.ToInt32(il, p); p += 4; break;
                case OperandType.ShortInlineVar: arg = (int)il[p++]; break;
                case OperandType.InlineVar: arg = (int)BitConverter.ToUInt16(il, p); p += 2; break;
                case OperandType.ShortInlineBrTarget: arg = p + 1 + (sbyte)il[p]; p++; break;
                case OperandType.InlineBrTarget: arg = p + 4 + BitConverter.ToInt32(il, p); p += 4; break;
                case OperandType.InlineMethod: arg = method.Module.ResolveMethod(BitConverter.ToInt32(il, p), method.DeclaringType?.GetGenericArguments(), methodArguments); p += 4; break;
                case OperandType.InlineField: arg = method.Module.ResolveField(BitConverter.ToInt32(il, p), method.DeclaringType?.GetGenericArguments(), methodArguments); p += 4; break;
                case OperandType.ShortInlineR: arg = BitConverter.ToSingle(il, p); p += 4; break;
                case OperandType.InlineR: arg = BitConverter.ToDouble(il, p); p += 8; break;
                case OperandType.InlineI8: arg = BitConverter.ToInt64(il, p); p += 8; break;
                case OperandType.InlineType:
                case OperandType.InlineTok:
                case OperandType.InlineString:
                case OperandType.InlineSig: arg = BitConverter.ToInt32(il, p); p += 4; break;
                case OperandType.InlineSwitch:
                    int count = BitConverter.ToInt32(il, p); p += 4;
                    if (count < 0 || count > (il.Length - p) / 4) throw new NotSupportedException();
                    int end = p + count * 4;
                    var targets = new int[count];
                    for (int i = 0; i < count; i++, p += 4) targets[i] = end + BitConverter.ToInt32(il, p);
                    arg = targets; break;
                default: throw new NotSupportedException();
            }
            if (op is "ldc.i4" or "ldc.i4.s") op = "const";
            else if (op.StartsWith("ldc.i4.")) { arg = op == "ldc.i4.m1" ? -1 : int.Parse(op.Substring(7)); op = "const"; }
            else if (op.StartsWith("ldarg.") || op.StartsWith("ldloc.") || op.StartsWith("stloc."))
            {
                string prefix = op.Split('.')[0];
                if (!op.EndsWith(".s")) arg = int.Parse(op.Substring(prefix.Length + 1));
                op = prefix;
            }
            if (preserveStructure || op != "nop") result.Add(new AmmoIl(offset, op, arg));
        }
        if (preserveStructure) return result;
        // An unconditional transfer to the immediately following instruction is
        // compiler structure, not a gameplay condition.
        for (int i = result.Count - 2; i >= 0; i--)
            if (result[i].Op is "br" or "br.s" && Equals(result[i].Arg, result[i + 1].Offset)) result.RemoveAt(i);
        // Compiler spill/reload identity only; reject branch entry into either.
        for (int i = result.Count - 2; i >= 0; i--)
            if (result[i].Op == "stloc" && result[i + 1].Op == "ldloc" && Equals(result[i].Arg, result[i + 1].Arg)
                && !result.Any(x => x.Op.StartsWith("b") && (Equals(x.Arg, result[i].Offset) || Equals(x.Arg, result[i + 1].Offset))))
                result.RemoveRange(i, 2);
        if (result.Count >= 2 && result[^2].Op is "br" or "br.s" && Equals(result[^2].Arg, result[^1].Offset) && result[^1].Op == "ret") result.RemoveAt(result.Count - 2);
        return result;
    }

    private static JsonObject InspectAmmoHook(MethodInfo method)
    {
        string? certificate = AmmoMethodCertificate(method);
        var result = new JsonObject { ["method"] = method.DeclaringType!.FullName + "." + method.Name, ["shape"] = "opaque",
            ["sourceMethodSha256"] = certificate?.Split(':')[0], ["sourceModuleVersionId"] = method.Module.ModuleVersionId.ToString(),
            ["phase"] = method.Name,
            ["ownerKind"] = method.GetBaseDefinition().DeclaringType == typeof(GlobalItem) ? "GlobalItem" : "ModItem",
            ["scope"] = "Inspected override body only; no gameplay execution, caller admission or other hook outcome proof" };
        try
        {
            Type? declaration = method.GetBaseDefinition().DeclaringType;
            if (method.IsStatic || (declaration != typeof(ModItem) && declaration != typeof(GlobalItem))
                || method.ReturnType != (method.Name == "Shoot" ? typeof(bool) : typeof(void))) return result;
            var code = ReadAmmoIl(method);
            int typeArg = Array.FindIndex(method.GetParameters(), p => p.ParameterType == typeof(int).MakeByRefType()) + 1;
            bool Is(int n, string op, object? arg = null) => n >= 0 && n < code.Count && code[n].Op == op && (arg is null || Equals(code[n].Arg, arg));
            if (method.Name == "Shoot" && code.Count == 2 && Is(0, "const") && Is(1, "ret") && code[0].Arg is int boolean && boolean is 0 or 1)
            {
                result["shape"] = Equals(code[0].Arg, 1) ? "allows_default_shot" : "suppresses_default_shot";
                return result;
            }
            if (method.Name is "ModifyShootStats" or "PickAmmo")
            {
                int start = 0;
                int? input = null;
                if (Is(0, "ldarg", typeArg) && Is(1, "ldind.i4") && Is(2, "const"))
                {
                    if ((Is(3, "bne.un") || Is(3, "bne.un.s")) && Equals(code[3].Arg, code[^1].Offset)) { start = 4; input = (int)code[2].Arg!; }
                    else if (Is(3, "ceq") && (Is(4, "brfalse") || Is(4, "brfalse.s")) && Equals(code[4].Arg, code[^1].Offset)) { start = 5; input = (int)code[2].Arg!; }
                    else return result;
                }
                if (code.Count == start + 4 && Is(start, "ldarg", typeArg) && Is(start + 1, "const") && Is(start + 2, "stind.i4") && Is(start + 3, "ret"))
                {
                    result["shape"] = input is null ? "literal_projectile_replacement" : "conditional_literal_projectile_replacement";
                    result["outputProjectileId"] = (int)code[start + 1].Arg!;
                    if (input is not null) result["whenInputProjectileId"] = input.Value;
                    result["sourceStoreIlOffset"] = code[start + 2].Offset;
                }
                return result;
            }
            if (method.Name == "Shoot") InspectOwnAmmoSpawn(method, code, result);
        }
        catch { /* Opaque body remains a useful unknown, never a guessed result. */ }
        return result;
    }

    private static void InspectOwnAmmoSpawn(MethodInfo method, List<AmmoIl> code, JsonObject result)
    {
        int call = code.FindIndex(i => i.Op == "call" && i.Arg is MethodInfo m && m.DeclaringType == typeof(Projectile) && m.Name == "NewProjectile");
        if (call < 0 || call + 4 != code.Count || code[call + 1].Op != "pop" || code[call + 2].Op != "const" || !Equals(code[call + 2].Arg, 0) || code[call + 3].Op != "ret") return;
        var spawn = (MethodInfo)code[call].Arg!;
        if (spawn.GetParameters().Length != 10 || spawn.GetParameters()[1].ParameterType != typeof(Microsoft.Xna.Framework.Vector2)) return;
        int cursor = 0;
        var arguments = new List<AmmoIl>();
        while (cursor < call)
        {
            var arg = code[cursor++];
            if (arg.Op is not ("ldarg" or "const" or "ldc.r4")) return;
            arguments.Add(arg);
            if (cursor < call && code[cursor].Op == "ldfld") cursor++;
        }
        if (arguments.Count != 10 || arguments[3].Op != "const") return;
        int projectile = (int)arguments[3].Arg!;
        result["spawnProjectileLiteral"] = projectile;
        result["sourceSpawnIlOffset"] = code[call].Offset;
        result["defaultShotReturnLiteral"] = false;
        // Numeric call arguments are source facts, not SetDefaults or spawn success.
        if (projectile <= ProjectileID.None || projectile >= ProjectileLoader.ProjectileCount) return;
        result["shape"] = "fixed_projectile_spawn_suppresses_default";
        result["projectileId"] = projectile;
    }
}

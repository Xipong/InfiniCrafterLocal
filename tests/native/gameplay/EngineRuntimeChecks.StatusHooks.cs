using System;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Services;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private static int ModBuffSourceExecuted;
    private static void ParentModBuffSourceLinksWithoutExecution()
    {
        ModBuffSourceExecuted = 0;
        var inspect = typeof(GeneratorClient).GetMethod("InspectModBuffSource", BindingFlags.NonPublic | BindingFlags.Static)!;
        var facts = (JsonObject)inspect.Invoke(null, new object[] { typeof(SourceDataBuff), "npc" })!;
        Equal(0, ModBuffSourceExecuted, "no update, registration, static initializer or data constructor was executed");
        Equal("partial_source_statements", facts["completeness"]!.GetValue<string>(), "mod source is not categorically refused");
        var ops = facts["fragments"]!.AsArray().SelectMany(f => f!["operations"]!.AsArray()).ToArray();
        Equal(true, ops.Any(o => o!["nativeMember"]!.GetValue<string>() == "Terraria.NPC.lifeRegen" && o["value"]!.GetValue<int>() == -28),
            "literal native field write is read with its receiver");
        Equal(true, ops.Any(o => o!["receiverResolution"]?.GetValue<string>() == "helper_return_object; helper_body_not_analyzed"),
            "helper-return flag remains partial instead of inventing its consumers");
        var data = facts["registeredData"]!.AsArray();
        Equal(1, data.Count, "only Type-indexed registration is associated with this buff, not Type+1");
        var writes = data[0]!["initializer"]!["explicitFieldWrites"]!.AsArray();
        Equal(true, writes.Any(w => w!["member"]!.GetValue<string>().EndsWith(".Strength") && w["value"]!.GetValue<int>() == 17),
            "registration points to that exact field initializer");
        Equal(true, writes.Any(w => w!["member"]!.GetValue<string>().EndsWith(".Scale") && w["value"]!.GetValue<float>() == 0.5f),
            "typed float source value is retained without invented units");
        Equal(true, facts["unsupported"]!.AsArray().Count > 0, "data is not a fully decoded effect");
    }

    private sealed class SourceEffectData
    {
        public int Strength;
        public float Scale;
        public SourceEffectData() { ModBuffSourceExecuted++; }
    }
    private sealed class SourceGlobalNpc : GlobalNPC { public bool Active; }
    private static SourceGlobalNpc SourceNpc(NPC npc) => npc.GetGlobalNPC<SourceGlobalNpc>();
    private sealed class SourceDataBuff : ModBuff
    {
        private static readonly SourceEffectData data = new() { Strength = 17, Scale = 0.5f };
        private static readonly SourceEffectData[] registry = new SourceEffectData[4096];
        public override void SetStaticDefaults()
        {
            registry[Type] = data;
            registry[Type + 1] = data;
            ModBuffSourceExecuted++;
        }
        public override void Update(NPC npc, ref int buffIndex)
        {
            SourceNpc(npc).Active = true;
            npc.lifeRegen = -28;
            ModBuffSourceExecuted++;
        }
    }

    private static void ParentHitHooksPreserveSourceRequestsWithoutExecution()
    {
        var inspect = typeof(GeneratorClient).GetMethod("InspectStatusHook", BindingFlags.Static | BindingFlags.NonPublic)!;
        JsonObject Read(Type type) => (JsonObject)inspect.Invoke(null, new object[] { type.GetMethod("OnHitNPC")! })!;
        JsonObject fact = Read(typeof(StatusSourceItem));
        Equal("partial_source_statements", fact["completeness"]!.GetValue<string>(), "real mod override IL was inspected");
        var requests = fact["requests"]!.AsArray();
        Equal(3, requests.Count, "fixed, guarded and unregistered-generic requests are retained");
        Equal(BuffID.Poisoned, requests[0]!["buffId"]!.GetValue<int>(), "literal native identity");
        Equal(321, requests[0]!["requestedDurationTicks"]!.GetValue<int>(), "literal requested duration");
        Equal("partial_native_statement_fragments", requests[0]!["buffEffectReference"]!["completeness"]!.GetValue<string>(),
            "mod hook can expose native NPC buff semantics");
        Equal("control_must_reach_source_statement", requests[1]!["condition"]!.GetValue<string>(), "conditional hit is not flattened to unconditional");
        Equal(false, requests[1]!.AsObject().ContainsKey("probability"), "no guessed critical hit probability");
        Equal(false, requests[2]!.AsObject().ContainsKey("buffId"), "unregistered generic type never becomes a guessed ID");
        Equal(typeof(UnregisteredSourceBuff).FullName!, requests[2]!["buffClrType"]!.GetValue<string>(), "unknown runtime ID retains exact source type");
        Equal(0, StatusSourceItem.Calls, "capture did not execute the hit override");
        JsonObject unknown = Read(typeof(DynamicStatusSourceProjectile));
        Equal(0, unknown["requests"]!.AsArray().Count, "dynamic duration is not invented");
        Equal(1, unknown["unresolvedDirectAddBuffOffsets"]!.AsArray().Count, "unsupported direct call is visible");
        JsonObject merged = Read(typeof(ConditionalIdentitySource));
        Equal(0, merged["requests"]!.AsArray().Count, "a local with conditional definitions must not select one buff ID");
        Equal(1, merged["unresolvedDirectAddBuffOffsets"]!.AsArray().Count, "conditional identity remains explicit unknown");
        var potion = new Item(ItemID.MiningPotion);
        typeof(Item).GetProperty(nameof(Item.ModItem))!.SetValue(potion, new StatusSourceItem());
        var capture = typeof(GeneratorClient).GetMethod("CaptureParentNativeFacts", BindingFlags.Static | BindingFlags.NonPublic)!;
        object snapshot = capture.Invoke(null, new object?[] { potion, null })!;
        var raw = (JsonObject)snapshot.GetType().GetProperty("RuntimeFacts")!.GetValue(snapshot)!;
        Equal("partial_native_statement_fragments", raw["nativeBuffEffectReference"]!["completeness"]!.GetValue<string>(),
            "self-use capture must select the buff implementation by buff ID, not carrier ModItem presence");
    }

    private sealed class UnregisteredSourceBuff : ModBuff { }
    private sealed class StatusSourceItem : ModItem
    {
        public static int Calls;
        public override void OnHitNPC(Player player, NPC target, NPC.HitInfo hit, int damageDone)
        {
            target.AddBuff(BuffID.Poisoned, 321);
            if (hit.Crit) target.AddBuff(BuffID.Ichor, 45);
            target.AddBuff(ModContent.BuffType<UnregisteredSourceBuff>(), 67);
            Calls++;
            throw new InvalidOperationException("Source capture must never execute this hook.");
        }
    }
    private sealed class DynamicStatusSourceProjectile : ModProjectile
    {
        public override void OnHitNPC(NPC target, NPC.HitInfo hit, int damageDone)
            => target.AddBuff(BuffID.Poisoned, damageDone);
    }
    private sealed class ConditionalIdentitySource : ModProjectile
    {
        public override void OnHitNPC(NPC target, NPC.HitInfo hit, int damageDone)
        {
            int id = ModContent.BuffType<UnregisteredSourceBuff>();
            if (hit.Crit) id = BuffID.Ichor;
            target.AddBuff(id, 123);
        }
    }
}

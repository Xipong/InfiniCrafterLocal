using System;
using System.IO;
using System.Linq;
using System.Text.Json;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Runtime;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    private static void ComposableNpcEffectStrictRefusals()
    {
        var options = new JsonSerializerOptions { PropertyNameCaseInsensitive = true };
        string valid = JsonSerializer.Serialize(NpcEffectAction());
        void Refuse(string json)
        {
            bool refused = false;
            try { JsonSerializer.Deserialize<RuntimeEventActionSpec>(json, options)!.NormalizeAndValidate(); }
            catch (Exception error) when (error is InvalidDataException or JsonException or ArgumentException) { refused = true; }
            Equal(true, refused, "invalid NPC effect refuses rather than normalizing: " + json);
        }
        foreach (string effect in new[] { "null", "{}", "{\"Chance\":0.25}", "{\"LifeRegenPenalty\":401}",
            "{\"LifeRegenPenalty\":-1}", "{\"LifeRegenPenalty\":0.5}", "{\"DefenseDelta\":-101}",
            "{\"ContactDamageMultiplier\":0}", "{\"VelocityRetentionPerTick\":1.01}",
            "{\"ContactDamageMultiplier\":3.000000000001}", "{\"VelocityRetentionPerTick\":1.000000000001}",
            "{\"Chance\":1.01,\"LifeRegenPenalty\":3}", "{\"LifeRegenPenalty\":3,\"Unknown\":1}" })
        {
            var node = System.Text.Json.Nodes.JsonNode.Parse(valid)!;
            node["NpcEffect"] = System.Text.Json.Nodes.JsonNode.Parse(effect);
            Refuse(node.ToJsonString());
        }
        foreach (var mutation in new (string Field, object Value)[] { ("DurationTicks", 0), ("DurationTicks", 3601),
            ("DelayTicks", 601), ("Event", "periodic"), ("Event", "ON_HIT"), ("BuffId", 20),
            ("Strength", 1), ("EntityId", "other"), ("ActionCode", 2), ("Action", "apply_status_on_event") })
        {
            var node = System.Text.Json.Nodes.JsonNode.Parse(valid)!;
            node[mutation.Field] = JsonSerializer.SerializeToNode(mutation.Value);
            Refuse(node.ToJsonString());
        }
        foreach (string json in new[] { "{\"LifeRegenPenalty\":1}", "{\"DefenseDelta\":100}",
            "{\"ContactDamageMultiplier\":3}", "{\"VelocityRetentionPerTick\":0.1}" })
        {
            var effect = JsonSerializer.Deserialize<RuntimeNpcEffectSpec>(json)!; effect.Validate();
            Equal(1f, effect.Chance, "chance omission is neutral one");
        }
    }

    private static void ComposableNpcEffectLifecycleAndSync()
    {
        using var state = new NativeActorState();
        Terraria.Main.netMode = NetmodeID.Server; MaterialClock(100);
        var owner = Terraria.Main.player[0] = new Player { whoAmI = 0, active = true };
        var npc = Terraria.Main.npc[0] = new NPC { whoAmI = 0, active = true, life = 100 };
        var hook = new RuntimeHitNpcGeneration(); hook.OnSpawn(npc, owner.GetSource_Misc("check"));
        var entity = Entity(); var data = GeneratedItemData.Placeholder();
        var first = NpcEffectAction(duration: 10);
        Equal(true, RuntimeNpcEffects.Apply(data, entity, first, owner, npc), "first effect");
        MaterialClock(105); RuntimeNpcEffects.Apply(data, entity, first, owner, npc);
        Equal(1, RuntimeNpcEffects.GetTotals(npc).Count, "same source action refreshes without accumulating");
        Equal(3, RuntimeNpcEffects.GetTotals(npc).Regen, "refresh retains original magnitude");
        var second = NpcEffectAction(duration: 20); second.Id = "second";
        RuntimeNpcEffects.Apply(data, entity, second, owner, npc);
        Equal(6, RuntimeNpcEffects.GetTotals(npc).Regen, "independent actions combine");
        npc.netUpdate = false; npc.velocity = Vector2.One; hook.PostAI(npc);
        Equal(true, npc.netUpdate, "ongoing authoritative damping publishes changed NPC velocity");
        MaterialClock(115);
        Equal(1, RuntimeNpcEffects.GetTotals(npc).Count, "exact first expiry leaves second duration intact");
        using var snapshot = new MemoryStream(); hook.SendExtraAI(npc, null!, new BinaryWriter(snapshot));
        var peer = Terraria.Main.npc[0] = new NPC { whoAmI = 0, active = true, life = 100, defense = 20, damage = 30 };
        Terraria.Main.netMode = NetmodeID.MultiplayerClient; snapshot.Position = 0;
        hook.ReceiveExtraAI(peer, null!, new BinaryReader(snapshot));
        var hit = new NPC.HitModifiers(); hook.ModifyIncomingHit(peer, ref hit);
        Equal(-4f, hit.Defense.Flat, "remote combat consumes server-synchronized defense adjustment");
        var hurt = new Player.HurtModifiers(); hook.ModifyHitPlayer(peer, owner, ref hurt);
        Equal(.7f, hurt.SourceDamage.Multiplicative, "remote contact hit uses server-synchronized weakening");
        peer.velocity = Vector2.One; hook.PostAI(peer); int damage = 0; hook.UpdateLifeRegen(peer, ref damage);
        Equal(Vector2.One, peer.velocity, "peer does not run authoritative damping");
        Equal(0, peer.lifeRegen, "peer does not run authoritative DOT");
        MaterialClock(125); Equal(0, RuntimeNpcEffects.GetTotals(peer).Count, "remote entries expire without waiting for another packet");
        Terraria.Main.netMode = NetmodeID.Server;
        hook.OnSpawn(peer, owner.GetSource_Misc("reuse"));
        RuntimeNpcEffects.Apply(data, entity, first, owner, peer);
        hook.OnSpawn(peer, owner.GetSource_Misc("same-object-reuse"));
        Equal(0, RuntimeNpcEffects.GetTotals(peer).Count, "same-object spawn incarnation clears effects");
        RuntimeNpcEffects.Apply(data, entity, first, owner, peer); hook.OnKill(peer);
        Equal(0, RuntimeNpcEffects.GetTotals(peer).Count, "native death hook clears effects");
        for (int i = 0; i < RuntimeNpcEffects.MaxRecordsPerNpc; i++)
        {
            var action = NpcEffectAction(); action.Id = "effect_" + i;
            Equal(true, RuntimeNpcEffects.Apply(data, entity, action, owner, peer), "bounded distinct entry");
        }
        var overflow = NpcEffectAction(); overflow.Id = "overflow";
        Equal(false, RuntimeNpcEffects.Apply(data, entity, overflow, owner, peer), "cap refuses new record without evicting live effects");
        Equal(RuntimeNpcEffects.MaxRecordsPerNpc, RuntimeNpcEffects.GetTotals(peer).Count, "explicit record cap");
        RuntimeHitPullBridge.Clear();
        Equal(0, RuntimeNpcEffects.GetTotals(peer).Count, "world reset clears effects and generations together");
    }

    private static void ComposableNpcEffectChanceAdmissionAndNoReroll()
    {
        using var state = new NativeActorState();
        var entity = Entity(); entity.Id = "bolt"; entity.Kind = RuntimeEntityKind.FreeProjectile;
        var action = NpcEffectAction(chance: .25f); entity.Events = new[] { action };
        int rolls = 0;
        Equal((ushort)1, RuntimeHitPullBridge.SelectNpcEffectMask(entity, false, () => { rolls++; return .249999; }), "strict threshold admits below chance");
        Equal(1, rolls, "one draw per nontrivial chance");
        Equal((ushort)0, RuntimeHitPullBridge.SelectNpcEffectMask(entity, false, () => .25), "equal threshold misses");
        action.NpcEffect!.Chance = 0;
        Equal((ushort)0, RuntimeHitPullBridge.SelectNpcEffectMask(entity, false, () => throw new Exception("zero must not draw")), "zero never activates");
        action.NpcEffect.Chance = 1;
        Equal((ushort)1, RuntimeHitPullBridge.SelectNpcEffectMask(entity, false, () => throw new Exception("one must not draw")), "one always activates");
        action.Event = "on_crit";
        Equal((ushort)0, RuntimeHitPullBridge.SelectNpcEffectMask(entity, false, () => throw new Exception()), "noncritical hit cannot activate crit action");
        action.Event = "on_hit"; action.NpcEffect.Chance = .25f;
        var owner = Terraria.Main.player[0] = new Player { whoAmI = 0, active = true };
        var npc = Terraria.Main.npc[0] = new NPC { whoAmI = 0, active = true, life = 100 };
        var hook = new RuntimeHitNpcGeneration(); Terraria.Main.netMode = NetmodeID.Server;
        hook.OnSpawn(npc, owner.GetSource_Misc("check"));
        var data = GeneratedItemData.Placeholder(); data.Id = "chance_item"; data.RuntimeProgram.Entities = new[] { entity };
        GeneratedItemRegistryService.StampCurrentWorld(data);
        var projectile = Terraria.Main.projectile[0] = new Projectile { whoAmI = 0, owner = 0, identity = 91, active = true };
        var generated = Attach(projectile); typeof(Projectile).GetProperty("ModProjectile")!.SetValue(projectile, generated);
        generated.Configure(data, entity, 0, 0, Vector2.UnitX);
        int seed = 0;
        while (new Terraria.Utilities.UnifiedRandom(seed).NextDouble() >= .25) seed++;
        Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(seed);
        var expected = new Terraria.Utilities.UnifiedRandom(seed); expected.NextDouble();
        Terraria.Main.netMode = NetmodeID.MultiplayerClient; Terraria.Main.myPlayer = 0;
        using var receipt = new MemoryStream();
        RuntimeHitPullBridge.TryWriteProjectileReceipt(new BinaryWriter(receipt), projectile, npc, false);
        Equal(expected.NextDouble(), Terraria.Main.rand.NextDouble(), "sender rolls once before forwarding");
        Terraria.Main.netMode = NetmodeID.Server; receipt.Position = 0;
        Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(1337); expected = new Terraria.Utilities.UnifiedRandom(1337);
        RuntimeHitPullBridge.HandlePacket(new BinaryReader(receipt), 0);
        Equal(1, RuntimeNpcEffects.GetTotals(npc).Count, "received admitted action executes");
        Equal(expected.NextDouble(), Terraria.Main.rand.NextDouble(), "server does not reroll owner probability");
        // Actual SP hit callback has one admission owner; normal event loop must not
        // execute or roll a second copy after the bridge has already dispatched it.
        RuntimeNpcEffects.Clear(); Terraria.Main.netMode = NetmodeID.SinglePlayer;
        Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(seed); expected = new Terraria.Utilities.UnifiedRandom(seed); expected.NextDouble();
        generated.OnHitNPC(npc, new NPC.HitInfo(), 10);
        Equal(1, RuntimeNpcEffects.GetTotals(npc).Count, "actual SP hit callback executes numeric primitive");
        Equal(expected.NextDouble(), Terraria.Main.rand.NextDouble(), "SP callback rolls once, not bridge plus executor");
        RuntimeNpcEffects.Clear(); Terraria.Main.netMode = NetmodeID.MultiplayerClient; Terraria.Main.myPlayer = 1;
        Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(1337); expected = new Terraria.Utilities.UnifiedRandom(1337);
        generated.OnHitNPC(npc, new NPC.HitInfo(), 10);
        Equal(0, RuntimeNpcEffects.GetTotals(npc).Count, "remote callback never applies effect");
        Equal(expected.NextDouble(), Terraria.Main.rand.NextDouble(), "remote callback never draws effect RNG");
    }

    private static void ComposableNpcEffectItemReceiptAndDelayedFences()
    {
        using var state = new NativeActorState(); Terraria.Main.netMode = NetmodeID.Server; MaterialClock(100);
        var owner = Terraria.Main.player[0] = new Player { whoAmI = 0, active = true, selectedItem = 0 };
        var npc = Terraria.Main.npc[0] = new NPC { whoAmI = 0, active = true, life = 100 };
        var hook = new RuntimeHitNpcGeneration(); hook.OnSpawn(npc, owner.GetSource_Misc("check"));
        var entity = Entity(); entity.Id = "body"; entity.Kind = RuntimeEntityKind.ItemBody;
        var action = NpcEffectAction(delay: 2); entity.Events = new[] { action };
        var data = GeneratedItemData.Placeholder(); data.Id = "item_effect";
        data.RuntimeProgram.ItemEntityId = entity.Id; data.RuntimeProgram.Entities = new[] { entity };
        data.RuntimeProgram.Bindings = new[] { new RuntimeBindingSpec { Input = RuntimeInputKind.PrimaryUse,
            UsePolicy = new RuntimeBindingUsePolicySpec { ContactDamage = true } } };
        GeneratedItemRegistryService.StampCurrentWorld(data);
        var item = owner.inventory[0] = new Item { type = ItemID.CopperShortsword, stack = 1 };
        var generated = new GeneratedItem(); AttachItem(generated, item, data);
        RuntimeHitPullBridge.RememberItemActivation(owner);
        Terraria.Main.netMode = NetmodeID.MultiplayerClient; Terraria.Main.myPlayer = 0;
        using var receipt = new MemoryStream();
        Equal(true, RuntimeHitPullBridge.TryWriteItemReceipt(new BinaryWriter(receipt), owner, generated, npc, false), "item numeric effect uses existing activation snapshot receipt");
        Terraria.Main.netMode = NetmodeID.Server; receipt.Position = 0;
        RuntimeHitPullBridge.HandlePacket(new BinaryReader(receipt), 0);
        Equal(1, PendingActions(), "received item effect admitted to existing delayed queue");
        Equal(0, RuntimeNpcEffects.GetTotals(npc).Count, "delay does not apply early");
        MaterialClock(102); RuntimeDelayedActionScheduler.Update();
        Equal(1, RuntimeNpcEffects.GetTotals(npc).Count, "delayed receipt executes actual effect");
        RuntimeNpcEffects.Clear();
        Equal(true, RuntimeDelayedActionScheduler.TrySchedule(data, entity, action, owner,
            owner.GetSource_ItemUse(item), Vector2.Zero, Vector2.UnitX, npc, 0, 0, new RuntimeSpawnBudget(0)), "delayed target capture");
        hook.OnSpawn(npc, owner.GetSource_Misc("reuse")); MaterialClock(104); RuntimeDelayedActionScheduler.Update();
        Equal(0, RuntimeNpcEffects.GetTotals(npc).Count, "same-object NPC generation reuse refuses delayed effect");
        Equal(true, RuntimeDelayedActionScheduler.TrySchedule(data, entity, action, owner,
            owner.GetSource_ItemUse(item), Vector2.Zero, Vector2.UnitX, npc, 0, 0, new RuntimeSpawnBudget(0)), "delayed owner capture");
        Terraria.Main.player[0] = new Player { whoAmI = 0, active = true };
        MaterialClock(106); RuntimeDelayedActionScheduler.Update();
        Equal(0, RuntimeNpcEffects.GetTotals(npc).Count, "reused owner slot cannot inherit delayed action");
    }

    private static void ComposableNpcEffectTooltipUsesGeneratedSemantics()
    {
        var row = System.Text.Json.Nodes.JsonNode.Parse(File.ReadAllText(Path.Combine("tools", "fixtures", "played-secondaries-delivered.json")))!.AsArray()[0]!;
        WithForgePresentationLanguages(locale =>
        {
            var data = GeneratedItemData.FromJson(row.ToJsonString())!;
            var host = TooltipSecondaryHost(data); data = host.Data;
            var entity = data.RuntimeProgram.TryGetEntity(data.RuntimeProgram.PrimaryEntityId)!;
            entity.Events = new[] { NpcEffectAction(chance: .25f) };
            string before = JsonSerializer.Serialize(data);
            string text = string.Join("\n", TooltipSecondaryLines(host).Where(x => x.Name.StartsWith("InfiniSecondaryNpcEffect")).Select(x => x.Text));
            Equal(true, text.Contains("25%"), "effect chance is presented independently of magnitudes");
            Equal(true, text.Contains(locale == "en-US" ? "1.5 HP/s" : "1,5 ОЗ/с"), "native regeneration units shown as human HP/s");
            Equal(true, text.Contains(locale == "en-US" ? "post-AI" : "после ИИ"), "damping is not advertised as exact movement speed");
            Equal(false, text.Contains("Mods.InfiniCrafterLocal."), "generated effect tooltip localized");
            Equal(before, JsonSerializer.Serialize(data), "tooltip does not mutate accepted definition");
        });
    }

    private static void ComposableNpcEffectCompiledWireReplay()
    {
        // Canonical run has its own real strict-DTO roundtrip. Optional paths let
        // integration replay the actual Python compiler's final stripped delivery.
        var authored = GeneratedItemData.Placeholder();
        var body = authored.RuntimeProgram.Entities.Single();
        authored.RuntimeProgram.ItemUse.Configured = true;
        authored.Gameplay.Damage = 10;
        body.Events = new[] { NpcEffectAction() };
        authored.RuntimeProgram.Bindings = new[] { new RuntimeBindingSpec { Id = "use", Input = RuntimeInputKind.PrimaryUse,
            Role = RuntimeEntityRole.Primary, UsePolicy = new RuntimeBindingUsePolicySpec { ContactDamage = true,
                Action = new RuntimeBindingActionSpec { Kind = RuntimeBindingAction.UseItemBody, TargetId = body.Id } } } };
        string? path = Environment.GetEnvironmentVariable("INFINI_NPC_EFFECT_WIRE");
        GeneratedItemData data = GeneratedItemData.FromJson(path is null ? authored.ToJson() : File.ReadAllText(path))
            ?? throw new Exception("compiled NPC effect fixture refused by strict GeneratedItemData reader: " + ContractJsonDiagnostics.LastError);
        var selected = data.RuntimeProgram.Entities.SelectMany(entity => entity.Events.Select(action => (entity, action)))
            .First(row => row.action.ActionCode == RuntimeEventActionCode.ApplyNpcEffect);
        selected.action.NormalizeAndValidate();
        using var state = new NativeActorState(); Terraria.Main.netMode = NetmodeID.SinglePlayer;
        var owner = Terraria.Main.player[0] = new Player { whoAmI = 0, active = true };
        var npc = Terraria.Main.npc[0] = new NPC { whoAmI = 0, active = true, life = 100, defense = 20, damage = 30, velocity = new Vector2(10, 0) };
        var hook = new RuntimeHitNpcGeneration(); hook.OnSpawn(npc, owner.GetSource_Misc("compiled-wire"));
        RuntimeProgramExecutor.ExecuteAction(data, selected.entity, selected.action, owner, owner.GetSource_Misc("compiled-wire"),
            Vector2.Zero, Vector2.UnitX, npc, 10, 0, new RuntimeSpawnBudget(0));
        RuntimeNpcEffectSpec effect = selected.action.NpcEffect!;
        int damage = 0; hook.UpdateLifeRegen(npc, ref damage);
        Equal(-effect.LifeRegenPenalty, npc.lifeRegen, "compiled wire native DOT consumer");
        var hit = new NPC.HitModifiers(); hook.ModifyIncomingHit(npc, ref hit);
        Equal((float)effect.DefenseDelta, hit.Defense.Flat, "compiled wire native defense consumer");
        var hurt = new Player.HurtModifiers(); hook.ModifyHitPlayer(npc, owner, ref hurt);
        Equal(effect.ContactDamageMultiplier, hurt.SourceDamage.Multiplicative, "compiled wire native contact consumer");
        hook.PostAI(npc); Equal(10 * effect.VelocityRetentionPerTick, npc.velocity.X, "compiled wire native post AI damping");
    }
}

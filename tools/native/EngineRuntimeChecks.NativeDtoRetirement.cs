#nullable enable
// Check-only: compiles against baseline DTOs; no references to retired members.
// Linked-source CPU/native API-boundary observers, not game/audio/network execution.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.Runtime;
using InfiniCrafterLocal.Common.VFX;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using MonoMod.RuntimeDetour;
using Terraria;
using Terraria.Audio;
using Terraria.DataStructures;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    private static void NDTO05RetiredKnowledgeAndSummaryRefuse()
    {
        var source = GeneratedItemData.Placeholder();
        source.GeneratedParentSummary.Description = "Optional Author description";
        source.GeneratedParentSummary.PlayerExperience = "Advisory player experience";
        foreach (string json in new[] { source.ToJson(), source.ToNetworkJson() })
        {
            var current = JsonNode.Parse(json)!;
            foreach (string field in new[] { "itemKnowledge", "canonical", "sourceRepresentation", "inheritance", "lossBudget" })
                Equal(false, current.AsObject().ContainsKey(field), "no dead classifier payload is emitted: " + field);
            var summary = current["generatedParentSummary"]!.AsObject();
            foreach (string key in new[] { "notableEffects", "runtimePrimaryEntityId", "runtimeEntityIds" })
                Equal(false, summary.ContainsKey(key), "no dead recursive summary field is emitted: " + key);
            var accepted = GeneratedItemData.FromJson(json)
                ?? throw new InvalidOperationException("current advisory summary rejected");
            Equal(source.GeneratedParentSummary.Description, accepted.GeneratedParentSummary.Description, "optional description retained");
            Equal(source.GeneratedParentSummary.PlayerExperience, accepted.GeneratedParentSummary.PlayerExperience, "optional experience retained");
        }
        foreach (string field in new[] { "itemKnowledge", "canonical", "sourceRepresentation", "inheritance", "lossBudget" }) {
            var retired = JsonNode.Parse(source.ToJson())!;
            retired[field] = field is "sourceRepresentation" or "inheritance" ? new JsonArray() : new JsonObject();
            Equal(true, GeneratedItemData.FromJson(retired.ToJsonString()) is null, "retired root classifier refuses, never hides in extension data: " + field);
        }
        foreach (string field in new[] { "objectType", "style", "requiredAnchors", "dominantColorHex", "accentColorHex", "semanticReviewStatus" }) {
            var retired = JsonNode.Parse(source.ToJson())!;
            retired["visual"]![field] = field == "requiredAnchors" ? new JsonArray() : JsonValue.Create("unused");
            Equal(true, GeneratedItemData.FromJson(retired.ToJsonString()) is null, "retired visual metadata refuses: " + field);
        }
        foreach (string field in new[] { "stage", "powerBudget" }) {
            var retired=JsonNode.Parse(source.ToJson())!;
            Equal(false,retired["gameplay"]!.AsObject().ContainsKey(field),"no inert gameplay metadata serialized: "+field);
            retired["gameplay"]![field]=field=="stage"?JsonValue.Create("early"):JsonValue.Create(1);
            Equal(true,GeneratedItemData.FromJson(retired.ToJsonString()) is null,"inert gameplay metadata is refused: "+field);
        }
        var sidecars = JsonNode.Parse(source.ToJson())!;
        foreach (string field in new[] { "concept", "realization", "llmStageAccounting", "contractVersions", "recipeHealth" })
            sidecars[field] = new JsonObject { ["advisory"] = field, ["explicitZero"] = 0, ["unknownNestedProse"] = "read only" };
        var currentSidecars = GeneratedItemData.FromJson(sidecars.ToJsonString()) ?? throw new InvalidOperationException("current sidecars refused");
        var local = JsonNode.Parse(currentSidecars.ToJson())!;
        var network = JsonNode.Parse(currentSidecars.ToNetworkJson())!;
        foreach (string field in new[] { "concept", "realization", "llmStageAccounting", "contractVersions", "recipeHealth" }) {
            Equal(sidecars[field]!.ToJsonString(), local[field]!.ToJsonString(), "current sidecar retained locally: " + field);
            Equal(false, network.AsObject().ContainsKey(field), "advisory sidecar omitted from native network definition: " + field);
        }
        foreach (string unknown in new[] { "futureGameplay", "runtimeContract", "visualKit", "stageAccounting" }) {
            var invalid = JsonNode.Parse(source.ToJson())!; invalid[unknown] = new JsonObject();
            Equal(true, GeneratedItemData.FromJson(invalid.ToJsonString()) is null, "unknown root field is refused: " + unknown);
        }
        JsonNode wire;
        foreach (var field in new (string Key, string Literal)[] {
            ("notableEffects", "[]"), ("runtimePrimaryEntityId", "\"unavailable_item\""), ("runtimeEntityIds", "[]"),
        })
        {
            wire = JsonNode.Parse(source.ToJson())!;
            wire["generatedParentSummary"]![field.Key] = JsonNode.Parse(field.Literal);
            Equal(true, GeneratedItemData.FromJson(wire.ToJsonString()) is null, "retired recursive summary refuses: " + field.Key);
        }
    }

    // Match current Python delivery: it never emits these old default members.
    // This makes baseline/candidate tests share the SAME literal current input.
    private static JsonNode NativeDtoCurrentWire(GeneratedItemData data)
    {
        var root = JsonNode.Parse(data.ToNetworkJson())!;
        root["gameplay"]!.AsObject().Remove("buffCode");
        root["gameplay"]!.AsObject().Remove("buffTime");
        foreach (JsonNode? entity in root["runtimeProgram"]!["entities"]!.AsArray())
            foreach (string component in new[] { "controller", "movement" })
                if (entity?[component]?["params"] is JsonObject bag)
                    foreach (string key in new[] { "shotEntity", "intervalTicks", "sameTargetBias" }) bag.Remove(key);
        return root;
    }

    private static InfiniCraftPlayer NativeDtoBindPlayer(Player player)
    {
        var generated = new InfiniCraftPlayer();
        typeof(Terraria.ModLoader.ModType<Player>).GetProperty("Entity", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)!
            .SetValue(generated, player);
        typeof(Player).GetField("modPlayers", BindingFlags.Instance | BindingFlags.NonPublic)!
            .SetValue(player, new Terraria.ModLoader.ModPlayer[] { generated });
        return generated;
    }

    private static GeneratedItemData NativeDtoRead(GeneratedItemData data)
        => GeneratedItemData.FromJson(NativeDtoCurrentWire(data).ToJsonString())
            ?? throw new InvalidOperationException("current native DTO input rejected");

    private static void NDTO01RetiredControllerBagRefusesAndTypedCadenceExecutes()
    {
        var current = NativeDtoCurrentWire(SentryTargetingFixture());
        foreach (var field in new (string Key, string Literal)[] {
            ("shotEntity", "\"shot\""), ("shotEntity", "\"\""),
            ("intervalTicks", "90"), ("intervalTicks", "0"),
            ("sameTargetBias", "0.5"), ("sameTargetBias", "0"),
        }) {
            var old = current.DeepClone();
            var entity = old["runtimeProgram"]!["entities"]!.AsArray().Single(x => (string?)x!["id"] == "root")!;
            entity["controller"]!["params"]![field.Key] = JsonNode.Parse(field.Literal);
            Equal(true, GeneratedItemData.FromJson(old.ToJsonString()) is null, "retired controller bag refuses " + field.Key + "=" + field.Literal);
        }
        var missingInterval = current.DeepClone();
        var missingRoot = missingInterval["runtimeProgram"]!["entities"]!.AsArray().Single(x => (string?)x!["id"] == "root")!;
        missingRoot["targeting"]!.AsObject().Remove("intervalTicks");
        Equal(true, GeneratedItemData.FromJson(missingInterval.ToJsonString()) is null, "executable controller cannot invent missing typed interval");
        missingRoot["targeting"]!["intervalTicks"] = 0;
        Equal(true, GeneratedItemData.FromJson(missingInterval.ToJsonString()) is null, "zero typed interval cannot become implicit six-tick attack");

        using var state = new SentryTargetScope();
        state.Target(0, 100f);
        int attempts = 0;
        using var native = new Hook(NativeProjectileEntry(),
            (Func<IEntitySource, Vector2, Vector2, int, int, float, int, float, float, float, Projectile>)
            ((source, position, velocity, type, damage, knockback, owner, ai0, ai1, ai2) => {
                attempts++; return new Projectile(); // observe API, not a successful world spawn
            }));
        MethodInfo fire = typeof(GeneratedProjectile).GetMethod("ApplyTargetAndFire", SentryPrivate)!;
        foreach (int interval in new[] { 1, 12 })
        foreach (int extraUpdates in new[] { 0, 2 }) {
            var source = SentryTargetingFixture(); var authored = source.RuntimeProgram.TryGetEntity("root")!;
            authored.Targeting.IntervalTicks = interval; authored.Targeting.Count = 1;
            authored.Targeting.RequireLineOfSight = false; authored.Collision.ExtraUpdates = extraUpdates;
            var data = NativeDtoRead(source); var entity = data.RuntimeProgram.TryGetEntity("root")!;
            Equal(interval, entity.Targeting.IntervalTicks, "typed interval survives current reader");
            Equal("shot", entity.Targeting.ShotEntityId, "typed child selection survives current reader");
            Equal(0.9f, entity.Targeting.SameTargetBias, "typed bias survives current reader");
            var projectile = new Projectile { owner = 0, active = true };
            var generated = Attach(projectile); var budget = new RuntimeSpawnBudget(12);
            generated.Configure(data, entity, 0, 12, Vector2.UnitX, activationBudget: budget);
            projectile.Center = new Vector2(1600f, 1600f);
            int due = Math.Max(6, interval) * (extraUpdates + 1);
            attempts = 0;
            for (int update = 1; update < due; update++) fire.Invoke(generated, null);
            Equal(0, attempts, "typed cadence waits exact world-tick/update conversion");
            fire.Invoke(generated, null);
            Equal(1, attempts, "typed cadence fires exactly once at due update");
            Equal(12, budget.Remaining, "unregistered native result does not consume reservation");
            entity.Targeting.IntervalTicks = 0; attempts = 0;
            for (int update = 0; update <= due; update++) fire.Invoke(generated, null);
            Equal(0, attempts, "bypassed DTO validation still cannot invent zero-interval firing");
        }
    }

    private static void NDTO02SingleBuffRefusesAndCurrentExtraBuffsExecute()
    {
        var source = MobilityConsumptionFixture("", 0);
        source.Gameplay.ExtraBuffs = new[] { new BuffEntrySpec { BuffCode = BuffID.Ironskin, BuffTime = 60 } };
        var current = NativeDtoCurrentWire(source);
        foreach (var field in new (string Key, int Value)[] { ("buffCode", BuffID.Ironskin), ("buffCode", 0), ("buffTime", 60), ("buffTime", 0) }) {
            var old = current.DeepClone(); old["gameplay"]![field.Key] = field.Value;
            Equal(true, GeneratedItemData.FromJson(old.ToJsonString()) is null, "retired single native buff refuses " + field.Key + "=" + field.Value);
        }
        foreach (bool named in new[] { false, true }) {
            var bad = NativeDtoCurrentWire(named ? NamedItemEffectsFixture() : source);
            JsonNode effects = named ? bad["runtimeProgram"]!["effectGroups"]![0]! : bad["gameplay"]!;
            effects["extraBuffs"] = new JsonArray(new JsonObject { ["buffCode"] = int.MaxValue, ["buffTime"] = 60 });
            Equal(true, GeneratedItemData.FromJson(bad.ToJsonString()) is null, "current ExtraBuffs retains loaded-ID refusal named=" + named);
        }
        using var scope = new MobilityConsumptionNativeScope();
        foreach (string lane in new[] { "default", "primary", "alternate" })
            WithPlayer((player, generated) => {
                PrepareMobilityConsumptionPlayer(player);
                var data = lane == "default" ? MobilityConsumptionFixture("", 0) : NamedItemEffectsFixture();
                data.Gameplay.ExtraBuffs = new[] { new BuffEntrySpec { BuffCode = BuffID.Ironskin, BuffTime = 60 } };
                if (lane != "default") {
                    data.RuntimeProgram.EffectGroups![0].ExtraBuffs = new[] { new BuffEntrySpec { BuffCode = BuffID.Swiftness, BuffTime = 60 } };
                    data.RuntimeProgram.EffectGroups![1].ExtraBuffs = new[] { new BuffEntrySpec { BuffCode = BuffID.Regeneration, BuffTime = 90 } };
                }
                data = NativeDtoRead(data);
                var host = MobilityConsumptionHost(data); player.inventory[0] = host.Item;
                player.altFunctionUse = lane == "alternate" ? 2 : 0;
                // A reused native item may have carried an unrelated buff slot.
                host.Item.buffType = BuffID.Poisoned; host.Item.buffTime = 123;
                Equal(true, host.CanUseItem(player), lane + " current native admission");
                Equal(0, host.Item.buffType, lane + " native stale buff type is cleared");
                Equal(0, host.Item.buffTime, lane + " native stale buff time is cleared");
                scope.RunNativeSuffix(player);
                Equal(lane == "default", player.HasBuff(BuffID.Ironskin), lane + " default buff ownership");
                Equal(lane == "primary", player.HasBuff(BuffID.Swiftness), lane + " primary buff ownership");
                Equal(lane == "alternate", player.HasBuff(BuffID.Regeneration), lane + " alternate buff ownership");
                Equal(false, player.HasBuff(BuffID.Poisoned), lane + " removed slot cannot leak native effect");
                Equal(lane == "primary" ? 77 : 57, player.statLife, lane + " native healing remains current");
                Equal(lane == "alternate" ? 55 : 20, player.statMana, lane + " native mana remains current");
                Equal(1, host.UseCalls, lane + " one native use dispatch");
            });
    }

    private static void NDTO03OldSoundAbsenceRefusesBeforeAudioConsumers()
    {
        using var actors = new NativeActorState();
        WithLighting((config, lights) => {
            int calls = 0;
            ReLogic.Utilities.SlotId Observe(in SoundStyle style, Vector2? position, SoundUpdateCallback? callback) {
                calls++; return ReLogic.Utilities.SlotId.Invalid;
            }
            SoundSelectionBoundary observer = Observe;
            using var hook = new Hook(typeof(SoundEngine).GetMethod("PlaySound", new[] {
                typeof(SoundStyle).MakeByRefType(), typeof(Vector2?), typeof(SoundUpdateCallback) })!, observer);
            var data = GeneratedItemData.Placeholder();
            string item = data.RuntimeProgram.ItemEntityId;
            var owner = Terraria.Main.player[0] = new Player { whoAmI = 0, active = true, Center = new Vector2(160) };
            Terraria.Main.netMode = NetmodeID.SinglePlayer; Terraria.Main.myPlayer = 0; Terraria.Main.dedServ = false;
            var projectile = new Projectile { active = true, owner = 0, Center = new Vector2(240), velocity = Vector2.UnitX };
            foreach (string absent in new[] { "selector", "controls", "both" }) {
                var slot = SoundSelectionSlot(item, RuntimeEventKind.OnUse);
                slot.SoundId = "Item1"; slot.Sound = new VfxSoundSpec { Volume = 0.4f, Pitch = 0.2f, PitchVariance = 0 };
                slot.NormalizeAndValidate();
                string currentJson = new VfxManifestSpec { Slots = new[] { slot } }.ToJson();
                Equal(1, VfxManifestSpec.FromJson(currentJson).Slots.Length, "explicit current sound reader positive control");
                var root = JsonNode.Parse(currentJson)!;
                var row = root["slots"]![0]!.AsObject();
                if (absent is "selector" or "both") row.Remove("soundId");
                if (absent is "controls" or "both") row.Remove("sound");
                data.VfxManifest = VfxManifestSpec.FromJson(root.ToJsonString());
                Equal(0, data.VfxManifest.Slots.Length, "retired sound " + absent + " refuses real manifest reader");
                var full = NativeDtoCurrentWire(GeneratedItemData.Placeholder());
                full["vfxManifest"] = root.DeepClone();
                Equal(true, GeneratedItemData.FromJson(full.ToJsonString()) is null,
                    "full generated definition also refuses retired sound " + absent);
                var state = new InfiniVfxState(); calls = 0;
                InfiniItemVfxRuntime.ClearUseEventCaches();
                InfiniItemVfxRuntime.EmitAndSyncEvent(owner, data, item, RuntimeEventKind.OnUse);
                InfiniVfxRuntime.OnEvent(projectile, data, item, RuntimeEventKind.OnUse, data.VfxManifest, ref state, projectile.Center);
                InfiniVfxRuntime.OnDetachedEvent(data, item, RuntimeEventKind.OnUse, data.VfxManifest, projectile.Center, projectile.velocity, "retired_sound", InfiniVfxProjectileSnapshot.Capture(projectile,data,item));
                Equal(0, calls, "refused old sound never reaches item/projectile/detached audio API");
                // The playback projection itself is strict even when DTO reading is bypassed.
                if (absent is "selector" or "both") slot = new VfxSlotSpec { Sound = slot.Sound };
                else slot = new VfxSlotSpec { SoundId = "Item1" };
                bool refused = false;
                try { slot.ResolveSoundStyle(); } catch (InvalidDataException) { refused = true; }
                Equal(true, refused, "missing playback choices refuse instead of alpha/phase or Item1 fallback");
            }
            new InfiniDetachedVfxSystem().OnWorldUnload(); InfiniItemVfxRuntime.ClearUseEventCaches();
        });
    }

    private static void NDTO04CurrentUtilitySnapshotAndCopyMirrorRemainSupported()
    {
        using var actors = new NativeActorState();
        WithPlayer((player, generated) => {
            player.active = true;
            Terraria.Main.netMode = NetmodeID.SinglePlayer;
            generated.ApplyGeneratedUtilityBuff(new GeneratedBuffSpec { DurationTicks = 4, MovementSpeed = .5f });
            var receiverPlayer = new Player { whoAmI = 1, active = true };
            var receiver = NativeDtoBindPlayer(receiverPlayer);
            var writer = typeof(InfiniCraftPlayer).GetMethod("WriteGeneratedBuffState", MobilityConsumptionFlags)!;
            var reader = typeof(InfiniCraftPlayer).GetMethod("ReadGeneratedBuffState", MobilityConsumptionFlags)!;
            var tick = typeof(InfiniCraftPlayer).GetMethod("TickGeneratedUtilityBuff", MobilityConsumptionFlags)!;
            var ticks = typeof(InfiniCraftPlayer).GetField("_generatedBuffTicks", MobilityConsumptionFlags)!;
            var entries = typeof(InfiniCraftPlayer).GetField("_activeGeneratedUtilityBuffs", MobilityConsumptionFlags)!;
            using var stream = new MemoryStream();
            using (var binary = new BinaryWriter(stream, System.Text.Encoding.UTF8, true)) writer.Invoke(generated, new object[] { binary });
            stream.Position = 0;
            using (var binary = new BinaryReader(stream, System.Text.Encoding.UTF8, true)) {
                Equal((byte)player.whoAmI, binary.ReadByte(), "current snapshot exact owner");
                reader.Invoke(receiver, new object[] { binary });
                Equal(stream.Length, stream.Position, "current v5 entries and exhaustion fully consumed");
            }
            Equal(1, ((System.Collections.ICollection)entries.GetValue(receiver)!).Count, "current snapshot has exact entries");
            Terraria.Main.netMode = NetmodeID.MultiplayerClient; Terraria.Main.myPlayer = 0;
            tick.Invoke(receiver, null);
            Equal(3, (int)ticks.GetValue(receiver)!, "current remote exact-entry countdown remains supported");
            var mirror = NativeDtoBindPlayer(receiverPlayer);
            receiver.CopyClientState(mirror);
            Equal(0, ((System.Collections.ICollection)entries.GetValue(mirror)!).Count, "current CopyClientState is aggregate-only mirror");
            Equal(3, (int)ticks.GetValue(mirror)!, "current mirror contains positive aggregate without entries");
            tick.Invoke(mirror, null);
            Equal(2, (int)ticks.GetValue(mirror)!, "retained aggregate fallback supports current copied remote mirror");
        });
    }
}

#nullable enable
// Private candidate: parent owns canonical registration, compilation and execution.
// Real DTO -> item/projectile consumers -> native SoundEngine API boundary only.
// No audio device, game/world loop, sockets, GPU or artistic acceptance.
using System;
using System.Collections.Generic;
using System.Reflection;
using System.Text.Json;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.VFX;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.Audio;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    // Independent oracle: exact installed members, NOT the production resolver.
    private static (string Id, SoundStyle Style)[] SoundSelectionPalette() => new[] {
        ("Item1", SoundID.Item1), ("Item2", SoundID.Item2), ("Item3", SoundID.Item3), ("Item4", SoundID.Item4),
        ("Item8", SoundID.Item8), ("Item9", SoundID.Item9), ("Item14", SoundID.Item14), ("Item20", SoundID.Item20),
        ("Item21", SoundID.Item21), ("Item29", SoundID.Item29), ("Item43", SoundID.Item43), ("Dig", SoundID.Dig),
        ("Tink", SoundID.Tink), ("Grab", SoundID.Grab), ("Shatter", SoundID.Shatter), ("Splash", SoundID.Splash),
        ("Coins", SoundID.Coins), ("Unlock", SoundID.Unlock), ("MaxMana", SoundID.MaxMana), ("ResearchComplete", SoundID.ResearchComplete),
    };

    private static VfxSlotSpec SoundSelectionSlot(string entity, string eventName) => new() {
        Id = "exact_sound", EntityId = entity, Event = eventName, RendererKind = "soundCue",
        Channel = "sound", Lane = "cue", TextureRole = "none", ParticleRole = "none",
        ParticleSystemId = "none", EmissionMode = "none", Anchor = "self", RepeatEvery = 1, SlotSeed = 0,
    };

    // Deliberately baseline-compilable: no direct reference to the new DTO member.
    private static string SoundSelectionJson(string? selector, bool present = true, string renderer = "soundCue", bool frozenRepair = false)
    {
        var slot = SoundSelectionSlot("item", RuntimeEventKind.OnUse);
        slot.RendererKind = renderer;
        if (renderer == "lightCue") slot.Channel = "light";
        if (renderer == "impactRing") { slot.Channel = "impactShape"; slot.Lane = "primary"; }
        string json = new VfxManifestSpec { Slots = new[] { slot } }.ToJson();
        Equal(true, json.Length > 0, "legacy fixture serialization succeeds");
        var node = JsonNode.Parse(json)!.AsObject();
        var row = node["Slots"]![0]!.AsObject();
        row.Remove("SoundId"); // make literal absent/present distinction explicit
        if (present) row["soundId"] = selector;
        if (frozenRepair) row["frozenRepair"] = new JsonObject { ["soundId"] = "Item4" };
        return node.ToJsonString();
    }

    private static VfxManifestSpec SoundSelectionRead(string? selector, bool present = true)
    {
        var parsed = VfxManifestSpec.FromJson(SoundSelectionJson(selector, present));
        Equal(1, parsed.Slots.Length, $"soundId={selector ?? "<legacy absent>"} survives actual FromJson");
        return parsed;
    }

    private static void VfxSoundSelectorStrictDtoRoundTrips()
    {
        var legacy = SoundSelectionRead(null, present: false);
        Equal(false, legacy.ToJson().Contains("SoundId", StringComparison.OrdinalIgnoreCase), "legacy canonical serialization stays absent");
        Equal(false, JsonSerializer.Serialize(legacy).Contains("SoundId", StringComparison.OrdinalIgnoreCase), "alternate serializer does not invent explicit null");
        foreach (var sample in SoundSelectionPalette()) {
            var parsed = SoundSelectionRead(sample.Id);
            var round = VfxManifestSpec.FromJson(parsed.ToJson());
            Equal(1, round.Slots.Length, "explicit sample round trip");
            var property = typeof(VfxSlotSpec).GetProperty("SoundId") ?? throw new InvalidOperationException("missing finite SoundId DTO member");
            Equal(sample.Id, (string)property.GetValue(round.Slots[0])!, "literal selector preserved");
        }
        foreach (string? bad in new string?[] { null, "", "item4", " Item4", "Item9999", "frozenRepair", "Terraria/Sounds/Item_4" })
            Equal(0, VfxManifestSpec.FromJson(SoundSelectionJson(bad)).Slots.Length, "invalid present selector rejected without Item1 substitution");
        foreach (string renderer in new[] { "lightCue", "impactRing" })
            Equal(0, VfxManifestSpec.FromJson(SoundSelectionJson("Item4", renderer: renderer)).Slots.Length, "sound selector forbidden on foreign branch");
        Equal(0, VfxManifestSpec.FromJson(SoundSelectionJson("Item4", frozenRepair: true)).Slots.Length, "foreign frozenRepair field rejected");
        foreach (string literal in new[] { "4", "true", "{}", "[]" }) {
            string invalid = SoundSelectionJson("typed_probe").Replace("\"typed_probe\"", literal, StringComparison.Ordinal);
            Equal(0, VfxManifestSpec.FromJson(invalid).Slots.Length, "invalid soundId JSON type rejected");
        }
    }

    private delegate ReLogic.Utilities.SlotId SoundSelectionBoundary(in SoundStyle style, Vector2? position, SoundUpdateCallback? callback);

    private static void VfxSoundSelectorReachesItemAndProjectileNativeBoundary()
    {
        WithLighting((config, lights) => {
            var oldPlayer = Terraria.Main.player[0];
            int oldLocal = Terraria.Main.myPlayer;
            var system = new InfiniDetachedVfxSystem();
            int calls = 0;
            SoundStyle observed = default;
            Vector2? location = null;
            ReLogic.Utilities.SlotId ObserveSound(in SoundStyle style, Vector2? position, SoundUpdateCallback? callback) {
                calls++; observed = style; location = position;
                return ReLogic.Utilities.SlotId.Invalid; // terminate precisely at API; never initialize audio
            }
            SoundSelectionBoundary observer = ObserveSound;
            var play = typeof(SoundEngine).GetMethod("PlaySound", new[] {
                typeof(SoundStyle).MakeByRefType(), typeof(Vector2?), typeof(SoundUpdateCallback) })!;
            using var hook = new MonoMod.RuntimeDetour.Hook(play, observer);
            try {
                var owner = Terraria.Main.player[0] = new Player { whoAmI = 0, active = true, Center = new Vector2(160, 160) };
                Terraria.Main.myPlayer = 0;
                var samples = new List<(string? Id, SoundStyle Style)> { (null, SoundID.Item1) };
                foreach (var sample in SoundSelectionPalette()) samples.Add((sample.Id, sample.Style));
                foreach (var sample in samples)
                foreach (string route in new[] { "item_event", "item_periodic", "projectile_event", "projectile_periodic", "detached" })
                foreach (float alpha in new[] { 0f, 0.4f, 1f })
                foreach (float phase in new[] { -1f, 0f, 1f }) {
                    system.OnWorldUnload(); InfiniItemVfxRuntime.ClearUseEventCaches();
                    var data = GeneratedItemData.Placeholder();
                    data.VfxManifest = SoundSelectionRead(sample.Id, sample.Id is not null);
                    var entity = new RuntimeEntitySpec { Id = "sound_projectile", Kind = RuntimeEntityKind.FreeProjectile };
                    var item = data.RuntimeProgram.Entities[0];
                    data.RuntimeProgram.Entities = new[] { item, entity };
                    var slot = data.VfxManifest.Slots[0];
                    bool isItem = route.StartsWith("item", StringComparison.Ordinal);
                    slot.EntityId = isItem ? data.RuntimeProgram.ItemEntityId : entity.Id;
                    slot.Event = route.EndsWith("periodic", StringComparison.Ordinal) ? RuntimeEventKind.Periodic : isItem ? RuntimeEventKind.OnUse : RuntimeEventKind.OnSpawn;
                    slot.Alpha = alpha; slot.PhaseOffset = phase;
                    data.VfxManifest.NormalizeAndValidate();
                    string serialized = data.VfxManifest.ToJson();
                    var projectile = new Projectile { active = true, owner = 0, damage = 37, width = 16, height = 16,
                        Center = new Vector2(240, 160), velocity = Vector2.UnitX, scale = 1f, spriteDirection = 1 };
                    var state = new InfiniVfxState();
                    Vector2 expectedPosition = isItem ? owner.Center : projectile.Center;
                    calls = 0; location = null;
                    if (route == "item_event") InfiniItemVfxRuntime.EmitAndSyncEvent(owner, data, slot.EntityId, slot.Event);
                    else if (route == "item_periodic") InfiniItemVfxRuntime.OnPeriodic(owner, data, slot.EntityId);
                    else if (route == "projectile_event") InfiniVfxRuntime.OnEvent(projectile, data, slot.EntityId, slot.Event, data.VfxManifest, ref state, projectile.Center);
                    else if (route == "projectile_periodic") InfiniVfxRuntime.OnTick(projectile, data, slot.EntityId, data.VfxManifest, ref state);
                    else InfiniVfxRuntime.OnDetachedEvent(data, slot.EntityId, slot.Event, data.VfxManifest, projectile.Center, projectile.velocity, "sound_probe");
                    string label = $"{route}/{sample.Id ?? "legacy"}/alpha={alpha}/phase={phase}";
                    Equal(1, calls, label + " exact API call count");
                    Equal(sample.Style.SoundPath, observed.SoundPath, label + " exact native path");
                    Equal(true, sample.Style.Variants.SequenceEqual(observed.Variants), label + " variants preserve native constant");
                    Equal(sample.Style.PitchVariance, observed.PitchVariance, label + " native variance preserved");
                    Equal(true, sample.Style.VariantsWeights.SequenceEqual(observed.VariantsWeights), label + " native variant weights preserved");
                    Equal(sample.Style.Identifier ?? "", observed.Identifier ?? "", label + " native sharing identifier preserved");
                    Equal(sample.Style.LimitsArePerVariant, observed.LimitsArePerVariant, label + " native per-variant policy preserved");
                    Equal(sample.Style.IsLooped, observed.IsLooped, label + " native nonlooping style preserved");
                    Equal((int)sample.Style.Type, (int)observed.Type, label + " native sound type preserved");
                    Equal(sample.Style.MaxInstances, observed.MaxInstances, label + " native instance cap preserved");
                    Equal((int)sample.Style.SoundLimitBehavior, (int)observed.SoundLimitBehavior, label + " native cap policy preserved");
                    Equal(Math.Clamp(alpha, 0.05f, 1f), observed.Volume, label + " existing alpha-volume clamp preserved");
                    Equal(Math.Clamp(phase * 0.25f, -0.5f, 0.5f), observed.Pitch, label + " existing authored phase-to-pitch preserved");
                    Equal(expectedPosition, location!.Value, label + " exact world position");
                    Equal(serialized, data.VfxManifest.ToJson(), label + " no authored mutation");
                    Equal(37, projectile.damage, label + " no damage mutation");
                    Equal(Vector2.UnitX, projectile.velocity, label + " no movement mutation");
                }
            }
            finally {
                system.OnWorldUnload(); InfiniItemVfxRuntime.ClearUseEventCaches();
                Terraria.Main.player[0] = oldPlayer; Terraria.Main.myPlayer = oldLocal;
            }
        });
    }

    private static void VfxSoundSelectorPreservesSilentAndServerControls()
    {
        WithLighting((config, lights) => {
            int calls = 0;
            ReLogic.Utilities.SlotId ObserveSound(in SoundStyle style, Vector2? position, SoundUpdateCallback? callback) {
                calls++; return ReLogic.Utilities.SlotId.Invalid;
            }
            SoundSelectionBoundary observer = ObserveSound;
            var play = typeof(SoundEngine).GetMethod("PlaySound", new[] {
                typeof(SoundStyle).MakeByRefType(), typeof(Vector2?), typeof(SoundUpdateCallback) })!;
            using var hook = new MonoMod.RuntimeDetour.Hook(play, observer);
            var data = GeneratedItemData.Placeholder();
            string item = data.RuntimeProgram.ItemEntityId;
            var owner = new Player { active = true, Center = new Vector2(160) };
            var projectile = new Projectile { active = true, owner = -1, Center = new Vector2(160), velocity = Vector2.UnitX };
            var system = new InfiniDetachedVfxSystem();
            try {
                foreach (bool server in new[] { false, true }) {
                    Terraria.Main.dedServ = server;
                    data.VfxManifest = server ? SoundSelectionRead("Item4") : VfxManifestSpec.Empty();
                    if (server) data.VfxManifest.Slots[0].EntityId = item;
                    var state = new InfiniVfxState();
                    InfiniItemVfxRuntime.EmitAndSyncEvent(owner, data, item, RuntimeEventKind.OnUse);
                    InfiniVfxRuntime.OnEvent(projectile, data, item, RuntimeEventKind.OnUse, data.VfxManifest, ref state, projectile.Center);
                    InfiniVfxRuntime.OnDetachedEvent(data, item, RuntimeEventKind.OnUse, data.VfxManifest, projectile.Center, projectile.velocity, "silent_probe");
                    Equal(0, calls, server ? "dedicated server never reaches audio" : "empty slots retain deliberate silence");
                }
            }
            finally { system.OnWorldUnload(); InfiniItemVfxRuntime.ClearUseEventCaches(); }
        });
    }
}

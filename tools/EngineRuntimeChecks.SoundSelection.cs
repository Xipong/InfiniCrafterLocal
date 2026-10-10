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
        ("Item5", SoundID.Item5), ("Item7", SoundID.Item7), ("Item8", SoundID.Item8), ("Item9", SoundID.Item9),
        ("Item10", SoundID.Item10), ("Item11", SoundID.Item11), ("Item12", SoundID.Item12), ("Item13", SoundID.Item13),
        ("Item14", SoundID.Item14), ("Item15", SoundID.Item15), ("Item17", SoundID.Item17), ("Item20", SoundID.Item20),
        ("Item21", SoundID.Item21), ("Item26", SoundID.Item26), ("Item28", SoundID.Item28), ("Item29", SoundID.Item29),
        ("Item31", SoundID.Item31), ("Item33", SoundID.Item33), ("Item34", SoundID.Item34), ("Item36", SoundID.Item36),
        ("Item37", SoundID.Item37), ("Item38", SoundID.Item38), ("Item40", SoundID.Item40), ("Item41", SoundID.Item41),
        ("Item42", SoundID.Item42), ("Item43", SoundID.Item43), ("Item44", SoundID.Item44), ("Item46", SoundID.Item46),
        ("Item51", SoundID.Item51), ("Item54", SoundID.Item54), ("Item57", SoundID.Item57), ("Item58", SoundID.Item58),
        ("Item60", SoundID.Item60), ("Item62", SoundID.Item62), ("Item69", SoundID.Item69), ("Item70", SoundID.Item70),
        ("Item71", SoundID.Item71), ("Item72", SoundID.Item72), ("Item73", SoundID.Item73), ("Item74", SoundID.Item74),
        ("Item76", SoundID.Item76), ("Item77", SoundID.Item77), ("Item78", SoundID.Item78), ("Item82", SoundID.Item82),
        ("Item83", SoundID.Item83), ("Item84", SoundID.Item84), ("Item85", SoundID.Item85), ("Item88", SoundID.Item88),
        ("Item89", SoundID.Item89), ("Item91", SoundID.Item91), ("Item93", SoundID.Item93), ("Item94", SoundID.Item94),
        ("Item97", SoundID.Item97), ("Item98", SoundID.Item98), ("Item99", SoundID.Item99), ("Item102", SoundID.Item102),
        ("Item103", SoundID.Item103), ("Item105", SoundID.Item105), ("Item106", SoundID.Item106), ("Item107", SoundID.Item107),
        ("Item108", SoundID.Item108), ("Item109", SoundID.Item109), ("Item110", SoundID.Item110), ("Item113", SoundID.Item113),
        ("Item117", SoundID.Item117), ("Item123", SoundID.Item123), ("Item124", SoundID.Item124), ("Item152", SoundID.Item152),
        ("Item157", SoundID.Item157), ("Item158", SoundID.Item158), ("Item169", SoundID.Item169), ("Coins", SoundID.Coins),
        ("Dig", SoundID.Dig), ("Grab", SoundID.Grab), ("MaxMana", SoundID.MaxMana), ("ResearchComplete", SoundID.ResearchComplete),
        ("Shatter", SoundID.Shatter), ("Splash", SoundID.Splash), ("Tink", SoundID.Tink), ("Unlock", SoundID.Unlock),
    };

    private static VfxSlotSpec SoundSelectionSlot(string entity, string eventName) => new() {
        Id = "exact_sound", EntityId = entity, Event = eventName, RendererKind = "soundCue",
        Channel = "sound", Lane = "cue", TextureRole = "none", ParticleRole = "none",
        ParticleSystemId = "none", EmissionMode = "none", Anchor = "self", RepeatEvery = 1, SlotSeed = 0,
    };

    // Saved-wire fixtures intentionally omit new playback controls.
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

    private static void VfxSoundControlsStrictDtoAndPitchInterval()
    {
        string Json(Action<JsonObject>? mutate = null)
        {
            var node = JsonNode.Parse(SoundSelectionJson("Item26"))!.AsObject();
            var slot = node["Slots"]![0]!.AsObject();
            slot["sound"] = new JsonObject { ["volume"] = 0.37, ["pitch"] = -0.9, ["pitchVariance"] = 0.2 };
            mutate?.Invoke(slot);
            return node.ToJsonString();
        }
        var exact = VfxManifestSpec.FromJson(Json());
        Equal(1, exact.Slots.Length, "explicit full sound object survives native JSON");
        var round = VfxManifestSpec.FromJson(exact.ToJson());
        Equal(0.37f, round.Slots[0].Sound!.Volume, "sound volume round trip");
        Equal(-0.9f, round.Slots[0].Sound!.Pitch, "sound pitch round trip");
        Equal(0.2f, round.Slots[0].Sound!.PitchVariance, "sound variance round trip");
        var legacy = SoundSelectionRead("Item26");
        Equal(true, legacy.Slots[0].Sound is null, "absent sound keeps old mode");
        Equal(false, JsonNode.Parse(legacy.ToJson())!["Slots"]![0]!.AsObject().ContainsKey("Sound"), "serializer does not materialize sound controls");
        foreach (string field in new[] { "volume", "pitch", "pitchVariance" }) {
            Equal(0, VfxManifestSpec.FromJson(Json(slot => slot["sound"]!.AsObject().Remove(field))).Slots.Length, "missing sound leaf is not a default");
            Equal(0, VfxManifestSpec.FromJson(Json(slot => slot["sound"]![field] = null)).Slots.Length, "present null sound scalar rejected");
            Equal(0, VfxManifestSpec.FromJson(Json(slot => slot["sound"]![field] = true)).Slots.Length, "boolean sound scalar rejected");
            Equal(0, VfxManifestSpec.FromJson(Json(slot => slot["sound"]![field] = "native")).Slots.Length, "string sound scalar rejected");
        }
        foreach (Action<JsonObject> invalid in new Action<JsonObject>[] {
            slot => slot["sound"] = null,
            slot => slot["sound"] = new JsonObject(),
            slot => slot["sound"] = new JsonArray(),
            slot => slot["sound"]!["volume"] = 1.01,
            slot => slot["sound"]!["volume"] = -0.01,
            slot => slot["sound"]!["pitch"] = -0.91,
            slot => slot["sound"]!["pitch"] = 0.91,
            slot => slot["sound"]!["pitchVariance"] = -0.01,
            slot => slot["sound"]!["pitchVariance"] = 0.61,
            slot => slot["sound"]!["pitchVariance"] = 0.6, // individual bounds valid, random interval exceeds -1
            slot => slot["sound"]!["family"] = "harp",
            slot => slot.Remove("soundId"),
            slot => { slot["RendererKind"] = "lightCue"; slot["Channel"] = "light"; },
        }) Equal(0, VfxManifestSpec.FromJson(Json(invalid)).Slots.Length, "invalid sound presence fails closed");
        foreach (float invalid in new[] { float.NaN, float.PositiveInfinity, float.NegativeInfinity }) {
            bool rejected = false;
            try { new VfxSoundSpec { Volume = 1f, Pitch = invalid, PitchVariance = 0 }.NormalizeAndValidate(); }
            catch (System.IO.InvalidDataException) { rejected = true; }
            Equal(true, rejected, "nonfinite live sound control rejected");
        }
    }

    private static void VfxSoundControlsOwnPitchAndPreserveNativePolicies()
    {
        // This is the actual stable SoundStyle field used by SoundPlayer. The
        // production path has no reflection; the observer proves no hidden
        // Main.musicPitch addition survives the explicit projection for Item26.
        var instrument = typeof(SoundStyle).GetProperty("UsesMusicPitch", BindingFlags.Instance | BindingFlags.NonPublic)
            ?? throw new InvalidOperationException("native instrument-pitch boundary changed");
        Equal(true, (bool)instrument.GetValue(SoundID.Item26)!, "oracle reaches a native instrument sample");
        foreach (var sample in SoundSelectionPalette()) {
            var controls = new VfxSoundSpec { Volume = 0.27f, Pitch = -0.7f, PitchVariance = 0.6f };
            SoundStyle projected = controls.ApplyTo(sample.Style);
            Equal(false, (bool)instrument.GetValue(projected)!, "explicit pitch has no hidden music offset");
            Equal(0.27f, projected.Volume, "native volume does not multiply explicit volume");
            Equal(-0.7f, projected.Pitch, "native sample pitch does not add to explicit pitch");
            Equal(0.6f, projected.PitchVariance, "native jitter does not override explicit variance");
            for (int i = 0; i < 32; i++) {
                float pitch = projected.GetRandomPitch();
                Equal(true, pitch >= -1f && pitch <= -0.4f, "native random pitch remains inside authored interval");
            }
            controls.PitchVariance = 0;
            projected = controls.ApplyTo(sample.Style);
            for (int i = 0; i < 8; i++) Equal(-0.7f, projected.GetRandomPitch(), "explicit zero variance is deterministic");
        }
        var policy = new SoundStyle("Terraria/Sounds/Item_", new[] { 5, 58 }, SoundType.Sound) {
            VariantsWeights = new[] { 0.25f, 0.75f }, Identifier = "explicit_policy_probe",
            MaxInstances = 4, SoundLimitBehavior = SoundLimitBehavior.IgnoreNew, RerollAttempts = 7,
            LimitsArePerVariant = true, PlayOnlyIfFocused = true, PauseBehavior = PauseBehavior.StopWhenGamePaused,
            IsLooped = true,
        };
        SoundStyle copy = new VfxSoundSpec { Volume = 0.5f, Pitch = 0.3f, PitchVariance = 0 }.ApplyTo(policy);
        Equal(true, copy.Variants.SequenceEqual(policy.Variants), "exact native variants retained");
        Equal(true, copy.VariantsWeights.SequenceEqual(policy.VariantsWeights), "exact native variant weights retained");
        Equal(policy.Identifier!, copy.Identifier!, "native grouping identifier retained");
        Equal(4, copy.MaxInstances, "native max instances retained");
        Equal((int)policy.SoundLimitBehavior, (int)copy.SoundLimitBehavior, "native limit policy retained");
        Equal(7, copy.RerollAttempts, "native variant reroll budget retained");
        Equal(true, copy.LimitsArePerVariant && copy.PlayOnlyIfFocused && copy.IsLooped, "native boolean playback policies retained");
        Equal((int)policy.PauseBehavior, (int)copy.PauseBehavior, "native pause behavior retained");
    }

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
                foreach (float phase in new[] { -1f, 0f, 1f })
                foreach (bool explicitSound in new[] { false, true }) {
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
                    if (explicitSound) {
                        // New controls always include an exact sample; legacy null
                        // fixtures remain tested only on their old-wire path.
                        if (sample.Id is null) continue;
                        slot.Sound = new VfxSoundSpec { Volume = alpha, Pitch = phase * 0.9f, PitchVariance = 0.2f };
                    }
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
                    string label = $"{route}/{sample.Id ?? "legacy"}/alpha={alpha}/phase={phase}/explicit={explicitSound}";
                    Equal(explicitSound && alpha == 0f ? 0 : 1, calls, label + " exact API call count");
                    if (explicitSound && alpha == 0f) {
                        Equal(serialized, data.VfxManifest.ToJson(), label + " zero volume stays authored silence");
                        continue;
                    }
                    Equal(sample.Style.SoundPath, observed.SoundPath, label + " exact native path");
                    Equal(true, sample.Style.Variants.SequenceEqual(observed.Variants), label + " variants preserve native constant");
                    Equal(explicitSound ? 0.2f : sample.Style.PitchVariance, observed.PitchVariance, label + " explicit or legacy variance");
                    Equal(true, sample.Style.VariantsWeights.SequenceEqual(observed.VariantsWeights), label + " native variant weights preserved");
                    Equal(sample.Style.Identifier ?? "", observed.Identifier ?? "", label + " native sharing identifier preserved");
                    Equal(sample.Style.LimitsArePerVariant, observed.LimitsArePerVariant, label + " native per-variant policy preserved");
                    Equal(sample.Style.IsLooped, observed.IsLooped, label + " native nonlooping style preserved");
                    Equal((int)sample.Style.Type, (int)observed.Type, label + " native sound type preserved");
                    Equal(sample.Style.MaxInstances, observed.MaxInstances, label + " native instance cap preserved");
                    Equal((int)sample.Style.SoundLimitBehavior, (int)observed.SoundLimitBehavior, label + " native cap policy preserved");
                    Equal(explicitSound ? alpha : Math.Clamp(alpha, 0.05f, 1f), observed.Volume, label + " exact new volume or legacy alpha");
                    Equal(sample.Style.RerollAttempts, observed.RerollAttempts, label + " native variant reroll policy");
                    Equal(sample.Style.PlayOnlyIfFocused, observed.PlayOnlyIfFocused, label + " native focus policy");
                    Equal((int)sample.Style.PauseBehavior, (int)observed.PauseBehavior, label + " native pause policy");
                    Equal(explicitSound ? phase * 0.9f : Math.Clamp(phase * 0.25f, -0.5f, 0.5f), observed.Pitch, label + " exact new pitch or legacy phase");
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

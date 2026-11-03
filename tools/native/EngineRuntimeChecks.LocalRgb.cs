using System;
using System.Collections;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.VFX;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    private static VfxSlotSpec LocalRgbSlot(string renderer, string eventName = "on_hit")
    {
        var slot = new VfxSlotSpec { Id = "local_rgb", EntityId = "unavailable_item", Event = eventName, RendererKind = renderer,
            Color = Rgb(17, 83, 241), Scale = 1 };
        if (renderer is not ("lightCue" or "impactSprite")) { slot.StartTick = 0; slot.Density = 0; slot.RepeatEvery = 0; }
        else if (eventName == "periodic") slot.RepeatEvery = 0; // item ownership; projectile tests add their consumed leaves
        if (renderer is "impactSprite" or "spriteStampTrail")
            slot.TextureRole = renderer == "impactSprite" ? "impact" : "entity";
        if (renderer is not ("lightCue" or "impactSprite")) { slot.ParticleSystemId = "none"; slot.Spread = 0; }
        if (renderer is not ("lightCue" or "childMotes")) { slot.Alpha = .5f; slot.Duration = 10; slot.Blend = "alpha"; slot.Layer = "BeforeProjectiles"; }
        return slot;
    }

    private static void VfxBranchControlsHaveExactPresenceAndCurrentSelectors()
    {
        var element = MaterialElementWire()["vfxManifest"]!.DeepClone().AsObject();
        var path = element.DeepClone().AsObject();
        var pathRow = path["slots"]![0]!.AsObject();
        var payload = pathRow["element"]!.AsObject();
        pathRow["rendererKind"] = "texturedPath";
        pathRow.Remove("duration"); pathRow.Remove("repeatEvery");
        pathRow["path"] = new JsonObject {
            ["texture"] = payload["texture"]!.DeepClone(), ["source"] = "anchorHistory", ["historyTicks"] = 8,
            ["minDistancePx"] = 0, ["maxSegmentLengthPx"] = 128, ["widthPx"] = 8,
            ["widthProfile"] = payload["widthProfile"]!.DeepClone(), ["opacityProfile"] = payload["opacityProfile"]!.DeepClone(),
            ["colorProfile"] = payload["colorProfile"]!.DeepClone(), ["profileDomain"] = "age", ["uvMode"] = "stretch",
            ["repeatLengthPx"] = 1, ["scrollPxPerTick"] = 0,
        };
        pathRow.Remove("element");
        var sound = JsonNode.Parse(new VfxManifestSpec { Slots = new[] { SoundSelectionSlot("unavailable_item", "on_use") } }.ToJson())!.AsObject();
        foreach (var branch in new[] { element, path, LibraryManifestWire(), LibraryManifestWire(true), sound })
        {
            string kind = (string)branch["slots"]![0]!["rendererKind"]!;
            string[] forbidden = kind == "soundCue"
                ? new[] { "scale", "spread", "particleSystemId", "textureRole", "duration", "alpha", "blend", "layer", "startTick", "repeatEvery", "density" }
                : new[] { "scale", "density", "spread", "particleSystemId", "textureRole" }
                    .Concat(kind is "texturedPath" or "screenShakeCue" ? new[] { "duration", "repeatEvery" } : Array.Empty<string>())
                    .Concat(kind == "screenShakeCue" ? new[] { "alpha", "blend", "layer" } : Array.Empty<string>()).ToArray();
            var accepted = VfxManifestSpec.FromJson(branch.ToJsonString());
            Equal(true, accepted.HasSlots, "current sparse branch admitted: " + kind);
            foreach (string serialized in new[] { accepted.ToJson(), JsonSerializer.Serialize(accepted, new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase }) }) {
                var row = JsonNode.Parse(serialized)!["slots"]![0]!.AsObject();
                foreach (string field in forbidden) Equal(false, row.ContainsKey(field), "no placeholder emitted: " + kind + "." + field);
            }
            foreach (string field in forbidden) foreach (bool explicitNull in new[] { false, true }) {
                var invalid = branch.DeepClone();
                invalid["slots"]![0]![field] = explicitNull ? null : field is "particleSystemId" or "textureRole" ? JsonValue.Create("none")
                    : field == "blend" ? JsonValue.Create("alpha") : field == "layer" ? JsonValue.Create("BeforeProjectiles")
                    : JsonValue.Create(field is "scale" or "alpha" ? 1 : field == "duration" ? 3 : 0);
                Equal(false, VfxManifestSpec.FromJson(invalid.ToJsonString()).HasSlots, "foreign common field refused: " + kind + "." + field);
            }
        }
        foreach (string renderer in new[] { "soundCue", "lightCue", "impactSprite" })
        foreach (bool projectile in new[] { false, true }) foreach (int repeat in new[] { 0, 1 }) {
            var soundData = GeneratedItemData.Placeholder(); soundData.SourceMode="test_fixture";
            var current = JsonNode.Parse(soundData.ToJson())!;
            var slot = renderer == "soundCue" ? SoundSelectionSlot(soundData.RuntimeProgram.ItemEntityId, "periodic") : LocalRgbSlot(renderer, "periodic");
            slot.EntityId=soundData.RuntimeProgram.ItemEntityId;
            if (renderer == "impactSprite") soundData.RuntimeProgram.Entities[0].Visual.ImpactCanvasSize=32;
            slot.RepeatEvery=repeat;
            if (projectile) {
                var actor = RootSpawnFixture(0,1).RuntimeProgram.TryGetEntity("root")!;
                actor.Id="sound_actor"; actor.Visual.AssetMode="no_asset";
                if (renderer == "impactSprite") actor.Visual.ImpactCanvasSize=32;
                soundData.RuntimeProgram.Entities = new[] { soundData.RuntimeProgram.Entities[0], actor };
                current=JsonNode.Parse(soundData.ToJson())!;
                slot.EntityId=actor.Id;slot.StartTick=0;if(repeat==0)slot.Density=.4f;
            }
            current=JsonNode.Parse(soundData.ToJson())!;
            current["vfxManifest"]!["slots"] = new JsonArray(JsonSerializer.SerializeToNode(slot,new JsonSerializerOptions {PropertyNamingPolicy=JsonNamingPolicy.CamelCase}));
            Equal(true,GeneratedItemData.FromJson(current.ToJsonString()) is not null,"current periodic cue conditional control ownership: "+renderer);
            foreach(string field in projectile ? repeat==0 ? new[]{"startTick","repeatEvery","density"} : new[]{"startTick","repeatEvery"} : new[]{"repeatEvery"}) {
                var bad=current.DeepClone();bad["vfxManifest"]!["slots"]![0]!.AsObject().Remove(field);
                Equal(true,GeneratedItemData.FromJson(bad.ToJsonString()) is null,"required periodic cue field refuses absence: "+renderer+"."+field);
            }
            foreach(string field in projectile ? repeat==0 ? Array.Empty<string>() : new[]{"density"} : new[]{"density","startTick"}) {
                var bad=current.DeepClone();bad["vfxManifest"]!["slots"]![0]![field]=0;
                Equal(true,GeneratedItemData.FromJson(bad.ToJsonString()) is null,"unconsumed periodic cue field refuses: "+field);
            }
        }
        foreach (var choice in new[] { ("GemDiamond", Terraria.ID.DustID.GemDiamond), ("TintableDustLighted", Terraria.ID.DustID.TintableDustLighted),
            ("Glass", Terraria.ID.DustID.Glass), ("Smoke", Terraria.ID.DustID.Smoke), ("Electric", Terraria.ID.DustID.Electric) }) {
            var slot = LocalRgbSlot("childMotes"); slot.ParticleSystemId = choice.Item1;
            var manifest = new VfxManifestSpec { Slots = new[] { slot } };
            Equal(true, VfxManifestSpec.FromJson(manifest.ToJson()).HasSlots, "current Dust selector admitted: " + choice.Item1);
            Equal((int)choice.Item2, VfxRendererRegistry.DustId(slot.ParticleSystemId), "exact shared native Dust selector: " + choice.Item1);
        }
        foreach (string alias in new[] { "dust", "pl:glow", "pl:shard", "pl:smoke", "pl:spark" }) {
            var slot = LocalRgbSlot("childMotes"); slot.ParticleSystemId = alias;
            Equal("", new VfxManifestSpec { Slots = new[] { slot } }.ToJson(), "historical Dust selector refused: " + alias);
        }
        foreach (string renderer in new[] { "lightCue", "impactSprite", "childMotes" }) {
            var current = LocalRgbSlot(renderer);
            var manifest = new VfxManifestSpec { Slots = new[] { current } };
            Equal(true, manifest.ToJson().Length > 0, "only executed branch fields admitted: " + renderer);
            foreach (string field in (renderer == "impactSprite" ? new[] { "spread", "particleSystemId" }
                : renderer == "lightCue" ? new[] { "alpha", "blend", "layer", "duration", "spread", "particleSystemId", "textureRole" }
                : new[] { "alpha", "blend", "layer", "duration", "textureRole" })
                .Concat(renderer is "lightCue" or "impactSprite" ? new[] { "startTick", "repeatEvery", "density" } : Array.Empty<string>())) {
                var foreign = JsonNode.Parse(manifest.ToJson())!;
                foreign["slots"]![0]![field] = field is "blend" ? JsonValue.Create("alpha")
                    : field is "layer" ? JsonValue.Create("BeforeProjectiles")
                    : field is "particleSystemId" or "textureRole" ? JsonValue.Create("none") : JsonValue.Create(1);
                Equal(false, VfxManifestSpec.FromJson(foreign.ToJsonString()).HasSlots, "foreign field refused: " + renderer + "." + field);
            }
        }
        foreach (string alias in new[] { "projectileAfterimage", "actorAfterimage" }) {
            Equal(InfiniVfxRendererKind.None, VfxRendererRegistry.ParseKind(alias), "retired renderer is not translated: " + alias);
            var retired = LocalRgbSlot(alias); retired.TextureRole = "entity";
            var manifest = new VfxManifestSpec { Slots = new[] { retired } };
            string wire = JsonSerializer.Serialize(manifest, new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase });
            Equal(false, VfxManifestSpec.FromJson(wire).HasSlots, "retired renderer fails native persisted admission: " + alias);
            Equal(alias, retired.RendererKind, "retired renderer is never rewritten: " + alias);
            Equal("", manifest.ToJson(), "retired renderer fails native serialization: " + alias);
        }
        foreach (string alias in new[] { "projectile", "field" }) {
            var slot = LocalRgbSlot("spriteStampTrail"); slot.TextureRole = alias;
            Equal("", new VfxManifestSpec { Slots = new[] { slot } }.ToJson(), "historical texture alias refused: " + alias);
        }
        bool missingSizeRefused=false;
        try { SpritePresentation.FrameScale(null,64,64); } catch(System.IO.InvalidDataException) { missingSizeRefused=true; }
        Equal(true,missingSizeRefused,"selected main PNG never invents raw-frame world size");
        Equal(0.5f,SpritePresentation.FrameScale(32,64,16),"current main PNG uses explicit authored extent");
        var delivered=GeneratedItemData.Placeholder(); delivered.SourceMode="generated";
        delivered.Visual.SpritePath="current.png";delivered.Visual.SpriteStatus="generated";
        delivered.Visual.RenderSizePx=32;delivered.Visual.ForwardAngleDegrees=0;
        var currentPng=JsonNode.Parse(delivered.ToJson())!;
        foreach(string field in new[]{"renderSizePx","forwardAngleDegrees"}) {
            var bad=currentPng.DeepClone();bad["visual"]!.AsObject().Remove(field);
            Equal(true,GeneratedItemData.FromJson(bad.ToJsonString()) is null,"current delivered item requires authored frame metadata: "+field);
        }
        Equal(true,GeneratedItemData.FromPlayerSaveJson(delivered.ToPlayerSaveJson()) is not null,"compact identity remains valid without PNG metadata until hydration");
        var impactSelection=SpritePresentation.Resolve(delivered,delivered.RuntimeProgram.ItemEntityId,"impact");
        Equal(true,impactSelection.ImpactTexture,"dedicated impact selector is distinct from main-body metadata");
        Equal(1f,impactSelection.FrameScale(64,64),"dedicated impact uses actual effect frame scale without inventing main-body size");
        var data = GeneratedItemData.Placeholder(); data.SourceMode = "test_fixture";
        var impact = LocalRgbSlot("impactSprite", "periodic"); data.VfxManifest.Slots = new[] { impact };
        foreach (int size in new[] { 24, 32, 48, 64, 96, 128 }) {
            data.RuntimeProgram.Entities[0].Visual.ImpactCanvasSize = size;
            var accepted = GeneratedItemData.FromJson(data.ToNetworkJson()) ?? throw new InvalidOperationException("impact canvas rejected");
            Equal(size, accepted.RuntimeProgram.Entities[0].Visual.ImpactCanvasSize!.Value, "authored impact canvas retained");
        }
        var invalidImpact = JsonNode.Parse(data.ToJson())!;
        var visual = invalidImpact["runtimeProgram"]!["entities"]![0]!["visual"]!.AsObject();
        foreach (string literal in new[] { "null", "0", "16", "33", "32.5", "true", "\"32\"" }) {
            visual["impactCanvasSize"] = JsonNode.Parse(literal);
            Equal(true, GeneratedItemData.FromJson(invalidImpact.ToJsonString()) is null, "invalid impact canvas refused: " + literal);
        }
        visual.Remove("impactCanvasSize");
        var historicalImpact = GeneratedItemData.FromJson(invalidImpact.ToJsonString())
            ?? throw new InvalidOperationException("native impact execution must not require generation-only canvas metadata");
        Equal(true, historicalImpact.RuntimeProgram.Entities[0].Visual.ImpactCanvasSize is null, "missing impact canvas is preserved, never invented");
        Equal(1f, SpritePresentation.Resolve(historicalImpact, historicalImpact.RuntimeProgram.ItemEntityId, "impact").FrameScale(64,64), "impact frame still uses actual selected texture dimensions");
    }

    private static void VfxLocalRgbAdmissionAndSerialization()
    {
        string[] visible = { "historyRibbon", "tipTrail", "beamLine", "wavyStrip", "impactRing", "fieldPulse", "orbitingMotes", "ghostArc",
            "spriteStampTrail", "impactSprite", "childMotes", "lightCue" };
        foreach (string renderer in visible)
        {
            var slot = LocalRgbSlot(renderer);
            var manifest = new VfxManifestSpec { Slots = new[] { slot } };
            string json = manifest.ToJson();
            Equal(true, json.Length > 0, "current local RGB manifest serializes " + renderer);
            var accepted = VfxManifestSpec.FromJson(json);
            var serializedRow = JsonNode.Parse(json)!["slots"]![0]!.AsObject();
            bool sprite = renderer is "spriteStampTrail" or "impactSprite";
            Equal(sprite, serializedRow.ContainsKey("textureRole"), "common texture selector belongs only to sprites: " + renderer);
            var foreignSelector = JsonNode.Parse(json)!;
            if (sprite) foreignSelector["slots"]![0]!.AsObject().Remove("textureRole");
            else foreignSelector["slots"]![0]!["textureRole"] = "none";
            Equal(false, VfxManifestSpec.FromJson(foreignSelector.ToJsonString()).HasSlots, "exact common texture selector presence: " + renderer);
            Equal(1, accepted.Slots.Length, "simple visible renderer requires and preserves RGB " + renderer);
            Equal(new Color(17,83,241), accepted.Slots[0].Color!.ToColor(), "exact RGB rather than selected palette " + renderer);
            var root = JsonSerializer.SerializeToNode(manifest, new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase })!.AsObject();
            root["slots"]![0]!.AsObject().Remove("color");
            Equal(false, VfxManifestSpec.FromJson(root.ToJsonString()).HasSlots, "missing local RGB refuses " + renderer);
            Equal(true, ContractJsonDiagnostics.TryGet("VfxManifestSpec.FromJson", out _), "missing RGB diagnostic " + renderer);
            root["slots"]![0]!["color"] = null;
            Equal(false, VfxManifestSpec.FromJson(root.ToJsonString()).HasSlots, "explicit null RGB refuses " + renderer);
            root["slots"]![0]!["color"] = RgbWire(256,0,0);
            Equal(false, VfxManifestSpec.FromJson(root.ToJsonString()).HasSlots, "out of range RGB is not clamped " + renderer);
        }
        var foreign = new[] { LibraryManifestWire(), LibraryManifestWire(true), MaterialElementWire()["vfxManifest"]!.DeepClone().AsObject() };
        var sound = new VfxManifestSpec { Slots = new[] { SoundSelectionSlot("item", "on_use") } };
        foreign = foreign.Append(JsonSerializer.SerializeToNode(sound, new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase })!.AsObject()).ToArray();
        var path = MaterialElementWire()["vfxManifest"]!.DeepClone().AsObject();
        var row = path["slots"]![0]!.AsObject();
        var element = row["element"]!.AsObject();
        row["rendererKind"] = "texturedPath"; row.Remove("duration"); row.Remove("repeatEvery");
        row["path"] = new JsonObject { ["texture"] = element["texture"]!.DeepClone(), ["source"] = "anchorHistory", ["historyTicks"] = 8,
            ["minDistancePx"] = 0, ["maxSegmentLengthPx"] = 128, ["widthPx"] = 8, ["widthProfile"] = element["widthProfile"]!.DeepClone(),
            ["opacityProfile"] = element["opacityProfile"]!.DeepClone(), ["colorProfile"] = element["colorProfile"]!.DeepClone(),
            ["profileDomain"] = "age", ["uvMode"] = "stretch", ["repeatLengthPx"] = 1, ["scrollPxPerTick"] = 0 };
        row.Remove("element");
        foreign = foreign.Append(path).ToArray();
        foreach (var root in foreign)
        {
            Equal(true, VfxManifestSpec.FromJson(root.ToJsonString()).HasSlots, "color-owning or colorless renderer valid without common color");
            root["slots"]![0]!["color"] = RgbWire(1,2,3);
            Equal(false, VfxManifestSpec.FromJson(root.ToJsonString()).HasSlots, "common RGB forbidden for nested/colorless owner");
        }
        foreach (string text in new[] { "null", "{}", "{\"schema\":\"infini.vfx.runtime-events.v16\",\"slots\":[]}" }) {
            VfxManifestSpec.FromJson(text);
            Equal(true, ContractJsonDiagnostics.TryGet("VfxManifestSpec.FromJson", out _), "missing manifest/budget never synthesizes current wire " + text);
        }
        var canonical = JsonNode.Parse(new VfxManifestSpec { Slots = new[] { LocalRgbSlot("impactRing") } }.ToJson())!.AsObject();
        Equal("budget,recipeId,schema,slots", string.Join(",", canonical.Select(k => k.Key).OrderBy(k => k, StringComparer.Ordinal)), "standalone manifest emits only canonical serialized fields");
        foreach (string field in new[] { "maxParticlesPerTick", "maxParticlesTotal", "maxDrawCalls" }) {
            var missing = canonical.DeepClone().AsObject(); missing["budget"]!.AsObject().Remove(field);
            Equal(false, VfxManifestSpec.FromJson(missing.ToJsonString()).HasSlots, "required executable budget refuses absence " + field);
        }
        foreach (string retired in new[] { "seed", "effectName", "inspirationNames", "playbackMode", "confidence", "effectMagnitude", "visualBudgetClass", "motif", "overlayPolicy", "debug" })
        {
            var root = JsonSerializer.SerializeToNode(new VfxManifestSpec { Slots = new[] { LocalRgbSlot("impactRing") } })!.AsObject();
            root[retired] = new JsonObject();
            Equal(false, VfxManifestSpec.FromJson(root.ToJsonString()).HasSlots, "retired root metadata refuses " + retired);
        }
        foreach (string retired in new[] { "backend", "particleRole", "jitter", "fadeIn", "fadeOut", "budgetWeight", "signatureWeight", "visualCost", "bakedCommands", "bakedClipId", "channel", "lane", "emissionMode" })
        {
            var root = JsonSerializer.SerializeToNode(new VfxManifestSpec { Slots = new[] { LocalRgbSlot("impactRing") } }, new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase })!.AsObject();
            root["slots"]![0]![retired] = 0;
            Equal(false, VfxManifestSpec.FromJson(root.ToJsonString()).HasSlots, "retired slot fields refuse " + retired);
        }
        foreach (string schema in new[] { "infini.vfx.runtime-events.v15", "infini.vfx.runtime-events.v14", "infini.vfx.runtime-events.v16 " })
        {
            var root = JsonSerializer.SerializeToNode(new VfxManifestSpec { Slots = new[] { LocalRgbSlot("impactRing") } }, new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase })!.AsObject();
            root["schema"] = schema;
            Equal(false, VfxManifestSpec.FromJson(root.ToJsonString()).HasSlots, "only exact current schema admitted " + schema);
        }
    }

    private static void VfxLocalRgbReachesSimpleNativeConsumers()
    {
        WithVfxGeometryQueue((batch, texture, count, positions, colors) => {
            var system = new InfiniDetachedVfxSystem();
            using var cache = new BorrowedSpriteCache();
            var oldPixel = Terraria.GameContent.TextureAssets.MagicPixel;
            try {
                system.OnWorldUnload();
                Terraria.GameContent.TextureAssets.MagicPixel = CpuTextureAsset(texture);
                var data = GeneratedItemData.Placeholder(); data.Visual.Palette = new[] { "semantic fire must not select orange" };
                var slot = LocalRgbSlot("beamLine", "periodic"); slot.RepeatEvery = 1;
                data.VfxManifest.Slots = new[] { slot };
                var projectile = new Projectile { Center = new Vector2(40,60), velocity = Vector2.UnitX };
                var state = new InfiniVfxState();
                InfiniVfxRuntime.Draw(projectile,data,slot.EntityId,data.VfxManifest,ref state,Color.Magenta);
                Equal(1,count(),"active simple primitive reaches native FNA CPU queue");
                Equal(new Color(17,83,241)*.5f,colors(0)[0],"active RGB uses slot, not light/palette tint");
                var queue = (IList)typeof(InfiniDetachedVfxSystem).GetField("Emissions",BindingFlags.Static|BindingFlags.NonPublic)!.GetValue(null)!;
                foreach (string renderer in new[] { "beamLine", "impactSprite", "spriteStampTrail" }) {
                    system.OnWorldUnload();
                    slot = LocalRgbSlot(renderer);
                    var entity = data.RuntimeProgram.Entities[0];
                    entity.Visual.AssetMode = "reuse_item_icon";
                    entity.Visual.ImpactSpritePath = "rgb-impact.png";
                    data.Visual.SpritePath = "rgb-body.png"; data.Visual.RenderSizePx=32; data.Visual.ForwardAngleDegrees=0;
                    data.VfxManifest.Slots = new[] { slot };
                    InfiniVfxRuntime.OnDetachedEvent(data,slot.EntityId,"on_hit",data.VfxManifest,projectile.Center,Vector2.UnitX,"rgb-event",
                        InfiniVfxProjectileSnapshot.Capture(projectile,data,slot.EntityId));
                    Equal(1,queue.Count,"detached native consumer is reached " + renderer);
                    object emission = queue[0]!;
                    Color captured = (Color)emission.GetType().GetProperty("Color")!.GetValue(emission)!;
                    Equal(renderer == "beamLine" ? new Color(17,83,241)*.5f : new Color(17,83,241),captured,"detached RGB captured before source mutation " + renderer);
                    slot.Color!.R = 255;
                    Equal(captured,(Color)emission.GetType().GetProperty("Color")!.GetValue(emission)!,"detached RGB copy is immutable " + renderer);
                }
            } finally { system.OnWorldUnload(); Terraria.GameContent.TextureAssets.MagicPixel = oldPixel; }
        });
        WithLighting((config, lights) => {
            var data = GeneratedItemData.Placeholder();
            var slot = LocalRgbSlot("lightCue", "periodic"); slot.RepeatEvery = 1; slot.StartTick = 0;
            data.VfxManifest.Slots = new[] { slot };
            var state = new InfiniVfxState();
            config.PresentationLightMultiplier = 1;
            InfiniVfxRuntime.OnTick(new Projectile { Center = new Vector2(40,60) },data,slot.EntityId,data.VfxManifest,ref state);
            Equal(1,lights.Count,"projectile exact RGB reaches Lighting CPU queue");
            var colorField = lights[0]!.GetType().GetField("Color")!;
            Equal(slot.Color!.ToColor().ToVector3()*.22f,(Vector3)colorField.GetValue(lights[0])!,"projectile light has exact local RGB");
            lights.Clear();
            var player = new Player { active = true, whoAmI = 0, Center = new Vector2(40,60) };
            InfiniItemVfxRuntime.ClearUseEventCaches();
            slot = LocalRgbSlot("lightCue", "periodic"); slot.RepeatEvery=1;
            data.VfxManifest.Slots = new[] { slot };
            InfiniItemVfxRuntime.OnPeriodic(player,data,slot.EntityId);
            Equal(1,lights.Count,"item exact RGB reaches Lighting CPU queue");
            Equal(slot.Color!.ToColor().ToVector3()*.2f,(Vector3)colorField.GetValue(lights[0])!,"item light has exact local RGB");
        });
    }

    private static void VfxLocalRgbTexturedPathCopiesIndependentRamp()
    {
        var path = new VfxTexturedPathSpec {
            Texture = new VfxTextureSpec { Source = "item", AssetId = "" }, Source = "beam", HistoryTicks = 0, MinDistancePx = 0, MaxSegmentLengthPx = 128,
            WidthPx = 8, WidthProfile = new VfxNumericProfileSpec { Start = 1, Middle = 1, End = 1, Curve = "linear" },
            OpacityProfile = new VfxNumericProfileSpec { Start = 1, Middle = 1, End = 1, Curve = "linear" },
            ColorProfile = new VfxColorProfileSpec { Start = Rgb(255,0,0), Middle = Rgb(0,255,0), End = Rgb(0,0,255), Curve = "linear" },
            ProfileDomain = "length", UvMode = "stretch", RepeatLengthPx = 1, ScrollPxPerTick = 0,
        };
        object design = LibraryInvoke("CopyPath",path,1f,"alpha","", "BeforeProjectiles","self",512,0)!;
        path.ColorProfile.Start.G = 255; path.ColorProfile.Middle.R = 255;
        var mesh = (VertexPositionColorTexture[])LibraryInvoke("BuildMaterialPathMesh",new[] { Vector2.Zero,new Vector2(40,0) },Array.Empty<float>(),design,0UL,(Func<bool>)(()=>true))!;
        Equal(12,mesh.Length,"path adds physical midpoint and two real triangles per segment");
        Equal(Color.Red,mesh[0].Color,"path native start vertices use immutable local RGB");
        Equal(Color.Lime,mesh[2].Color,"path native midpoint vertices use independent local RGB");
        Equal(Color.Blue,mesh[^1].Color,"path native endpoint vertices use independent local RGB");

        // A decorative tapered strip follows the actual flexible collision path,
        // not an inventory PNG placed on its tip or a reconstructed trajectory.
        var generated = new InfiniCrafterLocal.Content.Projectiles.GeneratedProjectile();
        typeof(InfiniCrafterLocal.Content.Projectiles.GeneratedProjectile)
            .GetMethod("BuildLashPoints", System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic)!
            .Invoke(generated, new object[] { new Vector2(30, 40), Vector2.UnitX, .35f, 96f, 16, -1.2f, 1.2f, .2f, 1f, 1, 1f });
        var points = ((System.Collections.Generic.List<Vector2>)typeof(InfiniCrafterLocal.Content.Projectiles.GeneratedProjectile)
            .GetField("_whipPoints", System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic)!
            .GetValue(generated)!).ToArray();
        var frozen = (Vector2[])points.Clone();
        path.Source = "whip"; path.WidthPx = 12;
        path.WidthProfile = new VfxNumericProfileSpec { Start = .25f, Middle = 1, End = 0, Curve = "linear" };
        design = LibraryInvoke("CopyPath", path, 1f, "alpha", "", "BeforeProjectiles", "self", 512, 0)!;
        var skin = (VertexPositionColorTexture[])LibraryInvoke("BuildMaterialPathMesh", points, Array.Empty<float>(), design, 0UL, (Func<bool>)(()=>true))!;
        Equal(true, skin.Length >= 16*6, "textured skin retains every actual lash segment");
        AssertVfxNear(points[0], new Vector2((skin[0].Position.X+skin[1].Position.X)*.5f,
            (skin[0].Position.Y+skin[1].Position.Y)*.5f), "skin starts at exact lash anchor");
        AssertVfxNear(points[^1], new Vector2(skin[^1].Position.X, skin[^1].Position.Y), "zero-width taper ends at exact curve tip");
        Equal(true, Math.Abs(Vector3.Distance(skin[0].Position,skin[1].Position)-3f)<.001f,
            "explicit quarter-width profile is applied, not collision width");
        for(int n=0;n<points.Length;n++) Equal(frozen[n],points[n],"material skin never changes collision points");

    }
}

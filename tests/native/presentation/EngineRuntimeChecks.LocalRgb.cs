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
    private static RuntimeRgbSpec Rgb(int r, int g, int b) => new() { R = r, G = g, B = b };
    private static JsonObject RgbWire(int r, int g, int b) => new() { ["r"] = r, ["g"] = g, ["b"] = b };

    private static VfxSlotSpec LocalRgbSlot(string renderer, string eventName = "on_hit")
    {
        var slot = new VfxSlotSpec { Id = "local_rgb", EntityId = "unavailable_item", Event = eventName,
            RendererKind = renderer, Anchor = "self", Color = Rgb(17, 83, 241), StartTick = 0,
            RepeatEvery = eventName == RuntimeEventKind.Periodic ? 1 : 0 };
        if (renderer == "nativeLight") slot.Light = new() { Intensity = .37f };
        else if (renderer == "nativeDust") slot.Dust = new() {
            Spawn = new() { Shape = "point" }, Type = "GemDiamond", Count = 1, Size = 1,
            SpeedMinPxPerTick = 0, SpeedMaxPxPerTick = 0, SpreadRadians = 0, InheritVelocity = 0,
            NativeAlpha = 0, NoGravity = true, AngularDistribution = "even", DirectionFrame = "source", AngleOffsetRadians = 0 };
        else throw new ArgumentException("Expected current native RGB cue", nameof(renderer));
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
        foreach (var choice in new[] { ("GemDiamond", Terraria.ID.DustID.GemDiamond), ("TintableDustLighted", Terraria.ID.DustID.TintableDustLighted),
            ("Glass", Terraria.ID.DustID.Glass), ("Smoke", Terraria.ID.DustID.Smoke), ("Electric", Terraria.ID.DustID.Electric) }) {
            var slot = LocalRgbSlot("nativeDust"); slot.Dust!.Type = choice.Item1;
            var manifest = new VfxManifestSpec { Slots = new[] { slot } };
            Equal(true, VfxManifestSpec.FromJson(manifest.ToJson()).HasSlots, "current Dust selector admitted: " + choice.Item1);
            Equal((int)choice.Item2, VfxRendererRegistry.DustId(slot.Dust.Type), "exact shared native Dust selector: " + choice.Item1);
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
    }

    private static void VfxLocalRgbAdmissionAndSerialization()
    {
        string[] visible = { "nativeDust", "nativeLight" };
        foreach (string renderer in visible)
        {
            var slot = LocalRgbSlot(renderer);
            var manifest = new VfxManifestSpec { Slots = new[] { slot } };
            string json = manifest.ToJson();
            Equal(true, json.Length > 0, "current local RGB manifest serializes " + renderer);
            var accepted = VfxManifestSpec.FromJson(json);
            var serializedRow = JsonNode.Parse(json)!["slots"]![0]!.AsObject();
            Equal(false, serializedRow.ContainsKey("textureRole"), "native cue has no common texture selector");
            var foreignSelector = JsonNode.Parse(json)!;
            foreignSelector["slots"]![0]!["textureRole"] = "entity";
            Equal(false, VfxManifestSpec.FromJson(foreignSelector.ToJsonString()).HasSlots, "retired common texture selector refuses");
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
        var canonical = JsonNode.Parse(new VfxManifestSpec { Slots = new[] { LocalRgbSlot("nativeLight") } }.ToJson())!.AsObject();
        Equal("budget,recipeId,schema,slots", string.Join(",", canonical.Select(k => k.Key).OrderBy(k => k, StringComparer.Ordinal)), "standalone manifest emits only canonical serialized fields");
        foreach (string field in new[] { "maxParticlesPerTick", "maxParticlesTotal", "maxDrawCalls" }) {
            var missing = canonical.DeepClone().AsObject(); missing["budget"]!.AsObject().Remove(field);
            Equal(false, VfxManifestSpec.FromJson(missing.ToJsonString()).HasSlots, "required executable budget refuses absence " + field);
        }
        foreach (string retired in new[] { "seed", "effectName", "inspirationNames", "playbackMode", "confidence", "effectMagnitude", "visualBudgetClass", "motif", "overlayPolicy", "debug" })
        {
            var root = JsonSerializer.SerializeToNode(new VfxManifestSpec { Slots = new[] { LocalRgbSlot("nativeLight") } })!.AsObject();
            root[retired] = new JsonObject();
            Equal(false, VfxManifestSpec.FromJson(root.ToJsonString()).HasSlots, "retired root metadata refuses " + retired);
        }
        foreach (string retired in new[] { "backend", "particleRole", "jitter", "fadeIn", "fadeOut", "budgetWeight", "signatureWeight", "visualCost", "bakedCommands", "bakedClipId", "channel", "lane", "emissionMode" })
        {
            var root = JsonSerializer.SerializeToNode(new VfxManifestSpec { Slots = new[] { LocalRgbSlot("nativeLight") } }, new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase })!.AsObject();
            root["slots"]![0]![retired] = 0;
            Equal(false, VfxManifestSpec.FromJson(root.ToJsonString()).HasSlots, "retired slot fields refuse " + retired);
        }
        foreach (string schema in new[] { "infini.vfx.runtime-events.v15", "infini.vfx.runtime-events.v14", "infini.vfx.runtime-events.v16 " })
        {
            var root = JsonSerializer.SerializeToNode(new VfxManifestSpec { Slots = new[] { LocalRgbSlot("nativeLight") } }, new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase })!.AsObject();
            root["schema"] = schema;
            Equal(false, VfxManifestSpec.FromJson(root.ToJsonString()).HasSlots, "only exact current schema admitted " + schema);
        }
    }

    private static void VfxLocalRgbReachesSimpleNativeConsumers()
    {
        WithVfxGeometryQueue((batch, texture, count, positions, colors) => {
            var system = new InfiniDetachedVfxSystem();
            try {
                system.OnWorldUnload();
                var data = GeneratedItemData.Placeholder(); data.Visual.Palette = new[] { "semantic fire must not select orange" };
                var slot = ExplicitShapeSlot(); slot.EntityId = data.RuntimeProgram.ItemEntityId;
                slot.Shape!.ColorStart = Rgb(17,83,241); slot.Shape.ColorEnd = Rgb(17,83,241);
                slot.Shape.OpacityStart = slot.Shape.OpacityEnd = .5f;
                data.VfxManifest.Slots = new[] { slot };
                Equal(true, VfxManifestSpec.FromJson(data.VfxManifest.ToJson()).HasSlots, "complete current shape fixture admitted");
                var projectile = new Projectile { active = true, scale = 1, Center = new Vector2(40,60), velocity = Vector2.UnitX };
                Equal(true, InfiniVfxRuntime.OnDetachedEvent(data,slot.EntityId,"on_hit",data.VfxManifest,projectile.Center,Vector2.UnitX,"rgb-event",
                    InfiniVfxProjectileSnapshot.Capture(projectile,data,slot.EntityId)), "current shape event accepted");
                slot.Shape.ColorStart.R = 255; slot.Shape.ColorEnd.G = 255;
                slot.Shape.LengthPx = 90; // copied geometry and RGB must survive definition mutation
                typeof(InfiniDetachedVfxSystem).GetMethod("BeginDrawBudgetFrame",BindingFlags.Static|BindingFlags.NonPublic)!.Invoke(null,null);
                typeof(InfiniDetachedVfxSystem).GetMethod("DrawShapes",BindingFlags.Static|BindingFlags.NonPublic)!
                    .Invoke(null,new object[] { "AfterProjectiles", texture, (Action)(()=>{}) });
                Equal(1,count(),"current explicit line reaches native FNA CPU queue");
                Equal(new Color(17,83,241)*.5f,colors(0)[0],"immutable nested RGB, not palette/light or mutated source");
                var vertices = positions(0);
                Equal(true, Math.Abs(vertices.Max(v=>v.X)-vertices.Min(v=>v.X)-20f)<.001f,"captured explicit line length");
                Equal(true, Math.Abs(vertices.Max(v=>v.Y)-vertices.Min(v=>v.Y)-.5f)<.001f,"captured explicit subpixel line width");
            } finally { system.OnWorldUnload(); }
        });
        WithLighting((config, lights) => {
            var system = new InfiniDetachedVfxSystem();
            try {
                system.OnWorldUnload(); config.PresentationLightMultiplier = 1;
                var data = GeneratedItemData.Placeholder();
                var slot = LocalRgbSlot("nativeLight"); data.VfxManifest.Slots = new[] { slot };
                var state = new InfiniVfxState();
                var projectile = new Projectile { active = true, scale = 1, Center = new Vector2(40,60), velocity = Vector2.UnitX };
                Equal(true, InfiniVfxRuntime.OnEvent(projectile,data,slot.EntityId,slot.Event,data.VfxManifest,ref state,projectile.Center), "projectile native light event accepted");
                Equal(1,lights.Count,"projectile exact RGB reaches Lighting CPU queue");
                var colorField = lights[0]!.GetType().GetField("Color")!;
                Equal(new Color(17,83,241).ToVector3()*.37f,(Vector3)colorField.GetValue(lights[0])!,"projectile uses explicit light intensity and local RGB");
                lights.Clear();
                var player = new Player { active = true, whoAmI = 0, Center = new Vector2(40,60) };
                InfiniItemVfxRuntime.ClearUseEventCaches();
                slot = LocalRgbSlot("nativeLight", RuntimeEventKind.OnUse); data.VfxManifest.Slots = new[] { slot };
                InfiniItemVfxRuntime.EmitAndSyncEvent(player,data,slot.EntityId,slot.Event);
                Equal(1,lights.Count,"item exact RGB reaches Lighting CPU queue");
                Equal(new Color(17,83,241).ToVector3()*.37f,(Vector3)colorField.GetValue(lights[0])!,"item and projectile use the same explicit light law");
            } finally { system.OnWorldUnload(); InfiniItemVfxRuntime.ClearUseEventCaches(); }
        });
    }

    private static void VfxLocalRgbTexturedPathCopiesIndependentRamp()
    {
        var path = new VfxTexturedPathSpec {
            Texture = new VfxTextureSpec { Source = "item", AssetId = "", Uv = new() { QuarterTurns = 0, MirrorU = false, MirrorV = false } }, Source = "beam", HistoryTicks = 0, MinDistancePx = 0, MaxSegmentLengthPx = 128,
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

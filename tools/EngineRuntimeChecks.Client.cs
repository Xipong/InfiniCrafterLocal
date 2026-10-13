using System;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using MonoMod.Cil;
using ReLogic.Content;
using Terraria.DataStructures;
using Terraria.GameContent;
using InfiniCrafterLocal.Common.Services;

internal static partial class EngineRuntimeChecks
{

    private static void ParentSummaryUnicodeRoundtrip()
    {
        using var actorState = new NativeActorState();
        // Author behaviorChecks allow 280 Unicode code points, not UTF-16 units.
        string boundary = new string('ж', 279) + "🌟";
        string supplementary = string.Concat(Enumerable.Repeat("🌟", 280));
        var original = InfiniCrafterLocal.Common.Models.GeneratedItemData.Placeholder();
        original.Id = "parent_unicode_probe";
        original.Name = "Unicode parent";
        original.SourceMode = "test_fixture";
        original.GeneratedParentSummary.NotableEffects = new[] {
            boundary, supplementary, "  ASCII control  ", "   ", boundary + "overflow",
        }.Concat(Enumerable.Repeat("Remaining effect", 12)).ToArray();
        // Serialize without pre-normalization: exercise actual incoming JSON admission.
        string input = JsonSerializer.Serialize(original, new JsonSerializerOptions {
            PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        });
        var data = InfiniCrafterLocal.Common.Models.GeneratedItemData.FromJson(input)
            ?? throw new InvalidOperationException("unicode parent fixture rejected");
        var item = new Terraria.Item();
        item.SetDefaults(Terraria.ID.ItemID.WoodenSword);
        // Real GeneratedItem hooks on a vanilla-allocated host; no content registration.
        var host = new InfiniCrafterLocal.Content.Items.GeneratedItem();
        typeof(Terraria.ModLoader.ModType<Terraria.Item>).GetProperty("Entity", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)!.SetValue(host, item);
        typeof(Terraria.Item).GetProperty("ModItem")!.SetValue(item, host);
        typeof(InfiniCrafterLocal.Content.Items.GeneratedItem).GetProperty("Data")!.SetValue(host, data);
        data.ApplyToItem(item);
        string payload = new GeneratorClient().Prepare(item, item,
            new Terraria.Player { name = "unicode_parent_probe" }).PayloadJson;
        using var next = JsonDocument.Parse(payload);
        foreach (string side in new[] { "itemA", "itemB" })
        {
            var effects = next.RootElement.GetProperty(side).GetProperty("generatedData")
                .GetProperty("generatedParentSummary").GetProperty("notableEffects");
            Equal(12, effects.GetArrayLength(), "summary item count remains bounded");
            Equal(boundary, effects[0].GetString(), "accepted boundary never splits a surrogate");
            Equal(supplementary, effects[1].GetString(), "accepted supplementary prose is retained");
            Equal("ASCII control", effects[2].GetString(), "existing whitespace normalization retained");
            Equal(boundary, effects[3].GetString(), "overbound prose clips at 280 code points");
        }
        Equal(boundary, original.GeneratedParentSummary.NotableEffects[0], "incoming source unchanged");
    }

    private static void GeneratedParentPrefixIsRequestOnly()
    {
        using var actorState = new NativeActorState();

        var failures = new System.Collections.Generic.List<string>();
        Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(17);
        Terraria.Main.netMode = Terraria.ID.NetmodeID.SinglePlayer;
        var data = InfiniCrafterLocal.Common.Models.GeneratedItemData.Placeholder();
        data.Id = "parent_prefix_probe";
        data.SourceMode = "test_fixture";
        data.Name = "Authored parent";
        data.Gameplay.Damage = 100;
        data.Gameplay.DamageClass = "melee";
        data.Gameplay.Knockback = 5f;
        data.Gameplay.UseTime = data.Gameplay.UseAnimation = 30;
        data.Gameplay.Value = 10000;
        data.Normalize();
        var baseItem = new Terraria.Item();
        baseItem.SetDefaults(Terraria.ID.ItemID.WoodenSword);
        // Isolate the real GeneratedItem clone/data hooks on a vanilla-allocated
        // host type. This is not full ModLoader content registration.
        var generated = new InfiniCrafterLocal.Content.Items.GeneratedItem();
        typeof(Terraria.ModLoader.ModType<Terraria.Item>).GetProperty("Entity", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)!
            .SetValue(generated, baseItem);
        typeof(Terraria.Item).GetProperty("ModItem")!.SetValue(baseItem, generated);
        typeof(InfiniCrafterLocal.Content.Items.GeneratedItem).GetProperty("Data")!.SetValue(generated, data);
        data.ApplyToItem(baseItem);
        baseItem.stack = 3;
        baseItem.favorited = true;
        string definition = data.ToNetworkJson();
        string Stats(Terraria.Item item) => JsonSerializer.Serialize(new {
            item.type, item.prefix, item.damage, item.crit, item.knockBack, item.useTime,
            item.useAnimation, item.scale, item.shootSpeed, item.mana, item.rare, item.value,
            item.favorited, item.Name,
        });
        var client = new GeneratorClient();
        var owner = new Terraria.Player { name = "headless_prefix_probe" };
        using var baseline = JsonDocument.Parse(client.Prepare(baseItem.Clone(), baseItem.Clone(), owner).PayloadJson);
        foreach (int prefix in new[] { 0, (int)Terraria.ID.PrefixID.Legendary, (int)Terraria.ID.PrefixID.Broken, (int)Terraria.ID.PrefixID.Zealous })
        {
            try
            {
                Terraria.Item source = baseItem.Clone();
                if (prefix != 0) Equal(true, source.Prefix(prefix), "real prefix accepts " + prefix);
                string before = Stats(source);
                var sourceData = ((InfiniCrafterLocal.Content.Items.GeneratedItem)source.ModItem).Data;
                string sourceDefinition = JsonSerializer.Serialize(sourceData);
                var prepared = client.Prepare(source, source, owner);
                Equal(before, Stats(source), "source retains prefix/stats " + prefix);
                Equal(3, source.stack, "source stack untouched");
                Equal(sourceDefinition, JsonSerializer.Serialize(sourceData), "source definition unchanged by Prepare");
                foreach (Terraria.Item refund in new[] { prepared.RefundA, prepared.RefundB })
                {
                    Equal(false, ReferenceEquals(source, refund), "refund is independent item");
                    Equal(before, Stats(refund), "refund retains original prefix/stats " + prefix);
                    Equal(1, refund.stack, "refund reserves one unit");
                    Equal(sourceData.ToNetworkJson(), ((InfiniCrafterLocal.Content.Items.GeneratedItem)refund.ModItem).Data.ToNetworkJson(), "refund preserves generated definition");
                }
                using var payload = JsonDocument.Parse(prepared.PayloadJson);
                foreach (string side in new[] { "itemA", "itemB" })
                {
                    var actual = payload.RootElement.GetProperty(side);
                    var expected = baseline.RootElement.GetProperty(side);
                    Equal(prefix, actual.GetProperty("originalPrefix").GetInt32(), "original prefix is diagnostic only");
                    Equal(prefix != 0, actual.GetProperty("prefixIgnored").GetBoolean(), "ignored marker is truthful");
                    foreach (string field in new[] { "prefix", "name", "damage", "useTime", "useAnimation", "knockback", "manaCost", "shootSpeed", "rare", "value", "damageClass", "autoFeatures", "nameTokens", "runtimeFacts", "generatedData" })
                        Equal(expected.GetProperty(field).GetRawText(), actual.GetProperty(field).GetRawText(), "prefix " + prefix + " base payload " + field);
                }
                var identity = typeof(GeneratorClient).GetMethod("CraftIdentityItem", BindingFlags.Static | BindingFlags.NonPublic)!;
                var requestItem = (Terraria.Item)identity.Invoke(null, new object[] { source, data })!;
                Equal((byte)0, requestItem.prefix, "request identity actually unprefixed");
                Equal(baseItem.crit, requestItem.crit, "crit reset too, not only authored fields");
                Equal(baseItem.scale, requestItem.scale, "size reset");
                Equal(3, requestItem.stack, "request keeps source quantity");
                Equal(true, requestItem.ModItem is InfiniCrafterLocal.Content.Items.GeneratedItem, "generated type identity retained");
                Equal(definition, data.ToNetworkJson(), "canonical definition unchanged");
            }
            catch (Exception error) { failures.Add("prefix " + prefix + ": " + error); }
        }
        // A caller may have resolved a save-only parent's canonical definition.
        // Exercise that exact argument without pretending a registry/network match ran.
        var referenceItem = baseItem.Clone();
        var referenceMod = (InfiniCrafterLocal.Content.Items.GeneratedItem)referenceItem.ModItem;
        var tag = new Terraria.ModLoader.IO.TagCompound { ["infiniJson"] = data.ToPlayerSaveJson() };
        referenceMod.LoadData(tag);
        Equal(true, InfiniCrafterLocal.Common.Models.GeneratedItemData.IsPlayerSaveReferenceOnly(referenceMod.Data), "fixture really is save-only");
        Equal(0, referenceItem.damage, "save-only host is inert before resolution");
        var identityMethod = typeof(GeneratorClient).GetMethod("CraftIdentityItem", BindingFlags.Static | BindingFlags.NonPublic)!;
        var resolvedCopy = (Terraria.Item)identityMethod.Invoke(null, new object[] { referenceItem, data })!;
        Equal(100, resolvedCopy.damage, "resolved canonical argument restores authored stats");
        Equal(data.Name, resolvedCopy.Name, "resolved canonical name retained");
        Equal(0, referenceItem.damage, "request does not hydrate/mutate original save-only host");
        Equal(true, InfiniCrafterLocal.Common.Models.GeneratedItemData.IsPlayerSaveReferenceOnly(referenceMod.Data), "original remains save-only");

        if (failures.Count > 0) throw new InvalidOperationException(string.Join(Environment.NewLine, failures));
    }

    private static void CraftIdentityRejectsFailedDefaults()
    {
        var method = typeof(GeneratorClient).GetMethod("CraftIdentityItem", BindingFlags.Static | BindingFlags.NonPublic)!;
        int invalidType = Terraria.ModLoader.ItemLoader.ItemCount + 1000;
        bool defaultsFailed = false;
        try { new Terraria.Item().SetDefaults(invalidType); }
        catch (IndexOutOfRangeException) { defaultsFailed = true; }
        Equal(true, defaultsFailed, "fixture reaches a real SetDefaults failure");
        var source = new Terraria.Item { type = invalidType, stack = 2, prefix = Terraria.ID.PrefixID.Legendary, damage = 115 };
        bool rejected = false;
        try { method.Invoke(null, new object?[] { source, null }); }
        catch (TargetInvocationException error) when (error.InnerException is IndexOutOfRangeException) { rejected = true; }
        Equal(true, rejected, "failed defaults must not return a prefixed copy as base stats");
        Equal((byte)Terraria.ID.PrefixID.Legendary, source.prefix, "failure leaves source prefix unchanged");
        Equal(115, source.damage, "failure leaves source damage unchanged");
        Equal(2, source.stack, "failure leaves source stack unchanged");
        var vanilla = new Terraria.Item();
        vanilla.SetDefaults(Terraria.ID.ItemID.WoodenSword);
        int baseDamage = vanilla.damage;
        int baseCrit = vanilla.crit;
        Equal(true, vanilla.Prefix(Terraria.ID.PrefixID.Legendary), "real vanilla prefix control");
        int prefixedDamage = vanilla.damage;
        var plain = (Terraria.Item)method.Invoke(null, new object?[] { vanilla, null })!;
        Equal((byte)0, plain.prefix, "vanilla request remains unprefixed");
        Equal(baseDamage, plain.damage, "vanilla defaults preserved");
        Equal(baseCrit, plain.crit, "vanilla crit defaults preserved");
        Equal(prefixedDamage, vanilla.damage, "vanilla original unchanged");
        Equal((byte)Terraria.ID.PrefixID.Legendary, vanilla.prefix, "vanilla original prefix retained");
        foreach (Terraria.Item? empty in new Terraria.Item?[] { null, new Terraria.Item() })
        {
            var air = (Terraria.Item)method.Invoke(null, new object?[] { empty, null })!;
            Equal(true, air.IsAir, "null/air boundary remains inert");
        }
    }

    private static void GeneratorDeliveryRequiresIdentity()
    {
        var gate = typeof(GeneratorClient).GetMethod("IsDeliverableGeneratedData", BindingFlags.Static | BindingFlags.NonPublic)!;
        foreach (string id in new[] { "", " ", "\t", "placeholder", "recipe_identity_probe" })
        {
            var data = InfiniCrafterLocal.Common.Models.GeneratedItemData.Placeholder();
            data.Id = id;
            data.Name = "Identity probe";
            data.SourceMode = "test_fixture";
            var parsed = InfiniCrafterLocal.Common.Models.GeneratedItemData.FromJson(data.ToNetworkJson());
            Equal(true, parsed is not null, "test reaches delivery gate after real JSON boundary");
            bool accepted = (bool)gate.Invoke(null, new object?[] { parsed })!;
            Equal(id == "recipe_identity_probe", accepted, "delivery identity: '" + id + "'");
            Equal(id.Trim(), parsed!.Id, "delivery gate does not invent identity");
        }
    }

    // Synthetic metadata on real installed FNA/Asset types, no GPU or native PNG measurement.
    private static void WithParentSpriteMetadata(Action<Terraria.Item, Texture2D, Asset<Texture2D>> check)
    {
        using var actorState = new NativeActorState();
        var oldAssets = TextureAssets.Item;
        var oldAnimations = Terraria.Main.itemAnimations;

        var texture = (Texture2D)System.Runtime.CompilerServices.RuntimeHelpers.GetUninitializedObject(typeof(Texture2D));
        var asset = (Asset<Texture2D>)System.Runtime.CompilerServices.RuntimeHelpers.GetUninitializedObject(typeof(Asset<Texture2D>));
        GC.SuppressFinalize(texture);
        GC.SuppressFinalize(asset);
        typeof(Texture2D).GetProperty("Width")!.SetValue(texture, 40);
        typeof(Texture2D).GetProperty("Height")!.SetValue(texture, 68);
        typeof(Asset<Texture2D>).GetField("ownValue", BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(asset, texture);
        typeof(Asset<Texture2D>).GetProperty("State")!.SetValue(asset, AssetState.Loaded);
        var item = new Terraria.Item();
        item.SetDefaults(Terraria.ID.ItemID.WoodenSword);
        item.stack = 3;
        item.favorited = true;
        try
        {
            Terraria.Main.dedServ = false;
            Terraria.Main.netMode = Terraria.ID.NetmodeID.SinglePlayer;
            TextureAssets.Item = new Asset<Texture2D>[item.type + 1];
            TextureAssets.Item[item.type] = asset;
            Terraria.Main.itemAnimations = new DrawAnimation[item.type + 1];
            check(item, texture, asset);
        }
        finally
        {
            TextureAssets.Item = oldAssets;
            Terraria.Main.itemAnimations = oldAnimations;

        }
    }

    private static JsonElement CaptureParentSpriteMetadata(Terraria.Item? item,
        InfiniCrafterLocal.Common.Models.GeneratedItemData? definition = null)
    {
        var capture = typeof(GeneratorClient).GetMethod("TryCaptureNativeSpriteReference", BindingFlags.Static | BindingFlags.NonPublic)!;
        return JsonSerializer.SerializeToElement(capture.Invoke(null, new object?[] { item, definition }),
            new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase });
    }

    private sealed class ParentFrameProbe : DrawAnimation
    {
        public Rectangle Rectangle;
        public bool Throw;
        public int Reads;
        public int Updates;
        public override Rectangle GetFrame(Texture2D texture, int frameCounterOverride = -1)
        {
            Reads++;
            Equal(-1, frameCounterOverride, "observe the current state, not a frame override");
            if (Throw) throw new InvalidOperationException("fixture frame unavailable");
            return Rectangle;
        }
        public override void Update() { Updates++; throw new InvalidOperationException("snapshot cannot update animation"); }
    }

    private static void ParentNativeSpriteReferenceReachesPreparedRequest()
    {
        WithParentSpriteMetadata((source, texture, asset) =>
        {
            var owner = new Terraria.Player { name = "sprite_reference_probe" };
            var client = new GeneratorClient();
            string Stats(Terraria.Item item) => JsonSerializer.Serialize(new {
                item.type, item.prefix, item.damage, item.width, item.height, item.scale, item.favorited,
            });
            source.width = 999; source.height = 777; source.scale = 3.5f;
            string original = Stats(source);
            Terraria.Main.dedServ = true;
            var older = client.Prepare(source, source, owner);
            Terraria.Main.dedServ = false;
            var prepared = client.Prepare(source, source, owner);
            using var expected = JsonDocument.Parse(older.PayloadJson);
            using var actual = JsonDocument.Parse(prepared.PayloadJson);
            foreach (string side in new[] { "itemA", "itemB" })
            {
                var prior = expected.RootElement.GetProperty(side);
                var parent = actual.RootElement.GetProperty(side);
                Equal(false, prior.TryGetProperty("spriteReferenceRaw", out _), "absence is omission, not null");
                Equal(prior.EnumerateObject().Count() + 1, parent.EnumerateObject().Count(), "only one root fact added");
                foreach (var field in prior.EnumerateObject())
                    Equal(field.Value.GetRawText(), parent.GetProperty(field.Name).GetRawText(), "old field/null preserved: " + field.Name);
                var reference = parent.GetProperty("spriteReferenceRaw");
                Equal("TextureAssets.Item", reference.GetProperty("source").GetString()!, "exact source");
                Equal(40, reference.GetProperty("textureWidthPx").GetInt32(), "texture width, not item width");
                Equal(68, reference.GetProperty("textureHeightPx").GetInt32(), "texture height, not item height");
                var frame = reference.GetProperty("currentFrame");
                Equal("texture_bounds", frame.GetProperty("source").GetString()!, "null animation slot is static");
                Equal(0, frame.GetProperty("xPx").GetInt32(), "zero X preserved");
                Equal(0, frame.GetProperty("yPx").GetInt32(), "zero Y preserved");
                Equal(40, frame.GetProperty("widthPx").GetInt32(), "literal bounds width");
                Equal(68, frame.GetProperty("heightPx").GetInt32(), "literal bounds height");
                Equal(true, parent.GetProperty("generatedData").ValueKind == JsonValueKind.Null, "native top-level null retained");
            }
            Equal(original, Stats(source), "Prepare does not alter the source");
            Equal(3, source.stack, "original quantity unchanged");
            foreach (var refund in new[] { prepared.RefundA, prepared.RefundB })
            {
                Equal(false, ReferenceEquals(source, refund), "refund independent");
                Equal(original, Stats(refund), "refund keeps original fields");
                Equal(1, refund.stack, "one unit reserved");
            }
            var animation = new DrawAnimationVertical(7, 2, false) { Frame = 1, FrameCounter = 5 };
            Terraria.Main.itemAnimations[source.type] = animation;
            Rectangle observed = animation.GetFrame(texture); // Installed accessor excludes two separator pixels.
            var animated = client.Prepare(source, source, owner);
            using var animatedJson = JsonDocument.Parse(animated.PayloadJson);
            var current = animatedJson.RootElement.GetProperty("itemA").GetProperty("spriteReferenceRaw").GetProperty("currentFrame");
            Equal("draw_animation", current.GetProperty("source").GetString()!, "registered UI animation provenance");
            Equal(observed.X, current.GetProperty("xPx").GetInt32(), "current frame X");
            Equal(observed.Y, current.GetProperty("yPx").GetInt32(), "current frame Y");
            Equal(observed.Width, current.GetProperty("widthPx").GetInt32(), "current frame width");
            Equal(observed.Height, current.GetProperty("heightPx").GetInt32(), "current frame height, not atlas height");
            Equal(1, animation.Frame, "snapshot did not update native Frame");
            Equal(5, animation.FrameCounter, "snapshot did not update native FrameCounter");
            var probe = new ParentFrameProbe { Rectangle = new Rectangle(3, 5, 11, 13) };
            Terraria.Main.itemAnimations[source.type] = probe;
            var literal = CaptureParentSpriteMetadata(source).GetProperty("currentFrame");
            Equal(3, literal.GetProperty("xPx").GetInt32(), "exact custom accessor origin");
            Equal(13, literal.GetProperty("heightPx").GetInt32(), "no atlas subdivision inference");
            Equal(1, probe.Reads, "one current-frame sample");
            Equal(0, probe.Updates, "no animation update");
            string frozen = prepared.PayloadJson;
            source.SetDefaults(Terraria.ID.ItemID.WorkBench); // In-place source reuse after capture.
            typeof(Texture2D).GetProperty("Width")!.SetValue(texture, 9);
            probe.Rectangle = new Rectangle(0, 0, 1, 1);
            Equal(frozen, prepared.PayloadJson, "prepared observation is an immutable value snapshot");
        });
    }

    private static void ParentNativeSpriteReferenceAbsenceIsHonest()
    {
        WithParentSpriteMetadata((source, texture, asset) =>
        {
            var roster = TextureAssets.Item;
            var animations = Terraria.Main.itemAnimations;
            var capture = typeof(GeneratorClient).GetMethod("TryCaptureNativeSpriteReference", BindingFlags.Static | BindingFlags.NonPublic)!;
            int valueReads = 0;
            using var valueObserver = new MonoMod.RuntimeDetour.ILHook(capture, il => {
                var sites = il.Body.Instructions.Where(instruction =>
                    (instruction.OpCode == Mono.Cecil.Cil.OpCodes.Callvirt || instruction.OpCode == Mono.Cecil.Cil.OpCodes.Call)
                    && instruction.Operand is Mono.Cecil.MethodReference method && method.Name == "get_Value"
                    && method.DeclaringType.FullName.StartsWith("ReLogic.Content.Asset`1", StringComparison.Ordinal)).ToArray();
                Equal(1, sites.Length, "one exact loaded asset Value read site");
                new ILCursor(il) { Index = il.Body.Instructions.IndexOf(sites[0]) }.EmitDelegate<Action>(() => valueReads++);
            });
            void Absent(string why)
            {
                int before = valueReads;
                Equal(true, CaptureParentSpriteMetadata(source).ValueKind == JsonValueKind.Null, why);
                Equal(before, valueReads, why + " avoids Value read");
            }
            Equal(true, CaptureParentSpriteMetadata(null).ValueKind == JsonValueKind.Null, "null item absent");
            Equal(true, CaptureParentSpriteMetadata(new Terraria.Item()).ValueKind == JsonValueKind.Null, "air absent");
            TextureAssets.Item = null!; Absent("missing texture roster");
            TextureAssets.Item = Array.Empty<Asset<Texture2D>>(); Absent("out-of-range item type");
            TextureAssets.Item = roster; roster[source.type] = null!; Absent("missing asset"); roster[source.type] = asset;
            var defaultProperty = typeof(Asset<Texture2D>).GetProperty("DefaultValue", BindingFlags.Public | BindingFlags.Static)!;
            object? oldDefault = defaultProperty.GetValue(null);
            var pixel = (Texture2D)System.Runtime.CompilerServices.RuntimeHelpers.GetUninitializedObject(typeof(Texture2D));
            GC.SuppressFinalize(pixel);
            typeof(Texture2D).GetProperty("Width")!.SetValue(pixel, 1);
            typeof(Texture2D).GetProperty("Height")!.SetValue(pixel, 1);
            try
            {
                defaultProperty.SetValue(null, pixel);
                typeof(Asset<Texture2D>).GetProperty("State")!.SetValue(asset, AssetState.NotLoaded);
                Equal(true, ReferenceEquals(pixel, asset.Value), "real unloaded Value exposes a 1px placeholder");
                Absent("unloaded asset with 1px Value is not a reference");
                typeof(Asset<Texture2D>).GetProperty("State")!.SetValue(asset, AssetState.Loaded);
            }
            finally { defaultProperty.SetValue(null, oldDefault); }
            Terraria.Main.dedServ = true; Absent("dedicated server"); Terraria.Main.dedServ = false;
            Terraria.Main.netMode = Terraria.ID.NetmodeID.Server; Absent("server mode"); Terraria.Main.netMode = Terraria.ID.NetmodeID.SinglePlayer;
            typeof(Asset<Texture2D>).GetField("<IsDisposed>k__BackingField", BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(asset, true); Absent("disposed asset");
            typeof(Asset<Texture2D>).GetField("<IsDisposed>k__BackingField", BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(asset, false);
            typeof(GraphicsResource).GetField("<IsDisposed>k__BackingField", BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(texture, true);
            Equal(true, CaptureParentSpriteMetadata(source).ValueKind == JsonValueKind.Null, "disposed texture absent");
            typeof(GraphicsResource).GetField("<IsDisposed>k__BackingField", BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(texture, false);
            typeof(Texture2D).GetProperty("Width")!.SetValue(texture, 1);
            typeof(Texture2D).GetProperty("Height")!.SetValue(texture, 1);
            int readsBeforeLoadedPixel = valueReads;
            Equal(1, CaptureParentSpriteMetadata(source).GetProperty("textureWidthPx").GetInt32(), "real loaded 1px is accepted");
            Equal(readsBeforeLoadedPixel + 1, valueReads, "loaded positive executes the exact Value observer once");
            Terraria.Main.netMode = Terraria.ID.NetmodeID.MultiplayerClient;
            Equal(1, CaptureParentSpriteMetadata(source).GetProperty("textureHeightPx").GetInt32(), "ordinary multiplayer client may observe loaded art");
            Terraria.Main.netMode = Terraria.ID.NetmodeID.SinglePlayer;
            typeof(Texture2D).GetProperty("Width")!.SetValue(texture, 40);
            typeof(Texture2D).GetProperty("Height")!.SetValue(texture, 68);
            foreach (DrawAnimation[]? unknown in new DrawAnimation[]?[] { null, Array.Empty<DrawAnimation>() })
            {
                Terraria.Main.itemAnimations = unknown!;
                Equal(false, CaptureParentSpriteMetadata(source).TryGetProperty("currentFrame", out _), "missing animation roster leaves frame unknown");
            }
            Terraria.Main.itemAnimations = animations;
            var probe = new ParentFrameProbe { Throw = true };
            animations[source.type] = probe;
            Equal(false, CaptureParentSpriteMetadata(source).TryGetProperty("currentFrame", out _), "throwing accessor preserves dimensions only");
            probe.Throw = false;
            foreach (Rectangle invalid in new[] { new Rectangle(-1, 0, 3, 3), new Rectangle(0, 0, 0, 3),
                new Rectangle(39, 0, 2, 1), new Rectangle(0, 67, 1, 2), new Rectangle(int.MaxValue, 0, int.MaxValue, 1) })
            {
                probe.Rectangle = invalid;
                var fact = CaptureParentSpriteMetadata(source);
                Equal(40, fact.GetProperty("textureWidthPx").GetInt32(), "bad frame cannot erase valid texture dimensions");
                Equal(false, fact.TryGetProperty("currentFrame", out _), "bad frame omitted, not clamped");
            }
            Equal(0, probe.Updates, "unavailable frames do not trigger updates");
        });
    }

    private static void ParentGeneratedSpriteReferenceNeverUsesNativeProxy()
    {
        WithParentSpriteMetadata((source, texture, asset) =>
        {
            var data = InfiniCrafterLocal.Common.Models.GeneratedItemData.Placeholder();
            data.Id = "parent_declared_size_probe"; data.Name = "Literal definition"; data.SourceMode = "test_fixture";
            var generated = new InfiniCrafterLocal.Content.Items.GeneratedItem();
            typeof(Terraria.ModLoader.ModType<Terraria.Item>).GetProperty("Entity", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)!.SetValue(generated, source);
            typeof(Terraria.Item).GetProperty("ModItem")!.SetValue(source, generated);
            typeof(InfiniCrafterLocal.Content.Items.GeneratedItem).GetProperty("Data")!.SetValue(generated, data);
            data.ApplyToItem(source);
            var owner = new Terraria.Player { name = "declared_size_probe" };
            foreach (int? size in new int?[] { null, 1, 47, 512 })
            {
                if (size.HasValue) data.Visual.RenderSizePx = size.Value;
                string before = JsonSerializer.Serialize(data);
                var prepared = new GeneratorClient().Prepare(source, source, owner);
                using var json = JsonDocument.Parse(prepared.PayloadJson);
                foreach (string side in new[] { "itemA", "itemB" })
                {
                    var parent = json.RootElement.GetProperty(side);
                    Equal(false, parent.TryGetProperty("spriteReferenceRaw", out _), "loaded shared generated proxy is never reference art");
                    var visual = parent.GetProperty("generatedData").GetProperty("visual");
                    Equal(size.HasValue, visual.TryGetProperty("renderSizePx", out var declared), "accepted declaration is optional");
                    if (size.HasValue) Equal(size.Value, declared.GetInt32(), "literal declared extent reaches request");
                    foreach (string field in new[] { "createTile", "createWall", "placeStyle" })
                        Equal(true, parent.GetProperty(field).ValueKind == JsonValueKind.Null, "generated old null preserved: " + field);
                }
                Equal(before, JsonSerializer.Serialize(data), "canonical declaration not mutated by request");
                Equal(1, prepared.RefundA.stack, "refund reservation unchanged");
            }
            Equal(true, CaptureParentSpriteMetadata(source).ValueKind == JsonValueKind.Null, "generated ModItem excluded even without resolved argument");
        });
    }

    private static void CacheOnlyFlagPreservesRequest()
    {
        var method = typeof(GeneratorClient).GetMethod("WithCacheOnlyFlag", BindingFlags.Static | BindingFlags.NonPublic)!;
        foreach (string json in new[] {
            "{}", " { } ",
            "{\"itemA\":{\"name\":\"Тест } ,\",\"damage\":17},\"itemB\":{\"id\":23},\"worldId\":7}",
            "{\"cacheOnly\":false,\"nested\":{\"cacheOnly\":false},\"large\":9007199254740993,\"precise\":0.1234567890123456789}",
            "{\"cacheOnly\":true}",
        })
        {
            string result = (string)method.Invoke(null, new object[] { json })!;
            JsonDocument parsed;
            try { parsed = JsonDocument.Parse(result); }
            catch (JsonException ex) { throw new InvalidOperationException("cache-only transform produced invalid JSON: " + result, ex); }
            using (parsed)
            using (var original = JsonDocument.Parse(json))
            {
                Equal(true, parsed.RootElement.GetProperty("cacheOnly").GetBoolean(), "cache-only is explicit true");
                Equal(1, parsed.RootElement.EnumerateObject().Count(p => p.Name == "cacheOnly"), "one authoritative cache-only field");
                int expectedCount = original.RootElement.EnumerateObject().Count(p => p.Name != "cacheOnly") + 1;
                Equal(expectedCount, parsed.RootElement.EnumerateObject().Count(), "no lost or added payload fields");
                foreach (var field in original.RootElement.EnumerateObject().Where(p => p.Name != "cacheOnly"))
                {
                    // Compare compact JSON without converting numbers through double.
                    Equal(JsonSerializer.Serialize(field.Value), JsonSerializer.Serialize(parsed.RootElement.GetProperty(field.Name)), "preserved field " + field.Name);
                }
            }
        }
        foreach (string invalid in new[] { "[]", "null", "1", "\"text\"", "{", "" })
        {
            bool rejected = false;
            try { method.Invoke(null, new object[] { invalid }); }
            catch (TargetInvocationException ex) when (ex.InnerException is JsonException) { rejected = true; }
            Equal(true, rejected, "non-object or malformed request rejected: " + invalid);
        }
    }
}

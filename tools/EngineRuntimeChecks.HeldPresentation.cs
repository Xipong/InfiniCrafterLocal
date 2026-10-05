using System;
using System.Collections;
using System.Collections.Generic;
using System.Reflection;
using System.Runtime.CompilerServices;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Terraria;
using Terraria.DataStructures;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    // Real canonical Draw -> DrawData -> FNA CPU queue. Only FlushBatch (GPU boundary)
    // is intercepted. Texture/batch shells never allocate/dispose graphics resources.
    // Engine reference: tML v2026.06.3.6, 29bf9785f5f4de8cd305be002c4cc48aa1177b20,
    // PlayerDrawLayers.DrawPlayer_27_HeldItem: GetAdjustedItemScale, ItemLocation minus
    // screenPosition, itemRotation verbatim (including inverted gravity).
    private static void HeldRenderSizeUsesFinalFrameAndAdjustedScale(Func<Vector2, DrawData> render, GeneratedItemData data, Player player, Item item, Texture2D texture)
    {
        var previousVisual = data.Visual;
        float previousScale = item.scale, previousAuthored = data.Gameplay.ItemScale;
        try
        {
            foreach (int size in new[] { 1, 40, 512 })
            foreach (int canvas in new[] { 64, 128 })
            foreach (float authored in new[] { 0.25f, 1f, 4f })
            {
                typeof(Texture2D).GetProperty("Width")!.SetValue(texture, canvas);
                typeof(Texture2D).GetProperty("Height")!.SetValue(texture, canvas * 5 / 8);
                data.Visual = new VisualSpec { SpritePath = previousVisual.SpritePath, RenderSizePx = size, ForwardAngleDegrees = 45f };
                item.scale = 1.2f; data.Gameplay.ItemScale = authored;
                float adjusted = player.GetAdjustedItemScale(item);
                DrawData result = render(new Vector2(140, 260));
                Equal(new Vector2(adjusted * (size / (float)canvas)), result.scale, "root q multiplies exact adjusted G once, no new clamp");
                Equal(player.itemRotation, result.rotation, "root declared axis never redesigns native held pose");
                Equal(1.2f, item.scale, "presentation never changes Item.scale physics");
                Equal(authored, data.Gameplay.ItemScale, "presentation never changes authored G");
            }
        }
        finally
        {
            data.Visual = previousVisual; item.scale = previousScale; data.Gameplay.ItemScale = previousAuthored;
            typeof(Texture2D).GetProperty("Width")!.SetValue(texture, 64); typeof(Texture2D).GetProperty("Height")!.SetValue(texture, 40);
        }
    }

    private static void HeldRootVisibilityUsesExplicitPresentationOptIn()
    {
        HeldRootVisibilityObligations(false); // observer ABI and literal legacy control first
        HeldRootVisibilityObligations(false, true); // axis alone is NOT the visibility opt-in
        HeldRootVisibilityObligations(true);
    }

    private static void HeldRootVisibilityObligations(bool newPresentation, bool axisOnly = false)
    {
        const BindingFlags statics = BindingFlags.Static | BindingFlags.NonPublic;
        const BindingFlags instance = BindingFlags.Instance | BindingFlags.NonPublic;
        var remote = (IDictionary)typeof(GeneratedHeldItemDrawLayer).GetField("RemoteHeldPresentations", statics)!.GetValue(null)!;
        var savedRemote = new List<DictionaryEntry>();
        foreach (DictionaryEntry entry in remote) savedRemote.Add(entry);
        var registryProperty = typeof(global::InfiniCrafterLocal.InfiniCrafterLocalMod).GetProperty("GeneratedItems")!;
        object? savedRegistry = registryProperty.GetValue(null);
        int savedLocal = Terraria.Main.myPlayer, savedMode = Terraria.Main.netMode;
        var failures = new List<string>();
        int checkedCases = 0;
        using var registry = new GeneratedItemRegistryService();
        void Check(string label, Action check)
        {
            checkedCases++;
            try { check(); }
            catch (Exception error) { failures.Add(label + ": " + error.Message); }
        }
        try
        {
            Terraria.Main.myPlayer = 0;
            Terraria.Main.netMode = Terraria.ID.NetmodeID.SinglePlayer; // decoder only, never sends sockets
            registryProperty.SetValue(null, registry);
            var byId = (IDictionary)typeof(GeneratedItemRegistryService).GetField("_byId", instance)!.GetValue(registry)!;
            foreach (string owner in new[] { RuntimeProgramSpec.ItemBodyOwner, RuntimeProgramSpec.ProjectileOwner })
            foreach (bool hide in new[] { false, true })
            foreach (string hint in new[] { "", "immediate", "on_release", "after_charge" })
            {
                var data = GeneratedItemData.Placeholder();
                data.Id = "visibility_contract_probe";
                data.Visual.SpritePath = System.IO.Path.Combine(Terraria.Program.SavePath, "visibility_probe.png");
                data.RuntimeProgram.PrimaryOwner = owner;
                data.RuntimeProgram.ItemUse.UseStyle = "thrust";
                data.RuntimeProgram.ItemUse.HideUseGraphic = hide;
                data.RuntimeProgram.ItemUse.ReleaseTiming = hint;
                if (newPresentation) data.Visual.RenderSizePx = 40;
                if (axisOnly) data.Visual.ForwardAngleDegrees = 0f;
                byId[data.Id] = data;
                var player = new Player { whoAmI = 0, itemAnimation = 8, itemAnimationMax = 20 };
                var item = new Item { type = 1, stack = 1, noUseGraphic = true, useStyle = Terraria.ID.ItemUseStyleID.Thrust };
                // noUseGraphic is deliberately true even when authored hide=false:
                // static proxy suppression is NOT semantic root visibility.
                var generated = new GeneratedItem();
                typeof(ModType<Item>).GetProperty("Entity", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)!.SetValue(generated, item);
                typeof(Item).GetProperty("ModItem")!.SetValue(item, generated);
                typeof(GeneratedItem).GetProperty("Data")!.SetValue(generated, data);
                player.inventory[0] = item;
                var layer = new GeneratedHeldItemDrawLayer();
                var info = new PlayerDrawSet { drawPlayer = player, heldItem = item };
                bool expected = hint == "immediate" ? false : hint is "on_release" or "after_charge" ? true : !newPresentation || !hide;
                string label = $"owner={owner} hide={hide} hint='{hint}' modern={newPresentation}";
                string unchanged = System.Text.Json.JsonSerializer.Serialize(data);
                remote.Clear();
                Check(label + " local", () => Equal(expected, layer.GetDefaultVisibility(info), "public held layer visibility"));
                Check(label + " local inactive", () => {
                    player.itemAnimation = 0;
                    Equal(false, layer.GetDefaultVisibility(info), "inactive remains hidden");
                    player.itemAnimation = 8;
                });
                player.whoAmI = 1;
                player.inventory[0] = new Item(); // registry-only remote fallback
                void Receive(bool active)
                {
                    using var packet = new System.IO.MemoryStream();
                    using (var writer = new System.IO.BinaryWriter(packet, System.Text.Encoding.UTF8, true))
                    {
                        writer.Write(4); writer.Write((byte)1); writer.Write((byte)0); writer.Write(data.Id);
                        writer.Write(120f); writer.Write(180f); writer.Write(0.4f);
                        writer.Write(1); writer.Write(1f); writer.Write(active); writer.Write((byte)200);
                    }
                    packet.Position = 0;
                    using var reader = new System.IO.BinaryReader(packet);
                    GeneratedHeldItemDrawLayer.HandleHeldItemPresentationSyncPacket(reader, 0);
                }
                Receive(true);
                Check(label + " remote", () => Equal(expected, layer.GetDefaultVisibility(info), "real v4 decoder + registry-only visibility"));
                Receive(false);
                Check(label + " remote inactive", () => Equal(false, layer.GetDefaultVisibility(info), "inactive packet remains hidden"));
                Check(label + " immutability", () => Equal(unchanged, System.Text.Json.JsonSerializer.Serialize(data), "visibility must not change gameplay/identity/hints"));
            }
        }
        finally
        {
            remote.Clear();
            foreach (DictionaryEntry entry in savedRemote) remote.Add(entry.Key, entry.Value);
            registryProperty.SetValue(null, savedRegistry);
            Terraria.Main.myPlayer = savedLocal; Terraria.Main.netMode = savedMode;
        }
        Console.WriteLine($"Visibility obligations modern={newPresentation}: {checkedCases - failures.Count}/{checkedCases}");
        if (failures.Count != 0) throw new InvalidOperationException(string.Join(Environment.NewLine, failures));
    }

    public static void HeldPresentationGeometryMatchesEngine()
    {
        WithLighting((_, _) =>
        {
            const BindingFlags instance = BindingFlags.Instance | BindingFlags.NonPublic;
            const BindingFlags statics = BindingFlags.Static | BindingFlags.NonPublic;
            var texture = (Texture2D)RuntimeHelpers.GetUninitializedObject(typeof(Texture2D));
            var batch = (SpriteBatch)RuntimeHelpers.GetUninitializedObject(typeof(SpriteBatch));
            GC.SuppressFinalize(texture);
            GC.SuppressFinalize(batch);
            typeof(Texture2D).GetProperty("Width")!.SetValue(texture, 64);
            typeof(Texture2D).GetProperty("Height")!.SetValue(texture, 40);
            foreach (string name in new[] { "vertexInfo", "textureInfo", "spriteInfos", "sortedSpriteInfos" })
            {
                var field = typeof(SpriteBatch).GetField(name, instance)!;
                field.SetValue(batch, Array.CreateInstance(field.FieldType.GetElementType()!, 16));
            }
            var queued = typeof(SpriteBatch).GetField("numSprites", instance)!;
            int submitted = 0;
            using var flush = new MonoMod.RuntimeDetour.Hook(typeof(SpriteBatch).GetMethod("FlushBatch", instance)!,
                (Action<SpriteBatch>)(self => { submitted += (int)queued.GetValue(self)!; queued.SetValue(self, 0); }));
            var sprites = typeof(global::InfiniCrafterLocal.InfiniCrafterLocalMod).GetProperty("Sprites")!;
            object? previousCache = sprites.GetValue(null);
            var registries = typeof(global::InfiniCrafterLocal.InfiniCrafterLocalMod).GetProperty("GeneratedItems")!;
            object? previousRegistry = registries.GetValue(null);
            using var registry = new GeneratedItemRegistryService();
            var remote = (IDictionary)typeof(GeneratedHeldItemDrawLayer).GetField("RemoteHeldPresentations", statics)!.GetValue(null)!;
            var previousRemote = new List<DictionaryEntry>();
            foreach (DictionaryEntry entry in remote) previousRemote.Add(entry);
            Vector2 previousScreen = Terraria.Main.screenPosition;
            int previousMyPlayer = Terraria.Main.myPlayer;
            var cache = new RuntimeSpriteCache();
            var textures = (IDictionary)typeof(RuntimeSpriteCache).GetField("_textures", instance)!.GetValue(cache)!;
            var record = typeof(RuntimeSpriteCache).GetNestedType("CachedTexture", BindingFlags.NonPublic)!;
            string path = System.IO.Path.Combine(Terraria.Program.SavePath, "held_geometry_cpu.png");
            textures.Add(path, Activator.CreateInstance(record, texture, 0f, 0L)!);
            var layer = new GeneratedHeldItemDrawLayer();
            var draw = typeof(GeneratedHeldItemDrawLayer).GetMethod("Draw", instance)!;
            var failures = new List<string>();
            int cases = 0;
            try
            {
                sprites.SetValue(null, cache);
                Terraria.Main.myPlayer = 0;
                var player = new Player { whoAmI = 0, position = new Vector2(320, 480), itemAnimation = 12, itemAnimationMax = 20 };
                var data = GeneratedItemData.Placeholder();
                data.Id = "held_geometry_exact_identity";
                data.Visual.SpritePath = path;
                data.RuntimeProgram.ItemUse.ReleaseTiming = "";
                data.RuntimeProgram.ItemUse.HandPose = "";
                // Generic pose has no role translation: isolate engine coordinates from
                // existing artistic grip constants. Other roles are tested below too.
                data.RuntimeProgram.ItemUse.UseStyle = "eat_food";
                var item = new Item();
                item.SetDefaults(Terraria.ID.ItemID.WoodenSword);
                item.noUseGraphic = true;
                var generated = new GeneratedItem();
                typeof(ModType<Item>).GetProperty("Entity", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)!.SetValue(generated, item);
                typeof(Item).GetProperty("ModItem")!.SetValue(item, generated);
                typeof(GeneratedItem).GetProperty("Data")!.SetValue(generated, data);
                player.inventory[0] = item;
                DrawData Render(Vector2 location)
                {
                    string authored = System.Text.Json.JsonSerializer.Serialize(data);
                    var info = new PlayerDrawSet { drawPlayer = player, heldItem = item, ItemLocation = location, DrawDataCache = new List<DrawData>() };
                    object[] args = { info };
                    draw.Invoke(layer, args);
                    info = (PlayerDrawSet)args[0];
                    Equal(1, info.DrawDataCache.Count, "one generated draw entry");
                    DrawData result = info.DrawDataCache[0];
                    batch.Begin();
                    result.Draw(batch);
                    Equal(1, (int)queued.GetValue(batch)!, "real FNA queues generated DrawData");
                    batch.End();
                    Equal(authored, System.Text.Json.JsonSerializer.Serialize(data), "drawing preserves exact authored parameters and identity");
                    return result;
                }
                void Check(string label, Action check)
                {
                    cases++;
                    try { check(); }
                    catch (Exception error) { failures.Add(label + ": " + error.Message); }
                }
                foreach (int direction in new[] { -1, 1 })
                foreach (float gravity in new[] { -1f, 1f })
                foreach (float scale in new[] { 0.25f, 1f, 4f })
                {
                    player.direction = direction;
                    player.gravDir = gravity;
                    player.itemRotation = 0.63f;
                    player.itemLocation = new Vector2(99, 177); // must not override drawInfo
                    item.scale = 1.2f; // independent prefix/global-style scale multiplier
                    data.Gameplay.ItemScale = scale;
                    Terraria.Main.screenPosition = new Vector2(40, 60);
                    string label = $"direction={direction} gravity={gravity} authoredScale={scale}";
                    DrawData result = Render(new Vector2(140, 260));
                    Check(label + " rotation", () => Equal(player.itemRotation, result.rotation, "engine already owns gravity rotation"));
                    Check(label + " scale", () => Equal(new Vector2(player.GetAdjustedItemScale(item)), result.scale, "exact adjusted item scale, once"));
                    Check(label + " position", () => Equal(new Vector2(100, 200), result.position, "drawInfo world location is authoritative"));
                    SpriteEffects expectedEffects = (direction < 0 ? SpriteEffects.FlipHorizontally : SpriteEffects.None) |
                        (gravity < 0 ? SpriteEffects.FlipVertically : SpriteEffects.None);
                    Check(label + " effects", () => Equal((int)expectedEffects, (int)result.effect, "facing and gravity flips retained"));
                    Vector2 expectedOrigin = new(64 * (direction < 0 ? 1f - 0.20f : 0.20f), 40 * (gravity < 0 ? 1f - 0.62f : 0.62f));
                    Check(label + " grip", () => Equal(expectedOrigin, result.origin, "existing grip is not redesigned"));
                }
                HeldRenderSizeUsesFinalFrameAndAdjustedScale(Render, data, player, item, texture);
                data.Gameplay.ItemScale = 1f;
                item.scale = 1f;
                player.direction = 1;
                player.gravDir = 1f;
                // Legitimate world zero and camera-origin positions are not absence sentinels.
                Terraria.Main.screenPosition = new Vector2(40, 60);
                Check("world zero", () => Equal(new Vector2(-40, -60), Render(Vector2.Zero).position, "zero drawInfo location retained"));
                Terraria.Main.screenPosition = new Vector2(140, 260);
                Check("screen zero", () => Equal(Vector2.Zero, Render(new Vector2(140, 260)).position, "camera origin is not a missing pose"));
                Terraria.Main.screenPosition = new Vector2(40, 60);
                foreach (var pose in new[] { ("swing", 2f, -1f), ("thrust", 8f, 0f), ("shoot", 5f, 0f), ("hold_up", 4f, 0f) })
                {
                    data.RuntimeProgram.ItemUse.UseStyle = pose.Item1;
                    Check(pose.Item1 + " existing role", () => Equal(new Vector2(100 + pose.Item2, 200 + pose.Item3), Render(new Vector2(140, 260)).position, "role forward offset unchanged"));
                }
                ExplicitGripDraws(Render, data, player);
                // Real vanilla Rapier use-style control supplies the itemRotation ->
                // composite-arm conversion. Use its Full-stretch phase; no weapon art
                // or animation style is chosen for generated items by this check.
                var vanilla = new Item();
                vanilla.SetDefaults(Terraria.ID.ItemID.WoodenSword);
                vanilla.useStyle = Terraria.ID.ItemUseStyleID.Rapier;
                foreach (string handPose in new[] { "one_handed", "two_handed" })
                foreach (int direction in new[] { -1, 1 })
                foreach (float gravity in new[] { -1f, 1f })
                foreach (float angle in new[] { -0.63f, 0f, 0.63f })
                {
                    var control = new Player { direction = direction, gravDir = gravity, itemRotation = angle, itemAnimation = 2, itemAnimationMax = 20 };
                    control.ItemCheck_ApplyUseStyle(0f, vanilla, new Rectangle(0, 0, 64, 40));
                    player.direction = direction; player.gravDir = gravity; player.itemRotation = angle;
                    data.RuntimeProgram.ItemUse.HandPose = handPose;
                    generated.UseStyle(player, new Rectangle(0, 0, 64, 40));
                    string label = $"hand={handPose} direction={direction} gravity={gravity} angle={angle}";
                    Check(label + " front", () => Equal(control.compositeFrontArm.rotation, player.compositeFrontArm.rotation, "same engine angle conversion"));
                    Check(label + " stretch", () => Equal((int)control.compositeFrontArm.stretch, (int)player.compositeFrontArm.stretch, "existing full stretch retained"));
                    if (handPose == "two_handed")
                        Check(label + " back", () => Equal(control.compositeFrontArm.rotation, player.compositeBackArm.rotation, "back arm uses same engine angle conversion"));
                }
                var sentinel = player.compositeFrontArm;
                data.RuntimeProgram.ItemUse.HandPose = "";
                player.itemRotation += 0.2f;
                generated.UseStyle(player, new Rectangle(0, 0, 64, 40));
                Equal(sentinel.rotation, player.compositeFrontArm.rotation, "empty hand hint preserves vanilla arm");
                data.RuntimeProgram.ItemUse.HandPose = "one_handed";
                player.itemAnimation = 0;
                generated.UseStyle(player, new Rectangle(0, 0, 64, 40));
                Equal(sentinel.rotation, player.compositeFrontArm.rotation, "inactive use does not override arm");
                player.itemAnimation = 12;
                data.RuntimeProgram.ItemUse.HandPose = "";
                Equal("held_geometry_exact_identity", generated.Data.Id, "definition identity unchanged");
                Equal(true, ReferenceEquals(item, player.HeldItem), "live held instance unchanged");
                // Exercise the actual v4 decoder and registry-only remote draw, not a
                // second geometry implementation or a fabricated successful network send.
                registries.SetValue(null, registry);
                ((IDictionary)typeof(GeneratedItemRegistryService).GetField("_byId", instance)!.GetValue(registry)!).Add(data.Id, data);
                remote.Clear();
                player.whoAmI = 1;
                player.inventory[0] = new Item();
                data.RuntimeProgram.ItemUse.UseStyle = "eat_food";
                void Receive(Vector2 location)
                {
                    using var packet = new System.IO.MemoryStream();
                    using (var writer = new System.IO.BinaryWriter(packet, System.Text.Encoding.UTF8, true))
                    {
                        writer.Write(4); writer.Write((byte)1); writer.Write((byte)0); writer.Write(data.Id);
                        writer.Write(location.X); writer.Write(location.Y); writer.Write(-0.37f);
                        writer.Write(-1); writer.Write(-1f); writer.Write(true); writer.Write((byte)200);
                    }
                    packet.Position = 0;
                    using var reader = new System.IO.BinaryReader(packet);
                    GeneratedHeldItemDrawLayer.HandleHeldItemPresentationSyncPacket(reader, 0);
                }
                foreach (float scale in new[] { 0.25f, 1f, 4f })
                {
                    data.Gameplay.ItemScale = scale;
                    Receive(Vector2.Zero);
                    DrawData result = Render(new Vector2(140, 260));
                    Check("registry scale " + scale, () => Equal(new Vector2(scale), result.scale, "same authored scale without live ModItem"));
                    Check("remote zero", () => Equal(new Vector2(-40, -60), result.position, "decoded world zero retained"));
                    Check("remote rotation", () => Equal(-0.37f, result.rotation, "decoded rotation not re-inverted"));
                    Check("remote effects", () => Equal((int)(SpriteEffects.FlipHorizontally | SpriteEffects.FlipVertically), (int)result.effect, "decoded facing/gravity override local state"));
                }
                var legacyRemoteVisual = data.Visual;
                foreach (int canvas in new[] { 64, 128 })
                foreach (int size in new[] { 1, 40, 512 })
                foreach (float scale in new[] { 0.25f, 1f, 4f })
                {
                    typeof(Texture2D).GetProperty("Width")!.SetValue(texture, canvas); typeof(Texture2D).GetProperty("Height")!.SetValue(texture, canvas * 5 / 8);
                    data.Visual = new VisualSpec { SpritePath = path, RenderSizePx = size }; data.Gameplay.ItemScale = scale;
                    Receive(Vector2.Zero);
                    Equal(new Vector2(scale * (size / (float)canvas)), Render(Vector2.Zero).scale, "registry-only decoded pose uses canonical root R and G");
                }
                data.Visual = legacyRemoteVisual;
                typeof(Texture2D).GetProperty("Width")!.SetValue(texture, 64); typeof(Texture2D).GetProperty("Height")!.SetValue(texture, 40);
                foreach (float invalid in new[] { float.NaN, float.PositiveInfinity, 2_000_001f })
                {
                    Receive(new Vector2(invalid, 0));
                    Check("invalid remote location " + invalid, () => Equal(new Vector2(100, 200), Render(new Vector2(140, 260)).position, "invalid packet location uses valid drawInfo, not an invented grip"));
                }
                data.Visual.Grip = new ItemGripSpec { NormalizedX = 0.25, NormalizedY = 0.75 };
                Receive(new Vector2(140, 260));
                Equal(new Vector2(48, 10), Render(Vector2.Zero).origin, "decoded pose uses registry explicit grip");
                var compact = GeneratedItemData.FromPlayerSaveJson(data.ToPlayerSaveJson())!;
                typeof(GeneratedItem).GetProperty("Data")!.SetValue(generated, compact);
                player.inventory[0] = item;
                var beforeCompactSizing = data.Visual;
                data.Visual = new VisualSpec { SpritePath = path, Grip = beforeCompactSizing.Grip!, RenderSizePx = 40 };
                Equal(new Vector2(player.GetAdjustedItemScale(item) * (40f / 64f)), Render(Vector2.Zero).scale, "compact held reference borrows canonical root size, not inert reference metadata");
                data.Visual = beforeCompactSizing;
                Equal(new Vector2(48, 10), Render(Vector2.Zero).origin, "compact held save reference resolves registry grip");
                typeof(GeneratedItem).GetProperty("Data")!.SetValue(generated, data);
                Equal(true, ReferenceEquals(data, registry.TryGet(data.Id, out var resolved) ? resolved : null), "registry definition identity retained");
                Equal(true, submitted > 0, "real FNA batches reached CPU/GPU boundary");
                Console.WriteLine($"Held presentation geometry: {cases - failures.Count}/{cases} assertions; {submitted} real DrawData/FNA submissions");
            }
            finally
            {
                textures.Clear(); // never Dispose constructor-bypassed GPU resources
                sprites.SetValue(null, previousCache);
                registries.SetValue(null, previousRegistry);
                remote.Clear();
                foreach (DictionaryEntry entry in previousRemote) remote.Add(entry.Key, entry.Value);
                Terraria.Main.screenPosition = previousScreen;
                Terraria.Main.myPlayer = previousMyPlayer;
            }
            if (failures.Count != 0) throw new InvalidOperationException(string.Join(Environment.NewLine, failures));
        });
    }
}

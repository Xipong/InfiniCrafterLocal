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
                foreach (float invalid in new[] { float.NaN, float.PositiveInfinity, 2_000_001f })
                {
                    Receive(new Vector2(invalid, 0));
                    Check("invalid remote location " + invalid, () => Equal(new Vector2(100, 200), Render(new Vector2(140, 260)).position, "invalid packet location uses valid drawInfo, not an invented grip"));
                }
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

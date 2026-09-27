using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Common.VFX;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    // Real item hooks -> exact slot -> detached queue -> real FNA Begin/Draw/End.
    // Only FlushBatch is intercepted at the GPU boundary. No game or sockets.
    public static void ItemImpactSpriteUsesDetachedRenderer()
    {
        WithLighting((config, _) =>
        {
            const BindingFlags instance = BindingFlags.Instance | BindingFlags.NonPublic;
            const BindingFlags statics = BindingFlags.Static | BindingFlags.NonPublic;
            var system = new InfiniDetachedVfxSystem();
            var systemType = typeof(InfiniDetachedVfxSystem);
            var emissions = (IList)systemType.GetField("Emissions", statics)!.GetValue(null)!;
            var wrapper = systemType.GetMethod("DrawProjectiles", statics)!;
            var clock = typeof(Terraria.Main).GetField("_gameUpdateCount", statics)!;
            object oldTick = clock.GetValue(null)!;
            int oldMode = Terraria.Main.netMode, oldLocal = Terraria.Main.myPlayer;
            bool oldDedicated = Terraria.Main.dedServ;
            var oldPlayer = Terraria.Main.player[0];
            var oldBatch = Terraria.Main.spriteBatch;
            var oldView = Terraria.Main.GameViewMatrix;
            var oldScreen = Terraria.Main.screenPosition;
            var sprites = typeof(global::InfiniCrafterLocal.InfiniCrafterLocalMod).GetProperty("Sprites")!;
            object? oldCache = sprites.GetValue(null);
            var cache = new RuntimeSpriteCache();
            var textures = (IDictionary)typeof(RuntimeSpriteCache).GetField("_textures", instance)!.GetValue(cache)!;
            var recordType = typeof(RuntimeSpriteCache).GetNestedType("CachedTexture", BindingFlags.NonPublic)!;
            string path = Path.Combine(Terraria.Program.SavePath, "item_impact_cpu.png");

            // Constructor-bypassed CPU shells: no GraphicsDevice/resources allocated.
            var batch = (SpriteBatch)System.Runtime.CompilerServices.RuntimeHelpers.GetUninitializedObject(typeof(SpriteBatch));
            var texture = (Texture2D)System.Runtime.CompilerServices.RuntimeHelpers.GetUninitializedObject(typeof(Texture2D));
            GC.SuppressFinalize(batch); GC.SuppressFinalize(texture);
            foreach (string field in new[] { "vertexInfo", "textureInfo", "spriteInfos", "sortedSpriteInfos" })
            {
                var info = typeof(SpriteBatch).GetField(field, instance)!;
                info.SetValue(batch, Array.CreateInstance(info.FieldType.GetElementType()!, 16));
            }
            typeof(Texture2D).GetProperty("Width")!.SetValue(texture, 16);
            typeof(Texture2D).GetProperty("Height")!.SetValue(texture, 24);
            var begun = typeof(SpriteBatch).GetField("beginCalled", instance)!;
            var queued = typeof(SpriteBatch).GetField("numSprites", instance)!;
            var drains = new List<int>();
            Color? expectedVertexColor = null;
            void CheckVertexColors(object value)
            {
                if (value is Color color) { Equal(expectedVertexColor!.Value, color, "detached blend reaches real FNA vertex color"); return; }
                foreach (var field in value.GetType().GetFields(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic))
                    if (field.FieldType == typeof(Color) || (field.FieldType.IsValueType && !field.FieldType.IsPrimitive && !field.FieldType.IsEnum))
                        CheckVertexColors(field.GetValue(value)!);
            }
            Action<SpriteBatch> flush = self => {
                Equal(true, ReferenceEquals(batch, self), "isolated batch at GPU boundary");
                Equal(false, (bool)begun.GetValue(self)!, "real End closes item sprite batch");
                int count = (int)queued.GetValue(self)!;
                var drawnTextures = (Array)typeof(SpriteBatch).GetField("textureInfo", instance)!.GetValue(self)!;
                for (int i = 0; i < count; i++)
                    Equal(true, ReferenceEquals(texture, drawnTextures.GetValue(i)), "real FNA queue contains dedicated impact texture");
                if (expectedVertexColor.HasValue)
                {
                    var vertices = (Array)typeof(SpriteBatch).GetField("vertexInfo", instance)!.GetValue(self)!;
                    for (int i = 0; i < count; i++) CheckVertexColors(vertices.GetValue(i)!);
                }
                drains.Add(count);
                queued.SetValue(self, 0);
            };
            using var flushHook = new MonoMod.RuntimeDetour.Hook(typeof(SpriteBatch).GetMethod("FlushBatch", instance)!, flush);
            // Fail on any dust downgrade, including the missing-asset path.
            Func<Vector2, int, Vector2?, int, Color, float, Dust> rejectDust = (p, t, v, a, c, s) =>
                throw new InvalidOperationException("impactSprite must not invoke Dust.NewDustPerfect");
            using var dustHook = new MonoMod.RuntimeDetour.Hook(typeof(Dust).GetMethod("NewDustPerfect")!, rejectDust);
            try
            {
                system.OnWorldUnload();
                clock.SetValue(null, 100u);
                Terraria.Main.netMode = NetmodeID.MultiplayerClient;
                Terraria.Main.myPlayer = 0;
                Terraria.Main.spriteBatch = batch;
                Terraria.Main.GameViewMatrix = new Terraria.Graphics.SpriteViewMatrix(null!);
                Terraria.Main.GameViewMatrix.SetViewportOverride(new Viewport(0, 0, 800, 600));
                Terraria.Main.screenPosition = new Vector2(40, 60);
                sprites.SetValue(null, cache);
                object cached = Activator.CreateInstance(recordType, texture, 0.25f, 0L)!;
                textures.Add(path, cached);
                config.DrawBudgetMultiplier = 1f;
                config.ParticleSpawnMultiplier = 1f;
                var player = Terraria.Main.player[0] = new Player {
                    active = true, whoAmI = 0, Center = new Vector2(160, 240), velocity = new Vector2(0, 2),
                };
                var data = GeneratedItemData.Placeholder();
                var entity = data.RuntimeProgram.TryGetEntity(data.RuntimeProgram.ItemEntityId)!;
                entity.Visual.ImpactSpritePath = path;
                data.Visual.SpritePath = "must_not_use_inventory.png";
                entity.Visual.SpritePath = "must_not_use_entity.png";
                var binding = new RuntimeBindingSpec { Input = RuntimeInputKind.PrimaryUse,
                    UsePolicy = new RuntimeBindingUsePolicySpec { ContactDamage = true,
                        Action = new RuntimeBindingActionSpec { Kind = RuntimeBindingAction.UseItemBody, TargetId = entity.Id } } };
                data.RuntimeProgram.Bindings = new[] { binding };
                var slot = new VfxSlotSpec {
                    Id = "item_impact", EntityId = entity.Id, Event = RuntimeEventKind.OnUse,
                    RendererKind = "impactSprite", TextureRole = "impact", Duration = 15,
                    Layer = "AfterProjectiles", Scale = 1.75f, Alpha = 0.6f,
                };
                data.VfxManifest.Slots = new[] { slot };
                data.VfxManifest.Motif.Element = "fire";
                data.VfxManifest.Budget.MaxDrawCalls = 1;
                data.VfxManifest.Budget.MaxParticlesPerTick = 0;
                data.VfxManifest.Budget.MaxParticlesTotal = 0;
                var item = player.inventory[0] = new Item { type = ItemID.CopperShortsword, stack = 1 };
                var generated = new GeneratedItem();
                typeof(ModType<Item>).GetProperty("Entity")!.SetValue(generated, item);
                typeof(GeneratedItem).GetProperty("Data")!.SetValue(generated, data);
                typeof(Item).GetProperty("ModItem")!.SetValue(item, generated);
                void Emit() => InfiniItemVfxRuntime.EmitAndSyncEvent(player, data, entity.Id, slot.Event);
                T Field<T>(string name) => (T)emissions[0]!.GetType().GetProperty(name)!.GetValue(emissions[0])!;
                string Draw()
                {
                    drains.Clear();
                    On_Main.orig_DrawProjectiles orig = _ => {
                        Equal(false, (bool)begun.GetValue(batch)!, "item under batch ends before vanilla callback");
                        batch.Begin(); batch.End();
                    };
                    wrapper.Invoke(null, new object?[] { orig, null });
                    Equal(false, (bool)begun.GetValue(batch)!, "item over batch ends after vanilla callback");
                    return string.Join(",", drains);
                }

                Equal(true, generated.UseItem(player) == true, "real owner-client item use succeeds");
                Equal(1, emissions.Count, "item on_use must enqueue its authored impact sprite, not dust");
                Equal(path, Field<string>("TexturePath"), "exact item impact path");
                Equal(slot.Layer, Field<string>("Layer"), "authored layer");
                Equal(slot.Scale, Field<float>("Scale"), "authored scale");
                Equal(slot.Alpha, Field<float>("Alpha"), "authored alpha");
                Equal(Color.OrangeRed, Field<Color>("Color"), "same authored motif color as projectile sprite renderer");
                Equal(slot.Duration, Field<int>("Duration"), "authored duration");
                Equal(1, Field<int>("MaxDrawCalls"), "unscaled authored budget");
                Equal(player.Center, Field<Vector2>("Center"), "captured event center");
                Equal(true, MathF.Abs(MathHelper.PiOver2 - Field<float>("Rotation")) < 0.0001f, "owner velocity orientation");
                Equal("0,1", Draw(), "actual owner item sprite draws in over layer");
                Equal("0,1", Draw(), "next render resets budget without advancing world tick");
                slot.Layer = "BeforeProjectiles";
                generated.UseItem(player);
                Equal(2, emissions.Count, "repeated events remain detached");
                Equal("1,0", Draw(), "one source shares budget across simultaneous events and layers");
                player.whoAmI = 1; Emit(); player.whoAmI = 0;
                Equal("2,0", Draw(), "different owner has independent budget");
                config.DrawBudgetMultiplier = 0f;
                Equal("0", Draw(), "client zero budget suppresses item sprite draws");
                config.DrawBudgetMultiplier = 1f;
                clock.SetValue(null, 115u);
                Equal("0", Draw(), "authored duration expires all detached sprites");
                Equal(0, emissions.Count, "expired item sprites pruned");

                // Wrong identity/event, inactive source, dedicated server: no enqueue.
                InfiniItemVfxRuntime.EmitAndSyncEvent(player, data, "wrong_entity", slot.Event);
                InfiniItemVfxRuntime.EmitAndSyncEvent(player, data, entity.Id, RuntimeEventKind.OnKill);
                player.active = false; Emit(); player.active = true;
                Terraria.Main.dedServ = true; Emit(); Terraria.Main.dedServ = false;
                Equal(0, emissions.Count, "item event guards preserved");
                entity.Visual.ImpactSpritePath = ""; Emit();
                Equal(0, emissions.Count, "missing authored path has no inventory/entity/dust fallback");
                entity.Visual.ImpactSpritePath = path;
                textures.Remove(path); Emit();
                Equal("0", Draw(), "unavailable dedicated asset does not open a sprite batch");
                textures.Add(path, cached);
                system.OnWorldUnload();
                data.VfxManifest.Budget.MaxDrawCalls = 0; Emit();
                Equal("0", Draw(), "authored zero draw budget remains zero");
                data.VfxManifest.Budget.MaxDrawCalls = 1;

                // Real contact hooks choose exact hit/crit event, not a synthetic on_use.
                var target = new NPC { active = true };
                foreach (string eventName in new[] { RuntimeEventKind.OnHit, RuntimeEventKind.OnCrit })
                {
                    system.OnWorldUnload(); slot.Event = eventName;
                    generated.OnHitNPC(player, target, new NPC.HitInfo { Crit = eventName == RuntimeEventKind.OnCrit }, 1);
                    Equal(1, emissions.Count, "real owner contact hook emits exact " + eventName);
                    Equal("1,0", Draw(), "contact sprite reaches real FNA queue");
                }
                system.OnWorldUnload();
                generated.OnHitNPC(player, target, new NPC.HitInfo { Crit = false }, 1);
                Equal(0, emissions.Count, "noncrit hit cannot emit crit sprite");
                slot.Event = RuntimeEventKind.OnHit; binding.UsePolicy.ContactDamage = false;
                generated.OnHitNPC(player, target, new NPC.HitInfo { Crit = true }, 1);
                Equal(0, emissions.Count, "disabled item contact cannot emit hit sprite");
                binding.UsePolicy.ContactDamage = true;
                slot.Event = RuntimeEventKind.OnUse;

                // Socket-free client receipt exercises the real relay consumer.
                Terraria.Main.myPlayer = 1;
                using (var stream = new MemoryStream())
                {
                    using (var writer = new BinaryWriter(stream, System.Text.Encoding.UTF8, true))
                    { writer.Write((byte)2); writer.Write((byte)0); writer.Write(data.Id); writer.Write(entity.Id); writer.Write(slot.Event); }
                    stream.Position = 0;
                    using var reader = new BinaryReader(stream);
                    InfiniItemVfxRuntime.HandleUseEventPacket(reader, 0);
                }
                Equal(1, emissions.Count, "relayed remote item event uses same sprite consumer");
                Equal("1,0", Draw(), "relayed sprite reaches actual FNA queue");

                system.OnWorldUnload();
                Terraria.Main.netMode = NetmodeID.SinglePlayer; Terraria.Main.myPlayer = 0;
                generated.UseItem(player);
                Equal("1,0", Draw(), "single-player use also reaches the same sprite renderer");
                system.OnWorldUnload(); slot.Event = RuntimeEventKind.Periodic; slot.RepeatEvery = 6;
                clock.SetValue(null, 120u);
                InfiniItemVfxRuntime.OnPeriodic(player, data, entity.Id);
                Equal(1, emissions.Count, "item periodic sprite respects eligible cadence");
                Equal("1,0", Draw(), "periodic item sprite reaches real FNA queue");
                system.OnWorldUnload(); clock.SetValue(null, 121u);
                InfiniItemVfxRuntime.OnPeriodic(player, data, entity.Id);
                Equal(0, emissions.Count, "ineligible periodic cadence emits nothing");

                // Same impact helper serves item, active-projectile and detached events.
                // Observe the actual detached FNA color at emission and mid-lifetime.
                foreach (string blend in new[] { "alpha", "additive" })
                {
                    system.OnWorldUnload(); clock.SetValue(null, 200u);
                    slot.Event = RuntimeEventKind.OnUse; slot.Blend = blend;
                    Emit();
                    Color baseColor = Color.OrangeRed;
                    if (blend == "additive") baseColor.A = 0;
                    foreach (uint age in new uint[] { 0, 3 })
                    {
                        clock.SetValue(null, 200u + age);
                        expectedVertexColor = baseColor * (slot.Alpha * (1f - age / (float)slot.Duration));
                        Equal("1,0", Draw(), "detached authored blend draws at age " + age);
                    }
                    expectedVertexColor = null;
                }
            }
            finally
            {
                system.OnWorldUnload();
                Terraria.Main.netMode = oldMode; Terraria.Main.myPlayer = oldLocal; Terraria.Main.dedServ = oldDedicated;
                Terraria.Main.player[0] = oldPlayer; clock.SetValue(null, oldTick);
                sprites.SetValue(null, oldCache);
                Terraria.Main.spriteBatch = oldBatch; Terraria.Main.GameViewMatrix = oldView; Terraria.Main.screenPosition = oldScreen;
                textures.Clear(); cache.Dispose(); // shells must not dispose nonexistent GPU resources
            }
        });
    }
}

using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Text.Json;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.VFX;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    private static void ProjectileRawImpactKeepsLiteralNativePose()
    {
        var rows = new List<object>();
        WithPlayer((owner, _) => WithVfxGeometryQueue((batch, _, count, positions, _) => {
            using var actors = new NativeActorState(); using var cache = new BorrowedSpriteCache();
            var system = new InfiniDetachedVfxSystem();
            var queue = (IList)typeof(InfiniDetachedVfxSystem).GetField("Emissions", BindingFlags.Static | BindingFlags.NonPublic)!.GetValue(null)!;
            try {
                foreach (string mode in new[] { "stationary", "velocity", "spin" }) {
                    var data = MotionDefinition(mode == "spin" ? "{\"rotation\":{\"mode\":\"spin\",\"offsetRadians\":0,\"radiansPerUpdate\":0.25}}" : "{}");
                    var entity = data.RuntimeProgram.TryGetEntity(data.RuntimeProgram.PrimaryEntityId)!;
                    entity.Visual.ImpactSpritePath = Path.Combine(Terraria.Program.SavePath, "raw_impact_" + mode + ".png");
                    var selected = SpritePresentation.Resolve(data, entity.Id, "impact");
                    var texture = CpuTexture(64, 16); // signed asymmetric UV frame, not a circular ambiguity
                    cache.Textures.Add(selected.Path, Activator.CreateInstance(cache.Record, texture, 0f, 0L)!);
                    var actor = MotionActor(data, owner, mode == "velocity" ? new Vector2(3, 4) : Vector2.Zero);
                    foreach (bool updated in new[] { false, true }) {
                        Terraria.Main.dedServ = false;
                        if (updated) {
                            system.OnWorldUnload(); MaterialClock(101u);
                            float beforeAi = actor.Body.rotation;
                            data.VfxManifest = MotionImpactManifest(entity.Id, RuntimeEventKind.OnSpawn);
                            actor.Host.AI(); // Actual EmitSpawnEvent runs before the driver's first angular update.
                            Equal(1, queue.Count, "real first-AI on_spawn callback captures one impact");
                            float spawnAngle = (float)queue[0]!.GetType().GetProperty("Rotation")!.GetValue(queue[0])!;
                            Equal(beforeAi, spawnAngle, "on_spawn observes already initialized native pose, not an after-draw repair");
                            data.VfxManifest = VfxManifestSpec.Empty();
                        }
                        system.OnWorldUnload(); MaterialClock(updated ? 101u : 100u);
                        var manifest = MotionImpactManifest(entity.Id, updated ? RuntimeEventKind.OnKill : RuntimeEventKind.OnSpawn);
                        var state = new InfiniVfxState();
                        Equal(true, InfiniVfxRuntime.OnEvent(actor.Body, data, entity.Id, manifest.Slots[0].Event, manifest, ref state, actor.Body.Center), "actual raw impact event emitted");
                        Equal(1, queue.Count, "one raw impact captured event");
                        object emission = queue[0]!;
                        float raw = (float)emission.GetType().GetProperty("Rotation")!.GetValue(emission)!;
                        Equal(actor.Body.rotation, raw, "impact event retains literal native angle, never invents PNG forward");
                        var periodic = MotionImpactManifest(entity.Id, RuntimeEventKind.Periodic);
                        state = new InfiniVfxState(); for (int i = 0; i < 4; i++) state.Push(actor.Body.Center);
                        int first = count();
                        typeof(InfiniVfxRuntime).GetMethod("DrawSelectedSpriteTrail", BindingFlags.Static | BindingFlags.NonPublic)!
                            .Invoke(null, new object?[] { texture, actor.Body, entity, selected, periodic, state, Color.White, periodic.Slots[0].Scale!.Value });
                        Equal(first + 1, count(), "actual asymmetrical impact UV quad");
                        MotionImpactQuad(batch, first, positions(first), actor.Body, texture, periodic.Slots[0].Scale!.Value, mode);
                        rows.Add(new { mode, updated, nativeAngle = actor.Body.rotation, capturedImpactAngle = raw,
                            centerX = actor.Body.Center.X, centerY = actor.Body.Center.Y,
                            velocityX = actor.Body.velocity.X, velocityY = actor.Body.velocity.Y });
                    }
                }
            } finally { system.OnWorldUnload(); }
        }));
        string? path = Environment.GetEnvironmentVariable("ICL_ANGLE_IMPACT_RECEIPT");
        if (!string.IsNullOrWhiteSpace(path)) File.WriteAllText(path, JsonSerializer.Serialize(rows, new JsonSerializerOptions { WriteIndented = true }));
    }
}

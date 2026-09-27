using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.VFX;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    // Optional offline observer, not a game screenshot or replacement renderer.
    public static void CaptureVfxPreview(string path)
    {
        var captures = new List<object>();
        WithVfxGeometryQueue((batch, texture, count, positions, colors) =>
        {
            var oldPixel = Terraria.GameContent.TextureAssets.MagicPixel;
            var clock = typeof(Terraria.Main).GetField("_gameUpdateCount", BindingFlags.Static | BindingFlags.NonPublic)!;
            object oldClock = clock.GetValue(null)!;
            var asset = (ReLogic.Content.Asset<Texture2D>)System.Runtime.CompilerServices.RuntimeHelpers.GetUninitializedObject(typeof(ReLogic.Content.Asset<Texture2D>));
            foreach (var field in asset.GetType().GetFields(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic))
                if (field.FieldType == typeof(Texture2D)) field.SetValue(asset, texture);
            asset.GetType().GetProperty("State")!.SetValue(asset, ReLogic.Content.AssetState.Loaded);
            try
            {
                Terraria.GameContent.TextureAssets.MagicPixel = asset;
                foreach (string kind in new[] { "beamLine", "wavyStrip", "fieldPulse", "orbitingMotes", "ghostArc", "historyRibbon", "tipTrail" })
                foreach (string blend in new[] { "alpha", "additive" })
                {
                    var data = new GeneratedItemData();
                    data.Visual.Palette = new[] { "cyan" };
                    data.Visual.EffectColor = "cyan";
                    var slot = new VfxSlotSpec { Id = "preview", EntityId = "probe", Event = RuntimeEventKind.Periodic,
                        RendererKind = kind, Scale = 1f, Alpha = 0.65f, Density = 0.5f, Spread = 0.5f,
                        Blend = blend, Layer = "BeforeProjectiles", ParticleSystemId = "none", RepeatEvery = 72, Duration = 72, SlotSeed = 17 };
                    var manifest = new VfxManifestSpec { Seed = 17, Slots = new[] { slot } };
                    manifest.Budget.MaxDrawCalls = 32;
                    var projectile = new Projectile { width = 24, height = 12, identity = 17, scale = 1f, velocity = new Vector2(3f, 0f) };
                    var state = new InfiniVfxState();
                    for (int tick = 0; tick < 92; tick++)
                    {
                        clock.SetValue(null, (uint)(1000 + tick));
                        // Controlled input motion only; no VFX geometry is synthesized here.
                        projectile.Center = new Vector2(140f + 12f * MathF.Sin(tick * 0.08f), 140f + 8f * MathF.Sin(tick * 0.13f));
                        InfiniVfxRuntime.OnTick(projectile, data, "probe", manifest, ref state);
                        if (tick < 20 || (tick - 20) % 6 != 0) continue;
                        state.DrawCallsThisFrame = 0; // same per-draw-frame allowance reset as the live producer
                        Equal(0, count(), "preview frame begins with empty queue");
                        InfiniVfxRuntime.Draw(projectile, data, "probe", manifest, ref state, Color.White, InfiniVfxDrawPass.UnderProjectile);
                        int queued = count();
                        Equal(true, queued > 0 && queued <= manifest.Budget.MaxDrawCalls, "preview uses bounded actual draws");
                        Equal(queued, state.DrawCallsThisFrame, "every captured quad charged to live draw budget");
                        var quads = new List<object>();
                        for (int i = 0; i < queued; i++)
                        {
                            var p = positions(i); var c = colors(i);
                            Equal(4, p.Length, "four real positions"); Equal(4, c.Length, "four real colors");
                            quads.Add(new { positions = p.Select(v => new[] { v.X, v.Y, v.Z }), colors = c.Select(v => new[] { (int)v.R, (int)v.G, (int)v.B, (int)v.A }) });
                        }
                        captures.Add(new { renderer = kind, blend, tick, worldTick = Terraria.Main.GameUpdateCount,
                            stateTick = state.Tick, scale = slot.Scale, alpha = slot.Alpha, repeatEvery = slot.RepeatEvery, duration = slot.Duration,
                            density = slot.Density, spread = slot.Spread, palette = data.Visual.Palette, effectColor = data.Visual.EffectColor,
                            center = new[] { projectile.Center.X, projectile.Center.Y }, screen = new[] { Terraria.Main.screenPosition.X, Terraria.Main.screenPosition.Y },
                            texture = new[] { texture.Width, texture.Height }, budget = manifest.Budget.MaxDrawCalls,
                            drawCalls = state.DrawCallsThisFrame, quads });
                        batch.End(); batch.Begin(); // only the fixture's GPU flush is intercepted
                    }
                }
            }
            finally { Terraria.GameContent.TextureAssets.MagicPixel = oldPixel; clock.SetValue(null, oldClock); }
        });
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(path))!);
        File.WriteAllText(path, JsonSerializer.Serialize(new {
            schema = "icl.offline-fna-quads.v1", label = "OFFLINE GEOMETRY / NOT GAME GPU",
            provenance = "Actual InfiniVfxRuntime.OnTick/Draw + FNA SpriteBatch CPU vertices; synthetic projectile and white 2x3 texture shell; GPU flush intercepted.",
            blendEquation = "premultiplied One / InverseSourceAlpha: dstRGB = srcRGB + dstRGB * (1-srcA); additive encoded by actual vertex A=0",
            assemblyMvid = typeof(InfiniVfxRuntime).Module.ModuleVersionId.ToString(), captures
        }, new JsonSerializerOptions { WriteIndented = true }));
        Console.WriteLine($"Captured {captures.Count} real FNA quad frames: {path}");
    }
}

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
            var asset = CpuTextureAsset(texture);
            try
            {
                Terraria.GameContent.TextureAssets.MagicPixel = asset;
                foreach (string kind in new[] { "line", "wave", "arc", "orbit" })
                foreach (string blend in new[] { "alpha", "additive" })
                {
                    var shape=ExplicitShape(kind);shape.ColorStart=Rgb(90,235,255);shape.ColorEnd=Rgb(255,120,30);
                    shape.OpacityStart=.65f;shape.OpacityEnd=0;
                    if(kind=="wave")shape.PhaseSpeedRadiansPerTick=.1f;
                    if(kind=="orbit")shape.RotationSpeedRadiansPerTick=.1f;
                    var center=new Vector2(140);
                    for (int tick = 0; tick < 92; tick++)
                    {
                        clock.SetValue(null, (uint)(1000 + tick));
                        // Controlled input motion only; no VFX geometry is synthesized here.
                        if (tick >= 72 || tick % 6 != 0) continue;
                        Equal(0, count(), "preview frame begins with empty queue");
                        int draws=0;
                        InfiniDetachedVfxSystem.DrawExplicitShape(texture,shape,new(center,Vector2.UnitX,Vector2.Zero),tick,72,blend,()=>++draws<=64);
                        int queued=count();Equal(true,queued>0&&queued<=64,"preview uses bounded actual shape draws");
                        var quads = new List<object>();
                        for (int i = 0; i < queued; i++)
                        {
                            var p = positions(i); var c = colors(i);
                            Equal(4, p.Length, "four real positions"); Equal(4, c.Length, "four real colors");
                            quads.Add(new { positions = p.Select(v => new[] { v.X, v.Y, v.Z }), colors = c.Select(v => new[] { (int)v.R, (int)v.G, (int)v.B, (int)v.A }) });
                        }
                        captures.Add(new { renderer = kind, blend, tick, worldTick = Terraria.Main.GameUpdateCount,
                            shape, center=new[]{center.X,center.Y},screen=new[]{Terraria.Main.screenPosition.X,Terraria.Main.screenPosition.Y},
                            texture=new[]{texture.Width,texture.Height},drawCalls=draws,quads });
                        batch.End(); batch.Begin(); // only the fixture's GPU flush is intercepted
                    }
                }
            }
            finally { Terraria.GameContent.TextureAssets.MagicPixel = oldPixel; clock.SetValue(null, oldClock); }
        });
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(path))!);
        File.WriteAllText(path, JsonSerializer.Serialize(new {
            schema = "icl.offline-fna-quads.v1", label = "OFFLINE GEOMETRY / NOT GAME GPU",
            provenance = "Actual InfiniDetachedVfxSystem.DrawExplicitShape + FNA SpriteBatch CPU vertices; explicit current shape and white 2x3 texture shell; GPU flush intercepted.",
            blendEquation = "premultiplied One / InverseSourceAlpha: dstRGB = srcRGB + dstRGB * (1-srcA); additive encoded by actual vertex A=0",
            assemblyMvid = typeof(InfiniVfxRuntime).Module.ModuleVersionId.ToString(), captures
        }, new JsonSerializerOptions { WriteIndented = true }));
        Console.WriteLine($"Captured {captures.Count} real FNA quad frames: {path}");
    }
}

using System;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.VFX;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using MonoMod.RuntimeDetour;
using Terraria;
using Terraria.GameContent;

// Native procedural VFX with the exact live GeneratedProjectile state. Artwork
// omission is explicit; no trail samples, geometry or physics are reconstructed.
internal sealed class WNativeActiveVfx : IDisposable
{
    const BindingFlags All = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static;
    delegate void TrailOriginal(Texture2D pixel, VfxManifestSpec manifest, ref InfiniVfxState state, Color color, float width);
    delegate void TrailObserver(TrailOriginal orig, Texture2D pixel, VfxManifestSpec manifest, ref InfiniVfxState state, Color color, float width);
    readonly Hook trail;
    readonly WNativeVisualGeometry? geometry;
    JsonArray draws = new();
    public JsonObject Frame { get; private set; } = new();

    public WNativeActiveVfx(bool artworkOwnsGeometry)
    {
        if (!artworkOwnsGeometry) geometry = new WNativeVisualGeometry();
        trail = new Hook(typeof(InfiniVfxRuntime).GetMethod("DrawTrail", All)!,
            (TrailObserver)((TrailOriginal orig, Texture2D pixel, VfxManifestSpec manifest, ref InfiniVfxState state, Color color, float width) => {
                var nativeState = state;
                var geometryRows = WNativeVisualGeometry.Capture(() => orig(pixel, manifest, ref nativeState, color, width));
                state = nativeState;
                var samples = new JsonArray();
                foreach (var point in state.CenterHistory.Take(state.HistoryCount)) samples.Add(WNativeVisualGeometry.Point(point));
                draws.Add(new JsonObject { ["sourceKey"] = state.SourceKey, ["historyCount"] = state.HistoryCount,
                    ["samples"] = samples, ["submittedSegments"] = geometryRows.Count, ["geometry"] = geometryRows,
                    ["nativeMagicPixel"] = ReferenceEquals(pixel, TextureAssets.MagicPixel.Value),
                    ["entrypoint"] = "InfiniVfxRuntime.Draw -> DrawTrail -> DrawHistory -> SpriteBatch.Draw (original)" });
            }));
        BeginFrame();
    }

    public void BeginFrame()
    {
        draws = new JsonArray();
        Frame = new JsonObject { ["historyRibbonDraws"] = draws, ["activeProjectilePasses"] = 0 };
    }

    public void Draw()
    {
        Main.spriteBatch.Begin(SpriteSortMode.Deferred, BlendState.AlphaBlend, SamplerState.PointClamp,
            DepthStencilState.None, Main.Rasterizer, null, Main.GameViewMatrix.TransformationMatrix);
        try {
            foreach (var projectile in Main.projectile.Where(p => p.active)) {
                if (projectile.ModProjectile is not GeneratedProjectile generated)
                    throw new NotSupportedException("Procedural projectile VFX scope requires generated projectiles");
                if (!generated.TryGetHitSource(out var data, out var entity))
                    throw new InvalidOperationException("Active generated projectile has no hydrated native source");
                var state = (InfiniVfxState)typeof(GeneratedProjectile).GetField("_vfxState", All)!.GetValue(generated)!;
                state.DrawCallsThisFrame = 0;
                InfiniDetachedVfxSystem.BeginActiveDraw(state.SourceKey);
                Color color = Lighting.GetColor((int)projectile.Center.X / 16, (int)projectile.Center.Y / 16);
                InfiniVfxRuntime.Draw(projectile, data, entity.Id, data.VfxManifest, ref state, color, InfiniVfxDrawPass.UnderProjectile);
                InfiniVfxRuntime.Draw(projectile, data, entity.Id, data.VfxManifest, ref state, color, InfiniVfxDrawPass.OverProjectile);
                typeof(GeneratedProjectile).GetField("_vfxState", All)!.SetValue(generated, state);
                Frame["activeProjectilePasses"] = Frame["activeProjectilePasses"]!.GetValue<int>() + 1;
            }
        } finally { Main.spriteBatch.End(); }
    }

    public void Dispose() { trail.Dispose(); geometry?.Dispose(); }
}

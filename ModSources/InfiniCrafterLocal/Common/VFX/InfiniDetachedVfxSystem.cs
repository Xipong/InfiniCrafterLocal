#nullable enable
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Common.Models;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using System;
using System.Collections.Generic;
using System.Linq;
using Terraria;
using Terraria.ModLoader;
using Terraria.GameContent;

namespace InfiniCrafterLocal.Common.VFX;

/// <summary>
/// World-owned presentation lifetime for event sprites. The queue is independent
/// of the source projectile, so an authored impact can finish after OnHit/OnKill
/// removes that projectile. Draw ownership is exact around Terraria's projectile
/// pass; this system never mutates gameplay state.
/// </summary>
public sealed partial class InfiniDetachedVfxSystem : ModSystem
{
    private const int MaxEmissions = 256;

    private sealed class DetachedEmission
    {
        public string SourceKey { get; init; } = "";
        public string TexturePath { get; init; } = "";
        // Immutable selected main-body size, never q*P and never a wire field.
        public int? RenderSizePx { get; init; }
        public InfiniVfxRendererKind PrimitiveKind { get; init; }
        public Vector2 Forward { get; init; }
        public float Density { get; init; }
        public float PhaseOffset { get; init; }
        public int RepeatEvery { get; init; }
        public string Layer { get; init; } = "BeforeProjectiles";
        public Vector2 Center { get; init; }
        public float Rotation { get; init; }
        public bool HasCapturedPose { get; init; }
        public SpriteEffects Effects { get; init; }
        public float Scale { get; init; } = 1f;
        public float Alpha { get; init; } = 1f;
        public Color Color { get; init; } = Color.White;
        public ulong StartUpdate { get; init; }
        public int Duration { get; init; } = 3;
        public int MaxDrawCalls { get; init; }
    }

    private static readonly List<DetachedEmission> Emissions = new();
    private static readonly Dictionary<string, int> DrawCallsBySource = new(StringComparer.Ordinal);
    private static readonly Dictionary<string, SourceParticleBudget> ParticleBudgetsBySource = new(StringComparer.Ordinal);

    private sealed class SourceParticleBudget
    {
        public ulong Tick { get; set; } = ulong.MaxValue;
        public int ThisTick { get; set; }
        public int Total { get; set; }
        public ulong LastSeenTick { get; set; }
    }

    public override void Load()
    {
        if (!Main.dedServ)
            On_Main.DrawProjectiles += DrawProjectiles;
    }

    public override void Unload()
    {
        if (!Main.dedServ)
            On_Main.DrawProjectiles -= DrawProjectiles;
        Clear();
    }

    public override void OnWorldUnload() => Clear();

    // Unlike PostUpdateWorld, this hook also runs on multiplayer clients.
    // Retire legacy snapshots and source budgets even when no Draw follows.
    public override void PostUpdateEverything()
    {
        if (!Main.dedServ) {
            UpdateMaterials();
            PruneExpired();
        }
    }

    internal static void Enqueue(
        string sourceKey,
        string texturePath,
        string layer,
        Vector2 center,
        float rotation,
        float scale,
        float alpha,
        Color color,
        int duration,
        int maxDrawCalls,
        InfiniVfxSpritePose? pose = null,
        int? renderSizePx = null)
    {
        if (Main.dedServ || string.IsNullOrWhiteSpace(sourceKey) || string.IsNullOrWhiteSpace(texturePath))
            return;
        PruneExpired();
        MakeRoomForLegacyEmission();
        Emissions.Add(new DetachedEmission
        {
            SourceKey = sourceKey,
            TexturePath = texturePath,
            RenderSizePx = renderSizePx,
            Layer = layer == "AfterProjectiles" ? "AfterProjectiles" : "BeforeProjectiles",
            Center = center,
            Rotation = rotation,
            // Captured body scale was clamped before the authored VFX multiplier.
            Scale = pose.HasValue ? scale : Math.Clamp(scale, 0.05f, 8f),
            HasCapturedPose = pose.HasValue,
            Effects = pose?.Effects ?? SpriteEffects.None,
            Alpha = Math.Clamp(alpha, 0f, 1f),
            Color = color,
            StartUpdate = Main.GameUpdateCount,
            Duration = Math.Clamp(duration, 3, 120),
            MaxDrawCalls = Math.Clamp(maxDrawCalls, 0, 512),
        });
    }

    internal static void EnqueuePrimitive(string sourceKey, InfiniVfxRendererKind kind, string layer,
        Vector2 center, Vector2 forward, float scale, float density, float phaseOffset,
        int repeatEvery, int duration, Color color, int maxDrawCalls)
    {
        if (Main.dedServ || string.IsNullOrWhiteSpace(sourceKey)) return;
        PruneExpired();
        MakeRoomForLegacyEmission();
        Emissions.Add(new DetachedEmission {
            SourceKey = sourceKey, PrimitiveKind = kind, Layer = layer, Center = center, Forward = forward,
            Scale = scale, Density = density, PhaseOffset = phaseOffset, RepeatEvery = repeatEvery,
            Color = color, StartUpdate = Main.GameUpdateCount, Duration = Math.Clamp(duration, 3, 120),
            MaxDrawCalls = Math.Clamp(maxDrawCalls, 0, 512),
        });
    }

    internal static bool TrySpendDetachedParticle(string sourceKey, int maxPerTick, int maxTotal)
    {
        if (string.IsNullOrWhiteSpace(sourceKey) || maxPerTick <= 0 || maxTotal <= 0)
            return false;
        ulong now = Main.GameUpdateCount;
        PruneParticleBudgets(now);
        if (!ParticleBudgetsBySource.TryGetValue(sourceKey, out SourceParticleBudget? budget))
        {
            budget = new SourceParticleBudget();
            ParticleBudgetsBySource[sourceKey] = budget;
        }
        if (budget.Tick != now)
        {
            budget.Tick = now;
            budget.ThisTick = 0;
        }
        budget.LastSeenTick = now;
        if (budget.ThisTick >= maxPerTick || budget.Total >= maxTotal)
            return false;
        budget.ThisTick++;
        budget.Total++;
        return true;
    }

    private static void DrawProjectiles(On_Main.orig_DrawProjectiles orig, Main self)
    {
        BeginDrawBudgetFrame();
        DrawingWorldPass=true;
        try{DrawLayer("BeforeProjectiles");orig(self);DrawLayer("AfterProjectiles");}
        finally{DrawingWorldPass=false;}
    }

    private static void DrawLayer(string layer)
    {
        if (Main.dedServ || OwnedRecordCount == 0)
            return;
        PruneExpired();
        // Vanilla DrawProjectiles owns its own Begin/End. These surrounding
        // layers therefore need separate batches with the same world transform.
        SpriteBatch batch = Main.spriteBatch;
        bool began = false;
        void EnsureBegin()
        {
            if (began) return;
            batch.Begin(SpriteSortMode.Deferred, BlendState.AlphaBlend, Main.DefaultSamplerState,
                DepthStencilState.None, Main.Rasterizer, null, Main.GameViewMatrix.TransformationMatrix);
            began = true;
        }
        try
        {
            if(MaterialPaths.Any(p=>p.Design.Layer==layer))DrawMaterialPaths(layer,batch.GraphicsDevice);
            // Authored PNG elements preserve texels, independent of vanilla's
            // configurable sampler. This batch is owned and ends before legacy.
            DrawMaterialSprites(layer,batch,()=>{
                if(began)return;
                batch.Begin(SpriteSortMode.Deferred,BlendState.AlphaBlend,SamplerState.PointClamp,DepthStencilState.None,Main.Rasterizer,null,Main.GameViewMatrix.TransformationMatrix);
                began=true;
            });
            if(began){began=false;batch.End();}
            foreach (DetachedEmission emission in Emissions)
            {
                if (!string.Equals(emission.Layer, layer, StringComparison.Ordinal))
                    continue;
                if (emission.PrimitiveKind != InfiniVfxRendererKind.None)
                {
                    float age = Main.GameUpdateCount - emission.StartUpdate;
                    float turns = age / Math.Max(1, emission.RepeatEvery > 0 ? emission.RepeatEvery : emission.Duration) + emission.PhaseOffset;
                    float phase = turns - MathF.Floor(turns);
                    InfiniVfxRuntime.DrawPrimitive(TextureAssets.MagicPixel.Value, emission.PrimitiveKind,
                        emission.Center - Main.screenPosition, emission.Forward, emission.Scale, emission.Density, phase,
                        emission.Color * (1f - age / emission.Duration), () => {
                            if (!SpendDraw(emission)) return false;
                            EnsureBegin();
                            return true;
                        });
                    continue;
                }
                Texture2D? texture = InfiniCrafterLocalMod.Sprites.TryGet(emission.TexturePath, out float localForwardRadians);
                if (texture is null || !SpendDraw(emission))
                    continue;
                EnsureBegin();
                float progress = Math.Clamp(
                    (Main.GameUpdateCount - emission.StartUpdate) / (float)Math.Max(1, emission.Duration),
                    0f,
                    1f);
                batch.Draw(
                    texture,
                    emission.Center - Main.screenPosition,
                    null,
                    emission.Color * (emission.Alpha * (1f - progress)),
                    emission.Rotation - (emission.HasCapturedPose ? 0f : localForwardRadians),
                    new Vector2(texture.Width * 0.5f, texture.Height * 0.5f),
                    emission.Scale * SpritePresentation.FrameScale(emission.RenderSizePx, texture.Width, texture.Height),
                    emission.Effects,
                    0f);
            }
        }
        finally
        {
            if (began)
                batch.End();
        }
    }

    private static bool SpendDraw(DetachedEmission emission)
    {
        return TrySpendSourceDraw(emission.SourceKey,emission.MaxDrawCalls,1);
    }

    private static bool DrawingWorldPass;
    internal static void BeginActiveDraw(string sourceKey)
    {
        if(!DrawingWorldPass&&sourceKey.Length>0)DrawCallsBySource.Remove(sourceKey);
    }
    private static void BeginDrawBudgetFrame()
    {
        // Called once by DrawProjectiles, not once per layer or simulation tick.
        DrawCallsBySource.Clear();
    }

    private static void PruneExpired()
    {
        ulong now = Main.GameUpdateCount;
        Emissions.RemoveAll(emission => now - emission.StartUpdate >= (ulong)emission.Duration);
        PruneParticleBudgets(now);
    }

    private static void PruneParticleBudgets(ulong now)
    {
        foreach (string stale in ParticleBudgetsBySource
            .Where(row => now - row.Value.LastSeenTick > (ulong)InfiniRuntimeLimits.MaxRuntimeLifetimeTicks)
            .Select(row => row.Key)
            .ToArray())
            ParticleBudgetsBySource.Remove(stale);
    }

    private static void Clear()
    {
        MaterialEventStream.Clear();
        InfiniItemVfxRuntime.ClearUseEventCaches();
        Content.Projectiles.GeneratedProjectile.ClearVfxEventSyncCaches();
        MaterialPaths.Clear();
        MaterialPathEffect?.Dispose();MaterialPathEffect=null;
        PeriodicElements.Clear();
        LastMaterialsTick=ulong.MaxValue;
        MaterialEmissions.Clear();
        Emissions.Clear();
        DrawCallsBySource.Clear();
        ParticleBudgetsBySource.Clear();
    }
}

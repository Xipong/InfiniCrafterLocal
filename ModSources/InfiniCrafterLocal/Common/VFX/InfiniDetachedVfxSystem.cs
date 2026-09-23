#nullable enable
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.Services;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using System;
using System.Collections.Generic;
using System.Linq;
using Terraria;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.VFX;

/// <summary>
/// World-owned presentation lifetime for event sprites. The queue is independent
/// of the source projectile, so an authored impact can finish after OnHit/OnKill
/// removes that projectile. Draw ownership is exact around Terraria's projectile
/// pass; this system never mutates gameplay state.
/// </summary>
public sealed class InfiniDetachedVfxSystem : ModSystem
{
    private const int MaxEmissions = 256;

    private sealed class DetachedEmission
    {
        public string SourceKey { get; init; } = "";
        public string TexturePath { get; init; } = "";
        public string Layer { get; init; } = "BeforeProjectiles";
        public Vector2 Center { get; init; }
        public float Rotation { get; init; }
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

    public override void PostUpdateWorld()
    {
        if (!Main.dedServ)
            PruneParticleBudgets(Main.GameUpdateCount);
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
        int maxDrawCalls)
    {
        if (Main.dedServ || string.IsNullOrWhiteSpace(sourceKey) || string.IsNullOrWhiteSpace(texturePath))
            return;
        PruneExpired();
        if (Emissions.Count >= MaxEmissions)
            Emissions.RemoveAt(0);
        Emissions.Add(new DetachedEmission
        {
            SourceKey = sourceKey,
            TexturePath = texturePath,
            Layer = layer == "AfterProjectiles" ? "AfterProjectiles" : "BeforeProjectiles",
            Center = center,
            Rotation = rotation,
            Scale = Math.Clamp(scale, 0.05f, 8f),
            Alpha = Math.Clamp(alpha, 0f, 1f),
            Color = color,
            StartUpdate = Main.GameUpdateCount,
            Duration = Math.Clamp(duration, 3, 120),
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
        DrawLayer("BeforeProjectiles");
        orig(self);
        DrawLayer("AfterProjectiles");
    }

    private static void DrawLayer(string layer)
    {
        if (Main.dedServ || Emissions.Count == 0)
            return;
        PruneExpired();
        // Vanilla DrawProjectiles owns its own Begin/End. These surrounding
        // layers therefore need separate batches with the same world transform.
        SpriteBatch batch = Main.spriteBatch;
        bool began = false;
        try
        {
            foreach (DetachedEmission emission in Emissions)
            {
                if (!string.Equals(emission.Layer, layer, StringComparison.Ordinal))
                    continue;
                Texture2D? texture = InfiniCrafterLocalMod.Sprites.TryGet(emission.TexturePath, out float localForwardRadians);
                if (texture is null || !SpendDraw(emission))
                    continue;
                if (!began)
                {
                    batch.Begin(SpriteSortMode.Deferred, BlendState.AlphaBlend, Main.DefaultSamplerState,
                        DepthStencilState.None, Main.Rasterizer, null, Main.GameViewMatrix.TransformationMatrix);
                    began = true;
                }
                float progress = Math.Clamp(
                    (Main.GameUpdateCount - emission.StartUpdate) / (float)Math.Max(1, emission.Duration),
                    0f,
                    1f);
                batch.Draw(
                    texture,
                    emission.Center - Main.screenPosition,
                    null,
                    emission.Color * (emission.Alpha * (1f - progress)),
                    emission.Rotation - localForwardRadians,
                    new Vector2(texture.Width * 0.5f, texture.Height * 0.5f),
                    emission.Scale,
                    SpriteEffects.None,
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
        int spent = DrawCallsBySource.TryGetValue(emission.SourceKey, out int value) ? value : 0;
        if (spent >= InfiniVfxClientOptions.EffectiveDrawBudget(emission.MaxDrawCalls))
            return false;
        DrawCallsBySource[emission.SourceKey] = spent + 1;
        return true;
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
        Emissions.Clear();
        DrawCallsBySource.Clear();
        ParticleBudgetsBySource.Clear();
    }
}

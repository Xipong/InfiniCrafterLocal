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
        LoadLibrary();
        if(!Main.dedServ)InfiniItemVfxRuntime.LoadItemHistory();
        if (!Main.dedServ)
            On_Main.DrawProjectiles += DrawProjectiles;
    }

    public override void Unload()
    {
        if (!Main.dedServ)
            On_Main.DrawProjectiles -= DrawProjectiles;
        if(!Main.dedServ)InfiniItemVfxRuntime.UnloadItemHistory();
        ClearLibrary(unload:true);
        Clear();
    }

    public override void OnWorldUnload() => Clear();

    // Unlike PostUpdateWorld, this hook also runs on multiplayer clients.
    // Retire source budgets even when no Draw follows.
    public override void PostUpdateEverything()
    {
        InfiniItemVfxRuntime.UpdatePendingItemEvents();
        if (!Main.dedServ) {
            InfiniItemVfxRuntime.PruneHeldHistory();
            UpdateMaterials();
            PruneExpired();
        }
    }

    internal static bool TrySpendDetachedParticle(string sourceKey, int maxPerTick, int maxTotal)
        => TrySpendDetachedParticles(sourceKey, maxPerTick, maxTotal, 1);

    internal static bool TrySpendDetachedParticles(string sourceKey, int maxPerTick, int maxTotal, int count)
    {
        if (string.IsNullOrWhiteSpace(sourceKey) || maxPerTick <= 0 || maxTotal <= 0 || count <= 0)
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
        if (count > maxPerTick - budget.ThisTick || count > maxTotal - budget.Total)
            return false;
        budget.ThisTick += count;
        budget.Total += count;
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
            DrawLibraryParticles(layer,batch.GraphicsDevice);
            if(MaterialPaths.Any(p=>p.Design.Layer==layer))DrawMaterialPaths(layer,batch.GraphicsDevice);
            DrawMeshShapes(layer,TextureAssets.MagicPixel.Value,batch.GraphicsDevice);
            DrawContours(layer,batch.GraphicsDevice);
            // Authored PNG elements preserve texels, independent of vanilla's
            // configurable sampler. This batch is owned and ends before explicit shape draws.
            DrawMaterialSprites(layer,batch,()=>{
                if(began)return;
                batch.Begin(SpriteSortMode.Deferred,BlendState.AlphaBlend,SamplerState.PointClamp,DepthStencilState.None,Main.Rasterizer,null,Main.GameViewMatrix.TransformationMatrix);
                began=true;
            });
            if(began){began=false;batch.End();}
            DrawShapes(layer,TextureAssets.MagicPixel.Value,EnsureBegin);

        }
        finally
        {
            if (began)
                batch.End();
        }
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
        ClearLibrary();
        MaterialEventStream.Clear();
        InfiniItemVfxRuntime.ClearUseEventCaches();
        Content.Projectiles.GeneratedProjectile.ClearVfxEventSyncCaches();
        MaterialPaths.Clear();
        Common.Systems.GeneratedPlacementLedgerSystem.RetirePlacedVfxSources();
        PeriodicElements.Clear();
        LastMaterialsTick=ulong.MaxValue;
        MaterialEmissions.Clear();
        ShapeEmissions.Clear();
        ContourEmissions.Clear();
        NativeCueEmissions.Clear();
        NativeEffectAdmissionTick = 0;
        NativeEffectParticlesThisTick = 0;
        DrawCallsBySource.Clear();
        ParticleBudgetsBySource.Clear();
        // SaveAndQuit calls OnWorldUnload on a worker. Retire all world-owned
        // CPU state before queuing any graphics work, and capture this exact
        // generation: a late callback must not dispose a new world's effect.
        BasicEffect? retiredEffect = System.Threading.Interlocked.Exchange(ref MaterialPathEffect, null);
        if (retiredEffect is not null)
            Main.QueueMainThreadAction(retiredEffect.Dispose);
    }
}

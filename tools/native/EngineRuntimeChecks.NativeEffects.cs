using System;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.VFX;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.Graphics.Renderers;
using Terraria.GameContent;
using Terraria.GameContent.Drawing;

internal static partial class EngineRuntimeChecks
{
    private static VfxSlotSpec NativeEffectSlot(string type = "goldCrossBurst") => new()
    {
        Id = "stock",
        EntityId = "unavailable_item",
        Event = "on_use",
        RendererKind = "nativeEffect",
        Anchor = "self",
        StartTick = 0,
        RepeatEvery = 0,
        NativeEffect = type is "rainbowBurst" or "shimmerStar" ? new()
        {
            Type = type,
            Movement = new()
            {
                X = 3,
                Y = -2
            }
        }

        : new()
        {
            Type = type
        }
    };
    private static void NativeEffectsStrictSelectorsAndAtomicBudgets()
    {
        Equal(ParticleOrchestraType.BlackLightningHit, VfxNativeEffects.Kind("darkLightningBurst"),
            "exact native lightning dispatcher; texture loading not simulated here");
        Equal(8, VfxNativeEffects.Cost("darkLightningBurst"), "conservative lightning cost");
        Equal(8, VfxNativeEffects.SpriteCount("darkLightningBurst"), "conservative lightning live reservation");
        foreach (var type in new[]
        {
            "goldCrossBurst",
            "rainbowBurst",
            "darkLightningBurst",
            "shimmerStar"
        })
        {
            var slot = NativeEffectSlot(type);
            var root = JsonNode.Parse(new VfxManifestSpec { Slots = new[] { slot }, Budget = new() { MaxParticlesPerTick = 64 } }.ToJson())!;
            Equal(true, VfxManifestSpec.FromJson(root.ToJsonString()).HasSlots, "stock effect accepted " + type);
            foreach (string field in new[]
            {
                "type"
            }.Concat(type is "rainbowBurst" or "shimmerStar" ? new[] { "movement" } : Array.Empty<string>()))
            {
                var bad = root.DeepClone();
                bad["slots"]![0]!["nativeEffect"]!.AsObject().Remove(field);
                Equal(false, VfxManifestSpec.FromJson(bad.ToJsonString()).HasSlots, "missing native effect " + field);
            }

            foreach (string field in new[]
            {
                "nativeEffect",
                "color",
                "duration",
                "alpha",
                "phaseOffset",
                "density",
                "blend"
            })
            {
                var bad = root.DeepClone();
                bad["slots"]![0]![field] = null;
                Equal(false, VfxManifestSpec.FromJson(bad.ToJsonString()).HasSlots, "native effect null/foreign " + field);
            }

            foreach (var budgetField in new[]
            {
                "maxParticlesPerTick",
                "maxParticlesTotal"
            })
            {
                var small = root.DeepClone();
                small["budget"]![budgetField] = VfxNativeEffects.Cost(type) - 1;
                Equal(false, VfxManifestSpec.FromJson(small.ToJsonString()).HasSlots, "unrenderable native recipe rejected " + budgetField);
                small["budget"]![budgetField] = VfxNativeEffects.Cost(type);
                Equal(true, VfxManifestSpec.FromJson(small.ToJsonString()).HasSlots, "exact native recipe cost accepted " + budgetField);
            }

            var invalid = root.DeepClone();
            invalid["slots"]![0]!["nativeEffect"]!["type"] = "ItemTransfer";
            Equal(false, VfxManifestSpec.FromJson(invalid.ToJsonString()).HasSlots, "unsafe orchestra selector rejected");
            invalid = root.DeepClone();
            invalid["slots"]![0]!["rendererKind"] = "nativeLight";
            Equal(false, VfxManifestSpec.FromJson(invalid.ToJsonString()).HasSlots, "foreign nativeEffect rejected before other validators");
            var clone = slot.NativeEffect!.Copy();
            if (slot.NativeEffect.Movement is { } movement)
            {
                movement.X = 22;
                Equal(3f, clone.Movement!.X, "movement snapshot immutable");
            }
        }

        var budgetClock = typeof(Terraria.Main).GetField("_gameUpdateCount", BindingFlags.Static | BindingFlags.NonPublic)!;
        object? budgetTime = budgetClock.GetValue(null);
        var system = new InfiniDetachedVfxSystem();
        try
        {
            system.OnWorldUnload();
            MaterialClock(120);
            Equal(false, InfiniDetachedVfxSystem.TrySpendDetachedParticles("atomic", 15, 99, 16), "one below whole burst refused");
            Equal(true, InfiniDetachedVfxSystem.TrySpendDetachedParticles("atomic", 16, 16, 16), "failed reservation spent nothing");
            Equal(false, InfiniDetachedVfxSystem.TrySpendDetachedParticle("atomic", 99, 16), "whole burst consumes total");
            Equal(false, InfiniDetachedVfxSystem.TrySpendDetachedParticles("other", 99, 15, 16), "total cannot partially reserve");
            Equal(true, InfiniDetachedVfxSystem.TrySpendDetachedParticles("other", 16, 16, 16), "exact total works after refusal");
        }
        finally
        {
            system.OnWorldUnload();
            budgetClock.SetValue(null, budgetTime);
        }
    }

    private static void NativeEffectsActualGoldBurstAndDelayedSnapshot()
    {
        WithLighting((config, _) =>
        {
            var oldDust = Terraria.Main.dust;
            var oldRandom = Terraria.Main.rand;
            var oldParticles = Terraria.Main.ParticleSystem_World_OverPlayers;
            var oldStars = TextureAssets.Star;
            var oldProjectiles = TextureAssets.Projectile;
            var oldProjectileFrames = Terraria.Main.projFrames;
            var oldMain = Terraria.Main.instance;
            bool menu = Terraria.Main.gameMenu, gen = WorldGen.gen;
            int mode = Terraria.Main.netMode, max = Terraria.Main.maxDustToDraw;
            int width = Terraria.Main.screenWidth, height = Terraria.Main.screenHeight;
            Vector2 screen = Terraria.Main.screenPosition;
            float dCount = Dust.dCount;
            var clock = typeof(Terraria.Main).GetField("_gameUpdateCount", BindingFlags.Static | BindingFlags.NonPublic)!;
            object? previous = clock.GetValue(null);
            var system = new InfiniDetachedVfxSystem();
            try
            {
                system.OnWorldUnload();
                Terraria.Main.gameMenu = false;
                WorldGen.gen = false;
                Terraria.Main.netMode = 0;
                Terraria.Main.maxDustToDraw = 6000;
                Terraria.Main.screenWidth = 800;
                Terraria.Main.screenHeight = 600;
                Terraria.Main.screenPosition = Vector2.Zero;
                Terraria.Main.dust = Enumerable.Range(0, 6001).Select(i => new Dust { dustIndex = i }).ToArray();
                Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(7);
                Dust.dCount = 0;
                Terraria.Main.ParticleSystem_World_OverPlayers = new ParticleRenderer();
                config.ParticleSpawnMultiplier = 1;
                MaterialClock(100);
                var data = GeneratedItemData.Placeholder();
                var slot = NativeEffectSlot();
                slot.StartTick = 2;
                data.VfxManifest = new()
                {
                    Slots = new[]
                    {
                        slot
                    }
                };
                data.VfxManifest.Budget.MaxParticlesPerTick = 16;
                data.VfxManifest.Budget.MaxParticlesTotal = 16;
                var frame = new VfxSourceFrame(new Vector2(100, 120), Vector2.UnitY, new Vector2(4, 0));
                var allowance = new MaterialEventAllowance(15);
                InfiniDetachedVfxSystem.EnqueueSnapshotVfx(data, slot.EntityId, slot, "stock-gold", frame, itemBudget: true, allowance: allowance);
                MaterialClock(102);
                system.PostUpdateEverything();
                Equal(0, Terraria.Main.ParticleSystem_World_OverPlayers.Particles.Count, "event allowance atomic refusal");
                Equal(15, allowance.Remaining, "allowance not partly spent");
                allowance.Remaining = 16;
                slot.StartTick = 2;
                MaterialClock(103);
                InfiniDetachedVfxSystem.EnqueueSnapshotVfx(data, slot.EntityId, slot, "stock-gold", frame, itemBudget: true, allowance: allowance);
                slot.NativeEffect!.Type = "ItemTransfer";
                MaterialClock(105);
                system.PostUpdateEverything();
                Equal(8, Terraria.Main.ParticleSystem_World_OverPlayers.Particles.Count, "actual stock gold sparkles");
                Equal(8, Terraria.Main.dust.Count(d => d.active), "actual stock gold dust");
                Equal(0, allowance.Remaining, "full native cost charged");
                Equal(false, InfiniDetachedVfxSystem.TrySpendDetachedParticle("stock-gold", 16, int.MaxValue), "native burst exhausted tick");
                foreach (var particle in Terraria.Main.ParticleSystem_World_OverPlayers.Particles.Cast<PrettySparkleParticle>())
                    Equal(new Vector2(100, 120), particle.LocalPosition, "captured native position");
                // Stock/other-mod occupancy shares the existing live capacity.
                // Test-owned renderer entries are never removed by IFC.
                var foreign = new PrettySparkleParticle();
                Terraria.Main.ParticleSystem_World_OverPlayers = new ParticleRenderer();
                for (int i = 0; i < 2041; i++)
                    Terraria.Main.ParticleSystem_World_OverPlayers.Particles.Add(foreign);
                slot.NativeEffect.Type = "goldCrossBurst";
                slot.StartTick = 0;
                var capacityAllowance = new MaterialEventAllowance(16);
                InfiniDetachedVfxSystem.EnqueueSnapshotVfx(data, slot.EntityId, slot, "capacity", frame,
                    itemBudget: true, allowance: capacityAllowance);
                Equal(2041, Terraria.Main.ParticleSystem_World_OverPlayers.Particles.Count, "native live capacity refuses whole burst");
                Equal(16, capacityAllowance.Remaining, "capacity refusal spends no event allowance");
                Terraria.Main.ParticleSystem_World_OverPlayers.Particles.RemoveAt(2040);
                InfiniDetachedVfxSystem.EnqueueSnapshotVfx(data, slot.EntityId, slot, "capacity", frame,
                    itemBudget: true, allowance: capacityAllowance);
                Equal(2048, Terraria.Main.ParticleSystem_World_OverPlayers.Particles.Count, "exact live boundary admitted");
                Equal(0, capacityAllowance.Remaining, "prior refusal did not spend source budget");
                var sharedCount = typeof(InfiniDetachedVfxSystem).GetProperty("OwnedParticleCount", BindingFlags.Static | BindingFlags.NonPublic)!;
                Equal(2048, (int)sharedCount.GetValue(null)!, "material and library shared occupancy includes native renderer");
                system.OnWorldUnload();
                Equal(2048, Terraria.Main.ParticleSystem_World_OverPlayers.Particles.Count, "IFC clear never clears foreign native renderer");

                // Independent sources cannot bypass the global native tick cap.
                Terraria.Main.ParticleSystem_World_OverPlayers = new ParticleRenderer();
                MaterialClock(110);
                for (int i = 0; i < 16; i++)
                    InfiniDetachedVfxSystem.EnqueueSnapshotVfx(data, slot.EntityId, slot, "global-" + i, frame,
                        itemBudget: true, allowance: new MaterialEventAllowance(16));
                Equal(128, Terraria.Main.ParticleSystem_World_OverPlayers.Particles.Count, "global tick accepts exact 256 full-cost units");
                var nextAllowance = new MaterialEventAllowance(16);
                InfiniDetachedVfxSystem.EnqueueSnapshotVfx(data, slot.EntityId, slot, "next-global", frame,
                    itemBudget: true, allowance: nextAllowance);
                Equal(128, Terraria.Main.ParticleSystem_World_OverPlayers.Particles.Count, "global tick refuses next burst atomically");
                Equal(16, nextAllowance.Remaining, "global refusal does not spend allowance");
                MaterialClock(111);
                InfiniDetachedVfxSystem.EnqueueSnapshotVfx(data, slot.EntityId, slot, "next-global", frame,
                    itemBudget: true, allowance: nextAllowance);
                Equal(136, Terraria.Main.ParticleSystem_World_OverPlayers.Particles.Count, "global tick resets and previous refusal leaves source intact");

                // Only texture metadata is supplied for ShimmerBlock. Native
                // spawn, movement and lifetime updates execute unchanged.
                TextureAssets.Star = oldStars.ToArray();
                TextureAssets.Star[0] = CpuTextureAsset(CpuTexture(16, 16));
                VerifyNativeStockRecipeCost(system, frame, "goldCrossBurst", 8, 8, 31);
                VerifyNativeStockRecipeCost(system, frame, "rainbowBurst", 12, 24, 61);
                VerifyNativeStockRecipeCost(system, frame, "shimmerStar", 1, 0, 46);
                // LoadProjectile sees a ready metadata asset, so its actual
                // native fast path executes without content loading or GPU.
                TextureAssets.Projectile = oldProjectiles.ToArray();
                TextureAssets.Projectile[916] = CpuTextureAsset(CpuTexture(16, 64));
                Terraria.Main.projFrames = oldProjectileFrames.ToArray();
                Terraria.Main.projFrames[916] = 4;
                Terraria.Main.instance ??= (Terraria.Main)System.Runtime.CompilerServices.RuntimeHelpers
                    .GetUninitializedObject(typeof(Terraria.Main));
                VerifyNativeStockRecipeCost(system, frame, "darkLightningBurst", 7, 0, 25, 8);

                Terraria.Main.netMode = 2;
                slot.NativeEffect.Type = "goldCrossBurst";
                Equal(false, InfiniDetachedVfxSystem.EnqueueSnapshotVfx(data, slot.EntityId, slot, "server", frame), "server never queues stock effect");
            }
            finally
            {
                system.OnWorldUnload();
                Terraria.Main.dust = oldDust;
                Terraria.Main.rand = oldRandom;
                Terraria.Main.ParticleSystem_World_OverPlayers = oldParticles;
                TextureAssets.Star = oldStars;
                TextureAssets.Projectile = oldProjectiles;
                Terraria.Main.projFrames = oldProjectileFrames;
                Terraria.Main.instance = oldMain;
                Terraria.Main.gameMenu = menu;
                WorldGen.gen = gen;
                Terraria.Main.netMode = mode;
                Terraria.Main.maxDustToDraw = max;
                Terraria.Main.screenWidth = width;
                Terraria.Main.screenHeight = height;
                Terraria.Main.screenPosition = screen;
                Dust.dCount = dCount;
                clock.SetValue(null, previous);
            }
        });
    }
    private static void VerifyNativeStockRecipeCost(InfiniDetachedVfxSystem system,
        VfxSourceFrame frame, string type, int expectedSprites, int expectedDust, int removalUpdates,
        int? reservedCost = null)
    {
        system.OnWorldUnload();
        MaterialClock(200);
        Dust.dCount = 0;
        Terraria.Main.dust = Enumerable.Range(0, 6001).Select(i => new Dust { dustIndex = i }).ToArray();
        Terraria.Main.ParticleSystem_World_OverPlayers = new ParticleRenderer();
        var slot = NativeEffectSlot(type);
        int cost = reservedCost ?? expectedSprites + expectedDust;
        var data = GeneratedItemData.Placeholder();
        data.VfxManifest = new()
        {
            Slots = new[] { slot },
            Budget = new() { MaxParticlesPerTick = cost, MaxParticlesTotal = cost },
        };
        var allowance = new MaterialEventAllowance(cost);
        var foreign = new PrettySparkleParticle();
        for (int i = 0; i < 2048; i++)
            Terraria.Main.ParticleSystem_World_OverPlayers.Particles.Add(foreign);
        InfiniDetachedVfxSystem.EnqueueSnapshotVfx(data, slot.EntityId, slot, type, frame,
            itemBudget: false, allowance: allowance);
        Equal(cost, allowance.Remaining, type + " live refusal keeps event allowance");
        var tickCounter = typeof(InfiniDetachedVfxSystem).GetField("NativeEffectParticlesThisTick",
            BindingFlags.Static | BindingFlags.NonPublic)!;
        Equal(0, (int)tickCounter.GetValue(null)!, type + " live refusal keeps global allowance");

        // A fresh test-owned renderer leaves exact source budget available.
        Terraria.Main.ParticleSystem_World_OverPlayers = new ParticleRenderer();
        InfiniDetachedVfxSystem.EnqueueSnapshotVfx(data, slot.EntityId, slot, type, frame,
            itemBudget: false, allowance: allowance);
        Equal(expectedSprites, Terraria.Main.ParticleSystem_World_OverPlayers.Particles.Count,
            type + " actual native sprite count");
        Equal(expectedDust, Terraria.Main.dust.Count(d => d.active), type + " actual native Dust count");
        Equal(cost, VfxNativeEffects.Cost(type), type + " declared reservation matches native allocation bound");
        Equal(0, allowance.Remaining, type + " exact source and event budgets admitted after refusal");
        int updates = 0;
        while (Terraria.Main.ParticleSystem_World_OverPlayers.Particles.Count > 0 && updates < 100)
        {
            Terraria.Main.ParticleSystem_World_OverPlayers.Update();
            updates++;
        }
        Equal(removalUpdates, updates, type + " actual native renderer lifetime");
    }

}

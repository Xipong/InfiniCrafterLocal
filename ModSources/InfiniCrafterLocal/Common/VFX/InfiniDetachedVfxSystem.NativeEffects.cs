#nullable enable
using System;
using System.IO;
using InfiniCrafterLocal.Common.Models;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.GameContent.Drawing;
using Terraria.ID;

namespace InfiniCrafterLocal.Common.VFX;

internal static class VfxNativeEffects
{
    // Pinned 1.4.4.9 native recipes. WholeCost includes native Dust; Sprites
    // counts the native renderer allocations. Lightning uses an upper bound.
    private static (ParticleOrchestraType Kind, int WholeCost, int Sprites) Definition(string type) => type switch
    {
        "goldCrossBurst" => (ParticleOrchestraType.Excalibur, 16, 8),
        "rainbowBurst" => (ParticleOrchestraType.RainbowRodHit, 36, 12),
        "darkLightningBurst" => (ParticleOrchestraType.BlackLightningHit, 8, 8),
        "shimmerStar" => (ParticleOrchestraType.ShimmerBlock, 1, 1),
        _ => throw new InvalidDataException("Unknown nativeEffect type"),
    };

    internal static int Cost(string type) => Definition(type).WholeCost;
    internal static int SpriteCount(string type) => Definition(type).Sprites;
    internal static ParticleOrchestraType Kind(string type) => Definition(type).Kind;
}

public sealed partial class InfiniDetachedVfxSystem
{
    private const int MaxNativeEffectParticlesPerTick = 256;
    private static ulong NativeEffectAdmissionTick;
    private static int NativeEffectParticlesThisTick;

    // Read-only occupancy includes stock and other-mod particles. We never clear
    // or remove them, and cannot prevent another producer adding particles later.
    private static int NativeWorldParticleCount
        => Main.ParticleSystem_World_OverPlayers?.Particles.Count ?? 0;

    private static void EmitNativeEffect(NativeCueEmission emission, VfxNativeEffectSpec effect)
    {
        // Use the existing source presentation-event route. Do not add a second
        // particle network route through Request/Broadcast.
        if (Main.dedServ || Main.netMode == NetmodeID.Server)
            return;
        float chance = Math.Min(1, InfiniVfxClientOptions.ParticleSpawnMultiplier);
        int admissionSeed = emission.Design.Seed ^ unchecked((int)emission.Due) ^ 0x4e415446;
        if (chance <= 0 || chance < 1 && new Random(admissionSeed).NextDouble() >= chance)
            return;
        int cost = VfxNativeEffects.Cost(effect.Type);
        if (Main.ParticleSystem_World_OverPlayers is null
            || VfxNativeEffects.SpriteCount(effect.Type) > MaxMaterialParticles - OwnedParticleCount)
            return;
        ulong now = Main.GameUpdateCount;
        if (NativeEffectAdmissionTick != now)
        {
            NativeEffectAdmissionTick = now;
            NativeEffectParticlesThisTick = 0;
        }
        if (cost > MaxNativeEffectParticlesPerTick - NativeEffectParticlesThisTick)
            return;
        var design = emission.Design;
        if (design.MaxTotal < cost || emission.Allowance is { } allowance && allowance.Remaining < cost)
            return;
        if (!TrySpendDetachedParticles(emission.SourceKey, design.MaxPerTick, design.Item ? int.MaxValue : design.MaxTotal, cost))
            return;
        NativeEffectParticlesThisTick += cost;
        if (emission.Allowance is { } spent)
            spent.Remaining -= cost;
        var settings = new ParticleOrchestraSettings
        {
            PositionInWorld = emission.Frame.Position,
            MovementVector = effect.Movement is { } movement
                ? new Vector2(movement.X, movement.Y)
                : Vector2.Zero,
        };
        ParticleOrchestrator.SpawnParticlesDirect(VfxNativeEffects.Kind(effect.Type), settings);
        // Native renderer now owns detached particles: no IFC attachment/kill,
        // color/layer/lifetime overrides. Native code consumes Main.rand.
    }
}

#nullable enable
using System;
using System.Collections.Generic;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.VFX;
using Luminance.Core.Sounds;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.Audio;

namespace InfiniCrafterLocal.Common.Audio;

/// <summary>
/// External audio backend for generated VFX sound cues.
///
/// Luminance is used only for live/looped presentation sounds. One-shot use/impact
/// sounds still go through vanilla SoundEngine because that is the canonical tML path.
/// This bridge is presentation-only: it must not route gameplay, damage, delivery,
/// resultKind, runtimeFamily, or projectile behavior.
/// </summary>
public static class InfiniLuminanceSoundBridge
{
    public const string ContractVersion = "infini.luminance-sound-bridge.v1";
    private const int MaxActiveLoops = 48;
    private const int StaleTicks = 90;

    private sealed class LoopHandle
    {
        public LoopedSoundInstance Instance = null!;
        public int LastTouchedTick;
    }

    private static readonly Dictionary<string, LoopHandle> ActiveLoops = new();

    public static bool TryUpdateLiveSoundCue(Projectile projectile, AttackSpec spec, VfxSlotSpec slot)
    {
        if (Main.dedServ || projectile is null || spec is null || slot is null)
            return false;
        if (!InfiniVfxClientOptions.EnableLuminanceSoundBackend)
            return false;
        if (!InfiniSoundLibrary.IsBuiltInCatalogId(spec.SoundUseCatalogId))
            return false;
        if (!ShouldLoop(slot))
            return false;

        int now = (int)Main.GameUpdateCount;
        Prune(now);

        string key = LoopKey(projectile, slot);
        if (!ActiveLoops.TryGetValue(key, out LoopHandle? handle) || handle.Instance is null || handle.Instance.HasBeenStopped)
        {
            if (ActiveLoops.Count >= MaxActiveLoops)
                return false;

            int owner = projectile.owner;
            int identity = projectile.identity;
            SoundStyle style = InfiniSoundLibrary.ForVfxCue(
                spec.RuntimeFamily,
                spec.Effect,
                spec.SoundVolume,
                spec.SoundPitch,
                spec.SoundPitchVariance,
                slot.SlotSeed,
                impact: false,
                spec.SoundUseCatalogId,
                spec.SoundUseCatalogPath,
                spec.SoundCatalogSource);
            float loopVolume = Math.Clamp(style.Volume * (0.18f + slot.Alpha * 0.42f), 0.02f, 0.55f);
            SoundStyle loopStyle = style with
            {
                Volume = loopVolume,
                Pitch = Math.Clamp(style.Pitch, -0.85f, 0.85f),
                MaxInstances = 0,
            };
            handle = new LoopHandle
            {
                Instance = LoopedSoundManager.CreateNew(loopStyle, () => LoopShouldStop(projectile, owner, identity)),
                LastTouchedTick = now,
            };
            ActiveLoops[key] = handle;
        }

        LoopedSoundInstance instance = handle.Instance;
        handle.LastTouchedTick = now;
        instance.Update(projectile.Center);
        return true;
    }

    private static bool ShouldLoop(VfxSlotSpec slot)
    {
        string group = (slot.EventGroup ?? "").Trim().ToLowerInvariant();
        if (group != "live")
            return false;
        string channel = (slot.Channel ?? "").Trim().ToLowerInvariant();
        string renderer = (slot.RendererKind ?? "").Trim();
        bool soundCue = channel == "sound" || VfxRendererRegistry.ParseKind(slot.RendererKind) == InfiniVfxRendererKind.SoundCue;
        if (!soundCue)
            return false;
        return slot.Duration >= 12 || slot.RepeatEvery <= 0 || slot.Density >= 0.20f;
    }

    private static bool LoopShouldStop(Projectile projectile, int owner, int identity)
    {
        if (Main.dedServ || !InfiniVfxClientOptions.EnableLuminanceSoundBackend)
            return true;
        if (projectile is null || !projectile.active)
            return true;
        return projectile.owner != owner || projectile.identity != identity;
    }

    private static void Prune(int now)
    {
        List<string>? dead = null;
        foreach (var pair in ActiveLoops)
        {
            LoopedSoundInstance? instance = pair.Value.Instance;
            bool stale = now - pair.Value.LastTouchedTick > StaleTicks;
            bool stopped = instance is null || instance.HasBeenStopped;
            if (!stale && !stopped)
                continue;
            dead ??= new List<string>();
            dead.Add(pair.Key);
            if (!stopped && instance is not null)
                instance.Stop();
        }
        if (dead is null)
            return;
        foreach (string key in dead)
            ActiveLoops.Remove(key);
    }

    private static string LoopKey(Projectile projectile, VfxSlotSpec slot)
    {
        string renderer = slot.RendererKind;
        return projectile.owner + ":" + projectile.identity + ":" + slot.SlotSeed + ":" + slot.EventGroup + ":" + slot.Channel + ":" + renderer;
    }
}

#nullable enable
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.Config;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Common.VFX;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;
using Terraria.ModLoader.IO;

namespace InfiniCrafterLocal.Common.Players;

public sealed partial class InfiniCraftPlayer
{
    private sealed class ActiveGeneratedUtilityBuff
    {
        public int Ticks;
        public int InitialDurationTicks;
        public float MiningSpeedMultiplier = 1f;
        public float EmitLightStrength;
        public string LightColorName = "";
        public int OreSenseRadiusTiles;
        public float MovementSpeed;
        public float JumpBoost;
        public int ManaRegen;
        public int LifeRegen;
        public string LifeRegenCondition = "always";
        public string TreasureSenseCondition = "always";
        public GeneratedCombatBuffSpec? Combat;
        public PlayerEffectSpec? PlayerEffect;
        public string SourceItemId = "";
        public string SourceDefinitionIdentity = "";
        public long SourceGeneration;
        // Predicted tokens are even, authority tokens odd. A confirmed row can
        // retain its one local alias without trusting that alias on the server.
        public long SourcePredictionGeneration;
        public bool SourceAuthorityConfirmed;
        public uint? SourceFinalTick;
        public string SourceComponent = "";
        // Local attachment identity, retained only across snapshots of a still
        // live exact row. Reappearing wire tokens cannot revive expired VFX.
        public object SourceLifetime = new();

        public GeneratedItemData? ResolveSource()
            => InfiniCrafterLocalMod.GeneratedItems is { } registry
                && registry.TryGet(SourceItemId, out var data)
                && GeneratedItemRegistryService.IsCurrentWorldData(data)
                && GeneratedItemRegistryService.DefinitionIdentity(data) == SourceDefinitionIdentity ? data : null;

        public static ActiveGeneratedUtilityBuff From(GeneratedBuffSpec buff) => new()
        {
            Ticks = buff.DurationTicks == GeneratedBuffSpec.PermanentDurationTicks ? int.MaxValue : buff.DurationTicks,
            InitialDurationTicks = buff.DurationTicks,
            MiningSpeedMultiplier = Math.Clamp(buff.MiningSpeedMultiplier, 0.25f, 4f),
            EmitLightStrength = Math.Clamp(buff.EmitLightStrength, 0f, 1.5f),
            LightColorName = buff.LightColorName ?? "",
            OreSenseRadiusTiles = Math.Clamp(buff.OreSenseRadiusTiles, 0, 60),
            MovementSpeed = Math.Clamp(buff.MovementSpeed, -0.8f, 2f),
            JumpBoost = Math.Clamp(buff.JumpBoost, -8f, 8f),
            ManaRegen = Math.Clamp(buff.ManaRegen, -100, 120),
            LifeRegen = Math.Clamp(buff.LifeRegen, -100, 120),
            LifeRegenCondition = buff.LifeRegenCondition ?? "always",
            TreasureSenseCondition = buff.TreasureSenseCondition ?? "always",
            Combat = buff.Combat,
            PlayerEffect = buff.PlayerEffect,
        };

        public bool SameEffect(ActiveGeneratedUtilityBuff other)
            => MiningSpeedMultiplier == other.MiningSpeedMultiplier
            && EmitLightStrength == other.EmitLightStrength
            && string.Equals(LightColorName, other.LightColorName, StringComparison.OrdinalIgnoreCase)
            && OreSenseRadiusTiles == other.OreSenseRadiusTiles
            && MovementSpeed == other.MovementSpeed
            && JumpBoost == other.JumpBoost
            && ManaRegen == other.ManaRegen
            && LifeRegen == other.LifeRegen
            && (LifeRegen == 0 || LifeRegenCondition == other.LifeRegenCondition)
            && (OreSenseRadiusTiles == 0 || TreasureSenseCondition == other.TreasureSenseCondition)
            && GeneratedCombatBuffSpec.SameEffect(Combat, other.Combat)
            && PlayerEffectSpec.SameEffect(PlayerEffect, other.PlayerEffect)
            && (PlayerEffect?.AirJump is null || (SourceItemId == other.SourceItemId
                && SourceDefinitionIdentity == other.SourceDefinitionIdentity && SourceComponent == other.SourceComponent));
    }

    private long _nextGeneratedBuffSourceGeneration;
    private long _lastAuthoritativeBuffGeneration;
    private readonly List<ActiveGeneratedUtilityBuff> _finalTickAirJumpSources = new();
    private readonly Dictionary<(string Item, string Definition, string Component), long> _retiredAirJumpPredictions = new();
    private bool _airJumpPredictionHistoryOverflow;
    private bool _airJumpAuthorityInitialized;
    private object? _airJumpAuthoritySocket;
    private string _airJumpAuthorityWorld = "";

    private static (string Item, string Definition, string Component) AirJumpPredictionKey(ActiveGeneratedUtilityBuff buff)
        => (buff.SourceItemId, buff.SourceDefinitionIdentity, buff.SourceComponent);

    private void RetireAirJumpPrediction(ActiveGeneratedUtilityBuff buff)
    {
        if (buff.SourceGeneration >= 0 || buff.SourceAuthorityConfirmed
            || buff.SourceGeneration >= _airJumpPredictionRecoveryGeneration) return;
        _airJumpPredictionLastRetiredGeneration = Math.Min(_airJumpPredictionLastRetiredGeneration, buff.SourceGeneration);
        var key = AirJumpPredictionKey(buff);
        if (_retiredAirJumpPredictions.TryGetValue(key, out long previous))
            _retiredAirJumpPredictions[key] = Math.Min(previous, buff.SourceGeneration);
        else if (_retiredAirJumpPredictions.Count < MaxAirJumpSources)
            _retiredAirJumpPredictions.Add(key, buff.SourceGeneration);
        else _airJumpPredictionHistoryOverflow = true; // recovered only by an ordered authority fence
    }

    private bool IsCurrentAirJumpAuthority => !_airJumpAuthorityInitialized
        || ReferenceEquals(_airJumpAuthoritySocket, Netplay.Connection?.Socket)
            && _airJumpAuthorityWorld == GeneratedItemRegistryService.CurrentWorldIdString();

    private void EnsureAirJumpAuthorityScope()
    {
        if (Main.netMode != NetmodeID.MultiplayerClient) return;
        if (!IsCurrentAirJumpAuthority) RetireAirJumpAuthority();
        _airJumpAuthorityInitialized = true;
        _airJumpAuthoritySocket = Netplay.Connection?.Socket;
        _airJumpAuthorityWorld = GeneratedItemRegistryService.CurrentWorldIdString();
    }

    internal void RetireAirJumpAuthority()
    {
        ClearAirJumpState();
        _activeGeneratedUtilityBuffs.RemoveAll(buff => buff.PlayerEffect?.AirJump is not null);
        RebuildGeneratedUtilityBuffAggregate();
        _lastAuthoritativeBuffGeneration = 0;
        _retiredAirJumpPredictions.Clear();
        _airJumpPredictionHistoryOverflow = false;
        _airJumpPredictionRecoveryGeneration = 0;
        _airJumpPredictionLastRetiredGeneration = 0;
        _airJumpAuthorityInitialized = false;
    }

    public bool TryReserveGeneratedMobilityCooldown(int cooldownTicks)
    {
        _lastGeneratedMobilityFailureMessage = "";
        if (_generatedMobilityCooldownTicks > 0)
        {
            _lastGeneratedMobilityFailureMessage = GeneratedUseFeedbackText("MobilityCooldown", GeneratedMobilityCooldownSeconds);
            return false;
        }
        StartGeneratedMobilityCooldown(cooldownTicks);
        return true;
    }

    private void StartGeneratedMobilityCooldown(int cooldownTicks)
    {
        _generatedMobilityCooldownTicks = Math.Clamp(cooldownTicks, 0, 36000);
    }

    public bool ApplyGeneratedUtilityBuff(GeneratedBuffSpec? buff, bool syncNetwork = false,
        GeneratedItemData? source = null, uint? activationTick = null)
    {
        if (buff is null) return false;
        EnsureAirJumpAuthorityScope();
        if (Player.dead || !IsGeneratedUtilityActivationCurrent(activationTick))
        {
            if (syncNetwork) CorrectGeneratedBuffPrediction();
            return false;
        }
        buff.Normalize();
        if (!buff.HasAnyEffect) return false;
        // Jump execution and VFX retain the exact source even after a consumable
        // disappears. Source-free calls cannot manufacture an unowned jump.
        string jumpSourceIdentity = "";
        string jumpSourceComponent = "";
        if (buff.PlayerEffect?.AirJump is not null)
        {
            if (!TryGeneratedExhaustionSource(source, out jumpSourceIdentity)) return false;
            if (ReferenceEquals(source!.Gameplay.GeneratedBuff, buff)) jumpSourceComponent = "buff";
            else if (source.RuntimeProgram.EffectGroups?.FirstOrDefault(group => ReferenceEquals(group.GeneratedBuff, buff)) is { } group)
                jumpSourceComponent = "group:" + group.Id;
            else return false; // source must identify this exact authored component
        }
        uint elapsed = activationTick.HasValue
            ? unchecked(Main.GameUpdateCount - activationTick.Value) : 0;
        if (elapsed > int.MaxValue)
        {
            if (syncNetwork) CorrectGeneratedBuffPrediction();
            return false;
        }
        if (!CanApplyGeneratedBuff(buff, source, activationTick, out var exhaustion))
        {
            if (syncNetwork) CorrectGeneratedBuffPrediction();
            return false;
        }
        // A confirmed delayed occurrence can have no buff time left while its
        // independent exhaustion is still live. Do not replay even one buff tick
        // or remove another active contribution merely to retain that lockout.
        int remaining = buff.DurationTicks == GeneratedBuffSpec.PermanentDurationTicks
            ? int.MaxValue : buff.DurationTicks - (int)elapsed;
        if (remaining > 0)
        {
            var incoming = ActiveGeneratedUtilityBuff.From(buff);
            incoming.Ticks = remaining;
            if (incoming.PlayerEffect?.AirJump is not null)
            {
                incoming.SourceItemId = source!.Id;
                incoming.SourceDefinitionIdentity = jumpSourceIdentity;
                incoming.SourceComponent = jumpSourceComponent;
            }
            var existing = _activeGeneratedUtilityBuffs.FirstOrDefault(active => active.SameEffect(incoming));
            if (existing is not null)
            {
                if (incoming.Ticks > existing.Ticks)
                {
                    existing.Ticks = incoming.Ticks;
                    existing.InitialDurationTicks = incoming.InitialDurationTicks;
                }
            }
            else
            {
                // Bound pathological repeated authoring while preserving independent
                // durations for distinct explicit effects. HoldItem refreshes an equal
                // entry instead of allocating one entry per tick.
                if (_activeGeneratedUtilityBuffs.Count >= 32)
                {
                    var shortest = _activeGeneratedUtilityBuffs.OrderBy(active => active.Ticks).First();
                    RetireAirJumpPrediction(shortest);
                    _activeGeneratedUtilityBuffs.Remove(shortest);
                }
                if (incoming.PlayerEffect?.AirJump is not null)
                {
                    // Negative tokens are disjoint from equipment presentation
                    // tokens. Refreshing an existing entry preserves its lifetime.
                    if (_nextGeneratedBuffSourceGeneration <= long.MinValue / 2) return false;
                    foreach (var finalTick in _finalTickAirJumpSources)
                        if (AirJumpPredictionKey(finalTick) == AirJumpPredictionKey(incoming))
                            RetireAirJumpPrediction(finalTick);
                    long sequence = --_nextGeneratedBuffSourceGeneration;
                    incoming.SourceAuthorityConfirmed = Main.netMode != NetmodeID.MultiplayerClient;
                    incoming.SourceGeneration = sequence * 2 + (incoming.SourceAuthorityConfirmed ? 1 : 0);
                }
                _activeGeneratedUtilityBuffs.Add(incoming);
            }
            RebuildGeneratedUtilityBuffAggregate();
        }
        if (exhaustion is not null) _generatedItemExhaustion.Add(exhaustion);
        if ((syncNetwork || exhaustion is not null) && Main.netMode == NetmodeID.Server)
            SendGeneratedBuffState();
        return true;
    }

    private int _generatedDefense;
    private float _generatedAttackSpeed, _generatedCrit;
    private readonly Dictionary<string, float> _generatedDamage = new(StringComparer.Ordinal);

    private void RebuildGeneratedUtilityBuffAggregate()
    {
        _generatedBuffTicks = 0;
        _generatedMiningSpeedMultiplier = 1f;
        _generatedLightStrength = 0f;
        _generatedLightColorName = "";
        _generatedOreSenseRadiusTiles = 0;
        _generatedMovementSpeed = 0f;
        _generatedJumpBoost = 0f;
        _generatedManaRegen = 0;
        _generatedLifeRegen = 0;
        _generatedDefense = 0; _generatedAttackSpeed = 0; _generatedCrit = 0;
        _generatedDamage.Clear();

        foreach (var active in _activeGeneratedUtilityBuffs)
        {
            if (active.Ticks <= 0)
                continue;
            _generatedBuffTicks = Math.Max(_generatedBuffTicks, active.Ticks);
            _generatedMiningSpeedMultiplier *= active.MiningSpeedMultiplier;
            if (active.EmitLightStrength >= _generatedLightStrength)
            {
                _generatedLightStrength = active.EmitLightStrength;
                _generatedLightColorName = active.LightColorName;
            }
            _generatedOreSenseRadiusTiles = Math.Max(_generatedOreSenseRadiusTiles, active.OreSenseRadiusTiles);
            _generatedMovementSpeed += active.MovementSpeed;
            _generatedJumpBoost += active.JumpBoost;
            _generatedManaRegen += active.ManaRegen;
            _generatedLifeRegen += active.LifeRegen;
            if (active.Combat is { } combat)
            {
                _generatedDefense += combat.DefensePoints;
                _generatedAttackSpeed += combat.AttackSpeedPercent;
                _generatedCrit += combat.CritChancePoints;
                _generatedDamage.TryGetValue(combat.DamageClass, out float current);
                _generatedDamage[combat.DamageClass] = current + combat.DamagePercent;
            }
        }
        // Bound totals, not intermediate sums/products: speed-up and slow-down
        // contributions must not depend on the order effects were received.
        _generatedMiningSpeedMultiplier = Math.Clamp(_generatedMiningSpeedMultiplier, 0.25f, 4f);
        _generatedMovementSpeed = Math.Clamp(_generatedMovementSpeed, -0.8f, 2f);
        _generatedJumpBoost = Math.Clamp(_generatedJumpBoost, -8f, 8f);
        _generatedManaRegen = Math.Clamp(_generatedManaRegen, -100, 120);
        _generatedLifeRegen = Math.Clamp(_generatedLifeRegen, -100, 120);
        _generatedDefense = Math.Clamp(_generatedDefense, -100, 100);
        _generatedAttackSpeed = Math.Clamp(_generatedAttackSpeed, -80f, 100f);
        _generatedCrit = Math.Clamp(_generatedCrit, -100f, 100f);
        foreach (string damageClass in _generatedDamage.Keys.ToArray())
            _generatedDamage[damageClass] = Math.Clamp(_generatedDamage[damageClass], -90f, 200f);
    }

    private void ResetGeneratedUtilityBuffAggregate()
    {
        _generatedBuffTicks = 0;
        _generatedMiningSpeedMultiplier = 1f;
        _generatedLightStrength = 0f;
        _generatedLightColorName = "";
        _generatedOreSenseRadiusTiles = 0;
        _generatedMovementSpeed = 0f;
        _generatedJumpBoost = 0f;
        _generatedManaRegen = 0;
        _generatedLifeRegen = 0;
        _generatedDefense = 0; _generatedAttackSpeed = 0; _generatedCrit = 0;
        _generatedDamage.Clear();
    }


    public bool TryRunGeneratedMobility(IItemEffectsSpec? gameplay)
    {
        _lastGeneratedMobilityFailureMessage = "";
        if (gameplay is null)
        {
            _lastGeneratedMobilityFailureMessage = GeneratedUseFeedbackText("MobilityDataMissing");
            return false;
        }
        string mode = (gameplay.MobilityMode ?? "").Trim().ToLowerInvariant();
        if (string.IsNullOrWhiteSpace(mode))
        {
            _lastGeneratedMobilityFailureMessage = GeneratedUseFeedbackText("MobilityModeMissing");
            return false;
        }
        if (_generatedMobilityCooldownTicks > 0)
        {
            _lastGeneratedMobilityFailureMessage = GeneratedUseFeedbackText("MobilityCooldown", GeneratedMobilityCooldownSeconds);
            return false;
        }

        bool ok = mode switch
        {
            "recall_home" => TryRecallHome(),
            "blink_to_cursor" => TryBlinkToCursor(gameplay),
            _ => UnsupportedGeneratedMobility(mode),
        };
        if (ok)
        {
            _lastGeneratedMobilityFailureMessage = "";
            StartGeneratedMobilityCooldown(gameplay.MobilityCooldownTicks);
        }
        return ok;
    }

    private bool UnsupportedGeneratedMobility(string mode)
    {
        _lastGeneratedMobilityFailureMessage = string.IsNullOrWhiteSpace(mode)
            ? GeneratedUseFeedbackText("MobilityModeMissing")
            : GeneratedUseFeedbackText("MobilityUnsupported", mode);
        return false;
    }

    private bool TryRecallHome()
    {
        if (Player.dead)
        {
            _lastGeneratedMobilityFailureMessage = GeneratedUseFeedbackText("MobilityDead");
            return false;
        }
        if (!InfiniCrafterLocal.Common.Services.InfiniRuntimeAuthority.ShouldRunPlayerGameplay(Player))
        {
            _lastGeneratedMobilityFailureMessage = GeneratedUseFeedbackText("MobilityAuthority");
            return false;
        }
        bool validBed = Player.SpawnX > 0 && Player.SpawnY > 0
            && Player.SpawnX < Main.maxTilesX - 1 && Player.SpawnY < Main.maxTilesY - 1
            && Terraria.Player.CheckSpawn(Player.SpawnX, Player.SpawnY);
        int sx = validBed ? Player.SpawnX : Main.spawnTileX;
        int sy = validBed ? Player.SpawnY : Main.spawnTileY;
        if (sx <= 0 || sy <= 0 || sx >= Main.maxTilesX - 1 || sy >= Main.maxTilesY - 1)
        {
            _lastGeneratedMobilityFailureMessage = GeneratedUseFeedbackText("MobilitySpawnMissing");
            return false;
        }
        Vector2 destination = new(sx * 16f + 8f - Player.width / 2f, sy * 16f - Player.height);
        if (!IsBlinkWithinWorld(destination))
        {
            _lastGeneratedMobilityFailureMessage = GeneratedUseFeedbackText("MobilitySpawnMissing");
            return false;
        }
        Player.Teleport(destination, 0);
        Player.velocity = Vector2.Zero;
        Player.fallStart2 = Player.fallStart;
        InfiniCrafterLocal.Common.Services.InfiniRuntimeAuthority.SyncTeleport(Player, destination);
        return true;
    }

    private bool TryBlinkToCursor(IItemEffectsSpec gameplay)
    {
        if (!InfiniCrafterLocal.Common.Services.InfiniRuntimeAuthority.ShouldRunLocalPlayerAction(Player))
        {
            _lastGeneratedMobilityFailureMessage = GeneratedUseFeedbackText("MobilityLocalControl");
            return false;
        }
        return TryBlinkToTarget(gameplay, Main.MouseWorld);
    }

    private bool TryBlinkToTarget(IItemEffectsSpec gameplay, Vector2 target)
    {
        if (Player.dead)
        {
            _lastGeneratedMobilityFailureMessage = GeneratedUseFeedbackText("MobilityDead");
            return false;
        }
        if (!InfiniCrafterLocal.Common.Services.InfiniRuntimeAuthority.ShouldRunPlayerGameplay(Player))
        {
            _lastGeneratedMobilityFailureMessage = GeneratedUseFeedbackText("MobilityAuthority");
            return false;
        }
        if (gameplay.MobilityRangeTiles <= 0)
        {
            _lastGeneratedMobilityFailureMessage = GeneratedUseFeedbackText("MobilityRangeMissing");
            return false;
        }
        if (!float.IsFinite(target.X) || !float.IsFinite(target.Y))
        {
            _lastGeneratedMobilityFailureMessage = GeneratedUseFeedbackText("MobilityUnsafe");
            return false;
        }
        int rangeTiles = Math.Clamp(gameplay.MobilityRangeTiles, 1, 120);
        Vector2 delta = target - Player.Center;
        float max = rangeTiles * 16f;
        if (delta.Length() > max)
            target = Player.Center + delta.SafeNormalize(Vector2.UnitX * Player.direction) * max;
        // Main.MouseWorld already mirrors the cursor under inverted gravity.
        // Match the native teleport rod's gravity-relative feet, not body centre.
        Vector2 destination = new(target.X - Player.width / 2, target.Y - (Player.gravDir == 1f ? Player.height : 0));
        if (!IsBlinkWithinWorld(destination) || gameplay.MobilitySafeTileOnly && !IsSafeBlinkDestination(destination))
        {
            _lastGeneratedMobilityFailureMessage = GeneratedUseFeedbackText("MobilityUnsafe");
            return false;
        }
        Player.Teleport(destination, 0);
        InfiniCrafterLocal.Common.Services.InfiniRuntimeAuthority.SyncTeleport(Player, destination);
        return true;
    }

    internal bool IsBlinkWithinWorld(Vector2 destination)
        => float.IsFinite(destination.X) && float.IsFinite(destination.Y)
            && destination.X >= 16f && destination.Y >= 16f
            && destination.X + Player.width < (Main.maxTilesX - 1) * 16f
            && destination.Y + Player.height < (Main.maxTilesY - 1) * 16f;

    private bool IsSafeBlinkDestination(Vector2 destination)
        // Safe policy follows native body geometry, including actuated/half
        // blocks and actual lava overlap. Finite/world bounds apply to both
        // safe and unsafe destinations before any native collision query.
        => IsBlinkWithinWorld(destination)
            && !Collision.SolidCollision(destination, Player.width, Player.height)
            && !Collision.LavaCollision(destination, Player.width, Player.height);


    private bool IsContinuouslyHeldAirJumpBuff(ActiveGeneratedUtilityBuff active)
    {
        if (active.Ticks <= 0 || active.SourceGeneration >= 0 || active.PlayerEffect?.AirJump is null
            || Player is not { active: true, dead: false }
            || Player.HeldItem is not { IsAir: false, ModItem: GeneratedItem held }
            || !ValidAirJumpSource(held.Data) || held.Data.Id != active.SourceItemId
            || GeneratedItemRegistryService.DefinitionIdentity(held.Data) != active.SourceDefinitionIdentity
            || active.SourceComponent != "group:" + held.Data.RuntimeProgram.HeldEffectGroupId
            || held.Data.RuntimeProgram.TryGetEffectGroup(held.Data.RuntimeProgram.HeldEffectGroupId)?.GeneratedBuff is not { } buff
            || buff.DurationTicks != active.InitialDurationTicks || buff.ExhaustionTicks is > 0
            || HasGeneratedItemExhaustion(held.Data)) return false;
        return PlayerEffectSpec.SameEffect(active.PlayerEffect, buff.PlayerEffect);
    }

    private void TickGeneratedUtilityBuff()
    {
        if (_activeGeneratedUtilityBuffs.Count > 0)
        {
            for (int index = _activeGeneratedUtilityBuffs.Count - 1; index >= 0; index--)
            {
                var active = _activeGeneratedUtilityBuffs[index];
                if (active.InitialDurationTicks == GeneratedBuffSpec.PermanentDurationTicks)
                    continue;
                // HoldItem runs later than this phase; duration=1 must not expire
                // and mint a new generation each tick. Remote peers may continue
                // an admitted row, but must never activate a buff from held data.
                if (IsContinuouslyHeldAirJumpBuff(active))
                    active.Ticks = active.InitialDurationTicks;
                else
                    active.Ticks--;
                if (active.Ticks <= 0)
                {
                    // The effect already granted this tick's native jump. Keep
                    // only its presentation witness through movement, never its
                    // stats, duration or next-tick availability.
                    if (active.PlayerEffect?.AirJump is not null)
                    {
                        active.SourceFinalTick = Main.GameUpdateCount;
                        _finalTickAirJumpSources.Add(active);
                    }
                    _activeGeneratedUtilityBuffs.RemoveAt(index);
                }
            }
            RebuildGeneratedUtilityBuffAggregate();
        }
        else if (!InfiniRuntimeAuthority.ShouldRunPlayerGameplay(Player)
            && _generatedBuffTicks is > 0 and < int.MaxValue)
        {
            // Client comparison mirrors can carry only an aggregate duration;
            // active network snapshots carry independently expiring entries.
            _generatedBuffTicks--;
        }

        if (_generatedBuffTicks <= 0 && _activeGeneratedUtilityBuffs.Count == 0)
            ResetGeneratedUtilityBuffAggregate();
    }

    private void TickGeneratedUtilityCooldowns()
    {
        // These clocks keep their existing end-of-update phase. Buff durations
        // advance after PostUpdateEquips has sampled their stats and light.
        if (PruneGeneratedItemExhaustion()) CorrectGeneratedBuffPrediction();
        if (_generatedMobilityCooldownTicks > 0)
            _generatedMobilityCooldownTicks--;
    }

    private void EmitGeneratedUtilityBuffLight()
    {
        if (_generatedBuffTicks > 0 && _generatedLightStrength > 0f && Main.netMode != NetmodeID.Server)
        {
            Color c = RuntimeColorPolicy.Resolve(_generatedLightColorName, Color.White);
            float strength = Math.Clamp(_generatedLightStrength, 0f, 1.5f);
            Lighting.AddLight(Player.Center, c.R / 255f * strength, c.G / 255f * strength, c.B / 255f * strength);
        }
    }

    internal int CurrentGeneratedLifeRegen
    {
        get
        {
            int units = 0;
            foreach (var active in _activeGeneratedUtilityBuffs)
                if (active.Ticks > 0 && PlayerEffectSpec.IsConditionActive(active.LifeRegenCondition, Player))
                    units += active.LifeRegen;
            // Select active contributions first, then preserve the existing cap.
            return Math.Clamp(units, -100, 120);
        }
    }

    internal bool HasActiveGeneratedTreasureSense
        => _activeGeneratedUtilityBuffs.Any(active =>
            active.Ticks > 0 && active.OreSenseRadiusTiles > 0
                && PlayerEffectSpec.IsConditionActive(active.TreasureSenseCondition, Player));

    private void ApplyGeneratedUtilityBuffEffects()
    {
        foreach (var active in _activeGeneratedUtilityBuffs)
            if (active.Ticks > 0 && active.PlayerEffect is { } effect)
                ApplyPlayerEffect(effect, active.ResolveSource(), active.SourceGeneration, active.SourceComponent);
        if (Player.dead || _generatedBuffTicks <= 0 || !InfiniRuntimeAuthority.ShouldRunPlayerGameplay(Player))
            return;
        if (_generatedMiningSpeedMultiplier != 1f)
            Player.pickSpeed /= Math.Clamp(_generatedMiningSpeedMultiplier, 0.25f, 4f);
        if (_generatedMovementSpeed != 0f)
            Player.moveSpeed += _generatedMovementSpeed;
        if (_generatedJumpBoost != 0f)
            Player.jumpSpeedBoost += _generatedJumpBoost;
        if (_generatedManaRegen != 0)
            Player.manaRegenBonus += _generatedManaRegen;
        ApplyLifeRegen(CurrentGeneratedLifeRegen);
        ApplyTreasureSense(HasActiveGeneratedTreasureSense);
        Player.statDefense += _generatedDefense;
        Player.GetAttackSpeed(DamageClass.Generic) += _generatedAttackSpeed / 100f;
        Player.GetCritChance(DamageClass.Generic) += _generatedCrit;
        foreach (var bonus in _generatedDamage)
            Player.GetDamage(TerrariaRuntimeVocabulary.ResolveDamageClass(bonus.Key)) += bonus.Value / 100f;
    }

}

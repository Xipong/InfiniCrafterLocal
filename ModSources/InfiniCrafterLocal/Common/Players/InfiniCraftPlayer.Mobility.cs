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
        public float MiningSpeedMultiplier = 1f;
        public float EmitLightStrength;
        public string LightColorName = "";
        public int OreSenseRadiusTiles;
        public float MovementSpeed;
        public float JumpBoost;
        public int ManaRegen;
        public int LifeRegen;

        public static ActiveGeneratedUtilityBuff From(GeneratedBuffSpec buff) => new()
        {
            Ticks = Math.Clamp(buff.DurationTicks, 1, 21600),
            MiningSpeedMultiplier = Math.Clamp(buff.MiningSpeedMultiplier, 0.25f, 4f),
            EmitLightStrength = Math.Clamp(buff.EmitLightStrength, 0f, 1.5f),
            LightColorName = buff.LightColorName ?? "",
            OreSenseRadiusTiles = Math.Clamp(buff.OreSenseRadiusTiles, 0, 60),
            MovementSpeed = Math.Clamp(buff.MovementSpeed, -0.5f, 2f),
            JumpBoost = Math.Clamp(buff.JumpBoost, 0f, 8f),
            ManaRegen = Math.Clamp(buff.ManaRegen, 0, 120),
            LifeRegen = Math.Clamp(buff.LifeRegen, 0, 120),
        };

        public bool SameEffect(ActiveGeneratedUtilityBuff other)
            => Math.Abs(MiningSpeedMultiplier - other.MiningSpeedMultiplier) < 0.0001f
            && Math.Abs(EmitLightStrength - other.EmitLightStrength) < 0.0001f
            && string.Equals(LightColorName, other.LightColorName, StringComparison.OrdinalIgnoreCase)
            && OreSenseRadiusTiles == other.OreSenseRadiusTiles
            && Math.Abs(MovementSpeed - other.MovementSpeed) < 0.0001f
            && Math.Abs(JumpBoost - other.JumpBoost) < 0.0001f
            && ManaRegen == other.ManaRegen
            && LifeRegen == other.LifeRegen;
    }

    public bool TryReserveGeneratedMobilityCooldown(int cooldownTicks)
    {
        _lastGeneratedMobilityFailureMessage = "";
        if (_generatedMobilityCooldownTicks > 0)
        {
            _lastGeneratedMobilityFailureMessage = $"Mobility cooldown: {GeneratedMobilityCooldownSeconds}s";
            return false;
        }
        StartGeneratedMobilityCooldown(cooldownTicks);
        return true;
    }

    private void StartGeneratedMobilityCooldown(int cooldownTicks)
    {
        _generatedMobilityCooldownTicks = Math.Clamp(cooldownTicks, 0, 36000);
    }


    public void ApplyGeneratedUtilityBuff(GeneratedBuffSpec? buff, bool syncNetwork = false)
    {
        if (buff is null) return;
        buff.Normalize();
        if (!buff.HasAnyEffect) return;
        var incoming = ActiveGeneratedUtilityBuff.From(buff);
        var existing = _activeGeneratedUtilityBuffs.FirstOrDefault(active => active.SameEffect(incoming));
        if (existing is not null)
            existing.Ticks = Math.Max(existing.Ticks, incoming.Ticks);
        else
        {
            // Bound pathological repeated authoring while preserving independent
            // durations for distinct explicit effects. HoldItem refreshes an equal
            // entry instead of allocating one entry per tick.
            if (_activeGeneratedUtilityBuffs.Count >= 32)
            {
                var shortest = _activeGeneratedUtilityBuffs.OrderBy(active => active.Ticks).First();
                _activeGeneratedUtilityBuffs.Remove(shortest);
            }
            _activeGeneratedUtilityBuffs.Add(incoming);
        }
        RebuildGeneratedUtilityBuffAggregate();
        if (syncNetwork && Main.netMode == NetmodeID.Server)
            SendGeneratedBuffState();
    }

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

        foreach (var active in _activeGeneratedUtilityBuffs)
        {
            if (active.Ticks <= 0)
                continue;
            _generatedBuffTicks = Math.Max(_generatedBuffTicks, active.Ticks);
            _generatedMiningSpeedMultiplier = Math.Clamp(_generatedMiningSpeedMultiplier * active.MiningSpeedMultiplier, 0.25f, 4f);
            if (active.EmitLightStrength >= _generatedLightStrength)
            {
                _generatedLightStrength = active.EmitLightStrength;
                _generatedLightColorName = active.LightColorName;
            }
            _generatedOreSenseRadiusTiles = Math.Max(_generatedOreSenseRadiusTiles, active.OreSenseRadiusTiles);
            _generatedMovementSpeed = Math.Clamp(_generatedMovementSpeed + active.MovementSpeed, -0.5f, 2f);
            _generatedJumpBoost = Math.Clamp(_generatedJumpBoost + active.JumpBoost, 0f, 8f);
            _generatedManaRegen = Math.Clamp(_generatedManaRegen + active.ManaRegen, 0, 120);
            _generatedLifeRegen = Math.Clamp(_generatedLifeRegen + active.LifeRegen, 0, 120);
        }
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
    }


    public bool TryRunGeneratedMobility(GameplaySpec? gameplay)
        => TryRunGeneratedMobility(gameplay, null);

    private bool TryRunGeneratedMobility(GameplaySpec? gameplay, Vector2? requestedTarget)
    {
        _lastGeneratedMobilityFailureMessage = "";
        if (gameplay is null)
        {
            _lastGeneratedMobilityFailureMessage = "Missing generated mobility data";
            return false;
        }
        string mode = (gameplay.MobilityMode ?? "").Trim().ToLowerInvariant();
        if (string.IsNullOrWhiteSpace(mode))
        {
            _lastGeneratedMobilityFailureMessage = "No generated mobility mode";
            return false;
        }
        if (_generatedMobilityCooldownTicks > 0)
        {
            _lastGeneratedMobilityFailureMessage = $"Mobility cooldown: {GeneratedMobilityCooldownSeconds}s";
            return false;
        }

        bool ok = mode switch
        {
            "recall_home" => TryRecallHome(),
            "blink_to_cursor" => requestedTarget.HasValue
                ? TryBlinkToTarget(gameplay, requestedTarget.Value)
                : TryBlinkToCursor(gameplay),
            _ => UnsupportedGeneratedMobility(mode),
        };
        if (ok)
        {
            _lastGeneratedMobilityFailureMessage = "";
            StartGeneratedMobilityCooldown(gameplay.MobilityCooldownTicks);
        }
        return ok;
    }


    public bool TryRunGeneratedMobility(string mode, int rangeTiles, int cooldownTicks, bool safeTileOnly)
    {
        mode = (mode ?? "").Trim().ToLowerInvariant();
        var gp = new GameplaySpec
        {
            MobilityMode = mode,
            MobilityRangeTiles = rangeTiles,
            MobilityCooldownTicks = cooldownTicks,
            MobilitySafeTileOnly = safeTileOnly,
        };
        return TryRunGeneratedMobility(gp);
    }

    public bool TryRunGeneratedMobilityFromServerIntent(
        string mode,
        int rangeTiles,
        int cooldownTicks,
        bool safeTileOnly,
        Vector2 requestedTarget)
    {
        if (Main.netMode != NetmodeID.Server)
            return false;
        var gp = new GameplaySpec
        {
            MobilityMode = mode,
            MobilityRangeTiles = rangeTiles,
            MobilityCooldownTicks = cooldownTicks,
            MobilitySafeTileOnly = safeTileOnly,
        };
        return TryRunGeneratedMobility(gp, requestedTarget);
    }

    private bool UnsupportedGeneratedMobility(string mode)
    {
        _lastGeneratedMobilityFailureMessage = string.IsNullOrWhiteSpace(mode)
            ? "No generated mobility mode"
            : $"Unsupported mobility: {mode}";
        return false;
    }

    private bool TryRecallHome()
    {
        if (Player.dead)
        {
            _lastGeneratedMobilityFailureMessage = "Cannot use mobility while dead";
            return false;
        }
        if (!InfiniCrafterLocal.Common.Services.InfiniRuntimeAuthority.ShouldRunPlayerGameplay(Player))
        {
            _lastGeneratedMobilityFailureMessage = "Mobility is waiting for gameplay authority";
            return false;
        }
        int sx = Player.SpawnX >= 0 ? Player.SpawnX : Main.spawnTileX;
        int sy = Player.SpawnY >= 0 ? Player.SpawnY : Main.spawnTileY;
        if (sx <= 0 || sy <= 0)
        {
            _lastGeneratedMobilityFailureMessage = "No valid spawn point";
            return false;
        }
        Vector2 destination = new(sx * 16f + 8f - Player.width / 2f, sy * 16f - Player.height);
        Player.Teleport(destination, 0);
        InfiniCrafterLocal.Common.Services.InfiniRuntimeAuthority.SyncTeleport(Player, destination);
        return true;
    }

    private bool TryBlinkToCursor(GameplaySpec gameplay)
    {
        if (!InfiniCrafterLocal.Common.Services.InfiniRuntimeAuthority.ShouldRunLocalPlayerAction(Player))
        {
            _lastGeneratedMobilityFailureMessage = "Mobility is waiting for local control";
            return false;
        }
        return TryBlinkToTarget(gameplay, Main.MouseWorld);
    }

    private bool TryBlinkToTarget(GameplaySpec gameplay, Vector2 target)
    {
        if (Player.dead)
        {
            _lastGeneratedMobilityFailureMessage = "Cannot use mobility while dead";
            return false;
        }
        if (!InfiniCrafterLocal.Common.Services.InfiniRuntimeAuthority.ShouldRunPlayerGameplay(Player))
        {
            _lastGeneratedMobilityFailureMessage = "Mobility is waiting for gameplay authority";
            return false;
        }
        if (gameplay.MobilityRangeTiles <= 0)
        {
            _lastGeneratedMobilityFailureMessage = "Missing authored blink range";
            return false;
        }
        int rangeTiles = Math.Clamp(gameplay.MobilityRangeTiles, 1, 80);
        Vector2 delta = target - Player.Center;
        float max = rangeTiles * 16f;
        if (delta.Length() > max)
            target = Player.Center + delta.SafeNormalize(Vector2.UnitX * Player.direction) * max;
        Vector2 destination = new(target.X - Player.width / 2f, target.Y - Player.height / 2f);
        if (gameplay.MobilitySafeTileOnly && !IsSafeBlinkDestination(destination))
        {
            _lastGeneratedMobilityFailureMessage = "Unsafe blink destination";
            return false;
        }
        Player.Teleport(destination, 0);
        InfiniCrafterLocal.Common.Services.InfiniRuntimeAuthority.SyncTeleport(Player, destination);
        return true;
    }

    private bool IsSafeBlinkDestination(Vector2 destination)
    {
        Rectangle target = new((int)destination.X, (int)destination.Y, Player.width, Player.height);
        if (target.Left < 16 || target.Top < 16 || target.Right >= (Main.maxTilesX - 1) * 16 || target.Bottom >= (Main.maxTilesY - 1) * 16)
            return false;
        int left = Math.Max(0, target.Left / 16 - 1);
        int right = Math.Min(Main.maxTilesX - 1, target.Right / 16 + 1);
        int top = Math.Max(0, target.Top / 16 - 1);
        int bottom = Math.Min(Main.maxTilesY - 1, target.Bottom / 16 + 1);
        for (int x = left; x <= right; x++)
        for (int y = top; y <= bottom; y++)
        {
            Tile tile = Main.tile[x, y];
            if (tile.HasTile && Main.tileSolid[tile.TileType] && !Main.tileSolidTop[tile.TileType])
            {
                Rectangle block = new(x * 16, y * 16, 16, 16);
                if (target.Intersects(block)) return false;
            }
            if (tile.LiquidAmount > 0 && tile.LiquidType == LiquidID.Lava)
                return false;
        }
        return true;
    }


    private void TickGeneratedUtilityBuff()
    {
        if (_generatedMobilityCooldownTicks > 0)
            _generatedMobilityCooldownTicks--;
        if (_generatedAltUseRequestCooldownTicks > 0)
            _generatedAltUseRequestCooldownTicks--;

        if (_activeGeneratedUtilityBuffs.Count > 0)
        {
            for (int index = _activeGeneratedUtilityBuffs.Count - 1; index >= 0; index--)
            {
                var active = _activeGeneratedUtilityBuffs[index];
                active.Ticks--;
                if (active.Ticks <= 0)
                    _activeGeneratedUtilityBuffs.RemoveAt(index);
            }
            RebuildGeneratedUtilityBuffAggregate();
        }
        else if (!InfiniRuntimeAuthority.ShouldRunPlayerGameplay(Player) && _generatedBuffTicks > 0)
        {
            // Version-mismatch fallback only; v2 snapshots carry exact entries.
            _generatedBuffTicks--;
        }

        if (_generatedBuffTicks <= 0)
        {
            if (_activeGeneratedUtilityBuffs.Count == 0)
                ResetGeneratedUtilityBuffAggregate();
            return;
        }
        if (_generatedLightStrength > 0f && Main.netMode != NetmodeID.Server)
        {
            Color c = RuntimeColorPolicy.Resolve(_generatedLightColorName, Color.White);
            float strength = Math.Clamp(_generatedLightStrength, 0f, 1.5f);
            Lighting.AddLight(Player.Center, c.R / 255f * strength, c.G / 255f * strength, c.B / 255f * strength);
        }
    }

    private void ApplyGeneratedUtilityBuffEffects()
    {
        if (_generatedBuffTicks <= 0 || !InfiniRuntimeAuthority.ShouldRunPlayerGameplay(Player))
            return;
        if (_generatedMiningSpeedMultiplier > 0.001f && Math.Abs(_generatedMiningSpeedMultiplier - 1f) > 0.001f)
            Player.pickSpeed /= Math.Clamp(_generatedMiningSpeedMultiplier, 0.25f, 4f);
        if (_generatedMovementSpeed != 0f)
            Player.moveSpeed += _generatedMovementSpeed;
        if (_generatedJumpBoost > 0f)
            Player.jumpSpeedBoost += _generatedJumpBoost;
        if (_generatedManaRegen > 0)
            Player.manaRegenBonus += _generatedManaRegen;
        if (_generatedLifeRegen > 0)
            Player.lifeRegen += _generatedLifeRegen;
        if (_generatedOreSenseRadiusTiles > 0)
            Player.findTreasure = true;
    }

}

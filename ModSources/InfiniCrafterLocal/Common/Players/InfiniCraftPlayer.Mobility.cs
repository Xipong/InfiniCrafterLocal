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
        _generatedMobilityCooldownTicks = Math.Clamp(cooldownTicks <= 0 ? 60 : cooldownTicks, 1, 36000);
    }


    public void ApplyGeneratedUtilityBuff(GeneratedBuffSpec? buff)
    {
        if (buff is null) return;
        buff.Normalize();
        if (!buff.HasAnyEffect) return;
        _generatedBuffTicks = Math.Max(_generatedBuffTicks, Math.Clamp(buff.DurationTicks, 1, 21600));
        _generatedMiningSpeedMultiplier = Math.Max(_generatedMiningSpeedMultiplier, Math.Clamp(buff.MiningSpeedMultiplier, 0.25f, 4f));
        _generatedLightStrength = Math.Max(_generatedLightStrength, Math.Clamp(buff.EmitLightStrength, 0f, 1.5f));
        if (!string.IsNullOrWhiteSpace(buff.LightColorName))
            _generatedLightColorName = buff.LightColorName;
        _generatedOreSenseRadiusTiles = Math.Max(_generatedOreSenseRadiusTiles, Math.Clamp(buff.OreSenseRadiusTiles, 0, 60));
        _generatedMovementSpeed = Math.Max(_generatedMovementSpeed, Math.Clamp(buff.MovementSpeed, -0.5f, 2f));
        _generatedJumpBoost = Math.Max(_generatedJumpBoost, Math.Clamp(buff.JumpBoost, 0f, 8f));
        _generatedManaRegen = Math.Max(_generatedManaRegen, Math.Clamp(buff.ManaRegen, 0, 120));
        _generatedLifeRegen = Math.Max(_generatedLifeRegen, Math.Clamp(buff.LifeRegen, 0, 120));
    }


    public bool TryRunGeneratedMobility(GameplaySpec? gameplay)
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
        if (!InfiniCrafterLocal.Common.Services.InfiniRuntimeAuthority.ShouldRunLocalPlayerAction(Player))
        {
            _lastGeneratedMobilityFailureMessage = "Mobility is waiting for local control";
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
        if (Player.dead)
        {
            _lastGeneratedMobilityFailureMessage = "Cannot use mobility while dead";
            return false;
        }
        if (!InfiniCrafterLocal.Common.Services.InfiniRuntimeAuthority.ShouldRunLocalPlayerAction(Player))
        {
            _lastGeneratedMobilityFailureMessage = "Mobility is waiting for local control";
            return false;
        }
        int rangeTiles = Math.Clamp(gameplay.MobilityRangeTiles <= 0 ? 18 : gameplay.MobilityRangeTiles, 1, 80);
        Vector2 target = Main.MouseWorld;
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
        if (_generatedBuffTicks <= 0)
            return;
        _generatedBuffTicks--;
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
        {
            // tMod exposes spelunker-like treasure visibility as a player bool.
            // Authored oreSenseRadiusTiles is kept/synced for debug/future radius
            // work, but current gameplay is enabled/disabled rather than spatial.
            Player.findTreasure = true;
        }
        if (_generatedLightStrength > 0f && Main.netMode != NetmodeID.Server)
        {
            Color c = RuntimeColorPolicy.Resolve(_generatedLightColorName, Color.White);
            float strength = Math.Clamp(_generatedLightStrength, 0f, 1.5f);
            Lighting.AddLight(Player.Center, c.R / 255f * strength, c.G / 255f * strength, c.B / 255f * strength);
        }
        if (_generatedBuffTicks <= 0)
        {
            _generatedMiningSpeedMultiplier = 1f;
            _generatedLightStrength = 0f;
            _generatedLightColorName = "";
            _generatedOreSenseRadiusTiles = 0;
            _generatedMovementSpeed = 0f;
            _generatedJumpBoost = 0f;
            _generatedManaRegen = 0;
            _generatedLifeRegen = 0;
        }
    }

}

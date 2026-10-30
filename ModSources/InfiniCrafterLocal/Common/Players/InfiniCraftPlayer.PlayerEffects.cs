#nullable enable
using System;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using Terraria;
using Terraria.DataStructures;
using Terraria.ID;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Players;

public sealed partial class InfiniCraftPlayer
{
    private int _itemPickupRange, _heartPickupRange, _manaPickupRange, _coinPickupRange;
    private int _potionReductionOnHit;
    private int _potionReductionPercent, _potionReductionTicks, _autoManaBelowPercent, _hurtImmunityBonus;
    private double _extraCrateChance;
    private double _traversalGravityMultiplier = 1d;
    private float _traversalFallSpeedCap;

    private void ResetPlayerEffects()
    {
        _itemPickupRange = _heartPickupRange = _manaPickupRange = _coinPickupRange = 0;
        _potionReductionPercent = _potionReductionTicks = _autoManaBelowPercent = _hurtImmunityBonus = 0;
        _extraCrateChance = 0;
        _potionReductionOnHit = 0;
        ResetAirJumpGrants();
        _traversalGravityMultiplier = 1f; _traversalFallSpeedCap = 0;
    }

    internal void ApplyPlayerEffect(PlayerEffectSpec effect, GeneratedItemData? source = null, long sourceGeneration = 0, string sourceComponent = "accessory")
    {
        effect.Validate();
        if (!Player.active || Player.dead || !effect.IsActive(Player)) return;
        if (effect.AirJump is { } jump && source is not null) RegisterAirJumpGrant(source, jump, sourceGeneration, sourceComponent);
        _potionReductionOnHit = Math.Min(3600, _potionReductionOnHit + (effect.HealingPotionCooldownOnHitReductionTicks ?? 0));
        if (effect.AutoJump == true) Player.autoJump = true;
        if (effect.GravityControl == true) Player.gravControl = true;
        if (effect.WaterBreathing == true) Player.gills = true;
        if (effect.SwimJump == true) Player.accFlipper = true;
        if (effect.WaterBuoyancy == true) Player.canFloatInWater = true;
        if (effect.WallSlideAndJump == true) Player.spikedBoots = Math.Max(Player.spikedBoots, 1);
        if (effect.WallCling == true) Player.spikedBoots = Math.Max(Player.spikedBoots, 2);
        Player.extraFall += effect.SafeFallDistanceBlocks ?? 0;
        Player.breathMax += effect.BreathCapacityBonus ?? 0;
        _traversalGravityMultiplier *= effect.GravityMultiplier ?? 1f;
        float fallCap = effect.MaxFallSpeedPxPerTick ?? 0;
        if (fallCap > 0) _traversalFallSpeedCap = _traversalFallSpeedCap > 0 ? Math.Min(_traversalFallSpeedCap, fallCap) : fallCap;
        Player.fishingSkill += effect.FishingPowerPoints ?? 0;
        if (effect.PreventLineBreak == true) Player.accFishingLine = true;
        if (effect.AllowLavaFishing == true) Player.accLavaFishing = true;
        if (effect.RevealHookedCatch == true) Player.sonarPotion = true;
        if (effect.HighlightDanger == true) Player.dangerSense = true;
        if (effect.HighlightCreatures == true) Player.detectCreature = true;
        if (effect.NightVision == true) Player.nightVision = true;
        _itemPickupRange = Math.Min(2560, _itemPickupRange + (effect.ItemPickupRangePx ?? 0));
        _heartPickupRange = Math.Min(2560, _heartPickupRange + (effect.HeartPickupRangePx ?? 0));
        _manaPickupRange = Math.Min(2560, _manaPickupRange + (effect.ManaPickupRangePx ?? 0));
        _coinPickupRange = Math.Min(2560, _coinPickupRange + (effect.CoinPickupRangePx ?? 0));
        _potionReductionPercent = Math.Min(90, _potionReductionPercent + (effect.HealingPotionCooldownReductionPercent ?? 0));
        _potionReductionTicks = Math.Min(3600, _potionReductionTicks + (effect.HealingPotionCooldownReductionTicks ?? 0));
        _autoManaBelowPercent = Math.Max(_autoManaBelowPercent, effect.AutoManaPotionBelowPercent ?? 0);
        _hurtImmunityBonus = Math.Min(300, _hurtImmunityBonus + (effect.HurtInvulnerabilityBonusTicks ?? 0));
        _extraCrateChance = 1 - (1 - _extraCrateChance) * (1 - (effect.ExtraCrateChancePercent ?? 0) / 100d);
    }

    private void ApplyGeneratedTraversalMovement()
    {
        Player.gravity *= (float)Math.Clamp(_traversalGravityMultiplier, 0.01d, 25d);
        if (_traversalFallSpeedCap <= 0) return;
        Player.maxFallSpeed = Math.Min(Player.maxFallSpeed, _traversalFallSpeedCap);
    }

    // Existing stat values have one consumer; conditions only gate when the
    // native contribution applies, never create another regeneration channel.
    internal void ApplyLifeRegen(int units, string? condition = null)
    {
        if (Player.active && !Player.dead && PlayerEffectSpec.IsConditionActive(condition ?? "always", Player))
            Player.lifeRegen += units;
    }

    internal void ApplyTreasureSense(bool enabled, string? condition = null)
    {
        if (enabled && Player.active && !Player.dead && PlayerEffectSpec.IsConditionActive(condition ?? "always", Player))
            Player.findTreasure = true;
    }

    internal void ModifyHealingPotionBaseDelay(ref int ticks)
        => ticks = Math.Max(0, (int)((long)ticks * (100 - _potionReductionPercent) / 100) - _potionReductionTicks);

    internal int PickupRangeBonus(Item item)
    {
        int specific = item.type switch {
            ItemID.Heart or ItemID.CandyApple or ItemID.CandyCane => _heartPickupRange,
            ItemID.Star or ItemID.SoulCake or ItemID.SugarPlum => _manaPickupRange,
            ItemID.CopperCoin or ItemID.SilverCoin or ItemID.GoldCoin or ItemID.PlatinumCoin => _coinPickupRange,
            _ => 0,
        };
        return _itemPickupRange + specific;
    }

    public override void ModifyFishingAttempt(ref FishingAttempt attempt)
    {
        if (attempt.crate || _extraCrateChance <= 0) return;
        if (_extraCrateChance >= 1 || Main.rand.NextDouble() < _extraCrateChance) attempt.crate = true;
    }

    private void AutoUseManaPotion()
    {
        if (_autoManaBelowPercent <= 0 || !InfiniRuntimeAuthority.ShouldRunLocalPlayerAction(Player)
            || Player.dead || Player.statLife <= 0 || Player.statMana >= Player.statManaMax2 * _autoManaBelowPercent / 100d) return;
        // Native inventory admission, consumption, mana sickness and mod hooks remain in QuickMana.
        Player.QuickMana();
    }

    private void ExtendHurtImmunity(Player.HurtInfo info)
    {
        if (_hurtImmunityBonus <= 0) return;
        if (info.CooldownCounter == -1) Player.immuneTime = Math.Min(3600, Player.immuneTime + _hurtImmunityBonus);
        else if ((uint)info.CooldownCounter < Player.hurtCooldowns.Length)
            Player.hurtCooldowns[info.CooldownCounter] = Math.Min(3600, Player.hurtCooldowns[info.CooldownCounter] + _hurtImmunityBonus);
    }

    public override void OnHitNPCWithItem(Item item, NPC target, NPC.HitInfo hit, int damageDone)
    {
        if (damageDone > 0 && _potionReductionOnHit > 0) ReduceHealingPotionCooldown(_potionReductionOnHit);
    }

    public override void OnHitNPCWithProj(Projectile projectile, NPC target, NPC.HitInfo hit, int damageDone)
    {
        if (projectile.owner == Player.whoAmI && damageDone > 0 && _potionReductionOnHit > 0)
            ReduceHealingPotionCooldown(_potionReductionOnHit);
    }

    internal void ReduceHealingPotionCooldown(int ticks)
    {
        if (ticks is < 1 or > 3600) throw new ArgumentOutOfRangeException(nameof(ticks));
        if (!InfiniRuntimeAuthority.ShouldRunLocalPlayerAction(Player) || Player.dead || Player.statLife <= 0) return;
        int index = Player.FindBuffIndex(BuffID.PotionSickness);
        Player.potionDelay = Math.Max(0, Player.potionDelay - ticks);
        if (index < 0) return;
        Player.buffTime[index] = Math.Max(0, Player.buffTime[index] - ticks);
        if (Player.buffTime[index] == 0) Player.DelBuff(index);
    }
}

// Native item hooks read the same per-player modifiers for vanilla and modded items.
public sealed class GeneratedPlayerEffectItemHooks : GlobalItem
{
    public override void GrabRange(Item item, Player player, ref int grabRange)
        => grabRange += player.GetModPlayer<InfiniCraftPlayer>().PickupRangeBonus(item);

    public override void ModifyPotionDelay(Item item, Player player, ref int baseDelay)
        => player.GetModPlayer<InfiniCraftPlayer>().ModifyHealingPotionBaseDelay(ref baseDelay);
}

#nullable enable
using System;
using System.IO;
using System.Text.Json.Serialization;
using Terraria;

namespace InfiniCrafterLocal.Common.Models;

public sealed record PlayerEffectSpec
{
    public string Condition { get; set; } = "always";
    public bool IsActive(Player player) => Condition == "always" || player.velocity == Microsoft.Xna.Framework.Vector2.Zero && player.itemAnimation == 0;
    private int? _fishingPowerPoints;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? FishingPowerPoints
    {
        get => _fishingPowerPoints;
        set {
            if (value is not int scalar || scalar < 0 || scalar > 100)
                throw new InvalidDataException("fishingPowerPoints must match its declared int domain when present");
            _fishingPowerPoints = scalar;
        }
    }
    private bool? _preventLineBreak;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public bool? PreventLineBreak
    {
        get => _preventLineBreak;
        set {
            if (value is not bool scalar)
                throw new InvalidDataException("preventLineBreak must match its declared bool domain when present");
            _preventLineBreak = scalar;
        }
    }
    private bool? _allowLavaFishing;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public bool? AllowLavaFishing
    {
        get => _allowLavaFishing;
        set {
            if (value is not bool scalar)
                throw new InvalidDataException("allowLavaFishing must match its declared bool domain when present");
            _allowLavaFishing = scalar;
        }
    }
    private bool? _revealHookedCatch;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public bool? RevealHookedCatch
    {
        get => _revealHookedCatch;
        set {
            if (value is not bool scalar)
                throw new InvalidDataException("revealHookedCatch must match its declared bool domain when present");
            _revealHookedCatch = scalar;
        }
    }
    private int? _extraCrateChancePercent;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? ExtraCrateChancePercent
    {
        get => _extraCrateChancePercent;
        set {
            if (value is not int scalar || scalar < 0 || scalar > 100)
                throw new InvalidDataException("extraCrateChancePercent must match its declared int domain when present");
            _extraCrateChancePercent = scalar;
        }
    }
    private int? _itemPickupRangePx;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? ItemPickupRangePx
    {
        get => _itemPickupRangePx;
        set {
            if (value is not int scalar || scalar < 0 || scalar > 640)
                throw new InvalidDataException("itemPickupRangePx must match its declared int domain when present");
            _itemPickupRangePx = scalar;
        }
    }
    private int? _heartPickupRangePx;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? HeartPickupRangePx
    {
        get => _heartPickupRangePx;
        set {
            if (value is not int scalar || scalar < 0 || scalar > 640)
                throw new InvalidDataException("heartPickupRangePx must match its declared int domain when present");
            _heartPickupRangePx = scalar;
        }
    }
    private int? _manaPickupRangePx;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? ManaPickupRangePx
    {
        get => _manaPickupRangePx;
        set {
            if (value is not int scalar || scalar < 0 || scalar > 640)
                throw new InvalidDataException("manaPickupRangePx must match its declared int domain when present");
            _manaPickupRangePx = scalar;
        }
    }
    private int? _coinPickupRangePx;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? CoinPickupRangePx
    {
        get => _coinPickupRangePx;
        set {
            if (value is not int scalar || scalar < 0 || scalar > 640)
                throw new InvalidDataException("coinPickupRangePx must match its declared int domain when present");
            _coinPickupRangePx = scalar;
        }
    }
    private bool? _highlightTreasure;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public bool? HighlightTreasure
    {
        get => _highlightTreasure;
        set {
            if (value is not bool scalar)
                throw new InvalidDataException("highlightTreasure must match its declared bool domain when present");
            _highlightTreasure = scalar;
        }
    }
    private bool? _highlightDanger;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public bool? HighlightDanger
    {
        get => _highlightDanger;
        set {
            if (value is not bool scalar)
                throw new InvalidDataException("highlightDanger must match its declared bool domain when present");
            _highlightDanger = scalar;
        }
    }
    private bool? _highlightCreatures;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public bool? HighlightCreatures
    {
        get => _highlightCreatures;
        set {
            if (value is not bool scalar)
                throw new InvalidDataException("highlightCreatures must match its declared bool domain when present");
            _highlightCreatures = scalar;
        }
    }
    private bool? _nightVision;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public bool? NightVision
    {
        get => _nightVision;
        set {
            if (value is not bool scalar)
                throw new InvalidDataException("nightVision must match its declared bool domain when present");
            _nightVision = scalar;
        }
    }
    private int? _healingPotionCooldownReductionPercent;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? HealingPotionCooldownReductionPercent
    {
        get => _healingPotionCooldownReductionPercent;
        set {
            if (value is not int scalar || scalar < 0 || scalar > 90)
                throw new InvalidDataException("healingPotionCooldownReductionPercent must match its declared int domain when present");
            _healingPotionCooldownReductionPercent = scalar;
        }
    }
    private int? _healingPotionCooldownReductionTicks;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? HealingPotionCooldownReductionTicks
    {
        get => _healingPotionCooldownReductionTicks;
        set {
            if (value is not int scalar || scalar < 0 || scalar > 3600)
                throw new InvalidDataException("healingPotionCooldownReductionTicks must match its declared int domain when present");
            _healingPotionCooldownReductionTicks = scalar;
        }
    }
    private int? _autoManaPotionBelowPercent;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? AutoManaPotionBelowPercent
    {
        get => _autoManaPotionBelowPercent;
        set {
            if (value is not int scalar || scalar < 0 || scalar > 100)
                throw new InvalidDataException("autoManaPotionBelowPercent must match its declared int domain when present");
            _autoManaPotionBelowPercent = scalar;
        }
    }
    private int? _lifeRegenUnits;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? LifeRegenUnits
    {
        get => _lifeRegenUnits;
        set {
            if (value is not int scalar || scalar < -100 || scalar > 200)
                throw new InvalidDataException("lifeRegenUnits must match its declared int domain when present");
            _lifeRegenUnits = scalar;
        }
    }
    private int? _hurtInvulnerabilityBonusTicks;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? HurtInvulnerabilityBonusTicks
    {
        get => _hurtInvulnerabilityBonusTicks;
        set {
            if (value is not int scalar || scalar < 0 || scalar > 300)
                throw new InvalidDataException("hurtInvulnerabilityBonusTicks must match its declared int domain when present");
            _hurtInvulnerabilityBonusTicks = scalar;
        }
    }
    private int? _healingPotionCooldownOnHitReductionTicks;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? HealingPotionCooldownOnHitReductionTicks
    {
        get => _healingPotionCooldownOnHitReductionTicks;
        set { if (value is not int ticks || ticks < 0 || ticks > 3600) throw new InvalidDataException("healingPotionCooldownOnHitReductionTicks must be 0..3600"); _healingPotionCooldownOnHitReductionTicks = ticks; }
    }
    [JsonIgnore] public bool HasEffect => (HealingPotionCooldownOnHitReductionTicks ?? 0) != 0 || (FishingPowerPoints ?? 0) != 0 || PreventLineBreak == true || AllowLavaFishing == true || RevealHookedCatch == true || (ExtraCrateChancePercent ?? 0) != 0 || (ItemPickupRangePx ?? 0) != 0 || (HeartPickupRangePx ?? 0) != 0 || (ManaPickupRangePx ?? 0) != 0 || (CoinPickupRangePx ?? 0) != 0 || HighlightTreasure == true || HighlightDanger == true || HighlightCreatures == true || NightVision == true || (HealingPotionCooldownReductionPercent ?? 0) != 0 || (HealingPotionCooldownReductionTicks ?? 0) != 0 || (AutoManaPotionBelowPercent ?? 0) != 0 || (LifeRegenUnits ?? 0) != 0 || (HurtInvulnerabilityBonusTicks ?? 0) != 0;
    public void Validate() { if (Condition is not ("always" or "stationary")) throw new InvalidDataException("Unknown player-effect condition"); }
    internal static bool SameEffect(PlayerEffectSpec? a, PlayerEffectSpec? b)
    {
        if (a?.HasEffect != true) a = null;
        if (b?.HasEffect != true) b = null;
        return (a?.HealingPotionCooldownOnHitReductionTicks ?? 0) == (b?.HealingPotionCooldownOnHitReductionTicks ?? 0)
        && (a?.Condition ?? "always") == (b?.Condition ?? "always")
        && (a?.FishingPowerPoints ?? 0) == (b?.FishingPowerPoints ?? 0)
        && (a?.PreventLineBreak ?? false) == (b?.PreventLineBreak ?? false)
        && (a?.AllowLavaFishing ?? false) == (b?.AllowLavaFishing ?? false)
        && (a?.RevealHookedCatch ?? false) == (b?.RevealHookedCatch ?? false)
        && (a?.ExtraCrateChancePercent ?? 0) == (b?.ExtraCrateChancePercent ?? 0)
        && (a?.ItemPickupRangePx ?? 0) == (b?.ItemPickupRangePx ?? 0)
        && (a?.HeartPickupRangePx ?? 0) == (b?.HeartPickupRangePx ?? 0)
        && (a?.ManaPickupRangePx ?? 0) == (b?.ManaPickupRangePx ?? 0)
        && (a?.CoinPickupRangePx ?? 0) == (b?.CoinPickupRangePx ?? 0)
        && (a?.HighlightTreasure ?? false) == (b?.HighlightTreasure ?? false)
        && (a?.HighlightDanger ?? false) == (b?.HighlightDanger ?? false)
        && (a?.HighlightCreatures ?? false) == (b?.HighlightCreatures ?? false)
        && (a?.NightVision ?? false) == (b?.NightVision ?? false)
        && (a?.HealingPotionCooldownReductionPercent ?? 0) == (b?.HealingPotionCooldownReductionPercent ?? 0)
        && (a?.HealingPotionCooldownReductionTicks ?? 0) == (b?.HealingPotionCooldownReductionTicks ?? 0)
        && (a?.AutoManaPotionBelowPercent ?? 0) == (b?.AutoManaPotionBelowPercent ?? 0)
        && (a?.LifeRegenUnits ?? 0) == (b?.LifeRegenUnits ?? 0)
        && (a?.HurtInvulnerabilityBonusTicks ?? 0) == (b?.HurtInvulnerabilityBonusTicks ?? 0);
    }
    internal void Write(BinaryWriter writer) {
        Validate(); writer.Write((byte)(Condition == "stationary" ? 1 : 0));
        writer.Write(HealingPotionCooldownOnHitReductionTicks ?? 0);
        writer.Write(FishingPowerPoints ?? 0);
        writer.Write(PreventLineBreak ?? false);
        writer.Write(AllowLavaFishing ?? false);
        writer.Write(RevealHookedCatch ?? false);
        writer.Write(ExtraCrateChancePercent ?? 0);
        writer.Write(ItemPickupRangePx ?? 0);
        writer.Write(HeartPickupRangePx ?? 0);
        writer.Write(ManaPickupRangePx ?? 0);
        writer.Write(CoinPickupRangePx ?? 0);
        writer.Write(HighlightTreasure ?? false);
        writer.Write(HighlightDanger ?? false);
        writer.Write(HighlightCreatures ?? false);
        writer.Write(NightVision ?? false);
        writer.Write(HealingPotionCooldownReductionPercent ?? 0);
        writer.Write(HealingPotionCooldownReductionTicks ?? 0);
        writer.Write(AutoManaPotionBelowPercent ?? 0);
        writer.Write(LifeRegenUnits ?? 0);
        writer.Write(HurtInvulnerabilityBonusTicks ?? 0);
    }
    internal static PlayerEffectSpec Read(BinaryReader reader) {
        byte condition = reader.ReadByte(); if (condition > 1) throw new InvalidDataException("Unknown player-effect condition");
        return new PlayerEffectSpec { Condition = condition == 1 ? "stationary" : "always",
            HealingPotionCooldownOnHitReductionTicks = reader.ReadInt32(),
            FishingPowerPoints = reader.ReadInt32(),
            PreventLineBreak = reader.ReadBoolean(),
            AllowLavaFishing = reader.ReadBoolean(),
            RevealHookedCatch = reader.ReadBoolean(),
            ExtraCrateChancePercent = reader.ReadInt32(),
            ItemPickupRangePx = reader.ReadInt32(),
            HeartPickupRangePx = reader.ReadInt32(),
            ManaPickupRangePx = reader.ReadInt32(),
            CoinPickupRangePx = reader.ReadInt32(),
            HighlightTreasure = reader.ReadBoolean(),
            HighlightDanger = reader.ReadBoolean(),
            HighlightCreatures = reader.ReadBoolean(),
            NightVision = reader.ReadBoolean(),
            HealingPotionCooldownReductionPercent = reader.ReadInt32(),
            HealingPotionCooldownReductionTicks = reader.ReadInt32(),
            AutoManaPotionBelowPercent = reader.ReadInt32(),
            LifeRegenUnits = reader.ReadInt32(),
            HurtInvulnerabilityBonusTicks = reader.ReadInt32(),
        };
    }
}

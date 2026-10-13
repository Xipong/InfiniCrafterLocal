#nullable enable
using System;
using System.IO;
using System.Linq;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;
using InfiniCrafterLocal.Common.VFX;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Models;

/// <summary>The fields consumed by both the legacy default and explicit named groups.</summary>
public interface IItemEffectsSpec
{
    int HealLife { get; }
    int HealMana { get; }
    bool Potion { get; }
    int BuffCode { get; }
    int BuffTime { get; }
    BuffEntrySpec[] ExtraBuffs { get; }
    GeneratedBuffSpec? GeneratedBuff { get; }
    string MobilityMode { get; }
    int MobilityRangeTiles { get; }
    int MobilityCooldownTicks { get; }
    bool MobilitySafeTileOnly { get; }
}

/// <summary>Only authored item effects; no item stats or implicit carrier entity.</summary>
public sealed class RuntimeItemEffectGroupSpec : IItemEffectsSpec
{
    public string Id { get; set; } = "";
    public int HealLife { get; set; }
    public int HealMana { get; set; }
    public bool Potion { get; set; }
    private BuffEntrySpec[] _extraBuffs = Array.Empty<BuffEntrySpec>();
    public BuffEntrySpec[] ExtraBuffs
    {
        get => _extraBuffs;
        set => _extraBuffs = value is { Length: <= 48 } ? value
            : throw new InvalidDataException("present effect-group extraBuffs requires a non-null array of up to 48 rows");
    }
    private GeneratedBuffSpec? _generatedBuff;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public GeneratedBuffSpec? GeneratedBuff
    {
        get => _generatedBuff;
        set => _generatedBuff = value ?? throw new InvalidDataException("present effect-group generatedBuff cannot be null");
    }
    public string MobilityMode { get; set; } = "";
    public int MobilityRangeTiles { get; set; }
    public int MobilityCooldownTicks { get; set; }
    public bool MobilitySafeTileOnly { get; set; } = true;
    // Named native buffs are an explicit append component, never a second hidden slot.
    int IItemEffectsSpec.BuffCode => 0;
    int IItemEffectsSpec.BuffTime => 0;

    internal static string RequireId(string? value)
        => value is not null && Regex.IsMatch(value, @"\A[a-z][a-z0-9_]{0,47}\z") ? value
            : throw new InvalidDataException("effect group ID must match [a-z][a-z0-9_]{0,47}");

    internal bool HasAnyEffect => HasEffects(this);
    internal bool IsGeneratedBuffOnly => GeneratedBuff?.HasAnyEffect == true
        && HealLife == 0 && HealMana == 0 && !Potion && ExtraBuffs.Length == 0
        && MobilityMode == "" && MobilityRangeTiles == 0 && MobilityCooldownTicks == 0;

    internal static bool HasEffects(IItemEffectsSpec effects)
        => effects.HealLife > 0 || effects.HealMana > 0 || effects.ExtraBuffs.Length > 0
            || effects.GeneratedBuff?.HasAnyEffect == true || effects.MobilityMode.Length > 0;

    internal void NormalizeAndValidate()
    {
        _ = RequireId(Id);
        if (HealLife is < 0 or > 500 || HealMana is < 0 or > 500
            || MobilityRangeTiles is < 0 or > 120 || MobilityCooldownTicks is < 0 or > 3600
            || MobilityMode is not ("" or "recall_home" or "blink_to_cursor"))
            throw new InvalidDataException("effect group has an out-of-domain resource or mobility field");
        if (ExtraBuffs.Any(x => x is null || x.BuffCode <= 0 || x.BuffCode >= BuffLoader.BuffCount
                || x.BuffTime is < 1 or > 21600))
            throw new InvalidDataException("effect group native buffs need loaded IDs and explicit 1..21600 duration");
        if (GeneratedBuff is { } buff)
        {
            static bool Between(float value, float low, float high) => float.IsFinite(value) && value >= low && value <= high;
            if (buff.DurationTicks is < 1 or > 21600 || !Between(buff.MiningSpeedMultiplier, .25f, 4f)
                || !Between(buff.EmitLightStrength, 0f, 1.5f) || buff.OreSenseRadiusTiles is not (0 or 1)
                || !Between(buff.MovementSpeed, -.5f, 2f) || !Between(buff.JumpBoost, 0f, 8f)
                || buff.ManaRegen is < 0 or > 120 || buff.LifeRegen is < 0 or > 120
                || buff.LightColorName != RuntimeColorPolicy.NormalizeRequired(buff.LightColorName, allowEmpty: buff.EmitLightStrength <= 0f))
                throw new InvalidDataException("effect group generated buff must match the exact registered wire domain");
        }
        if (!HasAnyEffect)
            throw new InvalidDataException("named effect group has no explicit executable item effect");
    }
}

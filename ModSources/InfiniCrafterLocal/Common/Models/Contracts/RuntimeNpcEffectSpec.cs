#nullable enable
using System;
using System.IO;
using System.Text.Json.Serialization;

namespace InfiniCrafterLocal.Common.Models;

// Generated numeric semantics, not a native BuffID/immunity or debuff UI identity.
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed class RuntimeNpcEffectSpec
{
    private int _lifeRegenPenalty, _defenseDelta;
    private float _contactDamageMultiplier = 1f, _velocityRetentionPerTick = 1f, _chance = 1f;
    public int LifeRegenPenalty { get => _lifeRegenPenalty; set => _lifeRegenPenalty = value is >= 0 and <= 400
        ? value : throw new InvalidDataException("lifeRegenPenalty must be 0..400 native regeneration units"); }
    public int DefenseDelta { get => _defenseDelta; set => _defenseDelta = value is >= -100 and <= 100
        ? value : throw new InvalidDataException("defenseDelta must be -100..100"); }
    public sealed class ContactMultiplierNumber : RawJsonFloatDomainConverter
    { public ContactMultiplierNumber() : base("0.1", "3", "1") { } }
    public sealed class RetentionNumber : RawJsonFloatDomainConverter
    { public RetentionNumber() : base("0.1", "1", "1") { } }
    public sealed class ChanceNumber : RawJsonFloatDomainConverter
    { public ChanceNumber() : base("0", "1", "1") { } }
    [JsonConverter(typeof(ContactMultiplierNumber))]
    public float ContactDamageMultiplier { get => _contactDamageMultiplier; set => _contactDamageMultiplier = Require(value, .1f, 3f); }
    // Post-AI damping once per world tick; not exact movement speed or an AI rewrite.
    [JsonConverter(typeof(RetentionNumber))]
    public float VelocityRetentionPerTick { get => _velocityRetentionPerTick; set => _velocityRetentionPerTick = Require(value, .1f, 1f); }
    [JsonConverter(typeof(ChanceNumber))]
    public float Chance { get => _chance; set => _chance = Require(value, 0f, 1f); }
    [JsonIgnore] public bool HasEffect => LifeRegenPenalty != 0 || DefenseDelta != 0
        || ContactDamageMultiplier != 1f || VelocityRetentionPerTick != 1f;
    private static float Require(float value, float low, float high)
        => float.IsFinite(value) && value >= low && value <= high ? value
            : throw new InvalidDataException("NPC effect number outside finite domain");
    public void Validate()
    {
        if (!HasEffect) throw new InvalidDataException("NPC effect requires a nonneutral numeric effect; chance alone is not an effect");
    }
}

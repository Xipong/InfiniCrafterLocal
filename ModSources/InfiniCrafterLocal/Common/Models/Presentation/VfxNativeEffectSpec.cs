#nullable enable
using System;
using System.IO;
using System.Text.Json.Serialization;
using InfiniCrafterLocal.Common.VFX;

namespace InfiniCrafterLocal.Common.Models;

/// <summary>A selected stock visual recipe, not a procedural lowering or gameplay projectile.</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed class VfxNativeEffectSpec
{
    [JsonRequired]
    public string Type { get; set; } = "";

    private VfxNativeEffectMovement? _movement;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public VfxNativeEffectMovement? Movement
    {
        get => _movement;
        set => _movement = value ?? throw new InvalidDataException("nativeEffect movement cannot be null");
    }

    internal VfxNativeEffectSpec Copy() => new()
    {
        Type = Type,
        _movement = Movement?.Copy()
    };

    internal void Validate()
    {
        _ = VfxNativeEffects.Cost(Type);
        bool moving = Type is "rainbowBurst" or "shimmerStar";
        if (moving != (Movement is not null))
            throw new InvalidDataException("nativeEffect movement is required only by rainbowBurst/shimmerStar");
        Movement?.Validate();
    }

    internal static void ValidateSlot(VfxSlotSpec slot, bool phasePresent)
    {
        if (slot.RendererKind != "nativeEffect")
        {
            if (slot.NativeEffect is not null)
                throw new InvalidDataException("Foreign nativeEffect payload");
            return;
        }

        if (slot.NativeEffect is null)
            throw new InvalidDataException("nativeEffect requires payload");
        slot.NativeEffect.Validate();
        if (slot.StartTick is null or < 0 or > 120
            || slot.RepeatEvery is null or < 0 or > 120
            || (slot.Event == RuntimeEventKind.Periodic ? slot.RepeatEvery < 1 : slot.RepeatEvery != 0))
            throw new InvalidDataException("nativeEffect requires exact cadence");
        if (slot.Anchor is not ("self" or "owner" or "tip" or "tipHistory" or "hitPoint" or "velocity" or "field"))
            throw new InvalidDataException("Invalid nativeEffect anchor");
        if (phasePresent || slot.Color is not null || slot.Scale is not null
            || slot.Density is not null || slot.Spread is not null || slot.Alpha is not null
            || slot.Duration is not null || slot.ParticleSystemId is not null
            || slot.Blend is not null || slot.Layer is not null || slot.TextureRole is not null
            || slot.Shape is not null || slot.Element is not null || slot.Path is not null
            || slot.Particle is not null || slot.ScreenShake is not null
            || slot.Sound is not null || slot.SoundId is not null
            || slot.Dust is not null || slot.Light is not null || slot.Trail is not null)
            throw new InvalidDataException("nativeEffect forbids unrelated controls");
    }
}

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed class VfxNativeEffectMovement
{
    [JsonRequired]
    public float X { get; set; }

    [JsonRequired]
    public float Y { get; set; }

    internal VfxNativeEffectMovement Copy() => new()
    {
        X = X,
        Y = Y
    };

    internal void Validate()
    {
        VfxNativeCueValidation.Range(X, -24, 24);
        VfxNativeCueValidation.Range(Y, -24, 24);
    }
}

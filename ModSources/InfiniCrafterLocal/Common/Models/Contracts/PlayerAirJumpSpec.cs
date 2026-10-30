#nullable enable
using System;
using System.IO;
using System.Text.Json.Serialization;

namespace InfiniCrafterLocal.Common.Models;

// Movement and presentation are independent: this DTO never chooses a dust,
// sound, vanilla jump id or visual style for the authored movement.
public sealed record PlayerAirJumpSpec
{
    [JsonRequired] public int Count { get; init; }
    [JsonRequired] public float LaunchSpeedPxPerTick { get; init; }
    [JsonRequired] public int HoldDurationTicks { get; init; }
    public float HorizontalAccelerationMultiplier { get; init; } = 1f;
    public float HorizontalSpeedMultiplier { get; init; } = 1f;

    public void Validate()
    {
        if (Count is < 1 or > 6 || !float.IsFinite(LaunchSpeedPxPerTick) || LaunchSpeedPxPerTick is < 0.1f or > 32f
            || HoldDurationTicks is < 1 or > 120
            || !float.IsFinite(HorizontalAccelerationMultiplier) || HorizontalAccelerationMultiplier is < 0.1f or > 5f
            || !float.IsFinite(HorizontalSpeedMultiplier) || HorizontalSpeedMultiplier is < 0.1f or > 5f)
            throw new InvalidDataException("airJump fields must match the registered finite domains");
    }

    internal void Write(BinaryWriter writer)
    {
        Validate(); writer.Write(Count); writer.Write(LaunchSpeedPxPerTick); writer.Write(HoldDurationTicks);
        writer.Write(HorizontalAccelerationMultiplier); writer.Write(HorizontalSpeedMultiplier);
    }

    internal static PlayerAirJumpSpec Read(BinaryReader reader)
    {
        var value = new PlayerAirJumpSpec { Count = reader.ReadInt32(), LaunchSpeedPxPerTick = reader.ReadSingle(),
            HoldDurationTicks = reader.ReadInt32(), HorizontalAccelerationMultiplier = reader.ReadSingle(),
            HorizontalSpeedMultiplier = reader.ReadSingle() };
        value.Validate(); return value;
    }
}

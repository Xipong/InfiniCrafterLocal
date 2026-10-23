#nullable enable
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace InfiniCrafterLocal.Common.Models;

// Strict additive wire components. Absence is not materialized on saved loads.
// Units are already native pixels/projectile update or world ticks.
public static class RuntimeMotionNumbers
{
    public sealed class Offset : RawJsonFloatDomainConverter
    { public Offset() : base("-4096", "4096") { } }
    public sealed class OptionalOffset : RawJsonNullableFloatDomainConverter
    { public OptionalOffset() : base("-4096", "4096") { } }
    public sealed class Phase : RawJsonFloatDomainConverter
    { public Phase() : base("-100", "100") { } }
    public sealed class OptionalPhase : RawJsonNullableFloatDomainConverter
    { public OptionalPhase() : base("-100", "100") { } }
    public sealed class AngularRate : RawJsonFloatDomainConverter
    { public AngularRate() : base("-6", "6") { } }
    public sealed class OptionalAngularRate : RawJsonNullableFloatDomainConverter
    { public OptionalAngularRate() : base("-6", "6") { } }
    public sealed class Frequency : RawJsonFloatDomainConverter
    { public Frequency() : base("0", "6") { } }
    public sealed class OptionalFrequency : RawJsonNullableFloatDomainConverter
    { public OptionalFrequency() : base("0", "6") { } }
    public sealed class Radius : RawJsonFloatDomainConverter
    { public Radius() : base("0.001", "1920") { } }
    public sealed class OptionalRadius : RawJsonNullableFloatDomainConverter
    { public OptionalRadius() : base("0.001", "1920") { } }
    public sealed class Width : RawJsonFloatDomainConverter
    { public Width() : base("0.001", "128") { } }
    public sealed class OptionalWidth : RawJsonNullableFloatDomainConverter
    { public OptionalWidth() : base("0.001", "128") { } }
    public sealed class Speed : RawJsonFloatDomainConverter
    { public Speed() : base("0.001", "80") { } }
    public sealed class OptionalSpeed : RawJsonNullableFloatDomainConverter
    { public OptionalSpeed() : base("0.001", "80") { } }
    public sealed class NonnegativeSpeed : RawJsonFloatDomainConverter
    { public NonnegativeSpeed() : base("0", "80") { } }
    public sealed class OptionalNonnegativeSpeed : RawJsonNullableFloatDomainConverter
    { public OptionalNonnegativeSpeed() : base("0", "80") { } }
    public sealed class UnitFloat : RawJsonFloatDomainConverter
    { public UnitFloat() : base("0", "1") { } }
    public sealed class OptionalUnitFloat : RawJsonNullableFloatDomainConverter
    { public OptionalUnitFloat() : base("0", "1") { } }
    public sealed class SearchRange : RawJsonFloatDomainConverter
    { public SearchRange() : base("0.001", "120") { } }
    public sealed class OptionalSearchRange : RawJsonNullableFloatDomainConverter
    { public OptionalSearchRange() : base("0.001", "120") { } }
    public sealed class OwnerDistance : RawJsonFloatDomainConverter
    { public OwnerDistance() : base("0.001", "32000") { } }
    public sealed class OptionalOwnerDistance : RawJsonNullableFloatDomainConverter
    { public OptionalOwnerDistance() : base("0.001", "32000") { } }
    public sealed class TriggerRadius : RawJsonFloatDomainConverter
    { public TriggerRadius() : base("0.001", "512") { } }
    public sealed class OptionalTriggerRadius : RawJsonNullableFloatDomainConverter
    { public OptionalTriggerRadius() : base("0.001", "512") { } }
    public sealed class Acceleration : RawJsonFloatDomainConverter
    { public Acceleration() : base("-2", "2") { } }
    public sealed class OptionalAcceleration : RawJsonNullableFloatDomainConverter
    { public OptionalAcceleration() : base("-2", "2") { } }
    public sealed class Retention : RawJsonFloatDomainConverter
    { public Retention() : base("0", "1.2") { } }
    public sealed class OptionalRetention : RawJsonNullableFloatDomainConverter
    { public OptionalRetention() : base("0", "1.2") { } }
    public sealed class Amplitude : RawJsonFloatDomainConverter
    { public Amplitude() : base("0", "100") { } }
    public sealed class OptionalAmplitude : RawJsonNullableFloatDomainConverter
    { public OptionalAmplitude() : base("0", "100") { } }
    public sealed class ScaleDelta : RawJsonFloatDomainConverter
    { public ScaleDelta() : base("-1", "1") { } }
    public sealed class OptionalScaleDelta : RawJsonNullableFloatDomainConverter
    { public OptionalScaleDelta() : base("-1", "1") { } }
    public sealed class ScaleMax : RawJsonFloatDomainConverter
    { public ScaleMax() : base("0.01", "20") { } }
    public sealed class OptionalScaleMax : RawJsonNullableFloatDomainConverter
    { public OptionalScaleMax() : base("0.01", "20") { } }
    public sealed class LashReach : RawJsonFloatDomainConverter
    { public LashReach() : base("0.001", "960") { } }
    public sealed class OptionalLashReach : RawJsonNullableFloatDomainConverter
    { public OptionalLashReach() : base("0.001", "960") { } }
    public sealed class Bend : RawJsonFloatDomainConverter
    { public Bend() : base("-4", "4") { } }
    public sealed class OptionalBend : RawJsonNullableFloatDomainConverter
    { public OptionalBend() : base("-4", "4") { } }
    public sealed class Progress : JsonConverter<double>
    {
        private static readonly RawJsonFloatDomain Domain = new("0", "1", null);
        public override bool HandleNull => true;
        public override double Read(ref Utf8JsonReader reader, Type type, JsonSerializerOptions options)
            => Domain.ReadDouble(ref reader);
        public override void Write(Utf8JsonWriter writer, double value, JsonSerializerOptions options)
        {
            RuntimeMotionAdmission.Range(value, 0d, 1d);
            writer.WriteNumberValue(value);
        }
    }
    public sealed class DamageMultiplier : JsonConverter<double>
    {
        private static readonly RawJsonFloatDomain Domain = new("1", "4", null);
        public override bool HandleNull => true;
        public override double Read(ref Utf8JsonReader reader, Type type, JsonSerializerOptions options)
            => Domain.ReadDouble(ref reader);
        public override void Write(Utf8JsonWriter writer, double value, JsonSerializerOptions options)
        {
            RuntimeMotionAdmission.Range(value, 1d, 4d);
            writer.WriteNumberValue(value);
        }
    }
    public sealed class KnockbackMultiplier : JsonConverter<double>
    {
        private static readonly RawJsonFloatDomain Domain = new("0", "4", null);
        public override bool HandleNull => true;
        public override double Read(ref Utf8JsonReader reader, Type type, JsonSerializerOptions options)
            => Domain.ReadDouble(ref reader);
        public override void Write(Utf8JsonWriter writer, double value, JsonSerializerOptions options)
        {
            RuntimeMotionAdmission.Range(value, 0d, 4d);
            writer.WriteNumberValue(value);
        }
    }
    public sealed class SpeedMultiplier : JsonConverter<double>
    {
        private static readonly RawJsonFloatDomain Domain = new("0.1", "4", null);
        public override bool HandleNull => true;
        public override double Read(ref Utf8JsonReader reader, Type type, JsonSerializerOptions options)
            => Domain.ReadDouble(ref reader);
        public override void Write(Utf8JsonWriter writer, double value, JsonSerializerOptions options)
        {
            RuntimeMotionAdmission.Range(value, 0.1d, 4d);
            writer.WriteNumberValue(value);
        }
    }
    public sealed class InitialMultiplier : JsonConverter<double>
    {
        private static readonly RawJsonFloatDomain Domain = new("0.01", "1", null);
        public override bool HandleNull => true;
        public override double Read(ref Utf8JsonReader reader, Type type, JsonSerializerOptions options)
            => Domain.ReadDouble(ref reader);
        public override void Write(Utf8JsonWriter writer, double value, JsonSerializerOptions options)
        {
            RuntimeMotionAdmission.Range(value, 0.01d, 1d);
            writer.WriteNumberValue(value);
        }
    }
}

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed class RuntimeMotionWindowSpec
{
    [JsonRequired] public string Phase { get; set; } = null!;
    private string? _clock;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? Clock
    {
        get => _clock;
        set => _clock = value ?? throw new InvalidDataException("present motion window clock cannot be null");
    }
    private int? _startDelayTicks;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? StartDelayTicks
    {
        get => _startDelayTicks;
        set => _startDelayTicks = value ?? throw new InvalidDataException("present motion window delay cannot be null");
    }
    private int? _durationTicks;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? DurationTicks
    {
        get => _durationTicks;
        set => _durationTicks = value ?? throw new InvalidDataException("present motion window duration cannot be null");
    }
    [JsonIgnore] public bool HasTimingWindow => Clock is not null && StartDelayTicks.HasValue && DurationTicks.HasValue;
    public void Validate()
    {
        RuntimeMotionAdmission.Choice(Phase, "always", "charging", "released", "outbound", "returning");
        bool anyTiming = Clock is not null || StartDelayTicks.HasValue || DurationTicks.HasValue;
        if (anyTiming && !HasTimingWindow)
            throw new InvalidDataException("motion window timing is an optional all-or-none clock/delay/duration group");
        if (!HasTimingWindow) return;
        RuntimeMotionAdmission.Choice(Clock, "active", "since_release", "since_return");
        RuntimeMotionAdmission.Range(StartDelayTicks!.Value, 0, 21600);
        RuntimeMotionAdmission.Range(DurationTicks!.Value, 1, 21600);
    }
}

public abstract class RuntimeWindowedMotionSpec
{
    private RuntimeMotionWindowSpec? _window;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public RuntimeMotionWindowSpec? Window
    {
        get => _window;
        set => _window = value ?? throw new InvalidDataException("present motion window cannot be null");
    }
    public virtual void Validate() => Window?.Validate();
}

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed class RuntimeMotionAimSpec
{
    [JsonRequired] public string Source { get; set; } = null!;
    [JsonRequired] public bool TurnOwner { get; set; }
    public void Validate()
    {
        RuntimeMotionAdmission.Choice(Source, "initial", "cursor", "facing", "velocity");
    }
}

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed class RuntimeAttachmentSpec : RuntimeWindowedMotionSpec
{
    [JsonRequired] public string Anchor { get; set; } = null!;
    [JsonConverter(typeof(RuntimeMotionNumbers.Offset))]
    [JsonRequired] public float AxisOffsetPx { get; set; }
    [JsonConverter(typeof(RuntimeMotionNumbers.Offset))]
    [JsonRequired] public float NormalOffsetPx { get; set; }
    public override void Validate()
    {
        base.Validate();
        RuntimeMotionAdmission.Range(AxisOffsetPx, -4096d, 4096d);
        RuntimeMotionAdmission.Range(NormalOffsetPx, -4096d, 4096d);
        RuntimeMotionAdmission.AnchorValue(Anchor);
    }
}

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed class RuntimeArmPoseSpec : RuntimeWindowedMotionSpec
{
    [JsonRequired] public int DurationTicks { get; set; }
    [JsonRequired] public string StartStretch { get; set; } = null!;
    [JsonRequired] public string PeakStretch { get; set; } = null!;
    [JsonRequired] public string EndStretch { get; set; } = null!;
    [JsonConverter(typeof(RuntimeMotionNumbers.Progress))]
    [JsonRequired] public double PeakProgress { get; set; }
    public override void Validate()
    {
        base.Validate();
        RuntimeMotionAdmission.Range(PeakProgress, 0d, 1d);
        RuntimeMotionAdmission.Range(DurationTicks, 2, 240); RuntimeMotionAdmission.Stretch(StartStretch); RuntimeMotionAdmission.Stretch(PeakStretch); RuntimeMotionAdmission.Stretch(EndStretch); RuntimeMotionAdmission.Peak(PeakProgress);
    }
}

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed class RuntimeReachSpec : RuntimeWindowedMotionSpec
{
    [JsonRequired] public int DurationTicks { get; set; }
    [JsonConverter(typeof(RuntimeMotionNumbers.Offset))]
    [JsonRequired] public float StartOffsetPx { get; set; }
    [JsonConverter(typeof(RuntimeMotionNumbers.Offset))]
    [JsonRequired] public float PeakOffsetPx { get; set; }
    [JsonConverter(typeof(RuntimeMotionNumbers.Offset))]
    [JsonRequired] public float EndOffsetPx { get; set; }
    [JsonConverter(typeof(RuntimeMotionNumbers.Progress))]
    [JsonRequired] public double PeakProgress { get; set; }
    public override void Validate()
    {
        base.Validate();
        RuntimeMotionAdmission.Range(StartOffsetPx, -4096d, 4096d);
        RuntimeMotionAdmission.Range(PeakOffsetPx, -4096d, 4096d);
        RuntimeMotionAdmission.Range(EndOffsetPx, -4096d, 4096d);
        RuntimeMotionAdmission.Range(PeakProgress, 0d, 1d);
        RuntimeMotionAdmission.Range(DurationTicks, 1, 21600); RuntimeMotionAdmission.Peak(PeakProgress);
    }
}

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed class RuntimeOrbitSpec : RuntimeWindowedMotionSpec
{
    [JsonRequired] public string Anchor { get; set; } = null!;
    [JsonConverter(typeof(RuntimeMotionNumbers.Radius))]
    [JsonRequired] public float RadiusPx { get; set; }
    [JsonConverter(typeof(RuntimeMotionNumbers.AngularRate))]
    [JsonRequired] public float RadiansPerUpdate { get; set; }
    [JsonConverter(typeof(RuntimeMotionNumbers.Phase))]
    [JsonRequired] public float PhaseRadians { get; set; }
    [JsonConverter(typeof(RuntimeMotionNumbers.Phase))]
    [JsonRequired] public float IdentityPhaseRadians { get; set; }
    public override void Validate()
    {
        base.Validate();
        RuntimeMotionAdmission.Range(RadiusPx, 0.001d, 1920d);
        RuntimeMotionAdmission.Range(RadiansPerUpdate, -6d, 6d);
        RuntimeMotionAdmission.Range(PhaseRadians, -100d, 100d);
        RuntimeMotionAdmission.Range(IdentityPhaseRadians, -100d, 100d);
        RuntimeMotionAdmission.AnchorValue(Anchor);
    }
}

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed class RuntimeSeekSpec : RuntimeWindowedMotionSpec
{
    [JsonRequired] public string Target { get; set; } = null!;
    [JsonConverter(typeof(RuntimeMotionNumbers.Speed))]
    [JsonRequired] public float MaxSpeed { get; set; }
    [JsonConverter(typeof(RuntimeMotionNumbers.UnitFloat))]
    [JsonRequired] public float VelocityLerpPerUpdate { get; set; }
    [JsonRequired] public bool LimitSpeedToDistance { get; set; }
    private float? _cursorLeashPx;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    [JsonConverter(typeof(RuntimeMotionNumbers.OptionalRadius))]
    public float? CursorLeashPx
    {
        get => _cursorLeashPx;
        set => _cursorLeashPx = value ?? throw new InvalidDataException("present CursorLeashPx cannot be null");
    }
    private float? _searchRangeTiles;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    [JsonConverter(typeof(RuntimeMotionNumbers.OptionalSearchRange))]
    public float? SearchRangeTiles
    {
        get => _searchRangeTiles;
        set => _searchRangeTiles = value ?? throw new InvalidDataException("present SearchRangeTiles cannot be null");
    }
    private bool? _requireLineOfSight;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public bool? RequireLineOfSight
    {
        get => _requireLineOfSight;
        set => _requireLineOfSight = value ?? throw new InvalidDataException("present RequireLineOfSight cannot be null");
    }
    private float? _minimumSpeed;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    [JsonConverter(typeof(RuntimeMotionNumbers.OptionalNonnegativeSpeed))]
    public float? MinimumSpeed
    {
        get => _minimumSpeed;
        set => _minimumSpeed = value ?? throw new InvalidDataException("present MinimumSpeed cannot be null");
    }
    public override void Validate()
    {
        base.Validate();
        RuntimeMotionAdmission.Range(MaxSpeed, 0.001d, 80d);
        RuntimeMotionAdmission.Range(VelocityLerpPerUpdate, 0d, 1d);
        if (CursorLeashPx.HasValue) RuntimeMotionAdmission.Range(CursorLeashPx.Value, 0.001d, 1920d);
        if (SearchRangeTiles.HasValue) RuntimeMotionAdmission.Range(SearchRangeTiles.Value, 0.001d, 120d);
        if (MinimumSpeed.HasValue) RuntimeMotionAdmission.Range(MinimumSpeed.Value, 0d, 80d);
        RuntimeMotionAdmission.Choice(Target, "owner_center", "owner_mounted", "cursor", "nearest_npc");
        if ((Target == "nearest_npc") != (SearchRangeTiles.HasValue && RequireLineOfSight.HasValue)
            || Target != "nearest_npc" && (SearchRangeTiles.HasValue || RequireLineOfSight.HasValue)
            || CursorLeashPx.HasValue && Target != "cursor" || MinimumSpeed > MaxSpeed)
            throw new InvalidDataException("seek requires exact target-specific fields and minimumSpeed <= maxSpeed");
    }
}

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed class RuntimeReturnTriggerSpec
{
    private int? _afterTicks;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? AfterTicks
    {
        get => _afterTicks;
        set => _afterTicks = value ?? throw new InvalidDataException("present AfterTicks cannot be null");
    }
    private float? _ownerDistancePx;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    [JsonConverter(typeof(RuntimeMotionNumbers.OptionalOwnerDistance))]
    public float? OwnerDistancePx
    {
        get => _ownerDistancePx;
        set => _ownerDistancePx = value ?? throw new InvalidDataException("present OwnerDistancePx cannot be null");
    }
    [JsonRequired] public bool OnOwnerRelease { get; set; }
    [JsonRequired] public bool OnTileCollision { get; set; }
    [JsonRequired] public bool DisableTileCollisionOnReturn { get; set; }
    public void Validate()
    {
        if (OwnerDistancePx.HasValue) RuntimeMotionAdmission.Range(OwnerDistancePx.Value, 0.001d, 32000d);
        if (AfterTicks.HasValue) RuntimeMotionAdmission.Range(AfterTicks.Value, 1, 21600);
        if (!AfterTicks.HasValue && !OwnerDistancePx.HasValue && !OnOwnerRelease && !OnTileCollision)
            throw new InvalidDataException("returnTrigger requires at least one enabled trigger");
    }
}

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed class RuntimeArrivalSpec : RuntimeWindowedMotionSpec
{
    [JsonRequired] public string Target { get; set; } = null!;
    [JsonConverter(typeof(RuntimeMotionNumbers.TriggerRadius))]
    [JsonRequired] public float RadiusPx { get; set; }
    [JsonRequired] public string Action { get; set; } = null!;
    public override void Validate()
    {
        base.Validate();
        RuntimeMotionAdmission.Range(RadiusPx, 0.001d, 512d);
        RuntimeMotionAdmission.Choice(Target, "owner_center", "owner_mounted"); RuntimeMotionAdmission.Choice(Action, "kill");
    }
}

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed class RuntimeProximitySpec : RuntimeWindowedMotionSpec
{
    [JsonConverter(typeof(RuntimeMotionNumbers.SearchRange))]
    [JsonRequired] public float SearchRangeTiles { get; set; }
    [JsonConverter(typeof(RuntimeMotionNumbers.TriggerRadius))]
    [JsonRequired] public float TriggerRadiusPx { get; set; }
    [JsonRequired] public bool RequireLineOfSight { get; set; }
    [JsonRequired] public string Action { get; set; } = null!;
    public override void Validate()
    {
        base.Validate();
        RuntimeMotionAdmission.Range(SearchRangeTiles, 0.001d, 120d);
        RuntimeMotionAdmission.Range(TriggerRadiusPx, 0.001d, 512d);
        RuntimeMotionAdmission.Choice(Action, "kill", "expire_then_kill");
    }
}

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed class RuntimeRotationSpec : RuntimeWindowedMotionSpec
{
    [JsonRequired] public string Mode { get; set; } = null!;
    [JsonConverter(typeof(RuntimeMotionNumbers.Phase))]
    [JsonRequired] public float OffsetRadians { get; set; }
    private float? _radiansPerUpdate;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    [JsonConverter(typeof(RuntimeMotionNumbers.OptionalAngularRate))]
    public float? RadiansPerUpdate
    {
        get => _radiansPerUpdate;
        set => _radiansPerUpdate = value ?? throw new InvalidDataException("present RadiansPerUpdate cannot be null");
    }
    public override void Validate()
    {
        base.Validate();
        RuntimeMotionAdmission.Range(OffsetRadians, -100d, 100d);
        if (RadiansPerUpdate.HasValue) RuntimeMotionAdmission.Range(RadiansPerUpdate.Value, -6d, 6d);
        RuntimeMotionAdmission.Choice(Mode, "axis", "velocity", "spin");
        if (Mode == "spin" && !RadiansPerUpdate.HasValue || Mode != "spin" && RadiansPerUpdate is not (null or 0f))
            throw new InvalidDataException("rotation spin requires rate; alignment permits only exact zero or absence");
    }
}

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed class RuntimeVerticalAccelerationSpec : RuntimeWindowedMotionSpec
{
    [JsonConverter(typeof(RuntimeMotionNumbers.Acceleration))]
    [JsonRequired] public float AccelerationYPerUpdate { get; set; }
    public override void Validate()
    {
        base.Validate();
        RuntimeMotionAdmission.Range(AccelerationYPerUpdate, -2d, 2d);
    }
}

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed class RuntimeVelocityRetentionSpec : RuntimeWindowedMotionSpec
{
    [JsonConverter(typeof(RuntimeMotionNumbers.Retention))]
    [JsonRequired] public float MultiplierPerUpdate { get; set; }
    public override void Validate()
    {
        base.Validate();
        RuntimeMotionAdmission.Range(MultiplierPerUpdate, 0d, 1.2d);
    }
}

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed class RuntimeOscillationSpec : RuntimeWindowedMotionSpec
{
    [JsonRequired] public string Law { get; set; } = null!;
    [JsonConverter(typeof(RuntimeMotionNumbers.Frequency))]
    [JsonRequired] public float FrequencyRadiansPerUpdate { get; set; }
    [JsonConverter(typeof(RuntimeMotionNumbers.Phase))]
    [JsonRequired] public float PhaseRadians { get; set; }
    [JsonConverter(typeof(RuntimeMotionNumbers.Amplitude))]
    [JsonRequired] public float Amplitude { get; set; }
    public override void Validate()
    {
        base.Validate();
        RuntimeMotionAdmission.Range(FrequencyRadiansPerUpdate, 0d, 6d);
        RuntimeMotionAdmission.Range(PhaseRadians, -100d, 100d);
        RuntimeMotionAdmission.Range(Amplitude, 0d, 100d);
        RuntimeMotionAdmission.Choice(Law, "angular_sine", "lateral_velocity_sine");
    }
}

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed class RuntimeOpacitySpec : RuntimeWindowedMotionSpec
{
    [JsonRequired] public int Alpha { get; set; }
    public override void Validate()
    {
        base.Validate();
        RuntimeMotionAdmission.Range(Alpha, 0, 255);
    }
}

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed class RuntimeVisualScaleRateSpec : RuntimeWindowedMotionSpec
{
    [JsonConverter(typeof(RuntimeMotionNumbers.ScaleDelta))]
    [JsonRequired] public float DeltaPerUpdate { get; set; }
    [JsonConverter(typeof(RuntimeMotionNumbers.ScaleMax))]
    [JsonRequired] public float MaxScale { get; set; }
    public override void Validate()
    {
        base.Validate();
        RuntimeMotionAdmission.Range(DeltaPerUpdate, -1d, 1d);
        RuntimeMotionAdmission.Range(MaxScale, 0.01d, 20d);
    }
}

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed class RuntimeOwnerControlSpec
{
    [JsonRequired] public bool RequireHeldItem { get; set; }
    [JsonRequired] public bool RequireChannel { get; set; }
    [JsonRequired] public bool RequireItemAnimation { get; set; }
    [JsonRequired] public bool ClaimHeldProjectile { get; set; }
    [JsonRequired] public string Animation { get; set; } = null!;
    [JsonRequired] public string Lifetime { get; set; } = null!;
    public void Validate()
    {
        RuntimeMotionAdmission.Choice(Animation, "none", "keep_alive", "match_lifetime"); RuntimeMotionAdmission.Choice(Lifetime, "authored", "keep_alive");
    }
}

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed class RuntimeChargeSpec
{
    [JsonRequired] public int DurationTicks { get; set; }
    private int? _autoReleaseAfterActiveTicks;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? AutoReleaseAfterActiveTicks
    {
        get => _autoReleaseAfterActiveTicks;
        set => _autoReleaseAfterActiveTicks = value ?? throw new InvalidDataException("present AutoReleaseAfterActiveTicks cannot be null");
    }
    public void Validate()
    {
        RuntimeMotionAdmission.Range(DurationTicks, 1, 600); if (AutoReleaseAfterActiveTicks.HasValue) RuntimeMotionAdmission.Range(AutoReleaseAfterActiveTicks.Value, 1, 21600);
    }
}

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed class RuntimeChargeReleaseSpec
{
    [JsonConverter(typeof(RuntimeMotionNumbers.DamageMultiplier))]
    [JsonRequired] public double DamageMultiplier { get; set; }
    [JsonConverter(typeof(RuntimeMotionNumbers.KnockbackMultiplier))]
    [JsonRequired] public double KnockbackMultiplier { get; set; }
    [JsonConverter(typeof(RuntimeMotionNumbers.SpeedMultiplier))]
    [JsonRequired] public double SpeedMultiplier { get; set; }
    [JsonConverter(typeof(RuntimeMotionNumbers.NonnegativeSpeed))]
    [JsonRequired] public float LaunchSpeed { get; set; }
    [JsonRequired] public bool PauseLifetimeWhileCharging { get; set; }
    public void Validate()
    {
        RuntimeMotionAdmission.Range(DamageMultiplier, 1d, 4d);
        RuntimeMotionAdmission.Range(KnockbackMultiplier, 0d, 4d);
        RuntimeMotionAdmission.Range(SpeedMultiplier, 0.1d, 4d);
        RuntimeMotionAdmission.Range(LaunchSpeed, 0d, 80d);
    }
}

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed class RuntimeContactGateSpec : RuntimeWindowedMotionSpec
{
    [JsonRequired] public bool Enabled { get; set; }
    public override void Validate()
    {
        base.Validate();
        if (Window is null) throw new InvalidDataException("contactGate requires an explicit window");
    }
}

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed class RuntimeBeamGeometrySpec
{
    [JsonConverter(typeof(RuntimeMotionNumbers.Radius))]
    [JsonRequired] public float LengthPx { get; set; }
    [JsonConverter(typeof(RuntimeMotionNumbers.Width))]
    [JsonRequired] public float WidthPx { get; set; }
    [JsonRequired] public bool RaycastTiles { get; set; }
    public void Validate()
    {
        RuntimeMotionAdmission.Range(LengthPx, 0.001d, 1920d);
        RuntimeMotionAdmission.Range(WidthPx, 0.001d, 128d);
    }
}

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed class RuntimeBeamRampSpec
{
    [JsonRequired] public int WarmupTicks { get; set; }
    [JsonConverter(typeof(RuntimeMotionNumbers.InitialMultiplier))]
    [JsonRequired] public double InitialWidthMultiplier { get; set; }
    [JsonConverter(typeof(RuntimeMotionNumbers.InitialMultiplier))]
    [JsonRequired] public double InitialDamageMultiplier { get; set; }
    [JsonConverter(typeof(RuntimeMotionNumbers.Progress))]
    [JsonRequired] public double DamageStartProgress { get; set; }
    public void Validate()
    {
        RuntimeMotionAdmission.Range(InitialWidthMultiplier, 0.01d, 1d);
        RuntimeMotionAdmission.Range(InitialDamageMultiplier, 0.01d, 1d);
        RuntimeMotionAdmission.Range(DamageStartProgress, 0d, 1d);
        RuntimeMotionAdmission.Range(WarmupTicks, 0, 600);
    }
}

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed class RuntimeManaSustainSpec
{
    [JsonRequired] public string Cadence { get; set; } = null!;
    public void Validate()
    {
        RuntimeMotionAdmission.Choice(Cadence, "held_item_use_time");
    }
}

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed class RuntimeLashGeometrySpec
{
    [JsonRequired] public string Clock { get; set; } = null!;
    private int? _durationTicks;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? DurationTicks
    {
        get => _durationTicks;
        set => _durationTicks = value ?? throw new InvalidDataException("present DurationTicks cannot be null");
    }
    [JsonRequired] public string Anchor { get; set; } = null!;
    [JsonConverter(typeof(RuntimeMotionNumbers.LashReach))]
    [JsonRequired] public float ReachPx { get; set; }
    [JsonRequired] public int Segments { get; set; }
    [JsonConverter(typeof(RuntimeMotionNumbers.Phase))]
    [JsonRequired] public float SweepStartRadians { get; set; }
    [JsonConverter(typeof(RuntimeMotionNumbers.Phase))]
    [JsonRequired] public float SweepEndRadians { get; set; }
    [JsonConverter(typeof(RuntimeMotionNumbers.Bend))]
    [JsonRequired] public float BendRatio { get; set; }
    [JsonRequired] public bool UseOwnerGravity { get; set; }
    [JsonRequired] public bool UseOwnerWhipRangeMultiplier { get; set; }
    public void Validate()
    {
        RuntimeMotionAdmission.Range(ReachPx, 0.001d, 960d);
        RuntimeMotionAdmission.Range(SweepStartRadians, -100d, 100d);
        RuntimeMotionAdmission.Range(SweepEndRadians, -100d, 100d);
        RuntimeMotionAdmission.Range(BendRatio, -4d, 4d);
        RuntimeMotionAdmission.Choice(Clock, "owner_animation", "active"); RuntimeMotionAdmission.AnchorValue(Anchor); RuntimeMotionAdmission.Range(Segments, 3, 48);
        if ((Clock == "active") != DurationTicks.HasValue) throw new InvalidDataException("lash active clock requires duration; animation clock forbids it");
        if (DurationTicks.HasValue) RuntimeMotionAdmission.Range(DurationTicks.Value, 1, 21600);
    }
}

public sealed partial class RuntimeEntitySpec
{
    private RuntimeMotionAimSpec? _aim;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public RuntimeMotionAimSpec? Aim
    {
        get => _aim;
        set => _aim = value ?? throw new InvalidDataException("present Aim cannot be null");
    }
    private RuntimeAttachmentSpec? _attachment;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public RuntimeAttachmentSpec? Attachment
    {
        get => _attachment;
        set => _attachment = value ?? throw new InvalidDataException("present Attachment cannot be null");
    }
    private RuntimeArmPoseSpec? _armPose;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public RuntimeArmPoseSpec? ArmPose
    {
        get => _armPose;
        set => _armPose = value ?? throw new InvalidDataException("present ArmPose cannot be null");
    }
    private RuntimeReachSpec? _reach;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public RuntimeReachSpec? Reach
    {
        get => _reach;
        set => _reach = value ?? throw new InvalidDataException("present Reach cannot be null");
    }
    private RuntimeOrbitSpec? _orbit;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public RuntimeOrbitSpec? Orbit
    {
        get => _orbit;
        set => _orbit = value ?? throw new InvalidDataException("present Orbit cannot be null");
    }
    private RuntimeSeekSpec[]? _seek;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public RuntimeSeekSpec[]? Seek
    {
        get => _seek;
        set => _seek = value ?? throw new InvalidDataException("present Seek cannot be null");
    }
    private RuntimeReturnTriggerSpec? _returnTrigger;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public RuntimeReturnTriggerSpec? ReturnTrigger
    {
        get => _returnTrigger;
        set => _returnTrigger = value ?? throw new InvalidDataException("present ReturnTrigger cannot be null");
    }
    private RuntimeArrivalSpec? _arrival;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public RuntimeArrivalSpec? Arrival
    {
        get => _arrival;
        set => _arrival = value ?? throw new InvalidDataException("present Arrival cannot be null");
    }
    private RuntimeProximitySpec? _proximity;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public RuntimeProximitySpec? Proximity
    {
        get => _proximity;
        set => _proximity = value ?? throw new InvalidDataException("present Proximity cannot be null");
    }
    private RuntimeRotationSpec? _rotation;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public RuntimeRotationSpec? Rotation
    {
        get => _rotation;
        set => _rotation = value ?? throw new InvalidDataException("present Rotation cannot be null");
    }
    private RuntimeVerticalAccelerationSpec? _verticalAcceleration;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public RuntimeVerticalAccelerationSpec? VerticalAcceleration
    {
        get => _verticalAcceleration;
        set => _verticalAcceleration = value ?? throw new InvalidDataException("present VerticalAcceleration cannot be null");
    }
    private RuntimeVelocityRetentionSpec? _velocityRetention;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public RuntimeVelocityRetentionSpec? VelocityRetention
    {
        get => _velocityRetention;
        set => _velocityRetention = value ?? throw new InvalidDataException("present VelocityRetention cannot be null");
    }
    private RuntimeOscillationSpec? _oscillation;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public RuntimeOscillationSpec? Oscillation
    {
        get => _oscillation;
        set => _oscillation = value ?? throw new InvalidDataException("present Oscillation cannot be null");
    }
    private RuntimeOpacitySpec? _opacity;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public RuntimeOpacitySpec? Opacity
    {
        get => _opacity;
        set => _opacity = value ?? throw new InvalidDataException("present Opacity cannot be null");
    }
    private RuntimeVisualScaleRateSpec? _visualScaleRate;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public RuntimeVisualScaleRateSpec? VisualScaleRate
    {
        get => _visualScaleRate;
        set => _visualScaleRate = value ?? throw new InvalidDataException("present VisualScaleRate cannot be null");
    }
    private RuntimeOwnerControlSpec? _ownerControl;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public RuntimeOwnerControlSpec? OwnerControl
    {
        get => _ownerControl;
        set => _ownerControl = value ?? throw new InvalidDataException("present OwnerControl cannot be null");
    }
    private RuntimeChargeSpec? _charge;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public RuntimeChargeSpec? Charge
    {
        get => _charge;
        set => _charge = value ?? throw new InvalidDataException("present Charge cannot be null");
    }
    private RuntimeChargeReleaseSpec? _chargeRelease;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public RuntimeChargeReleaseSpec? ChargeRelease
    {
        get => _chargeRelease;
        set => _chargeRelease = value ?? throw new InvalidDataException("present ChargeRelease cannot be null");
    }
    private RuntimeContactGateSpec? _contactGate;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public RuntimeContactGateSpec? ContactGate
    {
        get => _contactGate;
        set => _contactGate = value ?? throw new InvalidDataException("present ContactGate cannot be null");
    }
    private RuntimeBeamGeometrySpec? _beamGeometry;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public RuntimeBeamGeometrySpec? BeamGeometry
    {
        get => _beamGeometry;
        set => _beamGeometry = value ?? throw new InvalidDataException("present BeamGeometry cannot be null");
    }
    private RuntimeBeamRampSpec? _beamRamp;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public RuntimeBeamRampSpec? BeamRamp
    {
        get => _beamRamp;
        set => _beamRamp = value ?? throw new InvalidDataException("present BeamRamp cannot be null");
    }
    private RuntimeManaSustainSpec? _manaSustain;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public RuntimeManaSustainSpec? ManaSustain
    {
        get => _manaSustain;
        set => _manaSustain = value ?? throw new InvalidDataException("present ManaSustain cannot be null");
    }
    private RuntimeLashGeometrySpec? _lashGeometry;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public RuntimeLashGeometrySpec? LashGeometry
    {
        get => _lashGeometry;
        set => _lashGeometry = value ?? throw new InvalidDataException("present LashGeometry cannot be null");
    }

    [JsonIgnore] internal bool HasMotionComponents => Aim is not null
        || Attachment is not null
        || ArmPose is not null
        || Reach is not null
        || Orbit is not null
        || Seek is not null
        || ReturnTrigger is not null
        || Arrival is not null
        || Proximity is not null
        || Rotation is not null
        || VerticalAcceleration is not null
        || VelocityRetention is not null
        || Oscillation is not null
        || Opacity is not null
        || VisualScaleRate is not null
        || OwnerControl is not null
        || Charge is not null
        || ChargeRelease is not null
        || ContactGate is not null
        || BeamGeometry is not null
        || BeamRamp is not null
        || ManaSustain is not null
        || LashGeometry is not null;
    [JsonIgnore] internal bool HasMotionPositionDriver => Attachment is not null || Orbit is not null
        || Seek is not null || LashGeometry is not null || VerticalAcceleration is not null
        || VelocityRetention is not null || Oscillation is not null;

    internal IEnumerable<RuntimeMotionWindowSpec?> MotionWindows()
    {
        if (Attachment is not null) yield return Attachment.Window;
        if (ArmPose is not null) yield return ArmPose.Window;
        if (Reach is not null) yield return Reach.Window;
        if (Orbit is not null) yield return Orbit.Window;
        if (Arrival is not null) yield return Arrival.Window;
        if (Proximity is not null) yield return Proximity.Window;
        if (Rotation is not null) yield return Rotation.Window;
        if (VerticalAcceleration is not null) yield return VerticalAcceleration.Window;
        if (VelocityRetention is not null) yield return VelocityRetention.Window;
        if (Oscillation is not null) yield return Oscillation.Window;
        if (Opacity is not null) yield return Opacity.Window;
        if (VisualScaleRate is not null) yield return VisualScaleRate.Window;
        if (ContactGate is not null) yield return ContactGate.Window;
        foreach (var seek in Seek ?? Array.Empty<RuntimeSeekSpec>()) if (seek is not null) yield return seek.Window;
        if (TurnModifier is not null) yield return TurnModifier.Window;
        if (SpeedModifier is not null) yield return SpeedModifier.Window;
        if (HomingModifier is not null) yield return HomingModifier.Window;
        if (NpcAttraction is not null) yield return NpcAttraction.Window;
        if (VisualScaleCurve is not null) yield return VisualScaleCurve.Window;
    }

    internal void ValidateMotionComponents()
    {
        if (!HasMotionComponents && !MotionWindows().Any(w => w is not null)) return;
        if (!IsProjectileEntity) throw new InvalidDataException("motion components require a projectile entity");
        Aim?.Validate();
        Attachment?.Validate();
        ArmPose?.Validate();
        Reach?.Validate();
        Orbit?.Validate();
        ReturnTrigger?.Validate();
        Arrival?.Validate();
        Proximity?.Validate();
        Rotation?.Validate();
        VerticalAcceleration?.Validate();
        VelocityRetention?.Validate();
        Oscillation?.Validate();
        Opacity?.Validate();
        VisualScaleRate?.Validate();
        OwnerControl?.Validate();
        Charge?.Validate();
        ChargeRelease?.Validate();
        ContactGate?.Validate();
        BeamGeometry?.Validate();
        BeamRamp?.Validate();
        ManaSustain?.Validate();
        LashGeometry?.Validate();
        if (Seek is not null) {
            if (Seek.Length is < 1 or > 2 || Seek.Any(x => x is null))
                throw new InvalidDataException("seek requires 1..2 non-null typed instances");
            foreach (var seek in Seek) seek.Validate();
            if (Seek.Length == 2 && (Seek.Any(s => s.Window?.Phase is not ("outbound" or "returning"))
                || Seek[0].Window!.Phase == Seek[1].Window!.Phase))
                throw new InvalidDataException("two seek instances require distinct outbound/returning phase windows");
        }
        if ((Attachment is not null || ArmPose is not null || BeamGeometry is not null || LashGeometry is not null
                || Rotation?.Mode == "axis") && Aim is null)
            throw new InvalidDataException("attachment/pose/axis geometry requires explicit Aim");
        if (Reach is not null && Attachment is null)
            throw new InvalidDataException("reach requires an explicit attachment");
        if (ChargeRelease is not null && Charge is null)
            throw new InvalidDataException("chargeRelease requires Charge");
        if (BeamRamp is not null && BeamGeometry is null)
            throw new InvalidDataException("beamRamp requires BeamGeometry");
        if (ManaSustain is not null && (OwnerControl is null || !OwnerControl.RequireHeldItem || !OwnerControl.RequireChannel))
            throw new InvalidDataException("manaSustain requires explicit held-item/channel owner control");
        if (Collision.TileCollide && (LashGeometry is not null || Attachment is not null
            && (Attachment.Window is null || Attachment.Window.Phase == "always" && !Attachment.Window.HasTimingWindow)))
            throw new InvalidDataException("always-absolute attachment/lash does not execute native tile collision; choose false or a phase-limited attachment");
        if (BeamGeometry is not null && LashGeometry is not null)
            throw new InvalidDataException("beam and lash are competing collision geometry owners");
        if ((BeamGeometry is not null || LashGeometry is not null) && (HitboxCurve is not null || VisualScaleCurve is not null || VisualScaleRate is not null))
            throw new InvalidDataException("line geometry excludes dynamic body-scale/hitbox owners");
        if (VisualScaleRate is not null && HitboxCurve?.MirrorToSprite == true)
            throw new InvalidDataException("mirrored hitbox scale is an always-active visual scale owner");
        if (VisualScaleRate is not null && VisualScaleCurve is not null)
            RuntimeMotionAdmission.RequireDisjoint(VisualScaleRate.Window, VisualScaleCurve.Window);
        // Legacy opcode declarations remain exact, untouched and executable.
        // A configured composite cannot be an independent second stage writer.
        bool oldMovement = Movement.IsConfigured && Movement.Code != 0;
        bool oldPositionController = Controller.Code is RuntimeControllerCode.ChannelBeam or RuntimeControllerCode.ChargeThenRelease;
        if (oldPositionController && HasMotionComponents)
            throw new InvalidDataException("position-owning legacy controllers cannot execute additional motion stage writers");
        int oldCode = oldMovement ? Movement!.Code : -1;
        bool oldAbsolute = oldCode is 4 or 16 or 17 or 18 or 19 or 20;
        if (oldMovement && (Attachment is not null || Orbit is not null || LashGeometry is not null)
            || oldAbsolute && (Seek is not null || VerticalAcceleration is not null || VelocityRetention is not null || Oscillation is not null)
            || oldCode is 1 or 5 or 7 or 11 or 13 or 14 or 16 or 17 && Seek is not null
            || oldCode is 2 or 12 && VerticalAcceleration is not null
            || oldCode is 3 or 8 && VelocityRetention is not null
            || oldCode is 7 or 11 && Oscillation is not null
            || oldCode is 5 or 14 or 16 && (ReturnTrigger is not null || Arrival is not null)
            || oldCode == 13 && Proximity is not null
            || oldCode == 8 && Opacity is not null
            || oldCode is 14 or 16 or 17 or 18 or 20 && Rotation is not null
            || oldCode == 15 && VisualScaleRate is not null
            || oldCode is 18 or 20 && ArmPose is not null
            || oldCode is 16 or 17 or 18 or 19 or 20 && OwnerControl is not null
            || oldCode == 18 && BeamGeometry is not null)
            throw new InvalidDataException("new motion component conflicts with a retained opcode stage owner");

        var absolute = new List<RuntimeMotionWindowSpec?>();
        if (Attachment is not null) absolute.Add(Attachment.Window);
        if (Orbit is not null) absolute.Add(Orbit.Window);
        if (LashGeometry is not null) absolute.Add(null);
        var velocity = new List<RuntimeMotionWindowSpec?>();
        foreach (var seek in Seek ?? Array.Empty<RuntimeSeekSpec>()) velocity.Add(seek.Window);
        if (VerticalAcceleration is not null) velocity.Add(VerticalAcceleration.Window);
        if (VelocityRetention is not null) velocity.Add(VelocityRetention.Window);
        if (Oscillation is not null) velocity.Add(Oscillation.Window);
        if (TurnModifier is not null) velocity.Add(TurnModifier.Window);
        if (SpeedModifier is not null) velocity.Add(SpeedModifier.Window);
        if (HomingModifier is not null) velocity.Add(HomingModifier.Window);
        for (int i = 0; i < absolute.Count; i++) {
            for (int j = i + 1; j < absolute.Count; j++)
                RuntimeMotionAdmission.RequireDisjoint(absolute[i], absolute[j]);
            foreach (var window in velocity) RuntimeMotionAdmission.RequireDisjoint(absolute[i], window);
        }
        if (Seek is { Length: 2 }) RuntimeMotionAdmission.RequireDisjoint(Seek[0].Window, Seek[1].Window);
        foreach (var window in MotionWindows()) {
            window?.Validate();
            if (window is null) continue;
            if ((window.Phase is "charging" or "released" || window.Clock == "since_release")
                && Charge is null && Controller.Code != RuntimeControllerCode.ChargeThenRelease)
                throw new InvalidDataException("charge/release phase window requires its actual latch producer");
            if ((window.Phase == "returning" || window.Clock == "since_return") && ReturnTrigger is null
                && !(oldMovement && Movement!.Code is 5 or 14 or 16))
                throw new InvalidDataException("return phase window requires a return latch producer");
        }
    }
}

internal static class RuntimeMotionAdmission
{
    // Raw converters enforce decimal-token bounds before narrowing. Typed
    // validation compares Single endpoints in the same storage domain, so a
    // valid 1.2f is not rejected merely because its double expansion exceeds 1.2.
    internal static void Range(float value, double low, double high)
    {
        if (!float.IsFinite(value) || value < (float)low || value > (float)high)
            throw new InvalidDataException("motion value is outside exact finite registry bounds");
    }
    internal static void Range(int value, double low, double high) => Range((double)value, low, high);
    internal static void Range(double value, double low, double high)
    {
        if (!double.IsFinite(value) || value < low || value > high)
            throw new InvalidDataException("motion value is outside exact finite registry bounds");
    }
    internal static void Choice(string? value, params string[] choices)
    {
        if (value is null || !choices.Contains(value, StringComparer.Ordinal))
            throw new InvalidDataException("motion enum requires an exact registered token");
    }
    internal static void AnchorValue(string? value) => Choice(value, "owner_center", "owner_mounted", "front_hand");
    internal static void Stretch(string? value) => Choice(value, "none", "quarter", "three_quarters", "full");
    internal static void Peak(double value)
    {
        if (!double.IsFinite(value) || value <= 0 || value >= 1)
            throw new InvalidDataException("peakProgress must be strictly between zero and one");
    }
    // This is a proof over finite declared windows, not sampling a few ages.
    // A common clock permits half-open interval separation. Different clocks
    // require mutually exclusive latch phases; released can overlap returning.
    internal static bool Disjoint(RuntimeMotionWindowSpec? a, RuntimeMotionWindowSpec? b)
    {
        if (a is null || b is null) return false;
        bool opposite = (a.Phase == "charging" && b.Phase is "released" or "outbound")
            || (b.Phase == "charging" && a.Phase is "released" or "outbound")
            || (a.Phase == "outbound" && b.Phase == "returning")
            || (b.Phase == "outbound" && a.Phase == "returning");
        return opposite || a.HasTimingWindow && b.HasTimingWindow && a.Clock == b.Clock
            && ((long)a.StartDelayTicks!.Value + a.DurationTicks!.Value <= b.StartDelayTicks!.Value
                || (long)b.StartDelayTicks!.Value + b.DurationTicks!.Value <= a.StartDelayTicks!.Value);
    }
    internal static void RequireDisjoint(RuntimeMotionWindowSpec? a, RuntimeMotionWindowSpec? b)
    {
        if (!Disjoint(a, b)) throw new InvalidDataException("overlapping motion position writers require provably disjoint finite windows");
    }
    internal static void ValidateProgram(RuntimeProgramSpec program)
    {
        int poseOwners = program.Entities.Count(e => e.ArmPose is not null || e.Movement.Code == 20);
        if (poseOwners > 1) throw new InvalidDataException("native front arm pose has one primary writer, not one body reader");
        foreach (var entity in program.Entities) {
            bool activeSpawn = program.Bindings.Any(b => b is not null
                && b.Input is RuntimeInputKind.PrimaryUse or RuntimeInputKind.AlternateUse
                && b.UsePolicy?.Action?.Kind == RuntimeBindingAction.SpawnEntity && b.UsePolicy.Action.TargetId == entity.Id);
            if (entity.ArmPose is not null && (entity.Id != program.PrimaryEntityId
                || program.PrimaryOwner != RuntimeProgramSpec.ProjectileOwner || !activeSpawn
                || !string.IsNullOrEmpty(program.ItemUse.HandPose)))
                throw new InvalidDataException("armPose requires active primary pose owner and no competing item handPose");
            if (activeSpawn && (entity.Charge is not null || entity.ReturnTrigger?.OnOwnerRelease == true
                || entity.OwnerControl?.RequireChannel == true) && !program.ItemUse.Channel)
                throw new InvalidDataException("active native channel-dependent component requires explicit itemUse.channel=true");
        }
    }
}

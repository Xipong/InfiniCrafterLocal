#nullable enable
using System;
using System.IO;
using System.Text.Json.Serialization;
using Terraria.Audio;

namespace InfiniCrafterLocal.Common.Models;

/// <summary>Exact VFX-owned playback controls, independent of gameplay and slot alpha/phase.</summary>
public sealed class VfxSoundSpec
{
    public sealed class VolumeJsonConverter : RawJsonFloatDomainConverter
    {
        public VolumeJsonConverter() : base("0", "1", "0") { }
    }
    [JsonConverter(typeof(VolumeJsonConverter))]
    [JsonRequired] public float Volume { get; set; }
    public sealed class PitchJsonConverter : RawJsonFloatDomainConverter
    {
        public PitchJsonConverter() : base("-0.9", "0.9", "0") { }
    }
    [JsonConverter(typeof(PitchJsonConverter))]
    [JsonRequired] public float Pitch { get; set; }
    public sealed class PitchVarianceJsonConverter : RawJsonFloatDomainConverter
    {
        public PitchVarianceJsonConverter() : base("0", "0.6", "0") { }
    }
    [JsonConverter(typeof(PitchVarianceJsonConverter))]
    [JsonRequired] public float PitchVariance { get; set; }

    public void NormalizeAndValidate()
    {
        if (!float.IsFinite(Volume) || Volume is < 0f or > 1f)
            throw new InvalidDataException("sound.volume must be finite in [0,1]");
        if (!float.IsFinite(Pitch) || Pitch is < -0.9f or > 0.9f)
            throw new InvalidDataException("sound.pitch must be finite in [-0.9,0.9]");
        if (!float.IsFinite(PitchVariance) || PitchVariance is < 0f or > 0.6f)
            throw new InvalidDataException("sound.pitchVariance must be finite in [0,0.6]");
        if (Math.Abs(Pitch) + PitchVariance / 2f > 1f)
            throw new InvalidDataException("sound.pitchVariance must be <= 2*(1-abs(pitch))");
    }

    internal SoundStyle ApplyTo(SoundStyle sample)
    {
        NormalizeAndValidate();
        // SoundID.Item26 has internal UsesMusicPitch=true: a `with` copy would
        // add Main.musicPitch later in SoundPlayer and violate the explicit pitch.
        // Public construction keeps asset/variants and every public playback
        // policy, while the internal vanilla-instrument offset remains disabled.
        // No reflection, name classifier, native-volume multiplier or implicit jitter.
        return new SoundStyle(sample.SoundPath, sample.Variants, sample.Type) {
            Identifier = sample.Identifier,
            MaxInstances = sample.MaxInstances,
            SoundLimitBehavior = sample.SoundLimitBehavior,
            RerollAttempts = sample.RerollAttempts,
            LimitsArePerVariant = sample.LimitsArePerVariant,
            PlayOnlyIfFocused = sample.PlayOnlyIfFocused,
            PauseBehavior = sample.PauseBehavior,
            IsLooped = sample.IsLooped,
            VariantsWeights = sample.VariantsWeights,
            Volume = Volume,
            Pitch = Pitch,
            PitchVariance = PitchVariance,
        };
    }
}

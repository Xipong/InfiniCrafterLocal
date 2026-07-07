#nullable enable
using System;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using ParticleLibrary.Core;
using ParticleLibrary.Core.V3;
using ParticleLibrary.Core.V3.Particles;
using ParticleLibrary.Utilities;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.VFX;

/// <summary>
/// Real ParticleLibrary V3 binding for Infini VFX.
/// The gameplay/runtime still talks to IVfxBackend; this registry only owns shared ParticleLibrary buffers.
/// Do not allocate particle buffers per projectile.
/// </summary>
public sealed class VfxParticleSystemRegistry : ModSystem
{
    private static ParticleBuffer<InfiniV3ParticleBehavior>? GlowParticles { get; set; }
    private static ParticleBuffer<InfiniV3ParticleBehavior>? SparkParticles { get; set; }

    private static bool _initQueued;

    public static bool Ready => !Main.dedServ && GlowParticles is not null && SparkParticles is not null;

    public static bool EnsureReady()
    {
        if (Main.netMode == NetmodeID.Server)
            return false;
        if (Ready)
            return true;
        if (_initQueued)
            return false;

        _initQueued = true;
        Main.QueueMainThreadAction(() =>
        {
            try
            {
                if (Ready)
                    return;

                GlowParticles = new ParticleBuffer<InfiniV3ParticleBehavior>(3000)
                    .SetBlendState(BlendState.Additive)
                    .SetSamplerState(SamplerState.LinearClamp);
                ParticleManagerV3.RegisterUpdatable(GlowParticles);
                ParticleManagerV3.RegisterRenderable(Layer.BeforeProjectiles, GlowParticles);

                SparkParticles = new ParticleBuffer<InfiniV3ParticleBehavior>(4200)
                    .SetBlendState(BlendState.Additive)
                    .SetSamplerState(SamplerState.PointClamp);
                ParticleManagerV3.RegisterUpdatable(SparkParticles);
                ParticleManagerV3.RegisterRenderable(Layer.BeforeProjectiles, SparkParticles);
            }
            finally
            {
                _initQueued = false;
            }
        });
        return Ready;
    }

    public static void EmitGlow(
        Vector2 position,
        Vector2 velocity,
        Color startColor,
        Color endColor,
        Vector2 scale,
        Vector2 scaleVelocity,
        float rotation,
        float rotationVelocity,
        Vector2 velocityAcceleration,
        int lifespan)
    {
        GlowParticles?.Create(CreateParticleInfo(position, velocity, startColor, endColor, scale, scaleVelocity, rotation, rotationVelocity, velocityAcceleration, lifespan));
    }

    public static void EmitSpark(
        Vector2 position,
        Vector2 velocity,
        Color startColor,
        Color endColor,
        Vector2 scale,
        Vector2 scaleVelocity,
        float rotation,
        float rotationVelocity,
        Vector2 velocityAcceleration,
        int lifespan)
    {
        SparkParticles?.Create(CreateParticleInfo(position, velocity, startColor, endColor, scale, scaleVelocity, rotation, rotationVelocity, velocityAcceleration, lifespan));
    }

    private static ParticleInfo CreateParticleInfo(
        Vector2 position,
        Vector2 velocity,
        Color startColor,
        Color endColor,
        Vector2 scale,
        Vector2 scaleVelocity,
        float rotation,
        float rotationVelocity,
        Vector2 velocityAcceleration,
        int lifespan)
    {
        return new ParticleInfo(
            position: position.ToNumerics(),
            velocity: velocity.ToNumerics(),
            rotation: rotation,
            scale: scale.ToNumerics(),
            depth: 1f,
            color: startColor,
            duration: Math.Max(1, lifespan),
            PackColor(endColor),
            velocityAcceleration.X,
            velocityAcceleration.Y,
            scaleVelocity.X,
            scaleVelocity.Y,
            rotationVelocity);
    }

    private static float PackColor(Color color) => BitConverter.UInt32BitsToSingle(color.PackedValue);

    public override void OnModLoad()
    {
        // Lazy on purpose. Creating ParticleLibrary buffers at mod-load time made a
        // vanilla Torch scene flicker even when no generated projectile was active.
        // The first generated VFX emission calls EnsureReady(); stock Terraria scenes
        // no longer pay for or inherit ParticleLibrary draw state.
    }

    public override void Unload()
    {
        GlowParticles?.Dispose();
        SparkParticles?.Dispose();

        GlowParticles = null;
        SparkParticles = null;
        _initQueued = false;
    }
}

internal sealed class InfiniV3ParticleBehavior : Behavior<ParticleInfo>
{
    public override string Texture => "ParticleLibrary/Assets/Textures/Star";

    public override void Update(ref ParticleInfo info)
    {
        float life = info.Duration <= 0 ? 0f : Math.Clamp(info.Time / (float)info.Duration, 0f, 1f);
        Color endColor = Color.Transparent;
        Vector2 velocityAcceleration = Vector2.One;
        Vector2 scaleVelocity = Vector2.Zero;
        float rotationVelocity = 0f;

        if (info.Data is { Length: >= 6 })
        {
            endColor = new Color { PackedValue = BitConverter.SingleToUInt32Bits(info.Data[0]) };
            velocityAcceleration = new Vector2(info.Data[1], info.Data[2]);
            scaleVelocity = new Vector2(info.Data[3], info.Data[4]);
            rotationVelocity = info.Data[5];
        }

        info.Position += info.Velocity;
        info.Velocity *= velocityAcceleration.ToNumerics();
        info.Scale += scaleVelocity.ToNumerics();
        if (info.Scale.X < 0.01f || info.Scale.Y < 0.01f)
            info.Time = 1;
        info.Rotation += rotationVelocity;
        info.Color = Color.Lerp(endColor, info.InitialColor, life);
        info.Time--;
    }
}

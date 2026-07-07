#nullable enable
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using System;
using Terraria;
using Terraria.GameContent;
using Terraria.ID;


namespace InfiniCrafterLocal.Common.VFX;

/// <summary>
/// Foundation abstractions for the next VFX layer.
/// v0.3.23 does not replace the manifest runtime yet; it gives recipes/manifests
/// a stable vocabulary for stacked layers and backend routing.
/// </summary>
public enum VfxLayerKind
{
    ParticleBurst,
    ParticleEmitter,
    SpriteGhost,
    PrimitiveTrail,
    ActorAfterimage,
    SoundCue,
    LightCue
}

public enum VfxPlaybackMode
{
    Auto,
    Baked,
    Realtime,
    Hybrid
}

public readonly struct VfxEmitCommand
{
    public readonly Vector2 Position;
    public readonly Vector2 Velocity;
    public readonly Color StartColor;
    public readonly Color EndColor;
    public readonly Vector2 Scale;
    public readonly float Rotation;
    public readonly int Lifespan;
    public readonly float Alpha;
    public readonly int Seed;
    public readonly string ParticleSystemId;

    public VfxEmitCommand(
        Vector2 position,
        Vector2 velocity,
        Color startColor,
        Color endColor,
        Vector2 scale,
        float rotation,
        int lifespan,
        float alpha,
        int seed,
        string particleSystemId = "dust")
    {
        Position = position;
        Velocity = velocity;
        StartColor = startColor;
        EndColor = endColor;
        Scale = scale;
        Rotation = rotation;
        Lifespan = Math.Clamp(lifespan, 1, 240);
        Alpha = Math.Clamp(alpha, 0f, 1f);
        Seed = seed;
        ParticleSystemId = string.IsNullOrWhiteSpace(particleSystemId) ? "dust" : particleSystemId;
    }
}

public readonly struct VfxTrailCommand
{
    public readonly ReadOnlyMemory<Vector2> Points;
    public readonly Color Color;
    public readonly float Width;
    public readonly float Alpha;
    public readonly int Seed;

    public VfxTrailCommand(ReadOnlyMemory<Vector2> points, Color color, float width, float alpha, int seed)
    {
        Points = points;
        Color = color;
        Width = Math.Clamp(width, 0.5f, 96f);
        Alpha = Math.Clamp(alpha, 0f, 1f);
        Seed = seed;
    }
}

public readonly struct VfxActorCommand
{
    public readonly int OwnerWhoAmI;
    public readonly Vector2 Position;
    public readonly float Rotation;
    public readonly float Scale;
    public readonly float Alpha;
    public readonly int Seed;

    public VfxActorCommand(int ownerWhoAmI, Vector2 position, float rotation, float scale, float alpha, int seed)
    {
        OwnerWhoAmI = ownerWhoAmI;
        Position = position;
        Rotation = rotation;
        Scale = Math.Clamp(scale <= 0f ? 1f : scale, 0.1f, 5f);
        Alpha = Math.Clamp(alpha, 0f, 1f);
        Seed = seed;
    }
}

public interface IVfxBackend
{
    bool Available { get; }
    string Name { get; }
    void Emit(in VfxEmitCommand command);
    void EmitTrail(in VfxTrailCommand command);
    void EmitActor(in VfxActorCommand command);
}

public sealed class NullVfxBackend : IVfxBackend
{
    public static readonly NullVfxBackend Instance = new();
    public bool Available => false;
    public string Name => "null";
    public void Emit(in VfxEmitCommand command) { }
    public void EmitTrail(in VfxTrailCommand command) { }
    public void EmitActor(in VfxActorCommand command) { }
}

/// <summary>
/// Tiny CPU/Dust fallback inspired by the master document's SpiritMod-style fallback layer.
/// It is intentionally conservative: no long-lived custom particle pool yet, just a common
/// command endpoint that can later be swapped for ParticleLibrary or a real CPU pool.
/// </summary>
public sealed class VanillaDustVfxBackend : IVfxBackend
{
    public bool Available => !Main.dedServ;
    public string Name => "vanillaDust";

    public void Emit(in VfxEmitCommand command)
    {
        if (!Available)
            return;

        string resolved = VfxParticleAddress.Resolve(command.ParticleSystemId);
        VfxParticleSystemKind kind = VfxParticleAddress.KindFor(resolved);
        int type = PickDustType(kind, command.StartColor, command.Scale, command.Alpha);

        float scalarScale = Math.Clamp((command.Scale.X + command.Scale.Y) * 0.5f, 0.1f, 4.2f);
        float brightness = Brightness(command.StartColor);
        float alphaScale = Math.Clamp(0.35f + command.Alpha * 0.85f, 0.2f, 1.2f);
        float dustScale = kind switch
        {
            VfxParticleSystemKind.Spark => scalarScale * 0.65f,
            VfxParticleSystemKind.Smoke => scalarScale * 1.15f,
            VfxParticleSystemKind.Shard => scalarScale * 0.95f,
            _ => scalarScale
        };

        Vector2 velocity = command.Velocity;
        bool noGravity = true;
        bool noLight = false;
        float fadeIn = Math.Clamp(command.Lifespan / 90f, 0f, 1.45f);

        switch (kind)
        {
            case VfxParticleSystemKind.Smoke:
                velocity *= 0.42f;
                velocity += Main.rand.NextVector2Circular(0.2f, 0.2f);
                dustScale *= 1.1f;
                noGravity = false;
                noLight = true;
                fadeIn = Math.Clamp(0.45f + command.Lifespan / 72f, 0.35f, 1.8f);
                break;
            case VfxParticleSystemKind.Shard:
                velocity *= 0.82f;
                velocity += Main.rand.NextVector2Circular(0.18f, 0.18f);
                noGravity = Main.rand.NextBool(3);
                fadeIn = Math.Clamp(0.05f + command.Lifespan / 180f, 0f, 0.7f);
                break;
            case VfxParticleSystemKind.Spark:
                velocity *= 1.25f;
                velocity += Main.rand.NextVector2Circular(0.28f, 0.28f);
                dustScale *= 0.82f;
                noGravity = true;
                fadeIn = Math.Clamp(command.Lifespan / 240f, 0f, 0.25f);
                break;
            case VfxParticleSystemKind.Glow:
                velocity *= 0.68f;
                velocity += Main.rand.NextVector2Circular(0.12f, 0.12f);
                dustScale *= 1.05f;
                noGravity = true;
                fadeIn = Math.Clamp(0.18f + brightness * 0.55f, 0.1f, 1.1f);
                break;
            default:
                velocity *= 0.78f;
                break;
        }

        Dust d = Dust.NewDustPerfect(
            command.Position,
            type,
            velocity,
            Math.Clamp((int)(255 * (1f - Math.Clamp(command.Alpha * alphaScale, 0f, 1f))), 0, 245),
            command.StartColor,
            dustScale);
        d.noGravity = noGravity;
        d.noLight = noLight;
        d.rotation = command.Rotation;
        d.fadeIn = fadeIn;
        d.velocity = velocity;

        if (kind == VfxParticleSystemKind.Smoke)
        {
            d.velocity *= 0.72f;
            d.scale *= 1.06f;
        }
        else if (kind == VfxParticleSystemKind.Spark)
        {
            d.scale *= 0.92f;
        }
    }

    public void EmitTrail(in VfxTrailCommand command)
    {
        if (!Available)
            return;
        var points = command.Points.Span;
        Texture2D px = TextureAssets.MagicPixel.Value;
        int step = Math.Max(1, points.Length / 10);
        for (int i = 1; i < points.Length; i++)
        {
            Vector2 a = points[i - 1];
            Vector2 b = points[i];
            if (a == Vector2.Zero || b == Vector2.Zero)
                continue;
            Vector2 delta = b - a;
            float len = delta.Length();
            if (len <= 0.01f)
                continue;
            float k = 1f - i / (float)Math.Max(1, points.Length - 1);
            Main.spriteBatch.Draw(px, a - Main.screenPosition, new Rectangle(0, 0, 1, 1), command.Color * command.Alpha * k, delta.ToRotation(), Vector2.Zero, new Vector2(len, Math.Max(0.5f, command.Width * k)), SpriteEffects.None, 0f);

            if (i % step == 0)
            {
                int type = PickGlowDust(command.Color);
                Vector2 pos = Vector2.Lerp(a, b, 0.5f);
                Dust d = Dust.NewDustPerfect(pos, type, delta * 0.02f, 120, command.Color, Math.Clamp(command.Width * 0.08f, 0.55f, 1.8f));
                d.noGravity = true;
                d.fadeIn = 0.15f;
            }
        }
    }

    public void EmitActor(in VfxActorCommand command)
    {
        // Reserved for future VisualActor layer. Keeping this as a no-op prevents the
        // manifest/runtime from treating actor afterimages as gameplay projectiles.
    }

    private static int PickDustType(VfxParticleSystemKind kind, Color color, Vector2 scale, float alpha)
    {
        return kind switch
        {
            VfxParticleSystemKind.Smoke => PickSmokeDust(color),
            VfxParticleSystemKind.Shard => PickShardDust(color),
            VfxParticleSystemKind.Spark => PickSparkDust(color),
            VfxParticleSystemKind.Glow => PickGlowDust(color),
            _ => PickGenericDust(color, scale, alpha)
        };
    }

    private static int PickGenericDust(Color color, Vector2 scale, float alpha)
    {
        float size = (scale.X + scale.Y) * 0.5f;
        if (alpha < 0.25f || size > 1.8f)
            return PickSmokeDust(color);
        if (Brightness(color) > 0.72f)
            return PickGlowDust(color);
        return PickSparkDust(color);
    }

    private static int PickGlowDust(Color color)
    {
        if (color.G > color.R + 26 && color.G > color.B + 18)
            return DustID.GreenTorch;
        if (color.B > color.R + 22 && color.B > color.G + 8)
            return DustID.Ice;
        if (color.R > color.G + 24 && color.R > color.B + 8)
            return DustID.RedTorch;
        if (color.R > 190 && color.B > 170)
            return DustID.PinkTorch;
        if (color.R > 210 && color.G > 180 && color.B < 120)
            return DustID.YellowTorch;
        if (color.R > 150 && color.B > 150)
            return DustID.Shadowflame;
        return DustID.WhiteTorch;
    }

    private static int PickSparkDust(Color color)
    {
        if (color.B > color.R + 28 && color.B > color.G)
            return DustID.Electric;
        if (color.R > 200 && color.G > 170)
            return DustID.YellowStarDust;
        if (color.R > 180 && color.B > 150)
            return DustID.PinkTorch;
        if (color.G > color.R + 24 && color.G > color.B)
            return DustID.GreenTorch;
        if (color.R > color.G + 24)
            return DustID.RedTorch;
        return DustID.WhiteTorch;
    }

    private static int PickSmokeDust(Color color)
    {
        if (Brightness(color) < 0.33f)
            return DustID.Smoke;
        if (color.B > color.R + 18 && color.B > color.G)
            return DustID.Shadowflame;
        if (color.G > color.R + 26 && color.G > color.B)
            return DustID.GreenTorch;
        return DustID.Smoke;
    }

    private static int PickShardDust(Color color)
    {
        if (color.B > color.R + 18 && color.B > color.G + 8)
            return DustID.GemSapphire;
        if (color.G > color.R + 18 && color.G > color.B + 8)
            return DustID.GreenTorch;
        if (color.R > 200 && color.G > 170)
            return DustID.YellowTorch;
        if (color.R > 170 && color.B > 150)
            return DustID.PurpleTorch;
        if (color.R > color.G + 22 && color.R > color.B + 12)
            return DustID.RedTorch;
        if (Brightness(color) > 0.72f)
            return DustID.WhiteTorch;
        return DustID.WhiteTorch;
    }

    private static float Brightness(Color color)
        => (color.R + color.G + color.B) / (255f * 3f);
}

/// <summary>
/// Real ParticleLibrary backend. ParticleLibrary is now a hard mod reference, but the rest of
/// InfiniVfx still talks only to IVfxBackend. If ParticleLibrary systems are not ready, the
/// runtime automatically falls back to VanillaDustVfxBackend.
/// </summary>
public sealed class ParticleLibraryVfxBackend : IVfxBackend
{
    public bool Available => VfxParticleSystemRegistry.Ready || VfxParticleSystemRegistry.EnsureReady();
    public string Name => "particleLibrary";

    public void Emit(in VfxEmitCommand command)
    {
        if (!Available)
            return;

        string id = VfxParticleAddress.Resolve(command.ParticleSystemId);
        VfxParticleSystemKind kind = VfxParticleAddress.KindFor(id);

        // ParticleLibrary is safe only for additive glow/sparks/trails. AlphaBlend
        // MagicPixel quads can corrupt ordinary Terraria scenes: the bug was
        // reproduced with a stock Torch, so this is not limited to generated weapons.
        if (NeedsSoftParticleFallback(kind, command.StartColor, command.Alpha))
        {
            InfiniVfxBackends.VanillaDust.Emit(command);
            return;
        }

        float alpha = Math.Clamp(command.Alpha * InfiniVfxClientOptions.ParticleAlphaMultiplier, 0f, ParticleLibraryAlphaCap(kind));
        Color start = command.StartColor * alpha;
        Color end = command.EndColor;
        Vector2 scale = ParticleLibraryScaleClamp(kind, command.Scale);
        Vector2 velocity = command.Velocity;
        Vector2 accel = new(0.92f, 0.92f);
        Vector2 scaleVelocity = new(-0.0035f * Math.Max(1f, scale.X), -0.0035f * Math.Max(1f, scale.Y));
        float rotationVelocity = ((command.Seed % 200) - 100) * 0.0009f;

        switch (kind)
        {
            case VfxParticleSystemKind.Smoke:
                accel = new Vector2(0.97f, 0.97f);
                scale = new Vector2(scale.X * 1.2f, scale.Y * 1.2f);
                scaleVelocity = new Vector2(0.008f + scale.X * 0.0015f, 0.008f + scale.Y * 0.0015f);
                velocity *= 0.55f;
                start *= 0.82f;
                break;
            case VfxParticleSystemKind.Shard:
                accel = new Vector2(0.94f, 0.94f);
                scale = new Vector2(Math.Clamp(scale.X * 1.25f, 0.05f, 8f), Math.Clamp(scale.Y * 0.72f, 0.05f, 8f));
                scaleVelocity = new Vector2(-0.0022f * Math.Max(1f, scale.X), -0.0012f * Math.Max(1f, scale.Y));
                rotationVelocity *= 2.2f;
                break;
            case VfxParticleSystemKind.Spark:
                accel = new Vector2(0.88f, 0.88f);
                velocity *= 1.18f;
                break;
            case VfxParticleSystemKind.Glow:
                accel = new Vector2(0.95f, 0.95f);
                scale = new Vector2(scale.X * 1.08f, scale.Y * 1.08f);
                scaleVelocity = new Vector2(-0.0022f * Math.Max(1f, scale.X), -0.0022f * Math.Max(1f, scale.Y));
                break;
        }

        if (kind == VfxParticleSystemKind.Spark)
        {
            VfxParticleSystemRegistry.EmitSpark(
                command.Position,
                velocity,
                start,
                end,
                new Vector2(Math.Clamp(scale.X * 0.22f, 0.05f, 1.15f), Math.Clamp(scale.Y * 0.22f, 0.05f, 1.15f)),
                Vector2.Zero,
                command.Rotation,
                0f,
                accel,
                Math.Max(8, command.Lifespan));

            // Terraria-style spark read: a hard point plus a very short additive bloom.
            // This keeps sparks visible on bright backgrounds without turning them into smoke/glow.
            VfxParticleSystemRegistry.EmitGlow(
                command.Position,
                velocity * 0.28f,
                start * 0.42f,
                Color.Transparent,
                new Vector2(Math.Clamp(scale.X * 0.42f, 0.05f, 1.35f), Math.Clamp(scale.Y * 0.42f, 0.05f, 1.35f)),
                new Vector2(-0.010f, -0.010f),
                command.Rotation,
                0f,
                new Vector2(0.90f, 0.90f),
                Math.Max(6, command.Lifespan / 2));
            return;
        }

        VfxParticleSystemRegistry.EmitGlow(
            command.Position,
            velocity,
            start,
            end,
            scale,
            scaleVelocity,
            command.Rotation,
            rotationVelocity,
            accel,
            command.Lifespan);

        if (kind == VfxParticleSystemKind.Shard && (command.Seed & 3) == 0)
        {
            VfxParticleSystemRegistry.EmitSpark(
                command.Position,
                velocity * 0.45f,
                Color.Lerp(start, Color.White, 0.35f),
                Color.Transparent,
                new Vector2(0.35f, 0.35f),
                Vector2.Zero,
                command.Rotation,
                0f,
                new Vector2(0.88f, 0.88f),
                Math.Max(8, command.Lifespan / 2));
        }
    }

    public void EmitTrail(in VfxTrailCommand command)
    {
        if (!Available)
            return;

        var points = command.Points.Span;
        if (points.Length < 2)
            return;

        int step = Math.Max(1, points.Length / 18);
        for (int i = 1; i < points.Length; i += step)
        {
            Vector2 a = points[i - 1];
            Vector2 b = points[i];
            if (a == Vector2.Zero || b == Vector2.Zero)
                continue;
            Vector2 delta = b - a;
            float len = delta.Length();
            if (len <= 0.01f)
                continue;
            float k = 1f - i / (float)Math.Max(1, points.Length - 1);
            VfxParticleSystemRegistry.EmitGlow(
                a,
                Vector2.Zero,
                command.Color * Math.Clamp(command.Alpha * InfiniVfxClientOptions.ParticleAlphaMultiplier, 0f, 1f) * k,
                Color.Transparent,
                new Vector2(Math.Clamp(len / 18f, 0.12f, 7f), Math.Clamp(command.Width * k / 12f, 0.05f, 4f)),
                new Vector2(-0.004f),
                delta.ToRotation(),
                0f,
                new Vector2(0.96f),
                14 + (int)(12 * k));
        }
    }

    public void EmitActor(in VfxActorCommand command)
    {
        // VisualActor is still rendered by sprite/actor layers, not ParticleLibrary.
    }


    private static bool NeedsSoftParticleFallback(VfxParticleSystemKind kind, Color startColor, float alpha)
    {
        // These are smoke/dust/chip reads. Use vanilla Dust because ParticleLibrary
        // would need soft textures, not MagicPixel quads.
        if (kind is VfxParticleSystemKind.Smoke or VfxParticleSystemKind.Shard)
            return true;

        // Auto/dusty dark particles are also safer as Dust; additive glow/spark stays PL.
        return kind == VfxParticleSystemKind.Auto && alpha > 0.20f && ColorBrightness(startColor) < 0.35f;
    }

    private static float ParticleLibraryAlphaCap(VfxParticleSystemKind kind)
    {
        return kind switch
        {
            VfxParticleSystemKind.Spark => 0.82f,
            VfxParticleSystemKind.Glow => 0.68f,
            _ => 0.58f
        };
    }

    private static Vector2 ParticleLibraryScaleClamp(VfxParticleSystemKind kind, Vector2 scale)
    {
        float max = kind switch
        {
            VfxParticleSystemKind.Spark => 1.25f,
            VfxParticleSystemKind.Glow => 1.65f,
            _ => 1.35f
        };
        return new Vector2(Math.Clamp(scale.X, 0.05f, max), Math.Clamp(scale.Y, 0.05f, max));
    }

    private static float ColorBrightness(Color color)
        => (color.R + color.G + color.B) / (255f * 3f);
}

public static class InfiniVfxBackends
{
    public static readonly IVfxBackend Null = NullVfxBackend.Instance;
    public static readonly IVfxBackend ParticleLibrary = new ParticleLibraryVfxBackend();
    public static readonly IVfxBackend VanillaDust = new VanillaDustVfxBackend();

    public static IVfxBackend BestAvailable()
    {
        if (InfiniVfxClientOptions.ForceVanillaDustFallback && VanillaDust.Available)
            return VanillaDust;
        if (InfiniVfxClientOptions.EnableParticleLibraryBackend && ParticleLibrary.Available)
            return ParticleLibrary;
        if (VanillaDust.Available)
            return VanillaDust;
        return Null;
    }
}

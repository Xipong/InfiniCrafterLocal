#nullable enable
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.VFX;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using System;
using Terraria;
using Terraria.DataStructures;
using Terraria.ID;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Content.Projectiles;

/// <summary>
/// Pure visual carrier for hit/kill VFX that must outlive the gameplay projectile.
/// The real GeneratedProjectile can die immediately after OnHit/OnKill, so timers stored
/// inside it are often lost before PreDraw can show impact/decay layers. This projectile
/// is intentionally non-damaging and only executes the frozen VfxManifest.
///
/// v0.3.28 policy: client-local visual carrier. It is spawned only by the local owner and
/// carries no serialized manifest. If it ever appears on a remote endpoint unconfigured,
/// AI() kills it immediately instead of showing a wrong/default effect.
/// </summary>
public sealed class GeneratedVfxOverlayProjectile : ModProjectile
{
    public override string Texture => "InfiniCrafterLocal/Assets/GeneratedProjectile";

    private AttackSpec _spec = new();
    private VfxManifestSpec _manifest = new();
    private InfiniVfxState _state = new();
    private string _eventKind = "hit";
    private Vector2 _eventCenter;
    private bool _configured;
    private bool _started;

    public static bool Spawn(IEntitySource source, Vector2 center, Vector2 inheritedVelocity, int owner, AttackSpec spec, VfxManifestSpec manifest, string eventKind, int lifetime = 40)
    {
        if (Main.dedServ || manifest is null || !manifest.HasSlots)
            return false;

        lifetime = Math.Clamp(lifetime, 6, 180);
        int idx = Projectile.NewProjectile(source, center, inheritedVelocity * 0.08f, ModContent.ProjectileType<GeneratedVfxOverlayProjectile>(), 0, 0f, owner);
        if (idx >= 0 && Main.projectile[idx].ModProjectile is GeneratedVfxOverlayProjectile overlay)
        {
            overlay.Apply(center, inheritedVelocity, spec, manifest, eventKind, lifetime);
            return true;
        }
        return false;
    }

    public override void SetDefaults()
    {
        Projectile.width = 8;
        Projectile.height = 8;
        Projectile.friendly = false;
        Projectile.hostile = false;
        Projectile.damage = 0;
        Projectile.knockBack = 0f;
        Projectile.penetrate = -1;
        Projectile.timeLeft = 30;
        Projectile.tileCollide = false;
        Projectile.ignoreWater = true;
        Projectile.hide = true;
        Projectile.alpha = 255;
        Projectile.netImportant = false;
    }

    private void Apply(Vector2 center, Vector2 inheritedVelocity, AttackSpec spec, VfxManifestSpec manifest, string eventKind, int lifetime)
    {
        _spec = spec ?? new AttackSpec();
        _manifest = manifest ?? VfxManifestSpec.Empty();
        _manifest.Normalize();
        _eventKind = string.IsNullOrWhiteSpace(eventKind) ? "hit" : eventKind.ToLowerInvariant();
        _eventCenter = center;
        _state = new InfiniVfxState { LocalSeed = _manifest.Seed };
        _configured = true;
        Projectile.Center = center;
        Projectile.velocity = inheritedVelocity * 0.08f;
        Projectile.timeLeft = lifetime;
        Projectile.netUpdate = false; // local-only overlay; no SendExtraAI payload by design
    }

    public override void AI()
    {
        if (!_configured || _manifest is null || !_manifest.HasSlots)
        {
            Projectile.Kill();
            return;
        }

        Projectile.velocity *= 0.88f;
        Projectile.alpha = 255;

        if (!_started)
        {
            _started = true;
            if (_eventKind.Contains("kill") || _eventKind.Contains("expire") || _eventKind.Contains("decay"))
                InfiniVfxRuntime.OnKill(Projectile, _spec, _manifest, ref _state);
            else
                InfiniVfxRuntime.OnHit(Projectile, _eventCenter, _spec, _manifest, ref _state);
        }

        InfiniVfxRuntime.OnTick(Projectile, _spec, _manifest, ref _state);
    }

    public override bool PreDraw(ref Color lightColor)
    {
        if (_configured)
            InfiniVfxRuntime.Draw(Projectile, _spec, _manifest, ref _state, lightColor);
        return false;
    }
}

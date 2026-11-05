#nullable enable
using System;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Terraria;
using Terraria.GameContent;
using Terraria.ID;
using Terraria.ModLoader;

namespace WorkbenchObserverFixture;

// Explicit existing IFC resources are this fixture's own authored textures,
// not fallback art for the mod under test. No new binary assets are required.
public class RenderProbeItem : ModItem
{
    public override string Texture => "InfiniCrafterLocal/Assets/GeneratedItem";
    protected virtual int ProjectileType => ModContent.ProjectileType<RenderProbeProjectile>();
    public override void SetDefaults()
    {
        Item.width = Item.height = 20;
        Item.damage = 1;
        Item.DamageType = DamageClass.Ranged;
        Item.useTime = Item.useAnimation = 12;
        Item.useStyle = ItemUseStyleID.Shoot;
        Item.noMelee = true;
        Item.noUseGraphic = true;
        Item.shoot = ProjectileType;
        Item.shootSpeed = 2;
    }
}

public sealed class RenderHeldProbeItem : RenderProbeItem
{
    protected override int ProjectileType => ModContent.ProjectileType<RenderHeldProbeProjectile>();
}

public class RenderProbeProjectile : ModProjectile
{
    public override string Texture => "InfiniCrafterLocal/Assets/GeneratedProjectile";
    public override void SetDefaults()
    {
        Projectile.width = Projectile.height = 8;
        Projectile.friendly = true;
        Projectile.tileCollide = false;
        Projectile.timeLeft = 10;
    }
    public override void AI()
    {
        Projectile.ai[0]++;
        Observation.Hit("RenderProbe.AI");
    }
    public override bool PreDraw(ref Color lightColor)
    {
        Observation.Hit("RenderProbe.PreDraw");
        if (Environment.GetEnvironmentVariable("IFC_FIXTURE_THROW_ON_DRAW") == "1")
            throw new InvalidOperationException("fixture draw failure");
        // Native SpriteBatch/texture path with PreDraw=false: the host must not
        // replace the custom result with a default projectile sprite.
        Main.spriteBatch.Draw(TextureAssets.MagicPixel.Value,
            Projectile.Center - Main.screenPosition, new Rectangle(0, 0, 1, 1),
            Color.Red, Projectile.rotation, Vector2.Zero, new Vector2(20, 5), SpriteEffects.None, 0);
        return false;
    }
}

public sealed class RenderHeldProbeProjectile : RenderProbeProjectile
{
    public override void SetDefaults()
    {
        base.SetDefaults();
        Projectile.hide = true; // Native player held-projectile layer owns it.
    }
    public override void AI()
    {
        base.AI();
        var owner = Main.player[Projectile.owner];
        owner.heldProj = Projectile.whoAmI;
        Projectile.Center = owner.Center + new Vector2(owner.direction * 26, -10);
        Projectile.velocity = Vector2.Zero;
        owner.SetCompositeArmFront(true, Player.CompositeArmStretchAmount.Full, -MathHelper.PiOver2);
    }
}

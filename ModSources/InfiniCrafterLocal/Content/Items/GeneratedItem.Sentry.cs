#nullable enable
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using System;
using Terraria;
using Terraria.DataStructures;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Content.Items;

public partial class GeneratedItem
{
    private bool ShootGeneratedSentry(Player player, EntitySource_ItemUse_WithAmmo source, int damage, float knockback)
    {
        int type = ModContent.ProjectileType<GeneratedProjectile>();
        Vector2 position = Main.MouseWorld;
        player.LimitPointToPlayerReachableArea(ref position);
        bool floating = string.Equals(Data.Attack.SentryPlacement, "floating", StringComparison.Ordinal);
        if (!floating)
        {
            player.FindSentryRestingSpot(type, out int worldX, out int worldY, out _);
            int halfHeight = Math.Max(4, Data.Attack.ProjectileHeight / 2);
            position = new Vector2(worldX, worldY - halfHeight);
        }
        int idx = Projectile.NewProjectile(source, position, Vector2.Zero, type, damage, knockback, player.whoAmI, Data.Attack.MovementCode, Data.Attack.EffectCode, Data.Attack.OnHitCode);
        if (idx >= 0 && idx < Main.maxProjectiles && Main.projectile[idx].ModProjectile is GeneratedProjectile generated)
        {
            generated.ApplyGeneratedSpec(Data.Attack, Data.VfxManifest, Data.Id);
            Main.projectile[idx].netUpdate = true;
            generated.BroadcastVisualSync();
        }
        player.UpdateMaxTurrets();
        return false;
    }
}

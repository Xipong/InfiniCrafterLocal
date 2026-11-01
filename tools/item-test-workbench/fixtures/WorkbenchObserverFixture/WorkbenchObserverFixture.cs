#nullable enable
using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.DataStructures;
using Terraria.ID;
using Terraria.ModLoader;

// This test-only mod is discovered by tModLoader like any other mod. The
// workbench does not refer to these types: the fixture owns its observations.
namespace WorkbenchObserverFixture;

public sealed class WorkbenchObserverFixture : Mod
{
    public static bool Loaded { get; private set; }
    public override void Load() => Loaded = true;
    public override void Unload() => Loaded = false;
}

internal static class Observation
{
    internal const string OutputVariable = "IFC_WORKBENCH_OBSERVER_OUTPUT";
    internal static bool DamageModifiersEnabled => !string.Equals(
        Environment.GetEnvironmentVariable("IFC_FIXTURE_DISABLE_DAMAGE_MODIFIERS"), "1", StringComparison.Ordinal);
    private static readonly object Gate = new();
    private static readonly Dictionary<string, long> Counts = new(StringComparer.Ordinal);

    internal static void Reset() { lock (Gate) Counts.Clear(); }
    internal static void Hit(string hook)
    {
        lock (Gate) Counts[hook] = Counts.TryGetValue(hook, out long count) ? count + 1 : 1;
    }

    internal static void Flush()
    {
        string? path = Environment.GetEnvironmentVariable(OutputVariable);
        if (string.IsNullOrEmpty(path)) return;
        if (!Path.IsPathFullyQualified(path))
            throw new InvalidOperationException(OutputVariable + " must be an absolute file path");
        string? parent = Path.GetDirectoryName(path);
        if (string.IsNullOrEmpty(parent) || !Directory.Exists(parent))
            throw new DirectoryNotFoundException("Observer output parent must already exist");
        // World-unload hooks can run off the update thread. Serialize and write
        // under the same gate as counters to avoid torn or conflicting snapshots.
        lock (Gate) {
            string json = JsonSerializer.Serialize(new {
                schemaVersion = 1,
                mod = "WorkbenchObserverFixture",
                gameUpdateCount = Main.GameUpdateCount,
                counts = Counts
            });
            string temporary = path + ".tmp";
            File.WriteAllText(temporary, json);
            File.Move(temporary, path, true);
        }
    }
}

public sealed class ProbeItem : ModItem
{
    // Use vanilla assets so the fixture does not need any authored art.
    public override string Texture => "Terraria/Images/Item_98";
    public override void SetDefaults()
    {
        Item.width = 20;
        Item.height = 20;
        Item.damage = 20;
        Item.DamageType = DamageClass.Ranged;
        Item.useTime = 20;
        Item.useAnimation = 20;
        Item.useStyle = ItemUseStyleID.Shoot;
        Item.noMelee = true;
        Item.shoot = ModContent.ProjectileType<ProbeProjectile>();
        Item.shootSpeed = 8;
        Item.knockBack = 0;
    }
    public override bool CanUseItem(Player player)
    {
        Observation.Hit("ModItem.CanUseItem");
        return true;
    }
    public override bool Shoot(Player player, EntitySource_ItemUse_WithAmmo source,
        Vector2 position, Vector2 velocity, int type, int damage, float knockback)
    {
        Observation.Hit("ModItem.Shoot");
        return true; // Let native ItemCheck spawn the configured projectile.
    }
}

public sealed class ProbeGlobalItem : GlobalItem
{
    public override void ModifyWeaponDamage(Item item, Player player, ref StatModifier damage)
    {
        Observation.Hit("GlobalItem.ModifyWeaponDamage.Any");
        if (item.type != ModContent.ItemType<ProbeItem>()) return;
        Observation.Hit("GlobalItem.ModifyWeaponDamage");
        if (Observation.DamageModifiersEnabled) damage.Flat += 3;
    }
}

public sealed class ProbeProjectile : ModProjectile
{
    public override string Texture => "Terraria/Images/Projectile_1";
    public override void SetDefaults()
    {
        Projectile.width = 8;
        Projectile.height = 8;
        Projectile.friendly = true;
        Projectile.DamageType = DamageClass.Ranged;
        Projectile.tileCollide = false;
        Projectile.ignoreWater = true;
        Projectile.timeLeft = 120;
        Projectile.penetrate = 1;
    }
    public override void AI() => Observation.Hit("ModProjectile.AI");
    public override void OnHitNPC(NPC target, NPC.HitInfo hit, int damageDone)
        => Observation.Hit("ModProjectile.OnHitNPC");
}

public sealed class ProbeGlobalProjectile : GlobalProjectile
{
    public override void OnSpawn(Projectile projectile, IEntitySource source)
    {
        Observation.Hit("GlobalProjectile.OnSpawn.Any");
        if (projectile.type == ModContent.ProjectileType<ProbeProjectile>())
            Observation.Hit("GlobalProjectile.OnSpawn");
    }
    public override void PostAI(Projectile projectile)
    {
        Observation.Hit("GlobalProjectile.PostAI.Any");
        if (projectile.type == ModContent.ProjectileType<ProbeProjectile>())
            Observation.Hit("GlobalProjectile.PostAI");
    }
    public override void OnHitNPC(Projectile projectile, NPC target, NPC.HitInfo hit, int damageDone)
    {
        Observation.Hit("GlobalProjectile.OnHitNPC.Any");
        if (projectile.type == ModContent.ProjectileType<ProbeProjectile>())
            Observation.Hit("GlobalProjectile.OnHitNPC");
    }
}

public sealed class ProbeNpc : ModNPC
{
    public override string Texture => "Terraria/Images/NPC_1";
    public override void SetDefaults()
    {
        NPC.width = 32;
        NPC.height = 48;
        NPC.aiStyle = -1;
        NPC.lifeMax = 10000;
        NPC.damage = 0;
        NPC.defense = 0;
        NPC.knockBackResist = 0;
        NPC.noGravity = true;
        NPC.noTileCollide = true;
    }
    public override void AI() => Observation.Hit("ModNPC.AI");
}

public sealed class ProbeGlobalNpc : GlobalNPC
{
    public override void OnSpawn(NPC npc, IEntitySource source)
    {
        if (npc.type == ModContent.NPCType<ProbeNpc>()) Observation.Hit("GlobalNPC.OnSpawn");
    }
    public override void ModifyHitByProjectile(NPC npc, Projectile projectile, ref NPC.HitModifiers modifiers)
    {
        Observation.Hit("GlobalNPC.ModifyHitByProjectile.Any");
        if (npc.type != ModContent.NPCType<ProbeNpc>() || projectile.type != ModContent.ProjectileType<ProbeProjectile>()) return;
        Observation.Hit("GlobalNPC.ModifyHitByProjectile");
        if (Observation.DamageModifiersEnabled) modifiers.SourceDamage *= 1.25f;
    }
}

public sealed class ProbePlayer : ModPlayer
{
    public override void ModifyWeaponDamage(Item item, ref StatModifier damage)
    {
        Observation.Hit("ModPlayer.ModifyWeaponDamage.Any");
        if (item.type != ModContent.ItemType<ProbeItem>()) return;
        Observation.Hit("ModPlayer.ModifyWeaponDamage");
        if (Observation.DamageModifiersEnabled) damage.Flat += 5;
    }
    public override void PostUpdate()
    {
        if (Player.active) Observation.Hit("ModPlayer.PostUpdate");
    }
}

public sealed class ProbeSystem : ModSystem
{
    public override void PostSetupContent() => Observation.Hit("ModSystem.PostSetupContent");
    public override void OnWorldLoad() => Observation.Reset();
    public override void PostUpdateEverything()
    {
        Observation.Hit("ModSystem.PostUpdateEverything");
        if (Main.GameUpdateCount % 10 == 0) Observation.Flush();
    }
    public override void OnWorldUnload() => Observation.Flush();
}

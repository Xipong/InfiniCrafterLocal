using System;
using System.Collections.Generic;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private static void WhipGeometryTracksEquippedRangeInCollision()
    {
        WithPlayer((owner, _) =>
        {
            Player oldOwner = Terraria.Main.player[0];
            try
            {
                owner.active = true;
                owner.whoAmI = 0;
                owner.direction = 1;
                owner.itemAnimationMax = 20;
                owner.itemAnimation = 10;
                Terraria.Main.player[0] = owner;
                var entity = Entity();
                entity.Id = "range-whip";
                entity.Kind = RuntimeEntityKind.OwnerAttachedProjectile;
                entity.Movement.Name = "move_whip_lash";
                entity.Movement.Code = 18;
                entity.Movement.Params.RangeTiles = 10f;
                entity.Movement.Params.Segments = 12;
                var projectile = new Projectile { owner = 0, damage = 100, width = 12, height = 12 };
                var generated = Attach(projectile);
                generated.Configure(new GeneratedItemData(), entity, 0, 8, Vector2.UnitX);
                var points = (List<Vector2>)typeof(GeneratedProjectile)
                    .GetField("_whipPoints", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(generated)!;
                Vector2 origin = owner.MountedCenter;
                void Check(float multiplier, float expectedReach)
                {
                    owner.whipRangeMultiplier = multiplier;
                    generated.AI(); // Real movement updates the same points used by collision.
                    Equal(13, points.Count, "authored segment count");
                    float actualReach = Vector2.Distance(origin, points[^1]);
                    if (MathF.Abs(actualReach - expectedReach) > 0.05f)
                        throw new InvalidOperationException($"range {multiplier}: expected {expectedReach}, actual {actualReach}");
                    Equal(points[^1], projectile.Center, "projectile follows whip tip");
                    var tip = points[^1];
                    var target = new Rectangle((int)tip.X - 3, (int)tip.Y - 3, 6, 6);
                    Equal(true, generated.Colliding(new Rectangle(), target) == true, "tip collision follows equipped range");
                }
                Check(1f, 160f);
                Check(1.5f, 240f);
                Check(0.75f, 120f);
                var second = Entity();
                second.Id = "shorter-whip";
                second.Kind = RuntimeEntityKind.OwnerAttachedProjectile;
                second.Movement.Name = "move_whip_lash";
                second.Movement.Code = 18;
                second.Movement.Params.RangeTiles = 6f;
                second.Movement.Params.Segments = 12;
                generated.Configure(new GeneratedItemData(), second, 0, 8, Vector2.UnitX, preserveSyncedState: true);
                Check(1.5f, 144f); // Rehydrated per-instance geometry, not a shared proxy range.
            }
            finally { Terraria.Main.player[0] = oldOwner; }
        });
    }

    private static void WhipImpactMarksOnlyItsOwnerForSummonSourceDamage()
    {
        WithPlayer((owner, stats) =>
        {
            Player oldOwner = Terraria.Main.player[0];
            int oldMode = Terraria.Main.netMode;
            int oldLocalPlayer = Terraria.Main.myPlayer;
            var singleton = typeof(ContentInstance<GeneratedWhipTagGlobalNPC>).GetProperty("Instance")!;
            object? oldSingleton = singleton.GetValue(null);
            var tag = new GeneratedWhipTagGlobalNPC();
            var target = new NPC { type = 1, active = true };
            typeof(NPC).GetField("_globals", BindingFlags.Instance | BindingFlags.NonPublic)!
                .SetValue(target, new GlobalNPC[] { tag });
            var entity = Entity();
            entity.Id = "whip";
            entity.Kind = RuntimeEntityKind.OwnerAttachedProjectile;
            entity.Movement.Name = "move_whip_lash";
            entity.Movement.Code = 18;
            var data = new GeneratedItemData();
            data.Id = "whip-item";
            var hitProjectile = new Projectile { owner = 0, damage = 100 };
            var generated = Attach(hitProjectile);
            try
            {
                singleton.SetValue(null, tag);
                Terraria.Main.netMode = NetmodeID.MultiplayerClient;
                Terraria.Main.myPlayer = 0; // tML Projectile.Damage dispatches this hit on the owner client.
                owner.active = true;
                owner.whoAmI = 0;
                Terraria.Main.player[0] = owner;
                stats.AddGeneratedSummonTagDamage(0.25f);
                generated.Configure(data, entity, 0, 8, Vector2.UnitX);
                var minion = new Projectile { owner = 0, minion = true, DamageType = DamageClass.Summon };
                float Source(Projectile projectile)
                {
                    var modifiers = new NPC.HitModifiers();
                    tag.ModifyHitByProjectile(target, projectile, ref modifiers);
                    return modifiers.SourceDamage.ApplyTo(100f);
                }
                Equal(100f, Source(minion), "unmarked target");
                generated.OnHitNPC(target, new NPC.HitInfo(), 100);
                Equal(125f, Source(minion), "whip hit grants multiplicative summon source bonus");
                var twiceBase = new NPC.HitModifiers();
                tag.ModifyHitByProjectile(target, minion, ref twiceBase);
                Equal(250f, twiceBase.SourceDamage.ApplyTo(200f), "source bonus scales with base damage, not a flat tag");
                Equal(100f, Source(new Projectile { owner = 1, minion = true, DamageType = DamageClass.Summon }), "other owner cannot use tag");
                Equal(100f, Source(new Projectile { owner = 0, DamageType = DamageClass.Ranged }), "ranged cannot use tag");
                typeof(Projectile).GetProperty("ModProjectile")!.SetValue(hitProjectile, generated);
                Equal(100f, Source(hitProjectile), "tagging whip cannot consume own tag");
                tag.SetDefaults(target);
                Equal(100f, Source(minion), "NPC reuse clears marks");
                Terraria.Main.netMode = NetmodeID.Server;
                generated.OnHitNPC(target, new NPC.HitInfo(), 100);
                Equal(100f, Source(minion), "dedicated server cannot mint tag from a hook it does not receive");
                Terraria.Main.netMode = NetmodeID.MultiplayerClient;
                Terraria.Main.myPlayer = 1;
                generated.OnHitNPC(target, new NPC.HitInfo(), 100);
                Equal(100f, Source(minion), "remote client cannot mint owner's tag");
                Terraria.Main.myPlayer = 0;
                var otherEntity = Entity();
                otherEntity.Id = "ordinary-projectile";
                otherEntity.Kind = RuntimeEntityKind.FreeProjectile;
                generated.Configure(data, otherEntity, 0, 8, Vector2.UnitX);
                generated.OnHitNPC(target, new NPC.HitInfo(), 100);
                Equal(100f, Source(minion), "non-whip hit cannot mark target");
                generated.Configure(data, entity, 0, 8, Vector2.UnitX);
                owner.active = false;
                generated.OnHitNPC(target, new NPC.HitInfo(), 100);
                owner.active = true;
                Equal(100f, Source(minion), "inactive owner cannot mark target");
                generated.OnHitNPC(target, new NPC.HitInfo(), 100);
                for (int tick = 0; tick < 239; tick++) tag.PostAI(target);
                Equal(125f, Source(minion), "tag remains until its final tick");
                tag.PostAI(target);
                Equal(100f, Source(minion), "tag expires after its lifetime");
            }
            finally
            {
                singleton.SetValue(null, oldSingleton);
                Terraria.Main.player[0] = oldOwner;
                Terraria.Main.netMode = oldMode;
                Terraria.Main.myPlayer = oldLocalPlayer;
            }
        });
    }
}

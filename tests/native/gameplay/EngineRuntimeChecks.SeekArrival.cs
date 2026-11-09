using System;
using System.Text.Json.Nodes;
using System.Reflection;
using InfiniCrafterLocal.Common.Players;
using MonoMod.RuntimeDetour;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    private static void CoincidentSeekPreservesFiniteMotionAndExplicitRetirement()
    {
        // Exercise the real AI consumer, not a reimplementation of normalization.
        foreach (bool clampDistance in new[] { false, true })
        foreach (float lerp in new[] { 0f, .25f, 1f })
        {
            using var scope = new SwarmRuntimeScope();
            var owner = Terraria.Main.player[0];
            var data = MotionDefinition("""
                {"seek":[{"target":"owner_center","maxSpeed":12,
                "velocityLerpPerUpdate":1,"limitSpeedToDistance":false}]}
                """, body => {
                    body["kind"] = "free_projectile";
                    body["visualRole"] = "projectile";
                    body["visual"]!["role"] = "projectile";
                    body["seek"]![0]!["velocityLerpPerUpdate"] = lerp;
                    body["seek"]![0]!["limitSpeedToDistance"] = clampDistance;
                });
            var (host, projectile) = MotionActor(data, owner, new Vector2(8, 4));
            projectile.Center = owner.Center;
            int lifetime = projectile.timeLeft;
            host.AI();
            AssertVfxNear(new Vector2(8, 4) * (1f - lerp), projectile.velocity,
                "coincident target has zero desired velocity and keeps authored interpolation");
            Equal(true, float.IsFinite(projectile.velocity.X) && float.IsFinite(projectile.velocity.Y),
                "arrival cannot poison native position integration with NaN");
            Equal(true, projectile.active, "seek alone must not invent retirement");
            Equal(lifetime, projectile.timeLeft, "steering does not replace authored lifetime");
            Equal(false, GeneratedProjectile.CanAdmitEntityBatch(data,
                data.RuntimeProgram.TryGetEntity(data.RuntimeProgram.PrimaryEntityId)!, owner.whoAmI, 1),
                "a deliberately live entity still occupies its exact concurrency slot");

            // A nonzero displacement retains the pre-fix native arithmetic.
            projectile.Center = owner.Center + new Vector2(3, 4);
            projectile.velocity = new Vector2(8, 4);
            Vector2 expected = Vector2.Lerp(projectile.velocity,
                projectile.DirectionTo(owner.Center) * (clampDistance ? 5f : 12f), lerp);
            host.AI();
            Equal(expected, projectile.velocity, "noncoincident seek is arithmetically unchanged");
        }

        using (var scope = new SwarmRuntimeScope())
        {
            var owner = Terraria.Main.player[0];
            var data = MotionDefinition("""
                {"seek":[{"target":"owner_center","maxSpeed":12,
                "velocityLerpPerUpdate":1,"limitSpeedToDistance":true}],
                "arrival":{"target":"owner_center","radiusPx":20,"action":"kill"}}
                """, body => {
                    body["kind"] = "free_projectile";
                    body["visualRole"] = "projectile";
                    body["visual"]!["role"] = "projectile";
                });
            var (host, projectile) = MotionActor(data, owner, Vector2.UnitX);
            var entity = data.RuntimeProgram.TryGetEntity(data.RuntimeProgram.PrimaryEntityId)!;
            projectile.Center = owner.Center;
            Equal(false, GeneratedProjectile.CanAdmitEntityBatch(data, entity, owner.whoAmI, 1),
                "one active root occupies cap before arrival");
            host.AI();
            Equal(false, projectile.active, "explicit arrival kills through native projectile lifecycle");
            Equal(true, GeneratedProjectile.CanAdmitEntityBatch(data, entity, owner.whoAmI, 1),
                "native retirement frees singleton immediately without waiting for initial lifetime");
        }
    }

    private static void SingleActiveWeaponBusyKeepsAdmissionWithoutChatWarning()
    {
        WithForgePresentationLanguages(locale => WithPlayer((player, playerState) => {
            using var scope = new SwarmRuntimeScope();
            player.active = true; player.whoAmI = 0; player.direction = 1;
            Terraria.Main.player[0] = player;
            int notices = 0;
            using var notice = new Hook(typeof(InfiniCraftPlayer).GetMethod("NotifyGeneratedUseRefusal",
                BindingFlags.Instance | BindingFlags.NonPublic)!,
                (Action<InfiniCraftPlayer, string>)((_, _) => notices++));
            var generated = RootCombatHost(RootCombatFixture(20, 2, "magic"));
            var entity = generated.Data.RuntimeProgram.TryGetEntity("root")!;
            entity.Spawn.MaxActive = 1;
            var active = SwarmHost(generated.Data, entity);
            string diagnostic = generated.RootSpawnBlockedReason(player, entity, out bool routineBusy);
            Equal(true, diagnostic.Length > 0, "exact blocked reason remains inspectable");
            Equal(true, routineBusy, "normal one-at-a-time busy is quiet");
            Equal(false, generated.CanUseItem(player), "quiet busy still refuses duplicate attack");
            Equal(0, notices, "normal busy does not reach player-facing notification");
            active.Projectile.active = false;
            Equal("", generated.RootSpawnBlockedReason(player, entity, out routineBusy),
                "retirement immediately permits next attack");
            Equal(false, routineBusy, "successful admission is not a stale busy result");
            Equal(true, generated.CanUseItem(player), "no synthetic cooldown after retirement");
            active.Projectile.active = true;
            entity.Spawn.Count = 2; entity.Spawn.MaxActive = 2;
            Equal(true, generated.RootSpawnBlockedReason(player, entity, out routineBusy).Length > 0,
                "partial capacity still rejects whole authored batch");
            Equal(false, routineBusy, "multi-shot capacity error retains feedback");
            Equal(false, generated.CanUseItem(player), "whole batch still refused");
            Equal(1, notices, "exceptional batch refusal reaches player-facing notification");
        }));
    }
}

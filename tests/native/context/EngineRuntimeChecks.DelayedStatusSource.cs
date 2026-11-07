using System;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Runtime;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    private static void DelayedNpcStatusSurvivesProjectileReuse()
    {
        foreach (bool generatedEffect in new[] { false, true })
        foreach (string transition in new[] { "unchanged", "source-reused", "target-reused", "owner-reused" })
        {
            using var scope = new Rt01NpcScope(NetmodeID.SinglePlayer);
            NPC first = Rt01Npc(0), second = Rt01Npc(1);
            Rt01ReceiveToken(first, 41); Rt01ReceiveToken(second, 42);
            var data = SwarmGameplayFixture();
            var body = data.RuntimeProgram.TryGetEntity("root")!;
            body.Events = new[] { generatedEffect ? NpcEffectAction(delay: 2) : new RuntimeEventActionSpec {
                Id = "status", Event = RuntimeEventKind.OnHit, Action = "apply_status_on_event",
                ActionCode = RuntimeEventActionCode.ApplyStatus, BuffId = BuffID.OnFire,
                DurationTicks = 90, DelayTicks = 2 } };
            data = SwarmWire(data); body = data.RuntimeProgram.TryGetEntity("root")!;
            var generated = SwarmHost(data, body);
            var projectile = generated.Projectile;
            generated.OnHitNPC(first, new NPC.HitInfo(), 10);
            generated.OnHitNPC(second, new NPC.HitInfo(), 10);
            Equal(2, PendingActions(), transition + " each hit is admitted once");
            projectile.active = false;
            if (transition != "unchanged")
            {
                // Native reset replaces the ModProjectile and identifies a new
                // occupant, instead of just setting a test-only flag.
                projectile.SetDefaults(ProjectileID.WoodenArrowFriendly);
                projectile.whoAmI = 0; projectile.owner = 0; projectile.active = true;
            }
            if (transition == "target-reused")
            {
                first.SetDefaults(NPCID.BlueSlime);
                first.whoAmI = 0; first.active = true;
                Rt01ReceiveToken(first, 43);
            }
            if (transition == "owner-reused")
                Terraria.Main.player[0] = new Player { whoAmI = 0, active = true };

            bool Applied(NPC npc) => generatedEffect
                ? RuntimeNpcEffects.GetTotals(npc).Count > 0 : npc.HasBuff(BuffID.OnFire);
            MaterialClock(1001); RuntimeDelayedActionScheduler.Update();
            Equal(false, Applied(first), transition + " first does not apply early");
            Equal(false, Applied(second), transition + " second does not apply early");
            MaterialClock(1002); RuntimeDelayedActionScheduler.Update();
            Equal(transition is not ("target-reused" or "owner-reused"), Applied(first), transition + " first target fence");
            Equal(transition != "owner-reused", Applied(second), transition + " second target fence");
            Equal(0, PendingActions(), transition + " actions retired");
            if (!generatedEffect && Applied(second))
            {
                int index = second.FindBuffIndex(BuffID.OnFire);
                Equal(90, second.buffTime[index], transition + " authored duration retained");
                second.buffTime[index] = 17;
                MaterialClock(1003); RuntimeDelayedActionScheduler.Update();
                Equal(17, second.buffTime[index], transition + " retired action does not replay");
            }
        }
    }
}

using System;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Runtime;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using MonoMod.RuntimeDetour;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    private static GeneratedProjectile LateOwnerActionHost(Player owner, byte code, int delay)
    {
        var data = SwarmGameplayFixture(); var entity = data.RuntimeProgram.TryGetEntity("root")!;
        entity.Events = new[] { new RuntimeEventActionSpec {
            Id = "late_owner", ActionCode = code, Event = RuntimeEventKind.OnHit, DelayTicks = delay,
            DamageFraction = 0.5f, MaxHeal = 50, RangeTiles = 120, CooldownTicks = 60,
            Mode = code == RuntimeEventActionCode.MoveOwner ? "blink_to_event_position" : "", SafeTileOnly = false,
        } };
        return SwarmHost(data, entity, owner: owner.whoAmI);
    }

    private static NPC LateOwnerActionTarget(Player owner)
        => new NPC { active = true, whoAmI = 0, position = owner.Center + new Vector2(100,0), width = 20,height = 20 };

    private static void LateOwnerActionsRejectDeadAndZeroLife()
    {
        using var scope = new MobilityConsumptionNativeScope();
        foreach (byte code in new[] { RuntimeEventActionCode.HealOwner, RuntimeEventActionCode.MoveOwner })
        foreach (string reason in new[] { "dead", "zero-life", "inactive" })
        foreach (int delay in new[] { 0,2 })
        WithPlayer((owner, generated) => {
            PrepareMobilityConsumptionPlayer(owner);
            var host = LateOwnerActionHost(owner,code,delay);
            var target = LateOwnerActionTarget(owner);
            if (reason == "dead") owner.dead = true;
            if (reason == "zero-life") owner.statLife = 0;
            if (reason == "inactive") owner.active = false;
            Vector2 before = owner.position; int life = owner.statLife;
            int healCalls = 0, moveCalls = 0;
            using var heal = new Hook(typeof(Player).GetMethod(nameof(Player.Heal))!,
                (Action<Player,int>)((_,_) => healCalls++));
            using var move = new Hook(typeof(Player).GetMethod(nameof(Player.Teleport))!,
                (Action<Player,Vector2,int,int>)((_,_,_,_) => moveCalls++));
            host.OnHitNPC(target,new NPC.HitInfo(),100);
            Equal(0, PendingActions(), $"{reason}/{code}/{delay}: dead owner cannot admit delayed self action");
            MaterialClock(2002); RuntimeDelayedActionScheduler.Update();
            Equal(0, healCalls + moveCalls, $"{reason}/{code}/{delay}: late hit cannot reach native Heal or Teleport");
            Equal(life,owner.statLife,"refusal preserves health"); Equal(before,owner.position,"refusal preserves position");
            Equal(0,generated.GeneratedMobilityCooldownTicks,"refusal cannot spend mobility cooldown");
        });
    }

    private static void LateOwnerHealCapsNativeAmountToMissingLife()
    {
        using var scope = new MobilityConsumptionNativeScope();
        foreach (int life in new[] { 50,99,100,105 })
        WithPlayer((owner,_) => {
            PrepareMobilityConsumptionPlayer(owner); owner.statLife = life;
            var host = LateOwnerActionHost(owner,RuntimeEventActionCode.HealOwner,0);
            int passed = 0, calls = 0;
            using var heal = new Hook(typeof(Player).GetMethod(nameof(Player.Heal))!,
                (Action<Action<Player,int>,Player,int>)((orig,p,amount) => { passed = amount; calls++; orig(p,amount); }));
            host.OnHitNPC(LateOwnerActionTarget(owner),new NPC.HitInfo(),100);
            Equal(Math.Max(0,100-life),passed,"native Heal receives at most missing HP");
            Equal(life < 100 ? 1 : 0,calls,"full health does not emit a heal");
            Equal(Math.Max(life,100),owner.statLife,"real native Heal changes only available health");
        });
    }

    private static void LateOwnerActionsCannotCrossDeathAndRespawn()
    {
        using var scope = new MobilityConsumptionNativeScope();
        foreach (byte code in new[] { RuntimeEventActionCode.HealOwner, RuntimeEventActionCode.MoveOwner })
        foreach (string scenario in new[] { "alive", "dead", "zero-life", "respawn", "new-life" })
        WithPlayer((owner,generated) => {
            RuntimeDelayedActionScheduler.Clear(); MaterialClock(2000);
            PrepareMobilityConsumptionPlayer(owner);
            if (scenario == "new-life") {
                owner.dead = true; generated.UpdateDead(); owner.dead = false; MaterialClock(2001);
            }
            var host = LateOwnerActionHost(owner,code,2);
            var target = LateOwnerActionTarget(owner); Vector2 before = owner.Center; int life = owner.statLife;
            host.OnHitNPC(target,new NPC.HitInfo(),100);
            Equal(1,PendingActions(),"live hit admits exactly one delayed owner action");
            if (scenario is "dead" or "respawn") {
                MaterialClock(2001); owner.dead = true; generated.UpdateDead();
                if (scenario == "respawn") owner.dead = false;
            }
            if (scenario == "zero-life") owner.statLife = life = 0;
            MaterialClock(scenario == "new-life" ? 2003u : 2002u); RuntimeDelayedActionScheduler.Update();
            bool allowed = scenario is "alive" or "new-life";
            Equal(0,PendingActions(),"due action retires once");
            Equal(allowed && code == RuntimeEventActionCode.HealOwner ? 100 : life,owner.statLife,scenario+" delayed healing outcome");
            Equal(allowed && code == RuntimeEventActionCode.MoveOwner ? target.Center : before,owner.Center,scenario+" delayed real Teleport outcome");
            Equal(allowed && code == RuntimeEventActionCode.MoveOwner ? 60 : 0,generated.GeneratedMobilityCooldownTicks,scenario+" cooldown outcome");
            Vector2 arrived = owner.Center; int healed = owner.statLife;
            RuntimeDelayedActionScheduler.Update(); Equal(arrived,owner.Center,"no teleport replay"); Equal(healed,owner.statLife,"no heal replay");
        });
    }
}

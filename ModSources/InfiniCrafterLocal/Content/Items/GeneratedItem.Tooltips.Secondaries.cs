#nullable enable
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.UI;

namespace InfiniCrafterLocal.Content.Items;

public partial class GeneratedItem
{
    // Small read-only view of the two combat consumers, not a capability catalog.
    // Reach only exact binding/event/controller spawn references; never infer from
    // names/prose or mutate/normalize the admitted program to produce feedback.
    private static void AddRuntimeSecondaryCombat(GeneratedItemData data, Action<string, string, object[]> add)
    {
        RuntimeProgramSpec program = data.RuntimeProgram;
        bool activeUse = false, itemContact = false;
        var pending = new Queue<(RuntimeEntitySpec Entity, int Depth)>();
        var reached = new HashSet<string>(StringComparer.Ordinal);
        void Reach(RuntimeEntitySpec? entity, int depth)
        {
            if (entity is null || reached.Count >= InfiniRuntimeLimits.MaxRuntimeEntities
                || depth > program.Limits.MaxChildDepth || !reached.Add(entity.Id)) return;
            pending.Enqueue((entity, depth));
        }
        foreach (string input in new[] { RuntimeInputKind.PrimaryUse, RuntimeInputKind.AlternateUse, RuntimeInputKind.Hold })
        {
            RuntimeBindingSpec? binding = program.BindingForInput(input);
            if (binding is null || !RuntimeBindingAction.IsAllowed(input, binding.UsePolicy.Action.Kind)
                || binding.UsePolicy.StackCost is not (0 or 1)
                || (input == RuntimeInputKind.Hold && binding.UsePolicy.StackCost != 0)) continue;
            RuntimeBindingActionSpec action = binding.UsePolicy.Action;
            RuntimeEntitySpec? target = program.TryGetEntity(action.TargetId);
            bool spawn = action.Kind == RuntimeBindingAction.SpawnEntity;
            if (target is null || (spawn ? !RuntimeEntityKind.IsBindingSpawnable(target.Kind) || !target.Spawn.Enabled
                : target.Kind != RuntimeEntityKind.ItemBody)) continue;
            if (spawn) Reach(target, 0);
            if (input is RuntimeInputKind.PrimaryUse or RuntimeInputKind.AlternateUse
                && action.Kind != RuntimeBindingAction.PlaceItem)
            {
                activeUse = true;
                itemContact |= binding.UsePolicy.ContactDamage && !program.ItemUse.DisableMeleeHitbox
                    && data.Gameplay.AmmoCategory.Length == 0 && data.Gameplay.Damage > 0;
            }
        }
        // HoldItem emits item-body periodic actions independently of a hold binding.
        Reach(program.TryGetEntity(program.ItemEntityId), 0);
        int index = 0;
        while (pending.Count > 0)
        {
            var (source, depth) = pending.Dequeue();
            RuntimeEventActionSpec[] events = source.Events ?? Array.Empty<RuntimeEventActionSpec>();
            for (int i = 0; i < Math.Min(events.Length, InfiniRuntimeLimits.MaxRuntimeEventsPerEntity); i++)
            {
                RuntimeEventActionSpec? action = events[i];
                if (action is null || !SecondaryEventIsReachable(source, action, itemContact, activeUse, program.BindingForInput(RuntimeInputKind.Equipped) is not null)) continue;
                string occurrence = SecondaryOccurrence(source, action);
                if (action.Event is RuntimeEventKind.OnHurt or RuntimeEventKind.OnEnemyKill)
                    add("ReactionCooldown" + action.Id, "ReactionCooldown", new object[] { occurrence, RuntimeTooltipTime(action.ReactionCooldownTicks) });
                string delay = action.DelayTicks == 0 ? RuntimeTooltipText("SecondaryImmediate") : RuntimeTooltipTime(action.DelayTicks);
                string suffix = (index++).ToString(CultureInfo.InvariantCulture);
                if (action.ActionCode == RuntimeEventActionCode.ApplyGeneratedBuff
                    && source.Kind == RuntimeEntityKind.ItemBody
                    && program.TryGetEffectGroup(action.EffectGroupId ?? "") is { IsGeneratedBuffOnly: true } group)
                {
                    if (action.DelayTicks > 0)
                        add("ReactionDelay" + suffix, "ReactionDelay", new object[] { occurrence, delay });
                    AddRuntimeUseEffects(group, "Reaction" + suffix, occurrence, add);
                }
                else if (action.ActionCode is (RuntimeEventActionCode.DamageArea or RuntimeEventActionCode.DamageNearby) && action.RadiusPx is > 0 and <= 1024
                    && RuntimeTooltipFinite(action.DamageMultiplier, 0f, 10f))
                {
                    // RuntimeProgramExecutor.AuthoredEventDamage/DamageArea:
                    // source base (not live damageDone), midpoint-even rounding,
                    // <=16 chaseable NPC centers inside radius; exclude contact victim.
                    int authored = source.Kind == RuntimeEntityKind.ItemBody ? data.Gameplay.Damage : source.Damage.Damage;
                    int damage = Math.Max(1, (int)MathF.Round(Math.Max(1, authored) * Math.Max(.05f, action.DamageMultiplier)));
                    string exclusion = action.Event is RuntimeEventKind.OnHit or RuntimeEventKind.OnCrit
                        ? RuntimeTooltipText("SecondaryDirectExcluded") : "";
                    if (action.ActionCode == RuntimeEventActionCode.DamageNearby)
                        add("SecondaryNearby" + suffix, "SecondaryNearby", new object[] { occurrence, delay,
                            RuntimeTooltipNumber(PlayerDisplayUnits.Blocks(action.RadiusPx)), RuntimeTooltipNumber(damage), exclusion, action.MaxTargets });
                    else
                        add("SecondaryArea" + suffix, "SecondaryArea", new object[] { occurrence, delay,
                            RuntimeTooltipNumber(PlayerDisplayUnits.Blocks(action.RadiusPx)), RuntimeTooltipNumber(damage), exclusion });
                }
                else if (action.ActionCode == RuntimeEventActionCode.SpawnEntity)
                {
                    RuntimeEntitySpec? candidate = program.TryGetEntity(action.EntityId);
                    if (candidate is null || !SecondaryChildCanSpawn(program, source, action, candidate, depth)) continue;
                    RuntimeEntitySpec child = candidate;
                    Reach(child, depth + 1);
                    string damage;
                    if (action.DamageBasis == RuntimeChildCombatBasis.LiveParent)
                        damage = RuntimeTooltipText("SecondaryLiveParentDamage", RuntimeTooltipNumber(action.DamageMultiplier));
                    else
                    {
                        int literal = child!.Damage.Enabled
                            ? Math.Max(0, (int)MathF.Round(child.Damage.Damage * action.DamageMultiplier)) : 0;
                        damage = RuntimeTooltipText("SecondaryChildDamage", RuntimeTooltipNumber(literal));
                    }
                    string details = "";
                    // Native velocity is applied on each projectile update; authored
                    // lifetime is world ticks, but extraUpdates multiplies launch speed.
                    float nominalSpeed = PlayerDisplayUnits.BlocksPerSecond(child!.Spawn.SpeedPxPerTick, child.Collision.ExtraUpdates + 1);
                    if (child.UsesInitialVelocity && child.Spawn.VelocityDistribution is null
                        && (child.Spawn.Aim != "none" || action.HitTargetSpawn is not null)
                        && RuntimeTooltipFinite(nominalSpeed, 0f, float.MaxValue))
                        details += RuntimeTooltipText("SecondaryLaunchSpeed", RuntimeTooltipNumber(nominalSpeed));
                    if (child.LifetimeTicks > 0)
                        details += RuntimeTooltipText("SecondaryChildLifetime", RuntimeTooltipTime(child.LifetimeTicks));
                    if (action.HitTargetSpawn?.InitialIgnoreCountdownUpdates > 0)
                        details += RuntimeTooltipText("SecondaryChildInitialExclusion");
                    add("SecondaryChildren" + suffix, "SecondaryChildren", new object[] {
                        occurrence, delay, RuntimeTooltipNumber(Math.Min(action.Count, program.Limits.MaxEventSpawnsPerActivation)), damage, details });
                }
            }
            // A reachable target-and-fire controller can own a later event source;
            // an unused shotEntityId in another controller is not a spawn edge.
            if (source.Controller.Code == RuntimeControllerCode.TargetAndFire && source.Targeting.IntervalTicks > 0
                && SecondaryPeriodCanOccur(source, Math.Max(6, source.Targeting.IntervalTicks))
                && depth < program.Limits.MaxChildDepth && program.Limits.MaxEventSpawnsPerActivation > 0)
            {
                RuntimeEntitySpec? shot = program.TryGetEntity(source.Targeting.ShotEntityId);
                if (shot?.IsProjectileEntity == true && shot.Spawn.Enabled) Reach(shot, depth + 1);
            }
        }
    }

    private static bool SecondaryEventIsReachable(RuntimeEntitySpec source, RuntimeEventActionSpec action, bool itemContact, bool activeUse, bool equipped)
    {
        if (action.DelayTicks is < 0 or > 600 || action.ActionCode is not (RuntimeEventActionCode.DamageArea or RuntimeEventActionCode.DamageNearby or RuntimeEventActionCode.SpawnEntity or RuntimeEventActionCode.ApplyGeneratedBuff)
            || action.Action != RuntimeOpcodeNames.EventActionName(action.ActionCode)
            || (action.Event == RuntimeEventKind.Periodic
                && (action.PeriodTicks < 6 || !SecondaryPeriodCanOccur(source, action.PeriodTicks)))) return false;
        try { RuntimeEventKind.ValidateProducer(source, action.Event, itemContact, activeUse, equipped); }
        catch (InvalidDataException) { return false; }
        return true;
    }

    private static bool SecondaryPeriodCanOccur(RuntimeEntitySpec source, int periodTicks)
    {
        if (!source.IsProjectileEntity) return true;
        // These native controllers keep the actor alive independently of its
        // authored flight lifetime. Do not invent a hard expiry for them.
        if (source.Controller.Code is RuntimeControllerCode.ChannelBeam or RuntimeControllerCode.ChargeThenRelease
            || source.Controller.Code == RuntimeControllerCode.None && source.Movement.Code == 18) return true;
        int activeTicks = source.Controller.Code == RuntimeControllerCode.None && source.Movement.Code == 19
            ? Math.Max(2, source.Movement.Params.DurationTicks) : Math.Max(1, source.LifetimeTicks);
        // Age/period and timeLeft use the same extraUpdates multiplier; waiting
        // activation updates consume neither active age nor this flight window.
        return periodTicks <= activeTicks;
    }

    private static bool SecondaryChildCanSpawn(RuntimeProgramSpec program, RuntimeEntitySpec source,
        RuntimeEventActionSpec action, RuntimeEntitySpec? child, int depth)
        => depth < program.Limits.MaxChildDepth && program.Limits.MaxEventSpawnsPerActivation > 0
            && child?.IsProjectileEntity == true && child.Spawn.Enabled
            && action.Count is > 0 and <= InfiniRuntimeLimits.MaxRuntimeSpawnCount
            && RuntimeTooltipFinite(action.DamageMultiplier, 0f, 10f)
            && action.DamageBasis is (RuntimeChildCombatBasis.AuthoredChild or RuntimeChildCombatBasis.LiveParent)
            && action.KnockbackBasis is (RuntimeChildCombatBasis.AuthoredChild or RuntimeChildCombatBasis.LiveParent)
            && (source.IsProjectileEntity || (action.DamageBasis != RuntimeChildCombatBasis.LiveParent && action.KnockbackBasis != RuntimeChildCombatBasis.LiveParent))
            && child!.Spawn.AcceptsEmissionSpread(action.SpreadRadians)
            && (action.HitTargetSpawn is null || (action.HitTargetSpawn.IsValid && action.SpreadRadians == 0f
                && action.DamageBasis is not null && action.KnockbackBasis is not null && action.DamageMultiplier <= 4f && source.IsProjectileEntity
                && action.Event is (RuntimeEventKind.OnHit or RuntimeEventKind.OnCrit) && RuntimeEventActionSpec.SupportsTargetEmission(child)));

    private static string SecondaryOccurrence(RuntimeEntitySpec source, RuntimeEventActionSpec action)
    {
        if (action.Event == RuntimeEventKind.Periodic)
            return RuntimeTooltipText(source.IsProjectileEntity ? "SecondaryProjectilePeriodic" : "SecondaryItemPeriodic", RuntimeTooltipTime(action.PeriodTicks));
        string key = action.Event switch
        {
            RuntimeEventKind.OnUse => "SecondaryUse",
            RuntimeEventKind.OnHurt => "SecondaryOwnerHurt",
            RuntimeEventKind.OnEnemyKill => "SecondaryEnemyKilled",
            RuntimeEventKind.OnHit => source.IsProjectileEntity ? "SecondaryProjectileHit" : "SecondaryItemHit",
            RuntimeEventKind.OnCrit => source.IsProjectileEntity ? "SecondaryProjectileCrit" : "SecondaryItemCrit",
            RuntimeEventKind.OnSpawn => "SecondarySpawn",
            RuntimeEventKind.OnTileCollision => "SecondaryTileCollision",
            RuntimeEventKind.OnExpire => "SecondaryExpire",
            RuntimeEventKind.OnKill => "SecondaryKill",
            RuntimeEventKind.OnRelease => "SecondaryRelease",
            RuntimeEventKind.ChannelComplete => "SecondaryChannelComplete",
            _ => "",
        };
        return RuntimeTooltipText(key);
    }
}

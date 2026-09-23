using System;
using System.Collections.Generic;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Runtime;
using InfiniCrafterLocal.Content.Items;
using Terraria.ModLoader;
using System.Reflection;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    private static void EventDamageUsesAuthoredSource()
    {
        var oldMetrics = Terraria.Main.SceneMetrics;
        NPC[] oldNpcs = (NPC[])Terraria.Main.npc.Clone();
        Player[] oldPlayers = (Player[])Terraria.Main.player.Clone();
        int oldMode = Terraria.Main.netMode;
        var oldRandom = Terraria.Main.rand;
        var failures = new List<string>();
        try
        {
            Terraria.Main.netMode = NetmodeID.SinglePlayer;
            Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(11);
            for (int i = 0; i < Terraria.Main.npc.Length; i++) Terraria.Main.npc[i] = new NPC { whoAmI = i, active = false };
            for (int i = 0; i < Terraria.Main.player.Length; i++) Terraria.Main.player[i] = new Player { whoAmI = i, active = false };
            var owner = new Player { whoAmI = 0, active = true };
            Terraria.Main.player[0] = owner;
            Terraria.Main.SceneMetrics = new SceneMetrics();
            owner.GetArmorPenetration(Terraria.ModLoader.DamageClass.Magic) += 40f;
            NPC Target(int slot, float x) => new NPC {
                whoAmI = slot, active = true, life = 1000, lifeMax = 1000,
                defense = 80, width = 20, height = 20, position = new Vector2(x, 1600f),
                HideStrikeDamage = true, // no combat-text/font resources in this CPU check
            };
            int checkedCases = 0;
            var deliveries = new[] {
                (Event: "on_hit", FinalAI: false, Life: 10, ExpectedHit: true),
                (Event: "on_crit", FinalAI: false, Life: 10, ExpectedHit: true),
                (Event: "on_expire", FinalAI: false, Life: 0, ExpectedHit: true),
                (Event: "on_expire", FinalAI: false, Life: 1, ExpectedHit: true),
                (Event: "on_expire", FinalAI: false, Life: 10, ExpectedHit: false),
                (Event: "on_expire", FinalAI: true, Life: 0, ExpectedHit: true),
                (Event: "on_kill", FinalAI: false, Life: 0, ExpectedHit: true),
                (Event: "on_kill", FinalAI: false, Life: 10, ExpectedHit: true),
                (Event: "on_kill", FinalAI: true, Life: 0, ExpectedHit: true),
                (Event: "terminal_pair", FinalAI: false, Life: 0, ExpectedHit: true),
                (Event: "terminal_pair", FinalAI: false, Life: 1, ExpectedHit: true),
                (Event: "terminal_pair", FinalAI: false, Life: 10, ExpectedHit: false),
                (Event: "terminal_pair", FinalAI: true, Life: 0, ExpectedHit: true),
            };
            foreach (bool itemBody in new[] { false, true })
            foreach (bool chain in new[] { false, true })
            foreach (int delay in new[] { 0, 2 })
            foreach (var delivery in deliveries)
            foreach (int killDelay in new[] { -1, 0, 2, 4 })
            {
                bool pair = delivery.Event == "terminal_pair";
                if ((pair && killDelay < 0) || (!pair && killDelay >= 0)) continue;
                bool terminal = pair || delivery.Event is "on_expire" or "on_kill";
                // The registry only permits these terminal damage events on projectile AoE.
                if (terminal && (itemBody || chain)) continue;
                bool crit = delivery.Event == "on_crit";
                string label = $"{(itemBody ? "item" : "projectile")} {(chain ? "chain" : "area")} delay={delay} event={delivery.Event} finalAI={delivery.FinalAI} life={delivery.Life} killDelay={killDelay}";
                RuntimeDelayedActionScheduler.Clear();
                try
                {
                    NPC direct = Terraria.Main.npc[0] = Target(0, 1600f);
                    NPC nearby = Terraria.Main.npc[1] = Target(1, 1640f);
                    NPC outside = Terraria.Main.npc[2] = Target(2, 2400f);
                    Equal(true, nearby.CanBeChasedBy(), "fixture is eligible");
                    NPC control = Target(3, 2600f);
                    // Observe real Terraria defense + class-specific armor penetration,
                    // not a reimplementation of its damage formula.
                    owner.ApplyDamageToNPC(control, 50, 0f, 1, false, Terraria.ModLoader.DamageClass.Magic, false);
                    Equal(true, control.life < 1000, "real control damage was applied");
                    var data = GeneratedItemData.Placeholder();
                    data.Gameplay.Damage = itemBody ? 100 : 20;
                    data.Gameplay.DamageClass = itemBody ? "magic" : "melee";
                    var action = new RuntimeEventActionSpec {
                        Id = "event_damage_probe", Event = pair ? "on_expire" : delivery.Event, DelayTicks = delay,
                        Action = chain ? "chain_damage_on_event" : "damage_area_on_event",
                        ActionCode = chain ? RuntimeEventActionCode.ChainDamage : RuntimeEventActionCode.DamageArea,
                        DamageMultiplier = 0.5f, RadiusPx = 120, RangeTiles = 8f, Count = 1,
                    };
                    action.NormalizeAndValidate();
                    var entity = itemBody ? new RuntimeEntitySpec() : Entity();
                    entity.Id = "damage_source";
                    entity.Kind = itemBody ? RuntimeEntityKind.ItemBody : RuntimeEntityKind.FreeProjectile;
                    if (!itemBody) entity.Damage.DamageClass = "magic";
                    entity.Events = new[] { action };
                    if (pair)
                    {
                        var killAction = new RuntimeEventActionSpec {
                            Id = "kill_damage_probe", Event = "on_kill", DelayTicks = killDelay,
                            Action = "damage_area_on_event", ActionCode = RuntimeEventActionCode.DamageArea,
                            DamageMultiplier = 0.75f, RadiusPx = 120,
                        };
                        killAction.NormalizeAndValidate();
                        entity.Events = new[] { action, killAction };
                    }
                    // Live damage/damageDone are deliberately different from authored 100.
                    var projectile = new Projectile { owner = 0, active = true, damage = 777 };
                    if (itemBody)
                    {
                        data.RuntimeProgram.ItemEntityId = entity.Id;
                        data.RuntimeProgram.Entities = new[] { entity };
                        data.RuntimeProgram.Bindings = new[] { new RuntimeBindingSpec {
                            Id = "contact", Input = RuntimeInputKind.PrimaryUse,
                            UsePolicy = new RuntimeBindingUsePolicySpec {
                                ContactDamage = true,
                                Action = new RuntimeBindingActionSpec { Kind = RuntimeBindingAction.UseItemBody, TargetId = entity.Id },
                            },
                        } };
                        var generatedItem = new GeneratedItem();
                        typeof(ModType<Item>).GetProperty("Entity", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)!
                            .SetValue(generatedItem, new Item { damage = 777 });
                        typeof(GeneratedItem).GetProperty("Data")!.SetValue(generatedItem, data);
                        generatedItem.OnHitNPC(owner, direct, new NPC.HitInfo { Crit = crit }, 333);
                    }
                    else
                    {
                        var generated = Attach(projectile);
                        generated.Configure(data, entity, 0, 8, Vector2.UnitX);
                        projectile.Center = direct.Center;
                        if (terminal)
                        {
                            if (delivery.FinalAI)
                            {
                                projectile.timeLeft = 2;
                                generated.AI();
                                Equal(1000, nearby.life, label + " no damage before final AI");
                                Equal(0, PendingActions(), label + " no early reservation");
                                projectile.timeLeft = 1;
                                generated.AI();
                                if (pair)
                                {
                                    Equal(delay == 0 ? control.life : 1000, nearby.life, label + " final AI runs only expiry, before OnKill");
                                    Equal(delay == 0 ? control.life : 1000, direct.life, label + " final AI center target");
                                    Equal(delay > 0 ? 1 : 0, PendingActions(), label + " final AI reserves only expiry");
                                }
                            }
                            projectile.active = false;
                            generated.OnKill(delivery.Life);
                        }
                        else
                            generated.OnHitNPC(direct, new NPC.HitInfo { Crit = crit }, 333);
                    }
                    if (pair)
                    {
                        // Distinct multipliers make a lost kill/duplicated expiry observable.
                        // Build each expected transition with the actual Terraria damage API.
                        control.life = 1000;
                        void CheckPairTick(int tick)
                        {
                            if (delivery.ExpectedHit && delay == tick)
                                owner.ApplyDamageToNPC(control, 50, 0f, 1, false, DamageClass.Magic, false);
                            if (killDelay == tick)
                                owner.ApplyDamageToNPC(control, 75, 0f, 1, false, DamageClass.Magic, false);
                            Equal(control.life, nearby.life, label + " independent events tick=" + tick);
                            Equal(control.life, direct.life, label + " center receives both events tick=" + tick);
                            Equal(1000, outside.life, label + " captured center excludes distant target");
                            int pending = (delivery.ExpectedHit && delay > tick ? 1 : 0) + (killDelay > tick ? 1 : 0);
                            Equal(pending, PendingActions(), label + " exact remaining actions tick=" + tick);
                        }
                        CheckPairTick(0);
                        projectile.Center = outside.Center;
                        projectile.damage = 1;
                        for (int tick = 1; tick <= Math.Max(delay, killDelay) + 1; tick++)
                        {
                            RuntimeDelayedActionScheduler.Update();
                            CheckPairTick(tick);
                        }
                        checkedCases++;
                        continue;
                    }
                    if (delay > 0)
                    {
                        Equal(1000, nearby.life, label + " not immediate");
                        projectile.active = false; // delayed action outlives its projectile
                        projectile.damage = 1;
                        projectile.Center = outside.Center; // queued position must not follow the retired host
                        RuntimeDelayedActionScheduler.Update();
                        Equal(1000, nearby.life, label + " not early");
                        RuntimeDelayedActionScheduler.Update();
                    }
                    int expectedLife = delivery.ExpectedHit ? control.life : 1000;
                    Equal(expectedLife, nearby.life, label + " authored damage exactly once, or no premature expiry");
                    Equal(terminal ? expectedLife : 1000, direct.life, label + " terminal AoE has no excluded hit target");
                    Equal(1000, outside.life, label + " excludes out-of-range target");
                    RuntimeDelayedActionScheduler.Update();
                    Equal(expectedLife, nearby.life, label + " no delayed replay");
                    Equal(0, PendingActions(), label + " queue fully retired");
                    checkedCases++;
                }
                catch (Exception error) { failures.Add(label + ": " + error); }
            }
            Console.WriteLine($"DETAIL: event damage scenarios passed={checkedCases}");
        }
        finally
        {
            RuntimeDelayedActionScheduler.Clear();
            Array.Copy(oldNpcs, Terraria.Main.npc, oldNpcs.Length);
            Array.Copy(oldPlayers, Terraria.Main.player, oldPlayers.Length);
            Terraria.Main.netMode = oldMode;
            Terraria.Main.rand = oldRandom;
            Terraria.Main.SceneMetrics = oldMetrics;
        }
        if (failures.Count > 0) throw new InvalidOperationException(string.Join(Environment.NewLine, failures));
    }

    private static void DelayedStatusKeepsOriginalNpc()
    {
        NPC[] oldNpcs = (NPC[])Terraria.Main.npc.Clone();
        Player[] oldPlayers = (Player[])Terraria.Main.player.Clone();
        int oldMode = Terraria.Main.netMode;
        bool oldGoodWorld = Terraria.Main.getGoodWorld;
        var oldRandom = Terraria.Main.rand;
        var failures = new List<string>();
        try
        {
            Terraria.Main.netMode = NetmodeID.SinglePlayer;
            Terraria.Main.getGoodWorld = false;
            Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(11);
            for (int i = 0; i < Terraria.Main.npc.Length; i++) Terraria.Main.npc[i] = new NPC { whoAmI = i, active = false };
            for (int i = 0; i < Terraria.Main.player.Length; i++) Terraria.Main.player[i] = new Player { whoAmI = i, active = false };
            var owner = new Player { whoAmI = 0, active = true };
            Terraria.Main.player[0] = owner;
            foreach (string state in new[] { "same", "transform", "inactive", "new_same_type", "new_other_type", "absent" })
            {
                RuntimeDelayedActionScheduler.Clear();
                try
                {
                    Terraria.Main.npc[0].active = false;
                    int slot = NPC.NewNPC(owner.GetSource_Misc("engine_delayed_npc_check"), 1600, 1600, NPCID.BlueSlime);
                    Equal(0, slot, state + " original NPC occupies slot zero");
                    NPC original = Terraria.Main.npc[slot];
                    Equal(false, original.buffImmune[BuffID.OnFire], "real slime allows selected status");
                    var action = new RuntimeEventActionSpec {
                        Id = "delayed_status_probe", Event = "on_hit", DelayTicks = 2,
                        Action = "apply_status_on_event", ActionCode = RuntimeEventActionCode.ApplyStatus,
                        BuffId = BuffID.OnFire, DurationTicks = 90,
                    };
                    action.NormalizeAndValidate();
                    int budget = 8;
                    Equal(true, RuntimeDelayedActionScheduler.TrySchedule(GeneratedItemData.Placeholder(), new RuntimeEntitySpec { Kind = RuntimeEntityKind.ItemBody }, action,
                        owner, original.Center, Vector2.UnitX, state == "absent" ? null : original, 10, 0, ref budget), state + " queued");
                    RuntimeDelayedActionScheduler.Update();
                    Equal(false, original.HasBuff(BuffID.OnFire), state + " not early");
                    bool sameEntity = state is "same" or "transform";
                    if (!sameEntity && state != "absent") original.active = false;
                    if (state == "transform")
                    {
                        original.Transform(NPCID.Zombie);
                        Equal(true, ReferenceEquals(original, Terraria.Main.npc[slot]), "real Transform preserves NPC instance");
                        Equal(NPCID.Zombie, original.type, "real Transform changes type");
                        Equal(slot, original.whoAmI, "real Transform retains slot");
                        Equal(true, original.active, "transformed target remains active");
                        Equal(false, original.buffImmune[BuffID.OnFire], "transformed target permits status");
                    }
                    if (state.StartsWith("new_", StringComparison.Ordinal))
                    {
                        int type = state == "new_same_type" ? NPCID.BlueSlime : NPCID.Zombie;
                        int replacementSlot = NPC.NewNPC(owner.GetSource_Misc("engine_delayed_npc_reuse"), 1600, 1600, type);
                        Equal(slot, replacementSlot, state + " real NewNPC reuses the slot");
                        Equal(false, ReferenceEquals(original, Terraria.Main.npc[slot]), state + " real NewNPC replaces the instance");
                        Equal(type, Terraria.Main.npc[slot].type, state + " actual replacement type");
                    }
                    RuntimeDelayedActionScheduler.Update();
                    Equal(sameEntity, Terraria.Main.npc[slot].HasBuff(BuffID.OnFire), state + " only original hit target gets status");
                    if (sameEntity)
                    {
                        int index = original.FindBuffIndex(BuffID.OnFire);
                        Equal(90, original.buffTime[index], "authored duration reaches real NPC.AddBuff");
                        original.buffTime[index] = 17;
                        RuntimeDelayedActionScheduler.Update();
                        Equal(17, original.buffTime[index], "retired delayed status does not refresh again");
                    }
                }
                catch (Exception error) { failures.Add(state + ": " + error); }
            }
        }
        finally
        {
            RuntimeDelayedActionScheduler.Clear();
            Array.Copy(oldNpcs, Terraria.Main.npc, oldNpcs.Length);
            Array.Copy(oldPlayers, Terraria.Main.player, oldPlayers.Length);
            Terraria.Main.netMode = oldMode;
            Terraria.Main.getGoodWorld = oldGoodWorld;
            Terraria.Main.rand = oldRandom;
        }
        if (failures.Count > 0) throw new InvalidOperationException(string.Join(Environment.NewLine, failures));
    }

    private static void DelayedQueueHonorsLimits()
    {
        var oldOwner = Terraria.Main.player[0];
        var oldTarget = Terraria.Main.npc[0];
        int oldMode = Terraria.Main.netMode;
        try
        {
            RuntimeDelayedActionScheduler.Clear();
            Terraria.Main.netMode = NetmodeID.SinglePlayer;
            var owner = new Player { whoAmI = 0, active = true };
            owner.Center = Vector2.Zero;
            Terraria.Main.player[0] = owner;
            var target = new NPC { whoAmI = 0, active = true, knockBackResist = 1f };
            target.Center = new Vector2(32f, 0f);
            Terraria.Main.npc[0] = target;
            var data = GeneratedItemData.Placeholder();
            var pull = new RuntimeEventActionSpec {
                Id = "queue_budget_probe", Event = "on_hit", DelayTicks = 2,
                Action = "pull_on_event", ActionCode = RuntimeEventActionCode.Pull,
                Mode = "target_to_owner", Strength = 2f, RadiusTiles = 10f,
            };
            pull.NormalizeAndValidate();
            int budget = 5;
            int capacity = InfiniCrafterLocal.Common.InfiniRuntimeLimits.MaxPendingRuntimeActions;
            int perTick = InfiniCrafterLocal.Common.InfiniRuntimeLimits.MaxRuntimeDelayedActionsPerTick;
            for (int i = 0; i < capacity; i++)
                Equal(true, RuntimeDelayedActionScheduler.TrySchedule(data, new RuntimeEntitySpec { Kind = RuntimeEntityKind.ItemBody }, pull, owner, Vector2.Zero, Vector2.UnitX,
                    target, 0, 0, ref budget), "queue accepts entry " + i);
            Equal(false, RuntimeDelayedActionScheduler.TrySchedule(data, new RuntimeEntitySpec { Kind = RuntimeEntityKind.ItemBody }, pull, owner, Vector2.Zero, Vector2.UnitX,
                target, 0, 0, ref budget), "full queue rejects overflow");
            var spawn = new RuntimeEventActionSpec { DelayTicks = 2, ActionCode = RuntimeEventActionCode.SpawnEntity, Count = 3 };
            // Reservation-only probe. Do not dispatch this synthetic spawn or claim entity-spawn proof.
            Equal(false, RuntimeDelayedActionScheduler.TrySchedule(data, new RuntimeEntitySpec { Kind = RuntimeEntityKind.ItemBody }, spawn, owner, Vector2.Zero, Vector2.UnitX,
                null, 0, 0, ref budget), "full queue rejects spawn before reserving budget");
            Equal(5, budget, "rejection and non-spawn actions leave budget unchanged");
            RuntimeDelayedActionScheduler.Update();
            Equal(Vector2.Zero, target.velocity, "no early queue execution");
            int executed = 0;
            while (executed < capacity)
            {
                RuntimeDelayedActionScheduler.Update();
                executed = Math.Min(capacity, executed + perTick);
                Equal(new Vector2(-2f * executed, 0f), target.velocity, "real executor effects respect per-tick limit");
            }
            RuntimeDelayedActionScheduler.Update();
            Equal(new Vector2(-2f * capacity, 0f), target.velocity, "all accepted actions execute exactly once");
            Equal(true, RuntimeDelayedActionScheduler.TrySchedule(data, new RuntimeEntitySpec { Kind = RuntimeEntityKind.ItemBody }, spawn, owner, Vector2.Zero, Vector2.UnitX,
                null, 0, 0, ref budget), "drained queue accepts reservation");
            Equal(2, budget, "first reservation consumes exact requested count");
            Equal(true, RuntimeDelayedActionScheduler.TrySchedule(data, new RuntimeEntitySpec { Kind = RuntimeEntityKind.ItemBody }, spawn, owner, Vector2.Zero, Vector2.UnitX,
                null, 0, 0, ref budget), "last partial budget can be reserved");
            Equal(0, budget, "second reservation cannot overdraw budget");
            Equal(false, RuntimeDelayedActionScheduler.TrySchedule(data, new RuntimeEntitySpec { Kind = RuntimeEntityKind.ItemBody }, spawn, owner, Vector2.Zero, Vector2.UnitX,
                null, 0, 0, ref budget), "zero spawn budget rejects reservation");
            new RuntimeDelayedActionSystem().OnWorldUnload();
            // If unload left the reserved entries, the following full-capacity fill would fail.
            for (int i = 0; i < capacity; i++)
                Equal(true, RuntimeDelayedActionScheduler.TrySchedule(data, new RuntimeEntitySpec { Kind = RuntimeEntityKind.ItemBody }, pull, owner, Vector2.Zero, Vector2.UnitX,
                    target, 0, 0, ref budget), "unload restores full queue capacity");
        }
        finally
        {
            RuntimeDelayedActionScheduler.Clear();
            Terraria.Main.player[0] = oldOwner;
            Terraria.Main.npc[0] = oldTarget;
            Terraria.Main.netMode = oldMode;
        }
    }

    private static void DelayedActionsKeepOriginalOwner()
    {
        var oldOwner = Terraria.Main.player[0];
        var oldTarget = Terraria.Main.npc[0];
        var oldBuffer = NetMessage.buffer[0];
        int oldMode = Terraria.Main.netMode;
        var failures = new List<string>();
        try
        {
            Terraria.Main.netMode = NetmodeID.Server;
            // Reset a socket-free RemoteClient using the actual installed tML method.
            NetMessage.buffer[0] = new MessageBuffer();
            foreach (string state in new[] { "same", "inactive", "reset", "world_unload", "mod_unload" })
            {
                RuntimeDelayedActionScheduler.Clear();
                string label = "delayed owner " + state;
                try
                {
                    var owner = new Player { whoAmI = 0, active = true };
                    owner.Center = Vector2.Zero;
                    Terraria.Main.player[0] = owner;
                    var target = new NPC { whoAmI = 0, active = true, knockBackResist = 1f };
                    target.Center = new Vector2(32f, 0f);
                    Terraria.Main.npc[0] = target;
                    var action = new RuntimeEventActionSpec {
                        Id = "delayed_owner_probe", Event = "on_hit", DelayTicks = 2,
                        Action = "pull_on_event", ActionCode = RuntimeEventActionCode.Pull,
                        Mode = "target_to_owner", Strength = 2f, RadiusTiles = 10f,
                    };
                    action.NormalizeAndValidate();
                    int budget = 8;
                    Equal(true, RuntimeDelayedActionScheduler.TrySchedule(GeneratedItemData.Placeholder(), new RuntimeEntitySpec { Kind = RuntimeEntityKind.ItemBody }, action,
                        owner, Vector2.Zero, Vector2.UnitX, target, 0, 0, ref budget), label + " queued");
                    Equal(8, budget, label + " non-spawn action preserves budget");
                    RuntimeDelayedActionScheduler.Update();
                    Equal(Vector2.Zero, target.velocity, label + " not before authored tick");
                    if (state == "inactive") owner.active = false;
                    if (state == "reset")
                    {
                        var client = new RemoteClient { Id = 0, IsActive = true, State = 10 };
                        client.Reset();
                        Equal(false, ReferenceEquals(owner, Terraria.Main.player[0]), "actual RemoteClient.Reset replaces Player");
                        Equal(false, client.IsActive, "actual client reset completed");
                        // Model the next connection occupying exactly the vacated slot.
                        var newcomer = Terraria.Main.player[0];
                        newcomer.active = true;
                        newcomer.whoAmI = 0;
                        newcomer.Center = new Vector2(96f, 0f);
                    }
                    if (state == "world_unload") new RuntimeDelayedActionSystem().OnWorldUnload();
                    if (state == "mod_unload") new RuntimeDelayedActionSystem().Unload();
                    RuntimeDelayedActionScheduler.Update();
                    Vector2 expected = state == "same" ? new Vector2(-2f, 0f) : Vector2.Zero;
                    Equal(expected, target.velocity, label + " effect belongs only to original owner");
                    Equal(Vector2.Zero, owner.velocity, label + " no player impulse in NPC mode");
                    // Reviving the original owner must not re-execute a retired entry.
                    owner.active = true;
                    Terraria.Main.player[0] = owner;
                    RuntimeDelayedActionScheduler.Update();
                    Equal(expected, target.velocity, label + " executes once or is permanently retired");
                }
                catch (Exception error) { failures.Add(label + ": " + error.Message); }
            }
        }
        finally
        {
            RuntimeDelayedActionScheduler.Clear();
            Terraria.Main.player[0] = oldOwner;
            Terraria.Main.npc[0] = oldTarget;
            NetMessage.buffer[0] = oldBuffer;
            Terraria.Main.netMode = oldMode;
        }
        if (failures.Count > 0) throw new InvalidOperationException(string.Join(Environment.NewLine, failures));
    }

    private static void PullModesPreserveSubjectAndAuthority()
    {
        NPC[] previous = (NPC[])Terraria.Main.npc.Clone();
        int oldMode = Terraria.Main.netMode, oldLocal = Terraria.Main.myPlayer;
        var failures = new List<string>();
        try
        {
            for (int i = 0; i < Terraria.Main.npc.Length; i++)
                Terraria.Main.npc[i] = new NPC { whoAmI = i, active = false };
            var target = new NPC { whoAmI = 0, type = NPCID.BlueSlime, active = true, life = 100, lifeMax = 100,
                width = 16, height = 16, knockBackResist = 1f, friendly = false, dontTakeDamage = false };
            var nearby = new NPC { whoAmI = 1, type = NPCID.BlueSlime, active = true, life = 100, lifeMax = 100,
                width = 16, height = 16, knockBackResist = 1f, friendly = false, dontTakeDamage = false };
            target.Center = new Vector2(32f, 0f);
            nearby.Center = new Vector2(96f, 0f);
            Terraria.Main.npc[0] = target;
            Terraria.Main.npc[1] = nearby;
            Equal(true, nearby.CanBeChasedBy(), "real NPC is eligible for area-pull control");
            foreach (string mode in new[] { "owner_to_target", "target_to_owner", "target_to_entity" })
            foreach (int netMode in new[] { NetmodeID.SinglePlayer, NetmodeID.Server, NetmodeID.MultiplayerClient })
            foreach (bool local in new[] { true, false })
            foreach (bool ownerActive in new[] { true, false })
            foreach (string targetState in new[] { "active", "inactive", "absent" })
            {
                string label = $"{mode}, netMode={netMode}, local={local}, ownerActive={ownerActive}, target={targetState}";
                try
                {
                    Terraria.Main.netMode = netMode;
                    Terraria.Main.myPlayer = local ? 0 : 1;
                    var owner = new Player { whoAmI = 0, active = ownerActive, velocity = Vector2.Zero };
                    owner.Center = Vector2.Zero;
                    target.active = targetState != "inactive";
                    target.velocity = nearby.velocity = Vector2.Zero;
                    NPC? direct = targetState == "absent" ? null : target;
                    var action = new RuntimeEventActionSpec {
                        Id = "pull_probe", Event = "periodic", PeriodTicks = 6,
                        Action = "pull_on_event", ActionCode = RuntimeEventActionCode.Pull,
                        Mode = mode, Strength = 2f, RadiusTiles = 10f,
                    };
                    action.NormalizeAndValidate();
                    int budget = 8;
                    RuntimeProgramExecutor.ExecuteAction(GeneratedItemData.Placeholder(), new RuntimeEntitySpec { Kind = RuntimeEntityKind.ItemBody }, action, owner,
                        owner.GetSource_Misc("engine_pull_check"), new Vector2(64f, 0f), Vector2.UnitX,
                        direct, 0, 0, ref budget);
                    bool ownerAuthority = ownerActive && (netMode == NetmodeID.SinglePlayer || netMode == NetmodeID.MultiplayerClient && local);
                    bool npcAuthority = netMode != NetmodeID.MultiplayerClient;
                    if (mode == "owner_to_target")
                    {
                        Equal(ownerAuthority && targetState == "active" ? new Vector2(2f, 0f) : Vector2.Zero,
                            owner.velocity, label + " owner impulse");
                        Equal(Vector2.Zero, target.velocity, label + " must never move target");
                        Equal(Vector2.Zero, nearby.velocity, label + " must never fall through to area pull");
                    }
                    else
                    {
                        Equal(Vector2.Zero, owner.velocity, label + " NPC mode must never move owner");
                        Vector2 expectedTarget = !npcAuthority || !target.active ? Vector2.Zero
                            : mode == "target_to_owner" ? new Vector2(-2f, 0f) : new Vector2(2f, 0f);
                        Equal(expectedTarget, target.velocity, label + " NPC mode direct/area target");
                        Equal(npcAuthority && targetState != "active" ? new Vector2(-2f, 0f) : Vector2.Zero,
                            nearby.velocity, label + " NPC mode area control");
                    }
                    Equal(8, budget, label + " does not consume spawn budget");
                }
                catch (Exception error) { failures.Add(error.Message); }
            }
        }
        finally
        {
            Array.Copy(previous, Terraria.Main.npc, previous.Length);
            Terraria.Main.netMode = oldMode;
            Terraria.Main.myPlayer = oldLocal;
        }
        if (failures.Count > 0) throw new InvalidOperationException(string.Join(Environment.NewLine, failures));
    }
}

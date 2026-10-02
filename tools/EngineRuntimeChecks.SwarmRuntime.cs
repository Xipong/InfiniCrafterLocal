using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using MonoMod.Cil;
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Runtime;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Common.VFX;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ID;
using InfiniMod = InfiniCrafterLocal.InfiniCrafterLocalMod;

internal static partial class EngineRuntimeChecks
{
    // Only actor arrays, role and the actual Terraria world clock are isolated.
    // No fake projectile spawn, world loop, socket or graphics result is returned.
    private sealed class SwarmRuntimeScope : IDisposable
    {
        private readonly Player[] players = Terraria.Main.player;
        private readonly NPC[] npcs = Terraria.Main.npc;
        private readonly Projectile[] projectiles = Terraria.Main.projectile;
        private readonly int mode = Terraria.Main.netMode, local = Terraria.Main.myPlayer;
        private readonly bool dedicated = Terraria.Main.dedServ;
        private readonly uint tick = Terraria.Main.GameUpdateCount;
        internal SwarmRuntimeScope(int netMode = NetmodeID.SinglePlayer, int myPlayer = 0, bool visuals = false)
        {
            RuntimeDelayedActionScheduler.Clear();
            new InfiniDetachedVfxSystem().OnWorldUnload();
            Terraria.Main.player = Enumerable.Range(0, Terraria.Main.maxPlayers).Select(i => new Player { whoAmI = i, active = i < 2, direction = 1 }).ToArray();
            Terraria.Main.npc = Enumerable.Range(0, Terraria.Main.maxNPCs).Select(i => new NPC { whoAmI = i }).ToArray();
            Terraria.Main.projectile = Enumerable.Range(0, Terraria.Main.maxProjectiles).Select(i => new Projectile { whoAmI = i }).ToArray();
            Terraria.Main.netMode = netMode; Terraria.Main.myPlayer = myPlayer; Terraria.Main.dedServ = !visuals;
        }
        public void Dispose()
        {
            RuntimeDelayedActionScheduler.Clear(); new InfiniDetachedVfxSystem().OnWorldUnload();
            Terraria.Main.player = players; Terraria.Main.npc = npcs; Terraria.Main.projectile = projectiles;
            Terraria.Main.netMode = mode; Terraria.Main.myPlayer = local; Terraria.Main.dedServ = dedicated;
            MaterialClock(tick);
        }
    }

    private static readonly (string Name, int Mode, int Local)[] SwarmRoles = {
        ("SP", NetmodeID.SinglePlayer, 0), ("owner-client", NetmodeID.MultiplayerClient, 0),
        ("remote-client", NetmodeID.MultiplayerClient, 1), ("server", NetmodeID.Server, 255),
    };
    private static GeneratedItemData SwarmGameplayFixture()
    {
        var data = RootSpawnFixture(8, 1);
        var entity = data.RuntimeProgram.TryGetEntity("root")!;
        entity.Kind = RuntimeEntityKind.FreeProjectile;
        entity.Visual.Role = entity.VisualRole = "projectile";
        entity.LifetimeTicks = 90;
        entity.Damage.Enabled = true; entity.Damage.Damage = 100; entity.Damage.DamageClass = "generic"; entity.Damage.Knockback = 3;
        entity.Spawn.SpeedPxPerTick = 4;
        entity.Movement.Name = "move_straight"; entity.Movement.Code = 0;
        data.RuntimeProgram.ItemUse.Channel = true;
        data.RuntimeProgram.Bindings = data.RuntimeProgram.Bindings.Where(b => b.Input == RuntimeInputKind.PrimaryUse).ToArray();
        return data;
    }
    private static GeneratedItemData SwarmWire(GeneratedItemData data)
        => GeneratedItemData.FromJson(data.ToNetworkJson()) ?? throw new InvalidOperationException("strict swarm runtime fixture rejected");
    private static GeneratedProjectile SwarmHost(GeneratedItemData data, RuntimeEntitySpec entity, int slot = 0, int owner = 0, int damage = 100, float knockback = 3)
    {
        var projectile = Terraria.Main.projectile[slot] = new Projectile {
            whoAmI = slot, owner = owner, active = true, identity = slot + 70,
            width = 12, height = 12, scale = 1, velocity = Vector2.UnitX, damage = damage, knockBack = knockback, timeLeft = 90,
        };
        var generated = Attach(projectile);
        typeof(Projectile).GetProperty("ModProjectile")!.SetValue(projectile, generated);
        generated.Configure(data, entity, 0, 8, Vector2.UnitX, activationBudget: new RuntimeSpawnBudget(8));
        return generated;
    }

    private static void SwarmChargeKeepsCombatBasisOnce()
    {
        int cases = 0;
        foreach (var role in SwarmRoles)
        foreach (int basis in new[] { 0, 25, 100, 200 })
        foreach (float power in new[] { 1f, 2f })
        foreach (int chargeDuration in new[] { 1, 4 })
        foreach (bool liveCombatChange in new[] { false, true })
        {
            using var scope = new SwarmRuntimeScope(role.Mode, role.Local);
            var data = SwarmGameplayFixture(); var entity = data.RuntimeProgram.TryGetEntity("root")!;
            entity.Controller.Name = "charge_then_release"; entity.Controller.Code = RuntimeControllerCode.ChargeThenRelease;
            entity.Controller.Params.ChargeTicks = chargeDuration; entity.Controller.Params.PowerMultiplier = power;
            data = SwarmWire(data); entity = data.RuntimeProgram.TryGetEntity("root")!;
            string label = $"charge role={role.Name} spawnBasis={basis} power={power} chargeTicks={chargeDuration} liveCombatChange={liveCombatChange}";
            var generated = SwarmHost(data, entity, damage: basis, knockback: 7);
            Equal(basis, generated.Projectile.originalDamage, label + " exact spawn basis");
            // Explicit live combat inputs, not a claim of running Terraria's
            // damage-modifier pipeline: originalDamage must not replace them.
            int combatDamage = liveCombatChange ? basis / 2 : basis;
            float combatKnockback = liveCombatChange ? 11 : 7;
            generated.Projectile.damage = combatDamage;
            generated.Projectile.knockBack = combatKnockback;
            generated.Configure(data, entity, 0, 8, Vector2.UnitX, preserveSyncedState: true);
            Equal(combatDamage, generated.Projectile.damage, label + " hydration preserves live damage before release");
            Equal(combatKnockback, generated.Projectile.knockBack, label + " hydration preserves live knockback before release");
            Terraria.Main.player[0].channel = false;
            generated.AI();
            float multiplier = 1 + (power - 1) / chargeDuration;
            int expected = (int)MathF.Round(combatDamage * multiplier);
            Equal(expected, generated.Projectile.damage, label + " release scales actual combat damage, including zero");
            Equal(combatKnockback * multiplier, generated.Projectile.knockBack, label + " release scales actual combat knockback");
            Equal(basis, generated.Projectile.originalDamage, label + " original damage remains pre-release basis");
            for (int repeat = 0; repeat < 3; repeat++) {
                generated.Configure(data, entity, 0, 8, Vector2.UnitX, preserveSyncedState: true);
                generated.AI();
                Equal(expected, generated.Projectile.damage, label + " released AI/rehydration never compounds");
                Equal(combatKnockback * multiplier, generated.Projectile.knockBack, label + " released knockback never compounds");
            }
            cases++;
        }
        Console.WriteLine($"DETAIL: swarm charge basis named variants={cases} zero/fractional/unit/doubled spawn; unchanged/modified live combat inputs; partial/full release; four method roles");
    }

    // Existing fixtures counted scheduler visits as ticks. Keep their exact
    // effect/refund assertions, but advance the installed world clock explicitly.
    private sealed class RuntimeWorldClockScope : IDisposable
    {
        private readonly uint tick = Terraria.Main.GameUpdateCount;
        public void Dispose() => MaterialClock(tick);
    }
    private static void AdvanceRuntimeWorldTick()
    {
        MaterialClock(unchecked(Terraria.Main.GameUpdateCount + 1));
        RuntimeDelayedActionScheduler.Update();
    }

    private static void SwarmDelayedHooksHonorWorldClock()
    {
        int cases = 0;
        foreach (var role in SwarmRoles)
        foreach (int delay in new[] { 0, 1, 2, 600 })
        foreach (int extraUpdates in new[] { 0, 2 })
        foreach (uint origin in new[] { 1000u, 1001u, uint.MaxValue - 1 })
        {
            using var scope = new SwarmRuntimeScope(role.Mode, role.Local);
            var data = SwarmGameplayFixture(); var entity = data.RuntimeProgram.TryGetEntity("root")!;
            entity.Collision.ExtraUpdates = extraUpdates;
            entity.Events = new[] { new RuntimeEventActionSpec {
                Id = "world_clock_pull", Event = "on_hit", Action = "pull_on_event", ActionCode = RuntimeEventActionCode.Pull,
                Mode = "owner_to_target", Strength = 2, RadiusTiles = 4, DelayTicks = delay,
            } };
            data = SwarmWire(data); entity = data.RuntimeProgram.TryGetEntity("root")!;
            var owner = Terraria.Main.player[0]; owner.Center = Vector2.Zero;
            var target = Terraria.Main.npc[0]; target.active = true; target.Center = new Vector2(100, 0);
            var generated = SwarmHost(data, entity);
            bool authorized = role.Name is "SP" or "owner-client";
            string label = $"delay role={role.Name} ticks={delay} extraUpdates={extraUpdates} origin={origin}";
            MaterialClock(origin); generated.OnHitNPC(target, new NPC.HitInfo(), 10);
            Equal(authorized && delay > 0 ? 1 : 0, PendingActions(), label + " canonical eligibility before enqueue");
            if (authorized && delay > 0) {
                var entry = ((IList)typeof(RuntimeDelayedActionScheduler).GetField("Pending", BindingFlags.NonPublic | BindingFlags.Static)!.GetValue(null)!)[0]!;
                Equal(origin, (uint)entry.GetType().GetProperty("EnqueuedTick")!.GetValue(entry)!, label + " exact world-clock origin stored");
                Equal(unchecked(origin + (uint)delay), (uint)entry.GetType().GetProperty("DueTick")!.GetValue(entry)!, label + " exact authored due stored, including wrap");
            }
            Equal(authorized && delay == 0 ? 2f : 0f, owner.velocity.X, label + " immediate hook");
            var system = new RuntimeDelayedActionSystem();
            // A late callback in this exact update and repeated visits cannot
            // consume an authored world-tick delay (including extraUpdates).
            for (int repeat = 0; repeat < 4; repeat++) system.PostUpdateEverything();
            Equal(authorized && delay == 0 ? 2f : 0f, owner.velocity.X, label + " same-count callbacks do not dispatch");
            Equal(authorized && delay > 0 ? 1 : 0, PendingActions(), label + " same-count callbacks keep reservation");
            if (delay > 1) {
                MaterialClock(unchecked(origin + (uint)delay - 1)); system.PostUpdateEverything();
                Equal(0f, owner.velocity.X, label + " not one world tick early");
                Equal(authorized ? 1 : 0, PendingActions(), label + " retains until exact due count");
            }
            MaterialClock(unchecked(origin + (uint)Math.Max(1, delay))); system.PostUpdateEverything();
            Equal(authorized ? 2f : 0f, owner.velocity.X, label + " exact authored due count including wrap");
            Equal(0, PendingActions(), label + " retired on due count");
            for (int repeat = 0; repeat < 3; repeat++) system.PostUpdateEverything();
            AdvanceRuntimeWorldTick();
            Equal(authorized ? 2f : 0f, owner.velocity.X, label + " no replay"); cases++;
        }
        Console.WriteLine($"DETAIL: swarm delayed-hook clock named variants={cases} delay=0/1/2/600; before/after increment counts and uint wrap; extraUpdates=0/2; four roles");
    }

    private static void SwarmDelayedDuePressureKeepsWorldTickBudget()
    {
        using var scope = new SwarmRuntimeScope();
        var owner = Terraria.Main.player[0]; owner.Center = Vector2.Zero;
        var target = Terraria.Main.npc[0]; target.active = true; target.Center = new Vector2(64, 0); target.knockBackResist = 1;
        var data = GeneratedItemData.Placeholder(); var entity = data.RuntimeProgram.Entities[0];
        var action = new RuntimeEventActionSpec { Event = "on_hit", DelayTicks = 2, ActionCode = RuntimeEventActionCode.Pull,
            Mode = "target_to_owner", Strength = 2, RadiusTiles = 4 };
        var source = owner.GetSource_ItemUse(new Item { type = ItemID.CopperShortsword, stack = 1 });
        int capacity = InfiniRuntimeLimits.MaxPendingRuntimeActions, perTick = InfiniRuntimeLimits.MaxRuntimeDelayedActionsPerTick;
        var budget = new RuntimeSpawnBudget(5); MaterialClock(500);
        for (int i = 0; i < capacity; i++)
            Equal(true, RuntimeDelayedActionScheduler.TrySchedule(data, entity, action, owner, source, Vector2.Zero, Vector2.UnitX, target, 0, 0, budget), "due pressure admits " + i);
        Equal(false, RuntimeDelayedActionScheduler.TrySchedule(data, entity, action, owner, source, Vector2.Zero, Vector2.UnitX, target, 0, 0, budget), "due pressure full queue refuses overflow");
        RuntimeDelayedActionScheduler.Update(); AdvanceRuntimeWorldTick();
        Equal(Vector2.Zero, target.velocity, "due pressure never dispatches at origin/origin+1");
        AdvanceRuntimeWorldTick();
        Equal(capacity - perTick, PendingActions(), "only world-tick allowance dispatched");
        Equal(new Vector2(-2f * perTick, 0), target.velocity, "actual effects at first due world tick");
        for (int repeat = 0; repeat < 5; repeat++) RuntimeDelayedActionScheduler.Update();
        Equal(capacity - perTick, PendingActions(), "same-count visits cannot reset due dispatch budget");
        Equal(new Vector2(-2f * perTick, 0), target.velocity, "same-count visits do not add effects");
        var deferred = ((IList)typeof(RuntimeDelayedActionScheduler).GetField("Pending", BindingFlags.NonPublic | BindingFlags.Static)!.GetValue(null)!)[0]!;
        Equal(500u, (uint)deferred.GetType().GetProperty("EnqueuedTick")!.GetValue(deferred)!, "pressure keeps original clock origin");
        Equal(502u, (uint)deferred.GetType().GetProperty("DueTick")!.GetValue(deferred)!, "pressure never rewrites original authored due");
        int dispatched = perTick;
        while (dispatched < capacity) {
            AdvanceRuntimeWorldTick(); dispatched = Math.Min(capacity, dispatched + perTick);
            Equal(capacity - dispatched, PendingActions(), "throttled due entries remain eligible next real tick");
            Equal(new Vector2(-2f * dispatched, 0), target.velocity, "deferred pressure effects exactly once");
        }
        AdvanceRuntimeWorldTick(); Equal(new Vector2(-2f * capacity, 0), target.velocity, "no pressure replay");
        Equal(5, budget.Remaining, "nonspawn due actions never consume event ledger");
        Console.WriteLine($"DETAIL: swarm due pressure capacity={capacity} per-world-tick={perTick}; same-count repeated visits=5; no early/doubled effects");
    }

    private static void SwarmDelayedAuthorityMatchesImmediateDispatch()
    {
        // Lowered authority-only vectors, not an Author-admissibility matrix.
        // Each effect-capable vector runs authorized consumers before denied roles.
        // Reuse EventDamageUsesAuthoredSource's CPU NPC/SceneMetrics fixture. Only
        // presentation and outgoing socket boundaries are suppressed, never HP APIs.
        var oldMetrics = Terraria.Main.SceneMetrics;
        var oldRandom = Terraria.Main.rand;
        int cases = 0, revoked = 0, strikePackets = 0, healDisplays = 0, otherPackets = 0;
        try
        {
            Terraria.Main.SceneMetrics = new SceneMetrics();
            Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(11);
            Action<Player, int, bool> healDisplay = (_, _, _) => healDisplays++;
            using var healDisplayHook = new MonoMod.RuntimeDetour.Hook(typeof(Player).GetMethod(nameof(Player.HealEffect),
                new[] { typeof(int), typeof(bool) })!, healDisplay);
            Action<int, int, int, Terraria.Localization.NetworkText, int, float, float, float, int, int, int> packet =
                (_, _, _, _, _, _, _, _, _, _, _) => otherPackets++;
            using var packetHook = new MonoMod.RuntimeDetour.Hook(typeof(NetMessage).GetMethod(nameof(NetMessage.SendData),
                new[] { typeof(int), typeof(int), typeof(int), typeof(Terraria.Localization.NetworkText), typeof(int),
                    typeof(float), typeof(float), typeof(float), typeof(int), typeof(int), typeof(int) })!, packet);
            using var strikePacketHook = new MonoMod.RuntimeDetour.ILHook(typeof(Player).GetMethod(nameof(Player.StrikeNPCDirect),
                new[] { typeof(NPC), typeof(NPC.HitInfo) })!, il => {
                var sites = il.Body.Instructions.Where(ins => ins.OpCode == Mono.Cecil.Cil.OpCodes.Call
                    && ins.Operand is Mono.Cecil.MethodReference method && method.DeclaringType.FullName == typeof(NetMessage).FullName
                    && method.Name == "SendStrikeNPC" && method.ReturnType.FullName == "System.Void").ToArray();
                Equal(1, sites.Length, "one outgoing native strike site after real NPC.StrikeNPC");
                var site = sites[0]; var method = (Mono.Cecil.MethodReference)site.Operand;
                Equal(false, method.HasThis, "native strike sync boundary is static");
                var cursor = new MonoMod.Cil.ILCursor(il); cursor.Goto(site); cursor.Remove();
                for (int i = 0; i < method.Parameters.Count; i++) cursor.Emit(Mono.Cecil.Cil.OpCodes.Pop);
                cursor.EmitDelegate<Action>(() => strikePackets++);
            });
            NPC Target(int slot, float x) => new NPC {
                whoAmI = slot, active = true, life = 1000, lifeMax = 1000,
                defense = 80, width = 20, height = 20, position = new Vector2(x, 1600),
                knockBackResist = 1, HideStrikeDamage = true,
            };
            foreach (string ev in new[] { "on_hit", "periodic", "on_kill" })
            foreach (var variant in new[] {
                (Name: "heal", Code: RuntimeEventActionCode.HealOwner, Mode: ""),
                (Name: "area", Code: RuntimeEventActionCode.DamageArea, Mode: ""),
                (Name: "chain", Code: RuntimeEventActionCode.ChainDamage, Mode: ""),
                (Name: "status", Code: RuntimeEventActionCode.ApplyStatus, Mode: ""),
                (Name: "owner-pull", Code: RuntimeEventActionCode.Pull, Mode: "owner_to_target"),
                (Name: "npc-owner-pull", Code: RuntimeEventActionCode.Pull, Mode: "target_to_owner"),
                (Name: "npc-entity-pull", Code: RuntimeEventActionCode.Pull, Mode: "target_to_entity"),
                (Name: "spawn", Code: RuntimeEventActionCode.SpawnEntity, Mode: ""),
                (Name: "move", Code: RuntimeEventActionCode.MoveOwner, Mode: ""),
                (Name: "unknown", Code: 255, Mode: ""),
            })
            {
                bool Expected((string Name, int Mode, int Local) role) => variant.Name switch {
                    "spawn" or "owner-pull" or "heal" or "move" => role.Name is "SP" or "owner-client",
                    "npc-owner-pull" or "npc-entity-pull" => role.Mode != NetmodeID.MultiplayerClient,
                    "status" or "area" or "chain" => ev == "on_hit"
                        ? role.Name is "SP" or "owner-client" : role.Mode != NetmodeID.MultiplayerClient,
                    _ => false,
                };
                bool effectful = variant.Code is RuntimeEventActionCode.HealOwner or RuntimeEventActionCode.DamageArea
                    or RuntimeEventActionCode.ChainDamage or RuntimeEventActionCode.ApplyStatus or RuntimeEventActionCode.Pull;
                bool positiveSeen = false;
                foreach (var role in SwarmRoles.OrderByDescending(Expected))
                {
                    using var scope = new SwarmRuntimeScope(role.Mode, role.Local);
                    var owner = Terraria.Main.player[0]; owner.Center = new Vector2(0, 1600);
                    owner.statLifeMax2 = 100; owner.statLife = 50;
                    ref float armorPenetration = ref owner.GetArmorPenetration(Terraria.ModLoader.DamageClass.Magic);
                    armorPenetration += 40f;
                    var target = Terraria.Main.npc[0] = Target(0, 118);
                    owner.Center = new Vector2(0, target.Center.Y);
                    var nearby = Terraria.Main.npc[1] = Target(1, 240);
                    var outside = Terraria.Main.npc[2] = Target(2, 500);
                    var position = new Vector2(256, target.Center.Y);
                    var data = SwarmGameplayFixture(); var entity = data.RuntimeProgram.TryGetEntity("root")!;
                    entity.Damage.DamageClass = "magic";
                    var action = new RuntimeEventActionSpec { Event = ev, DelayTicks = 2, ActionCode = variant.Code, Mode = variant.Mode,
                        EntityId = "root", Count = 2, Strength = 2, RadiusTiles = 8, RadiusPx = 128, RangeTiles = 8, BuffId = BuffID.OnFire,
                        DurationTicks = 90, DamageMultiplier = 1, DamageFraction = 0.5f, MaxHeal = 10 };
                    bool expected = Expected(role);
                    string label = $"authority role={role.Name} event={ev} action={variant.Name}";
                    Equal(true, owner.statLife < owner.statLifeMax2, label + " wounded owner is effect-capable");
                    Equal(true, nearby.CanBeChasedBy(), label + " damage target is chaseable");
                    Equal(false, ReferenceEquals(target, nearby), label + " damage target is not excluded direct target");
                    Equal(true, Vector2.DistanceSquared(nearby.Center, position) <= action.RadiusPx * action.RadiusPx,
                        label + " damage target is inside area and chain range");
                    int damagedLife = 1000;
                    if (variant.Code is RuntimeEventActionCode.DamageArea or RuntimeEventActionCode.ChainDamage) {
                        var control = Target(3, 2600);
                        owner.ApplyDamageToNPC(control, 100, 0f, 1, false, Terraria.ModLoader.DamageClass.Magic, false);
                        Equal(true, control.life < 1000, label + " real Terraria damage API control works in this role");
                        damagedLife = control.life;
                    }
                    if (effectful && !expected) Equal(true, positiveSeen, label + " authorized consumer effect proved before denial");
                    var budget = new RuntimeSpawnBudget(5);
                    var source = owner.GetSource_ItemUse(new Item { type = ItemID.CopperShortsword, stack = 1 });
                    Equal(expected, RuntimeDelayedActionScheduler.TrySchedule(data, entity, action, owner, source,
                        position, Vector2.UnitX, target, 10, 0, budget), label + " admission uses dispatch authority");
                    Equal(expected ? 1 : 0, PendingActions(), label + " unauthorized actions cannot occupy global queue");
                    Equal(expected && variant.Code == RuntimeEventActionCode.SpawnEntity ? 3 : 5, budget.Remaining,
                        label + " unauthorized spawn cannot reserve activation slots");
                    RuntimeDelayedActionScheduler.Clear(); Equal(5, budget.Remaining, label + " admitted reservation refunded on clear");
                    void ResetEffects() {
                        RuntimeDelayedActionScheduler.Clear(); MaterialClock(1000);
                        owner.statLife = 50; owner.velocity = Vector2.Zero;
                        target.life = nearby.life = outside.life = 1000;
                        target.velocity = nearby.velocity = outside.velocity = Vector2.Zero;
                        Array.Clear(target.buffType); Array.Clear(target.buffTime);
                    }
                    void CheckEffects(bool runs, string phase) {
                        string witness = label + " " + phase;
                        Equal(runs && variant.Name == "heal" ? 55 : 50, owner.statLife, witness + " real heal consumer HP");
                        Equal(runs && (variant.Name is "area" or "chain") ? damagedLife : 1000, nearby.life,
                            witness + " real non-direct damage consumer HP");
                        Equal(runs && variant.Name == "area" && ev != "on_hit" ? damagedLife : 1000, target.life,
                            witness + " direct-target exclusion follows exact event");
                        Equal(1000, outside.life, witness + " out-of-range NPC unchanged");
                        Equal(runs && variant.Name == "status", target.HasBuff(BuffID.OnFire), witness + " actual NPC status");
                        Equal(runs && variant.Name == "owner-pull" ? new Vector2(2, 0) : Vector2.Zero, owner.velocity,
                            witness + " owner consumer without NPC fallback");
                        Equal(runs && variant.Name.StartsWith("npc-", StringComparison.Ordinal)
                            ? new Vector2(variant.Mode == "target_to_owner" ? -2 : 2, 0) : Vector2.Zero, target.velocity,
                            witness + " NPC consumer without owner fallback");
                        Equal(Vector2.Zero, nearby.velocity, witness + " independent damage target is never a pull fallback");
                    }
                    if (effectful || !expected) {
                        ResetEffects();
                        RuntimeProgramExecutor.ExecuteAction(data, entity, action, owner, source, position, Vector2.UnitX, target, 10, 0, budget);
                        CheckEffects(expected, "immediate");
                    }
                    if (effectful) {
                        ResetEffects();
                        Equal(expected, RuntimeDelayedActionScheduler.TrySchedule(data, entity, action, owner, source,
                            position, Vector2.UnitX, target, 10, 0, budget), label + " real delayed effect admission");
                        CheckEffects(false, "delayed origin"); RuntimeDelayedActionScheduler.Update();
                        CheckEffects(false, "delayed same-count"); AdvanceRuntimeWorldTick();
                        CheckEffects(false, "delayed before due"); AdvanceRuntimeWorldTick();
                        CheckEffects(expected, "delayed due"); Equal(0, PendingActions(), label + " effect entry retired");
                        AdvanceRuntimeWorldTick(); CheckEffects(expected, "delayed no replay");
                        if (expected) positiveSeen = true;
                        else {
                            ResetEffects();
                            Terraria.Main.netMode = NetmodeID.SinglePlayer; Terraria.Main.myPlayer = 0;
                            Equal(true, RuntimeDelayedActionScheduler.TrySchedule(data, entity, action, owner, source,
                                position, Vector2.UnitX, target, 10, 0, budget), label + " initially authorized delayed consumer");
                            Equal(1, PendingActions(), label + " transition has a real pending action");
                            Terraria.Main.netMode = role.Mode; Terraria.Main.myPlayer = role.Local;
                            AdvanceRuntimeWorldTick(); CheckEffects(false, "revoked before due");
                            AdvanceRuntimeWorldTick(); CheckEffects(false, "revoked dispatch");
                            Equal(0, PendingActions(), label + " revoked entry retires");
                            AdvanceRuntimeWorldTick(); CheckEffects(false, "revoked no replay"); revoked++;
                        }
                    }
                    cases++;
                }
            }
            // Preserve the original real spawn-reservation transition/refund check.
            using (var scope = new SwarmRuntimeScope()) {
                var data = SwarmGameplayFixture(); var entity = data.RuntimeProgram.TryGetEntity("root")!;
                var owner = Terraria.Main.player[0];
                var source = owner.GetSource_ItemUse(new Item { type = ItemID.CopperShortsword, stack = 1 });
                var spawn = new RuntimeEventActionSpec { ActionCode = RuntimeEventActionCode.SpawnEntity, EntityId = "root", DelayTicks = 2, Count = 2 };
                var budget = new RuntimeSpawnBudget(5);
                Equal(true, RuntimeDelayedActionScheduler.TrySchedule(data, entity, spawn, owner, source, Vector2.Zero, Vector2.UnitX, null, 0, 0, budget), "authorized spawn reserved");
                Equal(3, budget.Remaining, "dispatch-transition reservation taken");
                Terraria.Main.netMode = NetmodeID.MultiplayerClient; Terraria.Main.myPlayer = 1;
                AdvanceRuntimeWorldTick(); AdvanceRuntimeWorldTick();
                Equal(5, budget.Remaining, "final dispatch rechecks changed authority and refunds exactly once");
                Equal(0, PendingActions(), "authority transition retires delayed entry");
                AdvanceRuntimeWorldTick(); Equal(5, budget.Remaining, "refund cannot replay");
            }
            Console.WriteLine($"DETAIL: swarm authority role/event/action variants={cases}; real immediate/delayed HP/status/pull controls; revoked dispatch={revoked}; strike socket boundaries={strikePackets}; heal displays={healDisplays}; other packet boundaries={otherPackets}; no registered spawn/teleport/socket claim");
        }
        finally { Terraria.Main.SceneMetrics = oldMetrics; Terraria.Main.rand = oldRandom; }
    }

    private static void SwarmMaterialChurnDoesNotStarveFreshOwners()
    {
        WithLighting((config, _) => {
            using var scope = new SwarmRuntimeScope(visuals: true); config.ParticleSpawnMultiplier = 1;
            var data = ReviewProjectileData("on_spawn", "on_hit", "on_crit");
            foreach (var slot in data.VfxManifest.Slots) { slot.Duration = 3; slot.Element!.Count = 1; }
            data = SwarmWire(data); var entity = data.RuntimeProgram.TryGetEntity("actor")!;
            var system = new InfiniDetachedVfxSystem();
            MaterialClock(99); var older = SwarmHost(data, entity, slot: 7); older.AI();
            int accepted = 0, highRecords = 0, highParticles = 0;
            for (uint tick = 100; tick < 1200; tick++) {
                MaterialClock(tick); system.PostUpdateEverything();
                for (int source = 0; source < 4; source++) {
                    int before = OwnedMaterialQueue().Count;
                    var generated = SwarmHost(data, entity, slot: source); generated.AI();
                    Equal(before + 1, OwnedMaterialQueue().Count, $"fresh actual on_spawn remains admitted tick={tick} source={source}");
                    generated.OnKill(90); generated.Projectile.active = false;
                    accepted++; highRecords = Math.Max(highRecords, OwnedMaterialQueue().Count);
                    highParticles = Math.Max(highParticles, OwnedMaterialQueue().Cast<object>().Sum(ReviewParticleCount));
                }
            }
            Equal(true, accepted > 4096, "actual hook churn exceeds former global history cap inside retention");
            Equal(true, highRecords <= 16 && highParticles <= 16, "live occupancy remains far below 256 records/2048 particles");
            int prior = OwnedMaterialQueue().Count;
            var freshOwner = SwarmHost(data, entity, slot: 4, owner: 1); freshOwner.AI();
            Equal(prior + 1, OwnedMaterialQueue().Count, "fresh independent owner is not starved by historical admissions");
            int beforeHits = OwnedMaterialQueue().Count;
            var target = new NPC { active = true, Center = new Vector2(100, 0) };
            older.OnHitNPC(target, new NPC.HitInfo { Crit = true }, 1);
            older.OnHitNPC(target, new NPC.HitInfo(), 1);
            Equal(beforeHits + 3, OwnedMaterialQueue().Count, "older source two real hits plus crit retain independent occurrences in same tick");
            MaterialClock(1204); system.PostUpdateEverything(); Equal(0, OwnedMaterialQueue().Count, "ordinary lifetime cleanup retires all records without draw");
            SwarmHost(data, entity, slot: 5, owner: 1).AI();
            Equal(1, OwnedMaterialQueue().Count, "free live resources admit new owner before former TTL expiration");
            Console.WriteLine($"DETAIL: swarm actual material on_spawn churn={accepted} highRecords={highRecords} highParticles={highParticles}; fresh-owner/older-source/hit+crit/lifetime controls retained");
        });
    }

    private static void SwarmMaterialOrderedAdmissionFansOutWithoutReplay()
    {
        WithLighting((config, _) => {
            using var scope = new SwarmRuntimeScope(visuals: true); config.ParticleSpawnMultiplier = 1;
            var data = ReviewProjectileData("on_hit"); var first = data.VfxManifest.Slots[0]; first.Duration = 3;
            var delayed = System.Text.Json.JsonSerializer.Deserialize<VfxSlotSpec>(System.Text.Json.JsonSerializer.Serialize(first))!;
            delayed.Id = "delayed_fanout"; delayed.StartTick = 2;
            data.VfxManifest.Slots = new[] { first, delayed }; data = SwarmWire(data);
            var source = new Projectile { active = true, owner = 0, scale = 1, velocity = Vector2.UnitX, Center = Vector2.Zero };
            var snapshot = InfiniVfxProjectileSnapshot.Capture(source, data, "actor");
            var system = new InfiniDetachedVfxSystem(); MaterialClock(100);
            void Relay(ulong occurrence, string key = "relay") => InfiniVfxRuntime.OnDetachedEvent(data, "actor", "on_hit", data.VfxManifest,
                new Vector2(10, 20), source.velocity, key, snapshot, null, occurrence);
            Relay(71); Relay(72);
            Equal(4, OwnedMaterialQueue().Count, "one ordered admission per event fans out both immediate/delayed slots");
            Equal(2, OwnedMaterialQueue().Cast<object>().Sum(ReviewParticleCount), "only immediate slots spend particles before due");
            Relay(71); Relay(72); Equal(4, OwnedMaterialQueue().Count, "same/older relay occurrences do not repeat slot fanout");
            source.Center = new Vector2(700, 800); MaterialClock(102); system.PostUpdateEverything();
            Equal(4, OwnedMaterialQueue().Cast<object>().Sum(ReviewParticleCount), "delayed slots survive source mutation with captured world facts");
            MaterialClock(1401); system.PostUpdateEverything(); Equal(0, OwnedMaterialQueue().Count, "retired world slots leave no live records");
            Relay(71); Equal(0, OwnedMaterialQueue().Count, "old replay remains refused beyond former history retention");
            Relay(73, "older-source"); Equal(2, OwnedMaterialQueue().Count, "older independent source's fresh ordered event still fans out");
            var state = new InfiniVfxState { SourceKey = "local" };
            InfiniVfxRuntime.OnEvent(source, data, "actor", "on_hit", data.VfxManifest, ref state, source.Center);
            Equal(4, OwnedMaterialQueue().Count, "independent local occurrence is not mistaken for relay sequence");
            Relay(73); Equal(4, OwnedMaterialQueue().Count, "local admission cannot reset relay replay cursor");
            ulong local = InfiniDetachedVfxSystem.NewMaterialOccurrence();
            InfiniVfxRuntime.OnEvent(source, data, "actor", "on_hit", data.VfxManifest, ref state, source.Center, local);
            Equal(6, OwnedMaterialQueue().Count, "explicit local occurrence fans out all slots once");
            InfiniVfxRuntime.OnEvent(source, data, "actor", "on_hit", data.VfxManifest, ref state, source.Center, local);
            Equal(6, OwnedMaterialQueue().Count, "same explicit local occurrence cannot replay");
            Console.WriteLine("DETAIL: swarm ordered material admission immediate+delayed fanout, same-tick hits, replay past retention, independent older source, separate local/relay origins");
        });
    }

    private static void SwarmChargeReleasedExtraAiDoesNotRescale()
    {
        using var scope = new SwarmRuntimeScope();
        var property = typeof(InfiniMod).GetProperty("GeneratedItems")!; var previous = property.GetValue(null);
        using var registry = new GeneratedItemRegistryService();
        try {
            var data = SwarmGameplayFixture(); var entity = data.RuntimeProgram.TryGetEntity("root")!;
            entity.Controller.Name = "charge_then_release"; entity.Controller.Code = RuntimeControllerCode.ChargeThenRelease;
            entity.Controller.Params.ChargeTicks = 1; entity.Controller.Params.PowerMultiplier = 2;
            data = SwarmWire(data); entity = data.RuntimeProgram.TryGetEntity("root")!;
            property.SetValue(null, registry); GeneratedItemRegistryService.StampCurrentWorld(data);
            ((IDictionary)registry.GetType().GetField("_byId", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(registry)!)[data.Id] = data;
            foreach (int basis in new[] { 0, 25, 200 }) {
                Terraria.Main.netMode = NetmodeID.SinglePlayer; Terraria.Main.myPlayer = 0;
                var owner = SwarmHost(data, entity, damage: basis, knockback: 7); owner.AI();
                Equal(basis * 2, owner.Projectile.damage, "owner release before ExtraAI basis=" + basis);
                byte[] wire = ReviewExtra(owner);
                foreach (var role in SwarmRoles) {
                    Terraria.Main.netMode = role.Mode; Terraria.Main.myPlayer = role.Local;
                    var projectile = Terraria.Main.projectile[4] = new Projectile { whoAmI = 4, owner = 0, active = true,
                        width = 12, height = 12, scale = 1, velocity = owner.Projectile.velocity, timeLeft = 90,
                        damage = owner.Projectile.damage, knockBack = owner.Projectile.knockBack, originalDamage = basis };
                    var peer = Attach(projectile); typeof(Projectile).GetProperty("ModProjectile")!.SetValue(projectile, peer);
                    // Actual ExtraAI decoder and registry-backed metadata hydration,
                    // starting with no local Configure or event-budget grant.
                    peer.ReceiveExtraAI(new BinaryReader(new MemoryStream(wire)));
                    Equal(true, peer.Matches(data.Id, entity.Id), "real ExtraAI hydration completed " + role.Name);
                    Equal(true, (bool)typeof(GeneratedProjectile).GetField("_released", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(peer)!,
                        "decoder retained released generation flag " + role.Name);
                    Equal(true, typeof(GeneratedProjectile).GetField("_activationSpawnBudget", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(peer) is null,
                        "received budget snapshot is never a new mutable grant " + role.Name);
                    for (int repeat = 0; repeat < 3; repeat++) peer.AI();
                    Equal(basis * 2, peer.Projectile.damage, "received released state not rescaled " + role.Name + " basis=" + basis);
                    Equal(14f, peer.Projectile.knockBack, "received live knockback survives " + role.Name);
                    Equal(basis, peer.Projectile.originalDamage, "peer original basis survives " + role.Name);
                }
            }
            Console.WriteLine("DETAIL: swarm charge actual ExtraAI released variants=12; three repeated peer AI calls each; no socket delivery claim");
        } finally { property.SetValue(null, previous); }
    }
}

using System;
using System.Collections;
using InfiniCrafterLocal.Common.Services;
using System.Linq;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.VFX;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using System.Collections.Generic;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    // Actual packet encoder/receiver, registry lookup and detached consumer; no sockets/world loop.


    private delegate ReLogic.Utilities.SlotId EventSoundObserver(in Terraria.Audio.SoundStyle style,
        Vector2? position, Terraria.Audio.SoundUpdateCallback? callback);

    // Observe real AI -> slot clock / gameplay scheduler. No world spawning or GPU.
    private static void ProjectilePeriodicVfxIsIndependentOfGameplayActions()
    {
        WithLighting((config, lights) =>
        {
            var clock = typeof(Terraria.Main).GetField("_gameUpdateCount", BindingFlags.Static | BindingFlags.NonPublic)!;
            object? oldClock = clock.GetValue(null);
            var oldOwner = Terraria.Main.player[0]; var oldNpcs = Terraria.Main.npc; var oldProjectile = Terraria.Main.projectile[0];
            var system = new InfiniDetachedVfxSystem();
            var queue = (System.Collections.IList)typeof(InfiniDetachedVfxSystem)
                .GetField("ShapeEmissions", BindingFlags.Static | BindingFlags.NonPublic)!.GetValue(null)!;
            var pending = (System.Collections.IList)typeof(InfiniCrafterLocal.Common.Runtime.RuntimeDelayedActionScheduler)
                .GetField("Pending", BindingFlags.Static | BindingFlags.NonPublic)!.GetValue(null)!;
            try
            {
                config.PresentationLightMultiplier = 1f;
                Terraria.Main.player[0] = new Player { whoAmI = 0, active = true, Center = new Vector2(160f) };
                Terraria.Main.npc = new NPC[oldNpcs.Length];
                for (int i = 0; i < Terraria.Main.npc.Length; i++) Terraria.Main.npc[i] = new NPC { whoAmI = i };
                var npc = Terraria.Main.npc[0] = new NPC { active = true, whoAmI = 0, life = 1000, lifeMax = 1000,
                    knockBackResist = 1f, width = 16, height = 16, Center = new Vector2(176, 160) };
                foreach (bool actions in new[] { true, false })
                foreach (int extra in new[] { 0, 2 })
                {
                    system.OnWorldUnload(); InfiniCrafterLocal.Common.Runtime.RuntimeDelayedActionScheduler.Clear();
                    npc.velocity = Vector2.Zero;
                    var entity = Entity(); entity.Id = "periodic_probe"; entity.Kind = RuntimeEntityKind.StationaryProjectile;
                    entity.LifetimeTicks = 60;
                    entity.Events = actions ? new[] {
                        new RuntimeEventActionSpec { Id = "immediate", Event = RuntimeEventKind.Periodic,
                            ActionCode = RuntimeEventActionCode.Pull, PeriodTicks = 6, Mode = "target_to_point", RadiusTiles = 4, Strength = 0.5f },
                        new RuntimeEventActionSpec { Id = "delayed_a", Event = RuntimeEventKind.Periodic,
                            ActionCode = RuntimeEventActionCode.SpawnEntity,
                            DamageBasis = RuntimeChildCombatBasis.AuthoredChild, KnockbackBasis = RuntimeChildCombatBasis.AuthoredChild, PeriodTicks = 6, DelayTicks = 2, Count = 1 },
                        new RuntimeEventActionSpec { Id = "delayed_b", Event = RuntimeEventKind.Periodic,
                            ActionCode = RuntimeEventActionCode.SpawnEntity,
                            DamageBasis = RuntimeChildCombatBasis.AuthoredChild, KnockbackBasis = RuntimeChildCombatBasis.AuthoredChild, PeriodTicks = 6, DelayTicks = 3, Count = 1 },
                        new RuntimeEventActionSpec { Id = "delayed_c", Event = RuntimeEventKind.Periodic,
                            ActionCode = RuntimeEventActionCode.SpawnEntity,
                            DamageBasis = RuntimeChildCombatBasis.AuthoredChild, KnockbackBasis = RuntimeChildCombatBasis.AuthoredChild, PeriodTicks = 12, DelayTicks = 4, Count = 1 },
                    } : Array.Empty<RuntimeEventActionSpec>();
                    var data = GeneratedItemData.Placeholder(); data.RuntimeProgram.Entities = new[] { entity };
                    data.VfxManifest.Slots = new[] {
                        new VfxSlotSpec { Id = "periodic_shape", EntityId = entity.Id, Event = RuntimeEventKind.Periodic,
                            RendererKind = "shape", Shape=ExplicitShape("arc"), RepeatEvery=5, StartTick=0, SlotSeed=0, Blend="alpha", Layer="BeforeProjectiles", Duration=10 },
                        new VfxSlotSpec { Id = "periodic_light", EntityId = entity.Id, Event = RuntimeEventKind.Periodic,
                            RendererKind = "nativeLight", Light=new(){Intensity=.2f}, Color=Rgb(255,255,255), RepeatEvery=5, StartTick=0, SlotSeed=0, },
                    };
                    var projectile = Terraria.Main.projectile[0] = new Projectile { whoAmI=0, identity=17, active = true, owner = 0, Center = new Vector2(160f), damage = 100 };
                    var generated = Attach(projectile); typeof(Projectile).GetProperty("ModProjectile")!.SetValue(projectile,generated); generated.Configure(data, entity, 0, 8, Vector2.UnitX);
                    projectile.extraUpdates = extra;
                    for (uint tick = 1; tick <= 12; tick++)
                    {
                        clock.SetValue(null, tick); lights.Clear(); projectile.netUpdate = false;
                        for (int update = 0; update <= extra; update++) generated.AI();
                        system.PostUpdateEverything();
                        Equal(actions && tick >= 6 ? tick >= 12 ? 5 : 2 : 0, pending.Count,
                            "gameplay periods remain world-tick based with extraUpdates=" + extra + " tick=" + tick);
                        Equal(actions && tick % 6 == 0, projectile.netUpdate, "delayed spawn reservation keeps netUpdate timing");
                        Equal(actions ? -(float)(tick / 6) * 0.5f : 0f, npc.velocity.X, "real immediate periodic pull executes at authored period");
                        Equal(tick % 5 == 0 ? 1 : 0, lights.Count,
                            "periodic light follows own slot, not gameplay action period; actions=" + actions + " tick=" + tick);
                        Equal((int)(tick / 5), queue.Count, "explicit shape emission cadence is independent of gameplay actions");
                    }
                    if (actions)
                    {
                        string ids = string.Join(",", pending.Cast<object>().Select(p =>
                            ((RuntimeEventActionSpec)p.GetType().GetProperty("Action")!.GetValue(p)!).Id));
                        Equal("delayed_a,delayed_b,delayed_a,delayed_b,delayed_c", ids, "authored scheduler enqueue order unchanged");
                        Equal("2,3,2,3,4", string.Join(",", pending.Cast<object>().Select(p =>
                            unchecked((uint)p.GetType().GetProperty("DueTick")!.GetValue(p)!
                                - (uint)p.GetType().GetProperty("EnqueuedTick")!.GetValue(p)!))), "authored delays unchanged");
                    }
                    // Exact event lanes remain independent after removing only the periodic relay.
                    data.VfxManifest.Slots = new[] { RuntimeEventKind.OnHit, RuntimeEventKind.OnCrit,
                        RuntimeEventKind.OnExpire, RuntimeEventKind.OnKill }.Select(ev => new VfxSlotSpec {
                            Id = ev, EntityId = entity.Id, Event = ev, RendererKind="shape",Shape=ExplicitShape("arc"),Blend="alpha",Layer="BeforeProjectiles",Duration=10,RepeatEvery=0,StartTick=0 }).ToArray();
                    int beforeEvents=queue.Count;
                    clock.SetValue(null, 13u);
                    generated.OnHitNPC(npc, new NPC.HitInfo { Crit = true }, 1);
                    Equal(beforeEvents+2, queue.Count, "actual critical hit keeps both hit and crit presentation");
                    projectile.timeLeft = 1; generated.AI(); generated.OnKill(0);
                    Equal(beforeEvents+4, queue.Count, "final AI and kill keep both expire and kill presentation");
                }
            }
            finally
            {
                system.OnWorldUnload(); InfiniCrafterLocal.Common.Runtime.RuntimeDelayedActionScheduler.Clear();
                clock.SetValue(null, oldClock); Terraria.Main.player[0] = oldOwner; Terraria.Main.npc = oldNpcs; Terraria.Main.projectile[0] = oldProjectile;
            }
        });
    }

    private static void ItemVfxPeriodicUsesWorldClockAndIgnoresProjectileStartTick()
    {
        ItemPeriodicPresentationHasOneWorldTickOwner();
        ProjectilePeriodicVfxIsIndependentOfGameplayActions();

    }
}

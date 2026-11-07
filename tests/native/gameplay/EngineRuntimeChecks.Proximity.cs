using System;
using System.Collections;
using System.Linq;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Runtime;
using InfiniCrafterLocal.Common.VFX;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    // Hook-level CPU observer: real AI/OnKill and real nativeLight VFX, not a simulated event dispatcher.
    // Does not claim Terraria's world update, network broadcast, or a rendered/GPU frame.
    private static void ProximityMissileExpireVfxMatchesNaturalExpiry()
    {
        Player? priorOwner = Terraria.Main.player[0];
        NPC[] priorNpcs = (NPC[])Terraria.Main.npc.Clone();
        RuntimeDelayedActionScheduler.Clear();
        var vfxSystem = new InfiniDetachedVfxSystem();
        vfxSystem.OnWorldUnload();
        try
        {
            for (int i = 0; i < Terraria.Main.npc.Length; i++)
                Terraria.Main.npc[i] = new NPC { whoAmI = i, active = false };
            Terraria.Main.player[0] = new Player { whoAmI = 0, active = true };
            WithLighting((config, lights) =>
            {
                config.PresentationLightMultiplier = 1f;
                NPC target = Terraria.Main.npc[0] = new NPC {
                    whoAmI = 0, active = true, life = 1000, lifeMax = 1000,
                    width = 20, height = 20, position = new Vector2(1000f, 1600f),
                };
                Equal(true, target.CanBeChasedBy(), "proximity target is eligible");

                (GeneratedProjectile Generated, Projectile Projectile) Create(bool proximity)
                {
                    var entity = Entity();
                    entity.Id = "proximity_probe";
                    entity.Kind = RuntimeEntityKind.FreeProjectile;
                    entity.LifetimeTicks = 60;
                    entity.Events = new[] {
                        new RuntimeEventActionSpec { Id = "expire_action", Event = RuntimeEventKind.OnExpire,
                            ActionCode = RuntimeEventActionCode.DamageNearby, MaxTargets = 16, DelayTicks = 1, RadiusPx = 16 },
                        new RuntimeEventActionSpec { Id = "kill_action", Event = RuntimeEventKind.OnKill,
                            ActionCode = RuntimeEventActionCode.DamageNearby, MaxTargets = 16, DelayTicks = 1, RadiusPx = 16 },
                        new RuntimeEventActionSpec { Id = "hit_action", Event = RuntimeEventKind.OnHit,
                            ActionCode = RuntimeEventActionCode.DamageNearby, MaxTargets = 16, DelayTicks = 1, RadiusPx = 16 },
                    };
                    if (proximity)
                    {
                        entity.Proximity = new() { SearchRangeTiles = 6, TriggerRadiusPx = 24,
                            RequireLineOfSight = false, Action = "expire_then_kill" };
                    }
                    var manifest = new VfxManifestSpec {
                        Slots = new[] {
                            Cue("spawn_cue", RuntimeEventKind.OnSpawn, 1f),
                            Cue("expire_cue", RuntimeEventKind.OnExpire, 2f),
                            Cue("kill_cue", RuntimeEventKind.OnKill, 3f),
                            Cue("hit_cue", RuntimeEventKind.OnHit, 4f),
                        },
                    };
                    manifest.NormalizeAndValidate();
                    var data = GeneratedItemData.Placeholder();
                    data.VfxManifest = manifest;
                    var projectile = new Projectile { owner = 0, active = true, damage = 100, velocity = Vector2.UnitX };
                    projectile.Center = proximity ? target.Center : target.Center + new Vector2(600f, 0f);
                    var generated = Attach(projectile);
                    generated.Configure(data, entity, 0, 8, Vector2.UnitX);
                    return (generated, projectile);
                }

                // Each authored intensity identifies an event. Exact RGB and append
                // order observe current native cues, not the retired simple-slot ledger.
                static void Sequence(IList lights, string label, params int[] expected)
                {
                    Equal(expected.Length, lights.Count, label + " exact light cue multiplicity");
                    for (int i = 0; i < expected.Length; i++) {
                        var actual = (Vector3)lights[i]!.GetType().GetField("Color")!.GetValue(lights[i])!;
                        Equal(Vector3.One * (.22f * expected[i]), actual, label + " ordered authored cue " + i);
                    }
                }

                lights.Clear();
                var natural = Create(proximity: false);
                natural.Projectile.timeLeft = 1;
                natural.Generated.AI();
                Equal(1, PendingActions(), "natural final AI schedules only expiry gameplay");
                Sequence(lights, "natural final AI", 1, 2);
                natural.Generated.OnKill(0);
                Equal(2, PendingActions(), "natural OnKill adds kill gameplay, not duplicate expiry or hit");
                Sequence(lights, "natural expiry not doubled", 1, 2, 3);

                lights.Clear();
                RuntimeDelayedActionScheduler.Clear();
                var early = Create(proximity: false);
                early.Generated.AI();
                early.Generated.OnKill(10);
                Equal(1, PendingActions(), "early kill schedules only kill gameplay, no expire or hit");
                Sequence(lights, "early kill excludes expiry and hit", 1, 3);

                lights.Clear();
                RuntimeDelayedActionScheduler.Clear();
                var near = Create(proximity: true);
                near.Generated.AI(); // real movement finds and reaches a chaseable target
                Equal(true, (bool)typeof(GeneratedProjectile).GetField("_expireEventRan",
                    BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(near.Generated)!, "proximity AI took expiry branch");
                Equal(1, PendingActions(), "proximity AI schedules expiry gameplay, not on_hit");
                near.Generated.OnKill(near.Projectile.timeLeft); // hook-level vanilla kill boundary
                Equal(2, PendingActions(), "proximity kill adds only kill gameplay, no duplicate expiry or on_hit");
                Sequence(lights, "proximity kill (no synthetic on_hit)", 1, 2, 3);
            });
        }
        finally
        {
            RuntimeDelayedActionScheduler.Clear();
            vfxSystem.OnWorldUnload();
            Terraria.Main.player[0] = priorOwner!;
            Array.Copy(priorNpcs, Terraria.Main.npc, priorNpcs.Length);
        }
    }

    private static VfxSlotSpec Cue(string id, string eventName, float cueOrdinal)
        => new() {
            Id = id, EntityId = "proximity_probe", Event = eventName,
            RendererKind = "nativeLight", Color = Rgb(255, 255, 255), Anchor = "self",
            StartTick = 0, RepeatEvery = 0, Light = new() { Intensity = .22f * cueOrdinal },
        };
}

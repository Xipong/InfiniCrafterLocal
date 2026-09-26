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
    // Hook-level CPU observer: real AI/OnKill and real lightCue VFX, not a simulated event dispatcher.
    // Does not claim Terraria's world update, network broadcast, or a rendered/GPU frame.
    private static void ProximityMissileExpireVfxMatchesNaturalExpiry()
    {
        Player? priorOwner = Terraria.Main.player[0];
        NPC[] priorNpcs = (NPC[])Terraria.Main.npc.Clone();
        RuntimeDelayedActionScheduler.Clear();
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

                (GeneratedProjectile Generated, Projectile Projectile, InfiniVfxState State) Create(bool proximity)
                {
                    var entity = Entity();
                    entity.Id = "proximity_probe";
                    entity.Kind = RuntimeEntityKind.FreeProjectile;
                    entity.LifetimeTicks = 60;
                    entity.Events = new[] {
                        new RuntimeEventActionSpec { Id = "expire_action", Event = RuntimeEventKind.OnExpire,
                            ActionCode = RuntimeEventActionCode.DamageArea, DelayTicks = 1, RadiusPx = 16 },
                        new RuntimeEventActionSpec { Id = "kill_action", Event = RuntimeEventKind.OnKill,
                            ActionCode = RuntimeEventActionCode.DamageArea, DelayTicks = 1, RadiusPx = 16 },
                        new RuntimeEventActionSpec { Id = "hit_action", Event = RuntimeEventKind.OnHit,
                            ActionCode = RuntimeEventActionCode.DamageArea, DelayTicks = 1, RadiusPx = 16 },
                    };
                    if (proximity)
                    {
                        entity.Movement.Name = "move_proximity_missile";
                        entity.Movement.Code = 13;
                        entity.Movement.Params.RangeTiles = 6f;
                        entity.Movement.Params.ProximityRadiusPx = 24f;
                        entity.Movement.Params.HomingStrength = 0.1f;
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
                    var state = (InfiniVfxState)typeof(GeneratedProjectile)
                        .GetField("_vfxState", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(generated)!;
                    return (generated, projectile, state);
                }

                // Use the real light queue's append order and individual slot strengths as
                // an observable event trace; distinct on_hit would add a fourth cue.
                static int[] Cues(IList lights) => lights.Cast<object>()
                    .Select(light => (int)MathF.Round(((Vector3)light.GetType().GetField("Color")!
                        .GetValue(light)!).X / 0.22f))
                    .ToArray();
                static void Sequence(IList lights, string label, params int[] expected)
                {
                    string actual = string.Join(",", Cues(lights));
                    Equal(string.Join(",", expected), actual, label + " ordered real light cues");
                }
                static void Events(InfiniVfxState state, string label, params string[] expected)
                {
                    string actual = string.Join(",", state.LastSlotEmission.Keys.Select(k => k.EventName));
                    Equal(string.Join(",", expected), actual, label + " event slots marked once");
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
                Events(natural.State, "natural expiry", RuntimeEventKind.OnSpawn, RuntimeEventKind.OnExpire, RuntimeEventKind.OnKill);

                lights.Clear();
                RuntimeDelayedActionScheduler.Clear();
                var early = Create(proximity: false);
                early.Generated.AI();
                early.Generated.OnKill(10);
                Equal(1, PendingActions(), "early kill schedules only kill gameplay, no expire or hit");
                Sequence(lights, "early kill excludes expiry and hit", 1, 3);
                Events(early.State, "early kill", RuntimeEventKind.OnSpawn, RuntimeEventKind.OnKill);

                lights.Clear();
                RuntimeDelayedActionScheduler.Clear();
                var near = Create(proximity: true);
                near.Generated.AI(); // real movement finds and reaches a chaseable target
                Equal(true, (bool)typeof(GeneratedProjectile).GetField("_expireEventRan",
                    BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(near.Generated)!, "proximity AI took expiry branch");
                Equal(1, PendingActions(), "proximity AI schedules expiry gameplay, not on_hit");
                near.Generated.OnKill(near.Projectile.timeLeft); // hook-level vanilla kill boundary
                Equal(2, PendingActions(), "proximity kill adds only kill gameplay, no duplicate expiry or on_hit");
                Equal(false, near.State.LastSlotEmission.Keys.Any(k => k.EventName == RuntimeEventKind.OnHit),
                    "proximity kill does not synthesize on_hit VFX");
                Sequence(lights, "proximity kill (no synthetic on_hit)", 1, 2, 3);
                Events(near.State, "proximity kill", RuntimeEventKind.OnSpawn, RuntimeEventKind.OnExpire, RuntimeEventKind.OnKill);
            });
        }
        finally
        {
            RuntimeDelayedActionScheduler.Clear();
            Terraria.Main.player[0] = priorOwner!;
            Array.Copy(priorNpcs, Terraria.Main.npc, priorNpcs.Length);
        }
    }

    private static VfxSlotSpec Cue(string id, string eventName, float scale)
        => new() {
            Id = id, EntityId = "proximity_probe", Event = eventName,
            RendererKind = "lightCue", Channel = "light", Lane = "cue", Scale = scale,
        };
}

using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Runtime;
using InfiniCrafterLocal.Content.Items;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using MonoMod.RuntimeDetour;
using Terraria;
using Terraria.DataStructures;
using Terraria.ID;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private const BindingFlags SentryLifePrivate = BindingFlags.Instance | BindingFlags.NonPublic;

    private sealed class SentryLifeScope : IDisposable
    {
        private readonly NativeActorState state = new();
        internal readonly Player Owner;
        internal SentryLifeScope()
        {
            Terraria.Main.netMode = NetmodeID.SinglePlayer; Terraria.Main.myPlayer = 0;
            Owner = Terraria.Main.player[0] = new Player { whoAmI = 0, active = true, direction = 1 };
            Terraria.Main.projectile = Enumerable.Range(0, Terraria.Main.projectile.Length).Select(i => new Projectile { whoAmI = i, active = false }).ToArray();
        }
        public void Dispose()
        {
            state.Dispose();
        }
    }

    private delegate void SentryRestingHook(Player owner, int type, out int x, out int y, out int push);
    private static void SentryNativeRestingSpotAndTurretCap()
    {
        using var state = new SentryLifeScope();
        var data = RootSpawnFixture(32, 1); var entity = data.RuntimeProgram.TryGetEntity("root")!;
        entity.NativeSentry = true; entity.Spawn.Placement = "native_resting_spot"; entity.Hitbox.HeightPx = 42;
        int restCalls = 0, turretCalls = 0, spawns = 0;
        using (var resting = new Hook(typeof(Player).GetMethod(nameof(Player.FindSentryRestingSpot))!,
            (SentryRestingHook)((Player owner, int type, out int x, out int y, out int push) => {
                Equal(true, ReferenceEquals(state.Owner, owner), "native resting spot uses exact owner");
                Equal(ModContent.ProjectileType<GeneratedProjectile>(), type, "native resting spot uses generated projectile type");
                restCalls++; x = 1200; y = 2400; push = 999;
            })))
        using (var turrets = new Hook(typeof(Player).GetMethod(nameof(Player.UpdateMaxTurrets))!, (Action<Player>)(owner => {
            Equal(true, ReferenceEquals(state.Owner, owner), "native cap uses exact owner");
            Equal(true, Terraria.Main.projectile[spawns - 1].sentry, "native cap sees hydrated sentry flag"); turretCalls++;
        })))
        using (var native = new Hook(NativeProjectileEntry(),
            (Func<IEntitySource, Vector2, Vector2, int, int, float, int, float, float, float, Projectile>)
            ((source, position, velocity, type, damage, knockback, owner, a, b, c) => {
                Equal(new Vector2(1200, 2379), position, "native ground minus half authored height; pushYUp ignored");
                var projectile = Terraria.Main.projectile[spawns] = new Projectile { whoAmI = spawns++, owner = owner, active = true, Center = position };
                typeof(Projectile).GetProperty("ModProjectile")!.SetValue(projectile, Attach(projectile));
                return projectile; // isolated host; no game-world registration claimed
            }))) {
            Equal(1, GeneratedProjectile.SpawnRuntimeEntity(data, "root", state.Owner,
                state.Owner.GetSource_Misc("native sentry"), Vector2.Zero, Vector2.UnitX, 0, 1), "native spawn boundary delivers one host");
            Equal(1, restCalls, "explicit anchor reaches native resting method"); Equal(1, turretCalls, "native cap runs after successful configuration");
        }
        // Exercise the real tML cap separately from the boundary observers.
        foreach (Projectile projectile in Terraria.Main.projectile) projectile.active = false;
        var old = Terraria.Main.projectile[0] = new Projectile { whoAmI = 0, active = true, owner = 0, sentry = true, timeLeft = 300 };
        var fresh = Terraria.Main.projectile[1] = new Projectile { whoAmI = 1, active = true, owner = 0, sentry = true, timeLeft = 600 };
        var ordinary = Terraria.Main.projectile[2] = new Projectile { whoAmI = 2, active = true, owner = 0, sentry = false, timeLeft = 100 };
        state.Owner.maxTurrets = 1; state.Owner.UpdateMaxTurrets();
        Equal(false, old.active, "native maxTurrets retires oldest registered sentry");
        Equal(true, fresh.active && ordinary.active, "native cap retains newest and ignores ordinary stationary projectile");
    }


}

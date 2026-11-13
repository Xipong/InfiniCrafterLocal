using System;
using System.Reflection;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;
using InfiniCrafterLocal.Common.Players;

internal static partial class EngineRuntimeChecks
{
    private sealed class ChannelPlayerScope : IDisposable
    {
        private readonly PropertyInfo singleton = typeof(ContentInstance<InfiniCraftPlayer>).GetProperty("Instance")!;
        private readonly object? previous;
        internal ChannelPlayerScope(Player owner)
        {
            previous = singleton.GetValue(null);
            singleton.SetValue(null, NativeDtoBindPlayer(owner));
        }
        public void Dispose() => singleton.SetValue(null, previous);
    }

    private static GeneratedProjectile ChannelChild(GeneratedProjectile root, int slot)
    {
        var data = BeamFixture(false);
        var body = Terraria.Main.projectile[slot] = new Projectile {
            whoAmI = slot, identity = 900 + slot, owner = 0, type = root.Projectile.type,
            active = true, timeLeft = 60, width = 12, height = 12 };
        var child = Attach(body);
        typeof(Projectile).GetProperty("ModProjectile")!.SetValue(body, child);
        child.Configure(data, data.RuntimeProgram.TryGetEntity("root")!, 1, 0, Vector2.UnitX);
        // These are the actual native channel tracker methods called before OnSpawn.
        Terraria.Main.player[0].TryUpdateChannel(body);
        return child;
    }

    private static void GeneratedChannelChildDeathDoesNotCancelAndRootDeathDoes()
    {
        using var scope = new SwarmRuntimeScope();
        var owner = Terraria.Main.player[0]; using var playerScope = new ChannelPlayerScope(owner);
        var root = BeamHost(BeamFixture(false));
        int type = root.Type;
        bool old = ProjectileID.Sets.DontCancelChannelOnKill[type];
        try {
            root.SetStaticDefaults();
            owner.HeldItem.shoot = type;
            owner.StartChanneling(owner.HeldItem); owner.TryUpdateChannel(root.Projectile);
            var child = ChannelChild(root, 1);
            child.Projectile.Kill();
            Equal(false, child.Projectile.active, "actual native Kill retires child");
            Equal(true, owner.channel, "same proxy child death cannot cancel root channel");
            root.Projectile.Kill();
            Equal(false, owner.channel, "exact live primary root death still ends channel");
        } finally { ProjectileID.Sets.DontCancelChannelOnKill[type] = old; }
    }

    private static void GeneratedChannelRetiredRootCannotCancelNewUse()
    {
        using var scope = new SwarmRuntimeScope();
        var owner = Terraria.Main.player[0]; using var playerScope = new ChannelPlayerScope(owner);
        var data = BeamFixture(false);
        var oldRoot = BeamHost(data);
        var nextRoot = BeamHost(data, slot: 2);
        bool old = ProjectileID.Sets.DontCancelChannelOnKill[oldRoot.Type];
        try {
            oldRoot.SetStaticDefaults();
            oldRoot.Projectile.Kill();
            Equal(true, owner.channel, "retired root does not cancel replacement root");
            var child = ChannelChild(nextRoot, 3);
            owner.channel = false; // actual native input release, never resurrect it
            child.Projectile.Kill();
            Equal(false, owner.channel, "child death cannot resurrect released channel");
            owner.channel = true;
            owner.inventory[0] = new Item(); // a vanilla/new physical item owns this channel
            nextRoot.Projectile.Kill();
            Equal(true, owner.channel, "old root cannot cancel a different held item");
        } finally { ProjectileID.Sets.DontCancelChannelOnKill[oldRoot.Type] = old; }
    }
    private static void GeneratedChannelNativeTerminationPreservesControlAndMana()
    {
        using var scope = new SwarmRuntimeScope();
        var owner = Terraria.Main.player[0]; using var playerScope = new ChannelPlayerScope(owner);
        var host = BeamHost(BeamFixture());
        bool old = ProjectileID.Sets.DontCancelChannelOnKill[host.Type];
        try {
            host.SetStaticDefaults();
            owner.statMana = 0; owner.manaFlower = false;
            owner.HeldItem.mana = 10; owner.HeldItem.useTime = 4;
            MaterialClock(100); BeamApply(host);
            MaterialClock(104); BeamApply(host);
            Equal(false, host.Projectile.active, "actual native Kill retires mana-exhausted root");
            Equal(false, owner.channel, "mana exhaustion cancels exact root channel");
            foreach (string reason in new[] { "release", "dead", "noItems", "CCed", "different_item" }) {
                host = BeamHost(BeamFixture()); owner.statMana = 100;
                MaterialClock(200); BeamApply(host);
                if (reason == "release") owner.channel = false;
                if (reason == "dead") owner.dead = true;
                if (reason == "noItems") owner.noItems = true;
                if (reason == "CCed") owner.frozen = true;
                if (reason == "different_item") owner.inventory[0] = new Item();
                MaterialClock(204); BeamApply(host);
                Equal(false, host.Projectile.active, "actual native Kill after " + reason);
                Equal(100, owner.statMana, "no further payment after " + reason);
                Equal(reason == "different_item", owner.channel, "channel ownership after " + reason);
            }
        } finally { ProjectileID.Sets.DontCancelChannelOnKill[host.Type] = old; }
    }

}

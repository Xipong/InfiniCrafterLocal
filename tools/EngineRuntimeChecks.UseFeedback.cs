using System;
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    private static void GeneratedUseRefusalsKeepExactAdmissionAndLocalization()
    {
        WithForgePresentationLanguages(locale => {
            using var scope = new SwarmRuntimeScope();
            var player = Terraria.Main.player[0];
            var generated = RootCombatHost(RootCombatFixture(20, 2, "magic"));
            var entity = generated.Data.RuntimeProgram.TryGetEntity("root")!;
            string Text(string key, params object[] args) => InfiniCraftPlayer.GeneratedUseFeedbackText(key, args);
            Equal("", generated.RootSpawnBlockedReason(player, entity), "empty roster admits the exact root");
            entity.Spawn.Count = 2; entity.Spawn.MaxActive = 2;
            var active = SwarmHost(generated.Data, entity);
            Equal(Text("EntityBatchLimit", 2, 2), generated.RootSpawnBlockedReason(player, entity), "whole authored batch must fit entity concurrency");
            active.Projectile.owner = 1;
            Equal("", generated.RootSpawnBlockedReason(player, entity), "other player's same entity does not consume owner budget");
            active.Projectile.owner = 0; entity.Spawn.MaxActive = null;
            entity.Kind = RuntimeEntityKind.OwnerAttachedProjectile;
            Equal(Text("OwnerAttachedActive"), generated.RootSpawnBlockedReason(player, entity), "attached duplicate has distinct refusal");
            entity.Kind = RuntimeEntityKind.FreeProjectile;
            for (int i = 1; i < InfiniRuntimeLimits.MaxRuntimeActiveProjectilesPerOwner; i++)
                SwarmHost(generated.Data, entity, slot: i);
            Equal(Text("OwnerProjectileLimit", InfiniRuntimeLimits.MaxRuntimeActiveProjectilesPerOwner),
                generated.RootSpawnBlockedReason(player, entity), "all generated roots share owner ceiling");
            // The read-only feedback query cannot remove an actor or change authored limits.
            Equal(2, entity.Spawn.Count, "refusal does not lower or raise authored count");
            Equal(true, active.Projectile.active, "refusal leaves existing effects alive");
            foreach (string key in new[] { "GroundRequired", "Wet", "LifeRequired", "ManaRequired",
                "OwnerProjectileLimit", "EntityBatchLimit", "OwnerAttachedActive", "MobilityCooldown",
                "MobilityDataMissing", "MobilityModeMissing", "MobilityUnsupported", "MobilityDead",
                "MobilityAuthority", "MobilitySpawnMissing", "MobilityLocalControl", "MobilityRangeMissing", "MobilityUnsafe" })
                Equal(false, Text(key, 2, 3).StartsWith("Mods.", StringComparison.Ordinal), locale + " localized " + key);
        });
    }

    private static void GeneratedUseNoticesThrottlePerOwnerAndRespectAuthority()
    {
        var first = new InfiniCraftPlayer();
        var other = new InfiniCraftPlayer();
        Equal(true, first.TryReserveGeneratedUseNotice(0), "first refusal is immediate even at tick zero");
        Equal(false, first.TryReserveGeneratedUseNotice(0), "same tick repeated input suppressed");
        Equal(false, first.TryReserveGeneratedUseNotice(59), "auto reuse remains throttled");
        Equal(true, other.TryReserveGeneratedUseNotice(59), "each owner has independent notice state");
        Equal(true, first.TryReserveGeneratedUseNotice(60), "notice resumes after one second");
        var wrap = new InfiniCraftPlayer();
        Equal(true, wrap.TryReserveGeneratedUseNotice(uint.MaxValue - 10), "first near clock wrap");
        Equal(false, wrap.TryReserveGeneratedUseNotice(20), "clock wrap does not bypass throttle");
        Equal(true, wrap.TryReserveGeneratedUseNotice(49), "clock wrap retains elapsed duration");
        WithPlayer((player, owner) => {
            bool oldServer = Terraria.Main.dedServ; int oldMode = Terraria.Main.netMode, oldLocal = Terraria.Main.myPlayer;
            uint oldTick = Terraria.Main.GameUpdateCount;
            try {
                Terraria.Main.dedServ = true;
                owner.NotifyGeneratedUseRefusal("server must not announce");
                Equal(true, owner.TryReserveGeneratedUseNotice(Terraria.Main.GameUpdateCount), "dedicated server does not reserve notice");
                Terraria.Main.dedServ = false; Terraria.Main.netMode = NetmodeID.MultiplayerClient;
                Terraria.Main.myPlayer = player.whoAmI + 1;
                Terraria.Main.GameUpdateCount = unchecked(oldTick + 60);
                owner.NotifyGeneratedUseRefusal("remote owner must not announce");
                Equal(true, owner.TryReserveGeneratedUseNotice(Terraria.Main.GameUpdateCount), "remote owner does not reserve notice");
            } finally { Terraria.Main.dedServ = oldServer; Terraria.Main.netMode = oldMode; Terraria.Main.myPlayer = oldLocal; Terraria.Main.GameUpdateCount = oldTick; }
        });
    }
}

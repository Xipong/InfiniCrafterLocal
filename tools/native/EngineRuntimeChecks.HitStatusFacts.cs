using System;
using System.Reflection;
using System.Linq;
using System.Security.Cryptography;
using System.Text.Json;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Common.Commands;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private static void ParentHitStatusFactsAreCertifiedAndMatchNativeRequests()
    {
        using var state = new NativeActorState();
        Terraria.Main.netMode = NetmodeID.SinglePlayer;
        Terraria.Main.player[0] = new Player();
        Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(41);
        var capture = typeof(GeneratorClient).GetMethod("VerifiedSourceHitStatusReference", BindingFlags.NonPublic | BindingFlags.Static)!;
        byte[] il = typeof(Projectile).GetMethod(nameof(Projectile.StatusNPC))!.GetMethodBody()!.GetILAsByteArray()!;
        string certificate = Convert.ToHexString(SHA256.HashData(il)).ToLowerInvariant();
        string moduleVersionId = typeof(Projectile).Module.ModuleVersionId.ToString();
        string catalogKey = certificate + ":" + moduleVersionId;
        Equal(true, NativeHitStatusCatalog.Sources.ContainsKey(catalogKey),
            "native test dependency must exercise a certified source, not silently skip coverage");
        foreach (var (projectileType, buffType, minimum, maximum) in new[] {
            (ProjectileID.GoldenShowerFriendly, BuffID.Ichor, 600, 600),
            (ProjectileID.ShadowFlameKnife, BuffID.ShadowFlame, 60, 179),
        })
        {
            var projectile = new Projectile();
            projectile.SetDefaults(projectileType);
            projectile.owner = 0;
            Equal(null, capture.Invoke(null, new object?[] { projectile, "unverified-method", moduleVersionId }), "unknown native code must not claim status facts");
            Equal(null, capture.Invoke(null, new object?[] { projectile, certificate, Guid.Empty.ToString() }), "identical method bytes in an unknown module cannot claim facts");
            object? observation = capture.Invoke(null, new object?[] { projectile, certificate, moduleVersionId });
            if (NativeHitStatusCatalog.Sources.ContainsKey(catalogKey))
                Equal(true, observation is not null, "verified release must expose its certified facts");
            // Other native versions deliberately decline, not an extrapolated fact.
            if (observation is null) continue;
            var fact = JsonSerializer.SerializeToElement(observation);
            var effect = fact.GetProperty("effects")[0];
            Equal(buffType, effect.GetProperty("buffId").GetInt32(), "exact loaded buff identifier");
            Equal(minimum, effect.GetProperty("durationTicksMin").GetInt32(), "minimum requested duration");
            Equal(maximum, effect.GetProperty("durationTicksMax").GetInt32(), "inclusive maximum requested duration");
            Equal(certificate, fact.GetProperty("sourceMethodSha256").GetString()!, "native source certificate preserved");
            int itemType = projectileType == ProjectileID.GoldenShowerFriendly ? ItemID.GoldenShower : ItemID.ShadowFlameKnife;
            var item = new Item(itemType);
            Terraria.Main.npc[0] = new NPC { whoAmI = 0, active = true };
            using var request = JsonDocument.Parse(new GeneratorClient().Prepare(item, item, Terraria.Main.player[0]).PayloadJson);
            var delivered = request.RootElement.GetProperty("itemA").GetProperty("directProjectileRaw").GetProperty("onHitStatusReference");
            Equal(CanonicalParentFactJson(fact), CanonicalParentFactJson(delivered), "native certificate and limits delivered intact to generator");
            Equal(0, item.buffType, "NPC-hit fact does not rewrite native self-use buff");
            Equal(-1, Array.IndexOf(Terraria.Main.npc[0].buffType, buffType), "craft capture does not execute hit effects");
            var dumpCapture = typeof(InfiniDumpCommand).GetMethod("ProjectileRawSnapshot", BindingFlags.NonPublic | BindingFlags.Static)!;
            object dump = dumpCapture.Invoke(null, new object[] { projectileType, item.shootSpeed, "item.shoot",
                itemType, item.Name, "literal-source-name", item.ammo, item.useAmmo, item.damage, "magic",
                item.shoot, item.shootSpeed, item.knockBack })!;
            var dumpFact = JsonSerializer.SerializeToElement(dump).GetProperty("onHitStatusReference");
            Equal(CanonicalParentFactJson(fact), CanonicalParentFactJson(dumpFact), "offline dump and live request share exact source certificate and limits");
            for (int trial = 0; trial < 16; trial++)
            {
                // Real native status method on isolated test actors. Production
                // capture never performs this mutating observation during craft.
                var target = new NPC { whoAmI = 0, active = true };
                Terraria.Main.npc[0] = target;
                projectile.StatusNPC(0);
                int slot = Array.IndexOf(target.buffType, buffType);
                Equal(true, slot >= 0, "native hit requests reported buff");
                Equal(true, target.buffTime[slot] >= minimum && target.buffTime[slot] <= maximum,
                    "native duration is within exact declared distribution");
            }
        }
        if (NativeHitStatusCatalog.Sources.TryGetValue(catalogKey, out var catalog))
        {
            // Every generated row is exposed without losing multiplicity. Native
            // execution below covers fixed, integer-random and stepped-random cases.
            foreach (var entry in catalog)
            {
                var source = new Projectile();
                source.SetDefaults(entry.Key);
                var delivered = JsonSerializer.SerializeToElement(capture.Invoke(null, new object?[] { source, certificate, moduleVersionId }));
                var effects = delivered.GetProperty("effects").EnumerateArray().ToArray();
                Equal(entry.Value.Length, effects.Length, "all certified requests delivered including multiple effects");
                for (int i = 0; i < effects.Length; i++)
                {
                    Equal(entry.Value[i].BuffId, effects[i].GetProperty("buffId").GetInt32(), "certified buff identity");
                    Equal(entry.Value[i].StepTicks, effects[i].GetProperty("durationTicksStep").GetInt32(), "distribution step is not flattened to a range");
                }
            }
            foreach (int type in new[] { ProjectileID.PygmySpear, ProjectileID.CursedArrow, ProjectileID.PoisonDart })
            {
                var projectile = new Projectile();
                projectile.SetDefaults(type);
                projectile.owner = 0;
                var expected = catalog[type];
                for (int trial = 0; trial < 32; trial++)
                {
                    var target = new NPC { whoAmI = 0, active = true };
                    Terraria.Main.npc[0] = target;
                    projectile.StatusNPC(0);
                    foreach (var effect in expected)
                    {
                        int slot = Array.IndexOf(target.buffType, effect.BuffId);
                        Equal(true, slot >= 0, "systematically extracted request exists in actual native method");
                        int ticks = target.buffTime[slot];
                        Equal(true, ticks >= effect.MinimumTicks && ticks <= effect.MaximumTicks
                            && (ticks - effect.MinimumTicks) % effect.StepTicks == 0,
                            "native fixed/stepped random distribution matches certified fact");
                    }
                }
            }
        }
        var unknown = new Projectile();
        unknown.SetDefaults(ProjectileID.WoodenArrowFriendly);
        Equal(null, capture.Invoke(null, new object?[] { unknown, certificate, moduleVersionId }), "uncovered type does not borrow another projectile status");
        unknown.type = ProjectileID.GoldenShowerFriendly;
        typeof(Projectile).GetProperty(nameof(Projectile.ModProjectile))!.SetValue(unknown, new HitStatusModProjectile());
        Equal(null, capture.Invoke(null, new object?[] { unknown, certificate, moduleVersionId }), "modded projectile cannot claim vanilla-only reference");
    }

    private sealed class HitStatusModProjectile : ModProjectile { }
}

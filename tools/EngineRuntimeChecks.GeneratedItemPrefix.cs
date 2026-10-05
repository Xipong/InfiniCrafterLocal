using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Text.Json;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Items;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;
using Terraria.ModLoader.IO;

internal static partial class EngineRuntimeChecks
{
    // The three registered checks use only pre-fix public APIs. New state is
    // observed through real SaveData/NetSend, so the same tests compile on RED.
    private static void GeneratedItemNativePrefixSurvivesActiveUse()
    {
        WithGeneratedPrefixScope(() => WithPlayer((player, _) => {
            var failures = new List<string>();
            foreach (var (lane, prefix) in new[] {
                ("melee", 0), ("melee", (int)PrefixID.Legendary), ("melee", (int)PrefixID.Broken),
                ("melee", (int)PrefixID.Zealous), ("melee", (int)PrefixID.Keen),
                ("ranged", (int)PrefixID.Unreal), ("magic", (int)PrefixID.Mythical),
            })
            {
                try
                {
                    var data = GeneratedPrefixFixture(lane);
                    int hostType = lane == "ranged" ? ItemID.Musket : lane == "magic" ? ItemID.AmethystStaff : ItemID.CopperShortsword;
                    var generated = GeneratedPrefixHost(data, hostType);
                    string definition = data.ToNetworkJson();
                    if (prefix != 0) Equal(true, generated.Item.Prefix(prefix), "native positive prefix " + prefix);
                    string expected = GeneratedPrefixStats(generated.Item);
                    if (prefix == PrefixID.Legendary) Equal(14, generated.Item.damage, "native 12 -> 14 control");
                    if (prefix == PrefixID.Broken) Equal(8, generated.Item.damage, "native 12 -> 8 control");
                    if (prefix == PrefixID.Zealous) Equal(5, generated.Item.crit - GeneratedPrefixHost(data).Item.crit, "native additive crit-only control");
                    for (int repeat = 0; repeat < 3; repeat++)
                    {
                        Equal(true, generated.CanUseItem(player), "body use accepted");
                        Equal(expected, GeneratedPrefixStats(generated.Item), "all native prefix fields survive use " + prefix + "/" + repeat);
                    }
                    // Rehydration of this same instance is idempotent, not an extra prefix application.
                    GeneratedPrefixSetData(generated, data);
                    Equal(expected, GeneratedPrefixStats(generated.Item), "same-definition projection is idempotent");
                    var clone = (GeneratedItem)generated.Item.Clone().ModItem;
                    Equal(true, clone.CanUseItem(player), "native Item.Clone remains usable");
                    Equal(expected, GeneratedPrefixStats(clone.Item), "clone preserves base snapshot and prefix");
                    Equal(definition, data.ToNetworkJson(), "instance prefix does not mutate canonical definition");
                }
                catch (Exception error) { failures.Add(lane + " prefix " + prefix + ": " + error); }
            }
            if (failures.Count != 0) throw new InvalidOperationException(string.Join(Environment.NewLine, failures));
        }));
    }

    private static void GeneratedItemNativePrefixPlacementAndAmmoStayIndependent()
    {
        WithGeneratedPrefixScope(() => WithPlayer((player, _) => {
            foreach (int prefix in new[] { 0, (int)PrefixID.Legendary, (int)PrefixID.Broken, (int)PrefixID.Zealous })
            {
                var data = GeneratedPrefixFixture();
                var place = new RuntimeBindingSpec {
                    Id = "place", Input = RuntimeInputKind.AlternateUse, Role = RuntimeEntityRole.Primary,
                    UsePolicy = new RuntimeBindingUsePolicySpec { StackCost = 1, Action = new RuntimeBindingActionSpec {
                        Kind = RuntimeBindingAction.PlaceItem, TargetId = data.RuntimeProgram.ItemEntityId,
                        Placement = new RuntimePlacementSpec { TileId = -1, WallId = 1, PlaceStyle = 0 },
                    } },
                };
                data.RuntimeProgram.Bindings = new[] { data.RuntimeProgram.Bindings[0], place };
                var generated = GeneratedPrefixHost(data);
                if (prefix != 0) Equal(true, generated.Item.Prefix(prefix), "native placement control accepts prefix");
                string expected = GeneratedPrefixStats(generated.Item);
                // Exercise the actual projection without claiming a world placement or ledger admission.
                var projection = typeof(GeneratedItem).GetMethod("ApplyActiveUseProjection", BindingFlags.NonPublic | BindingFlags.Instance)!;
                projection.Invoke(generated, new object[] { place });
                Equal(0, generated.Item.damage, "placement suppresses contact damage");
                Equal(prefix, (int)generated.Item.prefix, "placement preserves actual accepted prefix token");
                Equal(1, generated.Item.createWall, "authored wall selected");
                Equal(true, generated.CanUseItem(player), "primary body use after placement");
                Equal(expected, GeneratedPrefixStats(generated.Item), "placement -> body restores every prefix field");
                Equal(-1, generated.Item.createWall, "placement field retired");
            }
            var ammoData = GeneratedPrefixFixture();
            ammoData.Gameplay.AmmoCategory = "bullet";
            ammoData.Gameplay.AmmoProjectileId = ProjectileID.Bullet;
            ammoData.Gameplay.AmmoShootSpeedPxPerTick = 7.25f;
            var ammo = GeneratedPrefixHost(ammoData);
            Equal(false, ammo.Item.Prefix(PrefixID.Legendary), "native ammo prefix refusal is not overridden");
            Equal(true, ammo.CanUseItem(player), "independent ammo direct-use accepted");
            Equal(AmmoID.Bullet, ammo.Item.ammo, "independent authored ammo category retained");
            Equal(ProjectileID.Bullet, ammo.Item.shoot, "independent authored ammo projectile retained");
            Equal(7.25f, ammo.Item.shootSpeed, "independent authored ammo speed retained");
            Equal(0, (int)ammo.Item.prefix, "unsupported prefix is not forced");
        }));
    }

    private static void GeneratedItemNativePrefixCompactHydration()
    {
        WithGeneratedPrefixScope(() => {
            using var serializer = WithPersistenceBoolSerializer();
            var failures = new List<string>();
            foreach (int prefix in new[] { 0, (int)PrefixID.Legendary, (int)PrefixID.Broken, (int)PrefixID.Zealous })
            foreach (string boundary in new[] { "save", "network" })
            {
                try
                {
                    var data = GeneratedPrefixFixture();
                    var original = GeneratedPrefixHost(data);
                    if (prefix != 0) Equal(true, original.Item.Prefix(prefix), "native serialization positive control");
                    string expected = GeneratedPrefixStats(original.Item);
                    string definition = data.ToNetworkJson();
                    var unresolved = GeneratedPrefixHost(GeneratedItemData.Placeholder());
                    if (boundary == "save")
                    {
                        var custom = new TagCompound(); original.SaveData(custom);
                        var native = PersistenceNbtRoundtrip(new TagCompound { ["data"] = custom, ["prefix"] = (byte)prefix });
                        unresolved.LoadData(native.GetCompound("data"));
                        // This is the installed native ItemIO prefix importer, in its
                        // exact post-LoadData order, not a substitute prefix algorithm.
                        typeof(ItemIO).GetMethod("LoadModdedPrefix", BindingFlags.Static | BindingFlags.NonPublic)!
                            .Invoke(null, new object[] { unresolved.Item, native });
                    }
                    else
                    {
                        // Native ItemIO.Receive applies prefix before ModItem.NetReceive.
                        // The inert host must reject it; the custom payload retains it.
                        Equal(false, unresolved.Item.Prefix(prefix), "native inert receive prefix refusal");
                        GeneratedPrefixNetRoundtrip(original, unresolved);
                    }
                    Equal(true, GeneratedItemData.IsPlayerSaveReferenceOnly(unresolved.Data), "actual compact reference import");
                    Equal(0, unresolved.Item.damage, "unresolved reference remains inert");
                    var repeatedSave = new TagCompound(); unresolved.SaveData(repeatedSave);
                    Equal(prefix, repeatedSave.GetInt("infiniNativePrefix"), "pending integer prefix survives unresolved save");
                    var forwarded = GeneratedPrefixHost(GeneratedItemData.Placeholder());
                    GeneratedPrefixNetRoundtrip(unresolved, forwarded);
                    var pendingClone = (GeneratedItem)unresolved.Item.Clone().ModItem;
                    foreach (var hydrated in new[] { unresolved, pendingClone, forwarded })
                    {
                        GeneratedPrefixSetData(hydrated, data);
                        Equal(expected, GeneratedPrefixStats(hydrated.Item), "native prefix restored on full hydration " + boundary);
                        WithPlayer((player, _) => {
                            Equal(true, hydrated.CanUseItem(player), "hydrated body usable");
                            Equal(expected, GeneratedPrefixStats(hydrated.Item), "hydrated prefix remains stable on use");
                        });
                    }
                    Equal(definition, data.ToNetworkJson(), "prefix never enters accepted definition bytes");
                }
                catch (Exception error) { failures.Add(boundary + " prefix " + prefix + ": " + error); }
            }
            // Legacy full-data native prefix import still works. This invokes the
            // real installed importer with an already-resolved item, not a legacy JSON migration.
            var legacy = GeneratedPrefixHost(GeneratedPrefixFixture());
            typeof(ItemIO).GetMethod("LoadModdedPrefix", BindingFlags.Static | BindingFlags.NonPublic)!
                .Invoke(null, new object[] { legacy.Item, new TagCompound { ["prefix"] = (byte)PrefixID.Legendary } });
            Equal((int)PrefixID.Legendary, (int)legacy.Item.prefix, "legacy native token is recognized after full data");
            string legacyStats = GeneratedPrefixStats(legacy.Item);
            GeneratedPrefixSetData(legacy, legacy.Data);
            Equal(legacyStats, GeneratedPrefixStats(legacy.Item), "legacy live prefix survives reapplication");
            foreach (int version in new[] { 5, 6 })
            {
                var legacyReceiver = GeneratedPrefixHost(GeneratedPrefixFixture());
                Equal(true, legacyReceiver.Item.Prefix(PrefixID.Legendary), "legacy full native host accepts prefix");
                string oldStats = GeneratedPrefixStats(legacyReceiver.Item);
                var fullData = legacyReceiver.Data;
                using var stream = new MemoryStream();
                using (var writer = new BinaryWriter(stream, System.Text.Encoding.UTF8, true))
                {
                    writer.Write(version); writer.Write(fullData.ToPlayerSaveJson());
                    if (version == 6) writer.Write(legacyReceiver.PresentationToken);
                }
                stream.Position = 0;
                legacyReceiver.NetReceive(new BinaryReader(stream));
                Equal(true, GeneratedItemData.IsPlayerSaveReferenceOnly(legacyReceiver.Data), "old payload admitted without definition migration");
                GeneratedPrefixSetData(legacyReceiver, fullData);
                Equal(oldStats, GeneratedPrefixStats(legacyReceiver.Item), "legacy v" + version + " keeps existing native token");
            }
            if (failures.Count != 0) throw new InvalidOperationException(string.Join(Environment.NewLine, failures));
        });
    }

    private static GeneratedItemData GeneratedPrefixFixture(string lane = "melee")
    {
        var data = lane == "melee" ? GeneratedItemData.Placeholder() : RootSpawnFixture(0, 1);
        data.Id = "native-prefix-lifecycle"; data.SourceMode = "test_fixture";
        data.Gameplay.Damage = 12; data.Gameplay.DamageClass = lane;
        data.Gameplay.Knockback = 3f; data.Gameplay.UseTime = data.Gameplay.UseAnimation = 18;
        data.Gameplay.UseStyleName = "swing"; data.Gameplay.Value = 10000;
        data.RuntimeProgram.ItemUse.Configured = true;
        data.RuntimeProgram.ItemUse.UseStyle = "swing";
        data.RuntimeProgram.ItemUse.DisableMeleeHitbox = false;
        data.RuntimeProgram.ItemUse.HideUseGraphic = false;
        if (lane != "melee")
        {
            data.RuntimeProgram.TryGetEntity("root")!.Spawn.SpeedPxPerTick = 10f;
            data.Gameplay.ManaCost = lane == "magic" ? 20 : 0;
            return data;
        }
        data.RuntimeProgram.Bindings = new[] { new RuntimeBindingSpec {
            Id = "body", Input = RuntimeInputKind.PrimaryUse, Role = RuntimeEntityRole.Primary,
            UsePolicy = new RuntimeBindingUsePolicySpec { ContactDamage = true, Action = new RuntimeBindingActionSpec {
                Kind = RuntimeBindingAction.UseItemBody, TargetId = data.RuntimeProgram.ItemEntityId,
            } },
        } };
        return data;
    }

    private static GeneratedItem GeneratedPrefixHost(GeneratedItemData data, int hostType = ItemID.CopperShortsword)
    {
        // Separate native host types keep native per-type prefix-category caches
        // isolated between class controls; no production pool override is installed.
        var item = new Item(hostType);
        var generated = new GeneratedItem();
        typeof(ModType<Item>).GetProperty("Entity", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)!.SetValue(generated, item);
        typeof(Item).GetProperty("ModItem")!.SetValue(item, generated);
        GeneratedPrefixSetData(generated, data);
        return generated;
    }

    private static void GeneratedPrefixSetData(GeneratedItem generated, GeneratedItemData data)
        => typeof(GeneratedItem).GetMethod("SetData", BindingFlags.Instance | BindingFlags.NonPublic,
            null, new[] { typeof(GeneratedItemData), typeof(bool), typeof(bool), typeof(bool) }, null)!
            .Invoke(generated, new object[] { data, false, false, false });

    private static string GeneratedPrefixStats(Item item) => JsonSerializer.Serialize(new {
        item.damage, item.knockBack, item.crit, item.useTime, item.useAnimation,
        item.reuseDelay, item.shootSpeed, item.scale, item.value, item.rare, item.mana,
        prefix = (int)item.prefix, damageClass = item.DamageType.FullName,
    });

    private static void GeneratedPrefixNetRoundtrip(GeneratedItem from, GeneratedItem to)
    {
        using var stream = new MemoryStream();
        using (var writer = new BinaryWriter(stream, System.Text.Encoding.UTF8, true)) from.NetSend(writer);
        stream.Position = 0;
        using var reader = new BinaryReader(stream);
        to.NetReceive(reader);
        Equal(stream.Length, stream.Position, "custom native payload consumed exactly");
    }

    private static void WithGeneratedPrefixScope(Action check)
    {
        int mode = Terraria.Main.netMode; var random = Terraria.Main.rand;
        var registry = typeof(global::InfiniCrafterLocal.InfiniCrafterLocalMod).GetProperty("GeneratedItems")!;
        object? savedRegistry = registry.GetValue(null);
        try
        {
            // Fixtures deliberately have no matching world registry; no hydration
            // request, registration, files/assets or network delivery is performed.
            Terraria.Main.netMode = NetmodeID.SinglePlayer;
            Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(17);
            registry.SetValue(null, null);
            check();
        }
        finally { registry.SetValue(null, savedRegistry); Terraria.Main.netMode = mode; Terraria.Main.rand = random; }
    }
}

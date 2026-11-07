using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Content.Items;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private static void ParentNativeFactEnvelopesKeepTheirExactShape()
    {
        using var state = new NativeActorState();
        Terraria.Main.netMode = NetmodeID.SinglePlayer;
        Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(17);
        var owner = new Player { name = "parent_fact_probe" };
        owner.inventory[54] = new Item(ItemID.WoodenArrow, 23);
        owner.inventory[55] = new Item(ItemID.FlamingArrow, 11);
        var sword = new Item(ItemID.WoodenSword);
        var prefixed = sword.Clone();
        Equal(true, prefixed.Prefix(PrefixID.Legendary), "native prefix fixture accepts");
        var workbench = new Item(ItemID.WorkBench);
        Item Generated(bool placing)
        {
            var data = GeneratedItemData.Placeholder();
            data.Id = placing ? "fact_placed" : "fact_unplaced";
            data.Name = "Generated fact fixture";
            data.SourceMode = "test_fixture";
            data.Gameplay.Damage = 37;
            data.Gameplay.DamageClass = "melee";
            data.RuntimeProgram.ItemUse.Configured = true;
            if (placing)
                data.RuntimeProgram.Bindings = new[] { new RuntimeBindingSpec {
                    Id = "place_use", Input = RuntimeInputKind.PrimaryUse, Role = RuntimeEntityRole.Primary,
                    UsePolicy = new RuntimeBindingUsePolicySpec {
                        StackCost = 1,
                        Action = new RuntimeBindingActionSpec { Kind = RuntimeBindingAction.PlaceItem,
                            TargetId = data.RuntimeProgram.ItemEntityId,
                            Placement = new RuntimePlacementSpec { TileId = workbench.createTile, WallId = -1, PlaceStyle = 0 } },
                    },
                } };
            var item = new Item(ItemID.WoodenSword);
            var host = new GeneratedItem();
            typeof(ModType<Item>).GetProperty("Entity", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)!.SetValue(host, item);
            typeof(Item).GetProperty("ModItem")!.SetValue(item, host);
            typeof(GeneratedItem).GetProperty("Data")!.SetValue(host, data);
            data.ApplyToItem(item);
            return item;
        }
        int rarityCaptures = 0, directProjectileCaptures = 0, sourceGraphCaptures = 0;
        Func<Func<Item, object>, Item, object> observeRarity = (original, item) => {
            rarityCaptures++;
            return original(item);
        };
        Func<Func<Item, object?>, Item, object?> observeProjectile = (original, item) => {
            directProjectileCaptures++;
            return original(item);
        };
        Func<Func<Item, JsonObject?, JsonObject>, Item, JsonObject?, JsonObject> observeGraph = (original, item, facts) => {
            sourceGraphCaptures++;
            return original(item, facts);
        };
        using var graphObserver = new MonoMod.RuntimeDetour.Hook(
            typeof(GeneratorClient).GetMethod("CaptureParentSourceGraph", BindingFlags.Static | BindingFlags.NonPublic)!, observeGraph);
        using var rarityObserver = new MonoMod.RuntimeDetour.Hook(
            typeof(GeneratorClient).GetMethod("RarityDetailsFromItem", BindingFlags.Static | BindingFlags.NonPublic)!, observeRarity);
        using var projectileObserver = new MonoMod.RuntimeDetour.Hook(
            typeof(GeneratorClient).GetMethod("DirectProjectileRawFromItem", BindingFlags.Static | BindingFlags.NonPublic)!, observeProjectile);
        var snapshots = new SortedDictionary<string, string>(StringComparer.Ordinal);
        foreach (var (label, item) in new[] {
            ("vanilla", sword), ("prefixed", prefixed), ("ammo_weapon", new Item(ItemID.WoodenBow)),
            ("ammo_stack", new Item(ItemID.WoodenArrow, 13)), ("placement", workbench),
            ("generated", Generated(false)), ("generated_placement", Generated(true)),
        })
        {
            rarityCaptures = directProjectileCaptures = sourceGraphCaptures = 0;
            using var request = JsonDocument.Parse(new GeneratorClient().Prepare(item, item, owner).PayloadJson);
            Equal(2, rarityCaptures, label + " one rarity observation per A/B parent");
            Equal(2, directProjectileCaptures, label + " one direct-projectile observation per A/B parent");
            bool nativeParent = label is not ("generated" or "generated_placement");
            Equal(nativeParent ? 2 : 0, sourceGraphCaptures, label + " source graph captured once per native A/B parent, never for a generated proxy");
            JsonElement root = request.RootElement.GetProperty("itemA");
            JsonElement facts = root.GetProperty("runtimeFacts");
            JsonElement fingerprint = root.GetProperty("fingerprint");
            string Keys(IEnumerable<string> keys) => string.Join(",", keys.Distinct(StringComparer.Ordinal).OrderBy(key => key, StringComparer.Ordinal));
            // Require the complete native field floor, but do not reject new
            // source observations. Every captured fact must survive each envelope
            // except its explicit identity/shape exclusions below.
            foreach (string key in ("accessory,ammo,ammoCategoryName,armorPenetration,autoReuse,axePower,bait,bodySlot,buffTime,buffType,"
                + "channel,consumable,createTile,createWall,crit,damage,damageClass,defense,dropSeedsIfInInventory,fishingPole,"
                + "hammerPower,headSlot,healLife,healMana,itemScale,knockback,legSlot,lifeRegen,manaCost,material,maxStack,"
                + "noMelee,noUseGraphic,notAmmo,pickPower,placeStyle,potion,rare,rarityDetails,reuseDelay,shoot,"
                + "shootProjectileFullName,shootSpeed,type,useAmmo,useAmmoCategoryName,useAnimation,useLimitPerAnimation,"
                + "useStyle,useStyleName,useTime,useTurn,value").Split(','))
                Equal(true, facts.TryGetProperty(key, out _), label + " native field retained: " + key);
            var factKeys = facts.EnumerateObject().Select(p => p.Name).ToArray();
            Equal(Keys(factKeys.Except(new[] { "type", "buffType", "buffTime" }).Concat((
                "id,name,sourceMod,internalName,fullName,tooltipLines,tooltipSource,prefix,originalPrefix,prefixIgnored,"
                + "stack,moddedOrigin,directProjectileRaw,effectiveProjectileRaw,ammoRaw,tags,runtimeFacts,autoFeatures,"
                + "nameTokens,fingerprint,generatedData,craftInput").Split(','))),
                Keys(root.EnumerateObject().Select(p => p.Name)), label + " exact root projection of all captured facts");
            Equal(Keys(factKeys.Except(new[] { "material", "reuseDelay", "shootProjectileFullName" }).Concat((
                "sourceMod,internalName,fullName,isVanilla,name,prefix,originalPrefix,prefixIgnored,directProjectileRaw,"
                + "effectiveProjectileRaw,ammoRaw,runtimeFacts,autoFeatures,nameTokens").Split(','))),
                Keys(fingerprint.EnumerateObject().Select(p => p.Name)), label + " exact fingerprint projection of all captured facts");
            var unprefixed = nativeParent ? new Item(item.type) : item;
            Equal(unprefixed.damage, facts.GetProperty("damage").GetInt32(), label + " unprefixed native damage");
            Equal(unprefixed.crit, facts.GetProperty("crit").GetInt32(), label + " unprefixed native crit");
            Equal(unprefixed.ArmorPenetration, facts.GetProperty("armorPenetration").GetInt32(), label + " literal armor penetration");
            Equal(unprefixed.scale, facts.GetProperty("itemScale").GetSingle(), label + " unprefixed native scale");
            Equal(unprefixed.shoot, facts.GetProperty("shoot").GetInt32(), label + " own native projectile identity");
            Equal(unprefixed.shootSpeed, facts.GetProperty("shootSpeed").GetSingle(), label + " native shoot speed, not a child spawn speed");
            AssertParentFingerprintNativeFacts(facts, fingerprint.GetProperty("runtimeFacts"), label + " nested native facts");
            Equal(CanonicalParentFactJson(root), CanonicalParentFactJson(request.RootElement.GetProperty("itemB")), label + " complete A/B observations agree for the same parent");
            foreach (JsonElement view in new[] { root, facts, fingerprint })
            {
                Equal(nativeParent, view.TryGetProperty("parentSourceGraph", out JsonElement graph), label + " explicit graph presence by parent provenance");
                Equal(nativeParent, view.TryGetProperty("nativeItemDispatchReference", out JsonElement dispatch), label + " dispatcher source belongs to native parents, not generated host defaults");
                if (nativeParent)
                {
                    Equal("parent_reachable_compiled_source_graph", graph.GetProperty("source").GetString()!, label + " source graph provenance");
                    Equal(CanonicalParentFactJson(facts.GetProperty("parentSourceGraph")), CanonicalParentFactJson(graph), label + " exact graph across native fact envelopes");
                    Equal("conditional_native_item_dispatch_csharp", dispatch.GetProperty("source").GetString()!, label + " dispatcher source provenance");
                    Equal(1, dispatch.GetProperty("version").GetInt32(), label + " dispatcher source contract");
                    Equal(item.type, dispatch.GetProperty("relevanceItemType").GetInt32(), label + " dispatcher relevance uses the actual parent identity");
                    Equal(true, dispatch.GetProperty("unknowns").EnumerateArray().Any(value => value.GetString() == "source_receiver_identity_and_runtime_entry_not_proved"), label + " source relevance is not an executed effect");
                    var roots = dispatch.GetProperty("roots").EnumerateArray().ToArray();
                    Equal("ApplyEquipFunctional,ItemCheck_Inner", Keys(roots.Select(value => value.GetProperty("root").GetString()!)), label + " independent dispatcher roots retained");
                    foreach (var sourceRoot in roots)
                    {
                        var method = typeof(Player).GetMethods(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)
                            .Single(candidate => candidate.Name == sourceRoot.GetProperty("root").GetString());
                        AssertParentSourceCertificate(sourceRoot.GetProperty("rootCertificate"), method, label + " actual native dispatcher certificate");
                    }
                }
            }
            Equal(root.GetProperty("id").GetInt32(), facts.GetProperty("type").GetInt32(), label + " root id retains native type");
            Equal(false, root.TryGetProperty("type", out _), label + " root has no nested type alias");
            Equal(false, root.TryGetProperty("buffType", out _), label + " root excludes native buff type");
            Equal(false, root.TryGetProperty("buffTime", out _), label + " root excludes native buff time");
            foreach (string key in new[] { "material", "reuseDelay", "shootProjectileFullName" })
                Equal(false, fingerprint.TryGetProperty(key, out _), label + " fingerprint excludes " + key);
            foreach (var property in facts.EnumerateObject())
            {
                if (root.TryGetProperty(property.Name, out JsonElement direct))
                    Equal(CanonicalParentFactJson(property.Value), CanonicalParentFactJson(direct), label + " root fact " + property.Name);
                if (fingerprint.TryGetProperty(property.Name, out JsonElement repeated))
                    AssertParentFingerprintNativeFacts(property.Value, repeated, label + " fingerprint fact " + property.Name);
            }
            if (label == "generated")
                foreach (string key in new[] { "createTile", "createWall", "placeStyle" })
                    Equal(JsonValueKind.Null, facts.GetProperty(key).ValueKind, "absent generated placement keeps null " + key);
            if (label == "generated_placement")
                Equal(0, facts.GetProperty("placeStyle").GetInt32(), "explicit zero placement style survives");
            if (label == "ammo_weapon")
                Equal(false, CanonicalParentFactJson(root.GetProperty("ammoRaw")) == CanonicalParentFactJson(fingerprint.GetProperty("ammoRaw")), "player ammo observations remain separate from fingerprint reference ammo");
            snapshots[label] = CanonicalParentFactJson(root);
        }
        // Optional local before/after evidence; never an application output or a fixture import.
        string? output = Environment.GetEnvironmentVariable("INFINI_PARENT_FACT_SNAPSHOT");
        if (!string.IsNullOrWhiteSpace(output))
            File.WriteAllText(output, JsonSerializer.Serialize(snapshots, new JsonSerializerOptions { WriteIndented = true }));
    }

    private static void ParentAmmoFactsKeepNativeCategoryAndInventoryFlag()
    {
        using var state = new NativeActorState();
        Terraria.Main.netMode = NetmodeID.SinglePlayer;
        Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(31);
        var owner = new Player { name = "parent_ammo_fact_probe" };
        foreach (var (type, required, inventorySeedDrop) in new[] {
            (ItemID.Musket, "bullet", false), (ItemID.Blowpipe, "dart", true),
            (ItemID.Blowgun, "dart", true), (ItemID.WoodenBow, "arrow", false),
            (ItemID.Seed, "", false), (ItemID.FallenStar, "", false),
        })
        {
            var item = new Item(type);
            using var request = JsonDocument.Parse(new GeneratorClient().Prepare(item, item, owner).PayloadJson);
            foreach (string parent in new[] { "itemA", "itemB" })
            {
                JsonElement root = request.RootElement.GetProperty(parent);
                foreach (JsonElement facts in new[] { root, root.GetProperty("runtimeFacts"), root.GetProperty("fingerprint") })
                {
                    Equal(required, facts.GetProperty("useAmmoCategoryName").GetString()!, type + " literal native required ammo category");
                    Equal(item.useAmmo, facts.GetProperty("useAmmo").GetInt32(), type + " native useAmmo remains unchanged");
                    Equal(inventorySeedDrop, facts.GetProperty("dropSeedsIfInInventory").GetBoolean(), type + " exact native inventory flag");
                }
                Equal(item.shoot, root.GetProperty("shoot").GetInt32(), type + " own shoot is not replaced by ammo");
            }
            Equal(type, item.type, "request leaves source identity unchanged");
        }
    }

    private static void AssertParentSourceCertificate(JsonElement certificate, MethodBase method, string label)
    {
        Equal(method.DeclaringType!.FullName + "." + method.Name, certificate.GetProperty("method").GetString()!, label + " method identity");
        Equal(method.Module.ModuleVersionId.ToString(), certificate.GetProperty("sourceModuleVersionId").GetString()!, label + " loaded module identity");
        Equal(Convert.ToHexString(SHA256.HashData(method.GetMethodBody()!.GetILAsByteArray()!)).ToLowerInvariant(),
            certificate.GetProperty("sourceMethodSha256").GetString()!, label + " independently hashed native IL");
    }

    private static string CanonicalParentFactJson(JsonElement element)
    {
        using var stream = new MemoryStream();
        using (var writer = new Utf8JsonWriter(stream))
            Write(element, writer);
        return Encoding.UTF8.GetString(stream.ToArray());

        static void Write(JsonElement value, Utf8JsonWriter writer)
        {
            if (value.ValueKind == JsonValueKind.Object)
            {
                writer.WriteStartObject();
                foreach (var property in value.EnumerateObject().OrderBy(p => p.Name, StringComparer.Ordinal))
                {
                    writer.WritePropertyName(property.Name);
                    Write(property.Value, writer);
                }
                writer.WriteEndObject();
            }
            else if (value.ValueKind == JsonValueKind.Array)
            {
                writer.WriteStartArray();
                foreach (var child in value.EnumerateArray()) Write(child, writer);
                writer.WriteEndArray();
            }
            else value.WriteTo(writer);
        }
    }
}

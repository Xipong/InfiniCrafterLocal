using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using System.Text.Json;
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
        int rarityCaptures = 0, directProjectileCaptures = 0;
        Func<Func<Item, object>, Item, object> observeRarity = (original, item) => {
            rarityCaptures++;
            return original(item);
        };
        Func<Func<Item, object?>, Item, object?> observeProjectile = (original, item) => {
            directProjectileCaptures++;
            return original(item);
        };
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
            rarityCaptures = directProjectileCaptures = 0;
            using var request = JsonDocument.Parse(new GeneratorClient().Prepare(item, item, owner).PayloadJson);
            Equal(2, rarityCaptures, label + " one rarity observation per A/B parent");
            Equal(2, directProjectileCaptures, label + " one direct-projectile observation per A/B parent");
            JsonElement root = request.RootElement.GetProperty("itemA");
            JsonElement facts = root.GetProperty("runtimeFacts");
            JsonElement fingerprint = root.GetProperty("fingerprint");
            Equal("accessory,ammo,ammoCategoryName,ammoRaw,autoFeatures,autoReuse,axePower,bait,bodySlot,channel,"
                + "consumable,craftInput,createTile,createWall,crit,damage,damageClass,defense,directProjectileRaw,"
                + "effectiveProjectileRaw,fingerprint,fishingPole,fullName,generatedData,hammerPower,headSlot,healLife,healMana,"
                + "id,internalName,knockback,legSlot,manaCost,material,maxStack,moddedOrigin,name,nameTokens,noMelee,"
                + "noUseGraphic,notAmmo,originalPrefix,pickPower,placeStyle,potion,prefix,prefixIgnored,rare,rarityDetails,"
                + "reuseDelay,runtimeFacts,shoot,shootProjectileFullName,shootSpeed,sourceMod,stack,tags,tooltipLines,"
                + "tooltipSource,useAmmo,useAnimation,useStyle,useStyleName,useTime,useTurn,value",
                string.Join(",", root.EnumerateObject().Select(p => p.Name).OrderBy(n => n, StringComparer.Ordinal)), label + " exact root keys");
            Equal("accessory,ammo,ammoCategoryName,ammoRaw,autoFeatures,autoReuse,axePower,bait,bodySlot,buffTime,buffType,"
                + "channel,consumable,createTile,createWall,crit,damage,damageClass,defense,directProjectileRaw,"
                + "effectiveProjectileRaw,fishingPole,fullName,hammerPower,headSlot,healLife,healMana,internalName,isVanilla,"
                + "knockback,legSlot,manaCost,maxStack,name,nameTokens,noMelee,noUseGraphic,notAmmo,originalPrefix,pickPower,"
                + "placeStyle,potion,prefix,prefixIgnored,rare,rarityDetails,runtimeFacts,shoot,shootSpeed,sourceMod,type,"
                + "useAmmo,useAnimation,useStyle,useStyleName,useTime,useTurn,value",
                string.Join(",", fingerprint.EnumerateObject().Select(p => p.Name).OrderBy(n => n, StringComparer.Ordinal)), label + " exact fingerprint keys");
            Equal("accessory,ammo,ammoCategoryName,autoReuse,axePower,bait,bodySlot,buffTime,buffType,channel,consumable,"
                + "createTile,createWall,crit,damage,damageClass,defense,fishingPole,hammerPower,headSlot,healLife,healMana,"
                + "knockback,legSlot,manaCost,material,maxStack,noMelee,noUseGraphic,notAmmo,pickPower,placeStyle,potion,rare,"
                + "rarityDetails,reuseDelay,shoot,shootProjectileFullName,shootSpeed,type,useAmmo,useAnimation,useStyle,"
                + "useStyleName,useTime,useTurn,value",
                string.Join(",", facts.EnumerateObject().Select(p => p.Name).OrderBy(n => n, StringComparer.Ordinal)), label + " exact facts keys");
            Equal(CanonicalParentFactJson(facts), CanonicalParentFactJson(fingerprint.GetProperty("runtimeFacts")), label + " same nested native facts");
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
                    Equal(CanonicalParentFactJson(property.Value), CanonicalParentFactJson(repeated), label + " fingerprint fact " + property.Name);
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

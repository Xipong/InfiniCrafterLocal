using System;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using InfiniCrafterLocal.Common.Services;

internal static partial class EngineRuntimeChecks
{
    private static void InventoryAmmoKeepsGeneratedDefinition()
    {
        var scan = typeof(GeneratorClient).GetMethod("FindPlayerAmmoCandidates", BindingFlags.Static | BindingFlags.NonPublic)!;
        var snapshot = typeof(GeneratorClient).GetMethod("AmmoItemRawSnapshot", BindingFlags.Static | BindingFlags.NonPublic)!;
        var owner = new Terraria.Player();
        Terraria.Item GeneratedAmmo(string id, int damage, int projectile, float speed)
        {
            var data = InfiniCrafterLocal.Common.Models.GeneratedItemData.Placeholder();
            data.Id = id;
            data.Name = id;
            data.SourceMode = "test_fixture";
            data.Gameplay.Damage = damage;
            data.Gameplay.DamageClass = "magic";
            data.Gameplay.Knockback = 6f;
            data.Gameplay.MaxStack = 777;
            data.Gameplay.AmmoCategory = "arrow";
            data.Gameplay.AmmoProjectileId = projectile;
            data.Gameplay.AmmoShootSpeedPxPerTick = speed;
            var item = new Terraria.Item();
            item.SetDefaults(Terraria.ID.ItemID.WoodenArrow);
            var generated = new InfiniCrafterLocal.Content.Items.GeneratedItem();
            typeof(Terraria.ModLoader.ModType<Terraria.Item>).GetProperty("Entity", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)!
                .SetValue(generated, item);
            typeof(Terraria.Item).GetProperty("ModItem")!.SetValue(item, generated);
            typeof(InfiniCrafterLocal.Content.Items.GeneratedItem).GetProperty("Data")!.SetValue(generated, data);
            data.ApplyToItem(item);
            item.stack = 17;
            item.favorited = true;
            return item;
        }
        // Same vanilla-allocated host type, distinct authored instance definitions.
        // This exercises real DTO/ModItem hooks without full content registration.
        owner.inventory[4] = GeneratedAmmo("ammo_first", 120, Terraria.ID.ProjectileID.FireArrow, 9.5f);
        owner.inventory[54] = GeneratedAmmo("ammo_second", 210, Terraria.ID.ProjectileID.FrostburnArrow, 7.25f);
        owner.inventory[55].SetDefaults(Terraria.ID.ItemID.WoodenArrow);
        owner.inventory[55].stack = 31;
        owner.inventory[0].SetDefaults(Terraria.ID.ItemID.WoodenSword); // not ammo
        owner.inventory[1].SetDefaults(Terraria.ID.ItemID.MusketBall); // wrong category
        var saveOnly = GeneratedAmmo("ammo_save_ref", 80, Terraria.ID.ProjectileID.FireArrow, 5f);
        var saveMod = (InfiniCrafterLocal.Content.Items.GeneratedItem)saveOnly.ModItem;
        saveMod.LoadData(new Terraria.ModLoader.IO.TagCompound { ["infiniJson"] = saveMod.Data.ToPlayerSaveJson() });
        Equal(0, saveOnly.ammo, "unhydrated save-only ammo is inert");
        owner.inventory[2] = saveOnly;
        string ItemStats(Terraria.Item item) => JsonSerializer.Serialize(new {
            item.type, item.prefix, item.damage, item.ammo, item.shoot, item.shootSpeed,
            item.knockBack, item.maxStack, item.stack, item.favorited, DamageClass = item.DamageType.Type,
        });
        string[] originalStats = new[] { 4, 54, 55 }.Select(slot => ItemStats(owner.inventory[slot])).ToArray();
        string[] definitions = new[] { 4, 54 }.Select(slot => JsonSerializer.Serialize(((InfiniCrafterLocal.Content.Items.GeneratedItem)owner.inventory[slot].ModItem).Data)).ToArray();
        var failures = new System.Collections.Generic.List<string>();
        foreach (int limit in new[] { 1, 3 })
        {
            var candidates = (System.Collections.IList)scan.Invoke(null, new object[] { Terraria.ID.AmmoID.Arrow, owner, limit })!;
            Equal(limit, candidates.Count, "candidate limit and unrelated-item filtering");
            int[] slots = { 4, 54, 55 };
            for (int i = 0; i < candidates.Count; i++)
            {
                try
                {
                    object candidate = candidates[i]!;
                    int slot = (int)candidate.GetType().GetProperty("InventorySlot")!.GetValue(candidate)!;
                    var copy = (Terraria.Item)candidate.GetType().GetProperty("Item")!.GetValue(candidate)!;
                    Equal(slots[i], slot, "inventory scan order unchanged");
                    Terraria.Item source = owner.inventory[slot];
                    Equal(originalStats[i], ItemStats(source), "original inventory stats untouched");
                    Equal(false, ReferenceEquals(source, copy), "candidate is a request-only copy");
                    Equal(source.damage, copy.damage, "slot " + slot + " authored damage");
                    Equal(source.ammo, copy.ammo, "authored ammo category");
                    Equal(source.shoot, copy.shoot, "authored projectile ID");
                    Equal(source.shootSpeed, copy.shootSpeed, "authored projectile speed");
                    Equal(source.knockBack, copy.knockBack, "authored knockback");
                    Equal(source.DamageType.Type, copy.DamageType.Type, "authored damage class");
                    Equal(source.maxStack, copy.maxStack, "authored stack cap");
                    Equal(source.stack, copy.stack, "quantity preserved");
                    if (slot == 55) continue; // vanilla control, no localized-name setup needed
                    Equal(true, copy.ModItem is InfiniCrafterLocal.Content.Items.GeneratedItem, "generated identity retained");
                    Equal(((InfiniCrafterLocal.Content.Items.GeneratedItem)source.ModItem).Data.Id,
                        ((InfiniCrafterLocal.Content.Items.GeneratedItem)copy.ModItem).Data.Id, "correct per-instance definition retained");
                    string provenance = (string)candidate.GetType().GetProperty("Source")!.GetValue(candidate)!;
                    var raw = JsonSerializer.SerializeToElement(snapshot.Invoke(null, new object[] { copy, provenance, slot }));
                    Equal(source.damage, raw.GetProperty("damage").GetInt32(), "real ammo raw snapshot damage");
                    Equal(source.shoot, raw.GetProperty("shoot").GetInt32(), "real ammo raw snapshot projectile");
                    Equal(source.Name, raw.GetProperty("name").GetString()!, "authored name reaches context");
                    Equal(slot, raw.GetProperty("inventorySlot").GetInt32(), "snapshot slot provenance");
                    Equal(definitions[i], JsonSerializer.Serialize(((InfiniCrafterLocal.Content.Items.GeneratedItem)source.ModItem).Data), "source definition unchanged");
                    Equal(true, source.favorited, "source favorite untouched");
                    Equal(17, source.stack, "source quantity untouched");
                }
                catch (Exception error) { failures.Add($"limit={limit} index={i}: {error}"); }
            }
        }
        foreach (var args in new object?[][] { new object?[] { Terraria.ID.AmmoID.Arrow, null, 3 }, new object?[] { Terraria.ID.AmmoID.None, owner, 3 } })
            Equal(0, ((System.Collections.IList)scan.Invoke(null, args)!).Count, "absent player/category yields no candidates");
        if (failures.Count > 0) throw new InvalidOperationException(string.Join(Environment.NewLine, failures));
    }

    private static void GeneratedParentPrefixIsRequestOnly()
    {
        var oldRandom = Terraria.Main.rand;
        int oldMode = Terraria.Main.netMode;
        var failures = new System.Collections.Generic.List<string>();
        try
        {
            Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(17);
            Terraria.Main.netMode = Terraria.ID.NetmodeID.SinglePlayer;
            var data = InfiniCrafterLocal.Common.Models.GeneratedItemData.Placeholder();
            data.Id = "parent_prefix_probe";
            data.SourceMode = "test_fixture";
            data.Name = "Authored parent";
            data.Gameplay.Damage = 100;
            data.Gameplay.DamageClass = "melee";
            data.Gameplay.Knockback = 5f;
            data.Gameplay.UseTime = data.Gameplay.UseAnimation = 30;
            data.Gameplay.Value = 10000;
            data.Normalize();
            var baseItem = new Terraria.Item();
            baseItem.SetDefaults(Terraria.ID.ItemID.WoodenSword);
            // Isolate the real GeneratedItem clone/data hooks on a vanilla-allocated
            // host type. This is not full ModLoader content registration.
            var generated = new InfiniCrafterLocal.Content.Items.GeneratedItem();
            typeof(Terraria.ModLoader.ModType<Terraria.Item>).GetProperty("Entity", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)!
                .SetValue(generated, baseItem);
            typeof(Terraria.Item).GetProperty("ModItem")!.SetValue(baseItem, generated);
            typeof(InfiniCrafterLocal.Content.Items.GeneratedItem).GetProperty("Data")!.SetValue(generated, data);
            data.ApplyToItem(baseItem);
            baseItem.stack = 3;
            baseItem.favorited = true;
            string definition = data.ToNetworkJson();
            string Stats(Terraria.Item item) => JsonSerializer.Serialize(new {
                item.type, item.prefix, item.damage, item.crit, item.knockBack, item.useTime,
                item.useAnimation, item.scale, item.shootSpeed, item.mana, item.rare, item.value,
                item.favorited, item.Name,
            });
            var client = new GeneratorClient();
            var owner = new Terraria.Player { name = "headless_prefix_probe" };
            using var baseline = JsonDocument.Parse(client.Prepare(baseItem.Clone(), baseItem.Clone(), owner).PayloadJson);
            foreach (int prefix in new[] { 0, (int)Terraria.ID.PrefixID.Legendary, (int)Terraria.ID.PrefixID.Broken, (int)Terraria.ID.PrefixID.Zealous })
            {
                try
                {
                    Terraria.Item source = baseItem.Clone();
                    if (prefix != 0) Equal(true, source.Prefix(prefix), "real prefix accepts " + prefix);
                    string before = Stats(source);
                    var sourceData = ((InfiniCrafterLocal.Content.Items.GeneratedItem)source.ModItem).Data;
                    string sourceDefinition = JsonSerializer.Serialize(sourceData);
                    var prepared = client.Prepare(source, source, owner);
                    Equal(before, Stats(source), "source retains prefix/stats " + prefix);
                    Equal(3, source.stack, "source stack untouched");
                    Equal(sourceDefinition, JsonSerializer.Serialize(sourceData), "source definition unchanged by Prepare");
                    foreach (Terraria.Item refund in new[] { prepared.RefundA, prepared.RefundB })
                    {
                        Equal(false, ReferenceEquals(source, refund), "refund is independent item");
                        Equal(before, Stats(refund), "refund retains original prefix/stats " + prefix);
                        Equal(1, refund.stack, "refund reserves one unit");
                        Equal(sourceData.ToNetworkJson(), ((InfiniCrafterLocal.Content.Items.GeneratedItem)refund.ModItem).Data.ToNetworkJson(), "refund preserves generated definition");
                    }
                    using var payload = JsonDocument.Parse(prepared.PayloadJson);
                    foreach (string side in new[] { "itemA", "itemB" })
                    {
                        var actual = payload.RootElement.GetProperty(side);
                        var expected = baseline.RootElement.GetProperty(side);
                        Equal(prefix, actual.GetProperty("originalPrefix").GetInt32(), "original prefix is diagnostic only");
                        Equal(prefix != 0, actual.GetProperty("prefixIgnored").GetBoolean(), "ignored marker is truthful");
                        foreach (string field in new[] { "prefix", "name", "damage", "useTime", "useAnimation", "knockback", "manaCost", "shootSpeed", "rare", "value", "damageClass", "autoFeatures", "nameTokens", "runtimeFacts", "generatedData" })
                            Equal(expected.GetProperty(field).GetRawText(), actual.GetProperty(field).GetRawText(), "prefix " + prefix + " base payload " + field);
                    }
                    var identity = typeof(GeneratorClient).GetMethod("CraftIdentityItem", BindingFlags.Static | BindingFlags.NonPublic)!;
                    var requestItem = (Terraria.Item)identity.Invoke(null, new object[] { source, data })!;
                    Equal((byte)0, requestItem.prefix, "request identity actually unprefixed");
                    Equal(baseItem.crit, requestItem.crit, "crit reset too, not only authored fields");
                    Equal(baseItem.scale, requestItem.scale, "size reset");
                    Equal(3, requestItem.stack, "request keeps source quantity");
                    Equal(true, requestItem.ModItem is InfiniCrafterLocal.Content.Items.GeneratedItem, "generated type identity retained");
                    Equal(definition, data.ToNetworkJson(), "canonical definition unchanged");
                }
                catch (Exception error) { failures.Add("prefix " + prefix + ": " + error); }
            }
            // A caller may have resolved a save-only parent's canonical definition.
            // Exercise that exact argument without pretending a registry/network match ran.
            var referenceItem = baseItem.Clone();
            var referenceMod = (InfiniCrafterLocal.Content.Items.GeneratedItem)referenceItem.ModItem;
            var tag = new Terraria.ModLoader.IO.TagCompound { ["infiniJson"] = data.ToPlayerSaveJson() };
            referenceMod.LoadData(tag);
            Equal(true, InfiniCrafterLocal.Common.Models.GeneratedItemData.IsPlayerSaveReferenceOnly(referenceMod.Data), "fixture really is save-only");
            Equal(0, referenceItem.damage, "save-only host is inert before resolution");
            var identityMethod = typeof(GeneratorClient).GetMethod("CraftIdentityItem", BindingFlags.Static | BindingFlags.NonPublic)!;
            var resolvedCopy = (Terraria.Item)identityMethod.Invoke(null, new object[] { referenceItem, data })!;
            Equal(100, resolvedCopy.damage, "resolved canonical argument restores authored stats");
            Equal(data.Name, resolvedCopy.Name, "resolved canonical name retained");
            Equal(0, referenceItem.damage, "request does not hydrate/mutate original save-only host");
            Equal(true, InfiniCrafterLocal.Common.Models.GeneratedItemData.IsPlayerSaveReferenceOnly(referenceMod.Data), "original remains save-only");
        }
        finally { Terraria.Main.rand = oldRandom; Terraria.Main.netMode = oldMode; }
        if (failures.Count > 0) throw new InvalidOperationException(string.Join(Environment.NewLine, failures));
    }

    private static void CraftIdentityRejectsFailedDefaults()
    {
        var method = typeof(GeneratorClient).GetMethod("CraftIdentityItem", BindingFlags.Static | BindingFlags.NonPublic)!;
        int invalidType = Terraria.ModLoader.ItemLoader.ItemCount + 1000;
        bool defaultsFailed = false;
        try { new Terraria.Item().SetDefaults(invalidType); }
        catch (IndexOutOfRangeException) { defaultsFailed = true; }
        Equal(true, defaultsFailed, "fixture reaches a real SetDefaults failure");
        var source = new Terraria.Item { type = invalidType, stack = 2, prefix = Terraria.ID.PrefixID.Legendary, damage = 115 };
        bool rejected = false;
        try { method.Invoke(null, new object?[] { source, null }); }
        catch (TargetInvocationException error) when (error.InnerException is IndexOutOfRangeException) { rejected = true; }
        Equal(true, rejected, "failed defaults must not return a prefixed copy as base stats");
        Equal((byte)Terraria.ID.PrefixID.Legendary, source.prefix, "failure leaves source prefix unchanged");
        Equal(115, source.damage, "failure leaves source damage unchanged");
        Equal(2, source.stack, "failure leaves source stack unchanged");
        var vanilla = new Terraria.Item();
        vanilla.SetDefaults(Terraria.ID.ItemID.WoodenSword);
        int baseDamage = vanilla.damage;
        int baseCrit = vanilla.crit;
        Equal(true, vanilla.Prefix(Terraria.ID.PrefixID.Legendary), "real vanilla prefix control");
        int prefixedDamage = vanilla.damage;
        var plain = (Terraria.Item)method.Invoke(null, new object?[] { vanilla, null })!;
        Equal((byte)0, plain.prefix, "vanilla request remains unprefixed");
        Equal(baseDamage, plain.damage, "vanilla defaults preserved");
        Equal(baseCrit, plain.crit, "vanilla crit defaults preserved");
        Equal(prefixedDamage, vanilla.damage, "vanilla original unchanged");
        Equal((byte)Terraria.ID.PrefixID.Legendary, vanilla.prefix, "vanilla original prefix retained");
        foreach (Terraria.Item? empty in new Terraria.Item?[] { null, new Terraria.Item() })
        {
            var air = (Terraria.Item)method.Invoke(null, new object?[] { empty, null })!;
            Equal(true, air.IsAir, "null/air boundary remains inert");
        }
    }

    private static void GeneratorDeliveryRequiresIdentity()
    {
        var gate = typeof(GeneratorClient).GetMethod("IsDeliverableGeneratedData", BindingFlags.Static | BindingFlags.NonPublic)!;
        foreach (string id in new[] { "", " ", "\t", "placeholder", "recipe_identity_probe" })
        {
            var data = InfiniCrafterLocal.Common.Models.GeneratedItemData.Placeholder();
            data.Id = id;
            data.Name = "Identity probe";
            data.SourceMode = "test_fixture";
            var parsed = InfiniCrafterLocal.Common.Models.GeneratedItemData.FromJson(data.ToNetworkJson());
            Equal(true, parsed is not null, "test reaches delivery gate after real JSON boundary");
            bool accepted = (bool)gate.Invoke(null, new object?[] { parsed })!;
            Equal(id == "recipe_identity_probe", accepted, "delivery identity: '" + id + "'");
            Equal(id.Trim(), parsed!.Id, "delivery gate does not invent identity");
        }
    }

    private static void CacheOnlyFlagPreservesRequest()
    {
        var method = typeof(GeneratorClient).GetMethod("WithCacheOnlyFlag", BindingFlags.Static | BindingFlags.NonPublic)!;
        foreach (string json in new[] {
            "{}", " { } ",
            "{\"itemA\":{\"name\":\"Тест } ,\",\"damage\":17},\"itemB\":{\"id\":23},\"worldId\":7}",
            "{\"cacheOnly\":false,\"nested\":{\"cacheOnly\":false},\"large\":9007199254740993,\"precise\":0.1234567890123456789}",
            "{\"cacheOnly\":true}",
        })
        {
            string result = (string)method.Invoke(null, new object[] { json })!;
            JsonDocument parsed;
            try { parsed = JsonDocument.Parse(result); }
            catch (JsonException ex) { throw new InvalidOperationException("cache-only transform produced invalid JSON: " + result, ex); }
            using (parsed)
            using (var original = JsonDocument.Parse(json))
            {
                Equal(true, parsed.RootElement.GetProperty("cacheOnly").GetBoolean(), "cache-only is explicit true");
                Equal(1, parsed.RootElement.EnumerateObject().Count(p => p.Name == "cacheOnly"), "one authoritative cache-only field");
                int expectedCount = original.RootElement.EnumerateObject().Count(p => p.Name != "cacheOnly") + 1;
                Equal(expectedCount, parsed.RootElement.EnumerateObject().Count(), "no lost or added payload fields");
                foreach (var field in original.RootElement.EnumerateObject().Where(p => p.Name != "cacheOnly"))
                {
                    // Compare compact JSON without converting numbers through double.
                    Equal(JsonSerializer.Serialize(field.Value), JsonSerializer.Serialize(parsed.RootElement.GetProperty(field.Name)), "preserved field " + field.Name);
                }
            }
        }
        foreach (string invalid in new[] { "[]", "null", "1", "\"text\"", "{", "" })
        {
            bool rejected = false;
            try { method.Invoke(null, new object[] { invalid }); }
            catch (TargetInvocationException ex) when (ex.InnerException is JsonException) { rejected = true; }
            Equal(true, rejected, "non-object or malformed request rejected: " + invalid);
        }
    }
}

using System;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Services;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private static void ParentEquipmentFactsSeparatePiecesAndConditionalSets()
    {
        using var state = new NativeActorState();
        var grant = typeof(Player).GetMethod("GrantArmorBenefits", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)!;
        var wizardFacts = GeneratorClient.CaptureNativeEquipmentReference(new Item(ItemID.WizardHat));
        Equal(true, wizardFacts is not null, "boolean world gate does not erase independently proved base contribution");
        var wizardBranch = wizardFacts!["equippedContributions"]!["branches"]![0]!;
        var conditional = wizardBranch["conditionalEffects"]![0]!;
        Equal("Terraria.Main.tenthAnniversaryWorld", conditional["condition"]!["nativeMember"]!.GetValue<string>(), "world condition remains literal native state");
        Equal(false, conditional["condition"]!["observed"]!.GetValue<bool>(), "source condition is not a current player/world observation");
        bool previousWorld = Terraria.Main.tenthAnniversaryWorld;
        try
        {
            foreach (bool world in new[] { false, true })
            {
                Terraria.Main.tenthAnniversaryWorld = world;
                var wizardPlayer = new Player();
                int beforeMinions = wizardPlayer.maxMinions;
                float beforeDamage = wizardPlayer.GetDamage(DamageClass.Magic).Additive;
                grant.Invoke(wizardPlayer, new object[] { new Item(ItemID.WizardHat) });
                Equal(world ? 1 : 0, wizardPlayer.maxMinions - beforeMinions, "actual native conditional minion slot agrees with retained world predicate");
                Equal(true, Math.Abs(wizardPlayer.GetDamage(DamageClass.Magic).Additive - beforeDamage - 0.05f) < 0.000001f, "base native magic contribution remains independent from world predicate");
            }
        }
        finally { Terraria.Main.tenthAnniversaryWorld = previousWorld; }

        foreach (int type in new[] { ItemID.AncientShadowHelmet, ItemID.AncientShadowScalemail, ItemID.AncientShadowGreaves })
        {
            var item = new Item(type);
            var facts = GeneratorClient.CaptureNativeEquipmentReference(item)!;
            var effects = facts["equippedContributions"]!["branches"]![0]!["effects"]!.AsArray();
            var crit = effects.OfType<JsonObject>().Single(e => e["stat"]?.GetValue<string>() == "critChance");
            Equal(5f, crit["value"]!.GetValue<float>(), "per-piece native generic crit contribution");
            var player = new Player();
            float before = player.GetCritChance(DamageClass.Generic);
            grant.Invoke(player, new object[] { item });
            Equal(crit["value"]!.GetValue<float>(), player.GetCritChance(DamageClass.Generic) - before,
                "reference agrees with actual native GrantArmorBenefits, not current owner stats");
            var set = facts["conditionalArmorSets"]!.AsArray().OfType<JsonObject>()
                .Single(x => x["setBonusLocalizationKey"]!.GetValue<string>() == "ArmorSetBonus.ShadowScale");
            Equal(true, set["condition"]!["allSlotsRequired"]!.GetValue<bool>(), "single item does not receive full set bonus");
            Equal(false, set["condition"]!["vanitySatisfies"]!.GetValue<bool>(), "vanity is not functional armor");
            Equal("5,74", string.Join(",", set["condition"]!["functionalEquipSlots"]!["head"]!.AsArray().Select(x => x!.GetValue<int>())), "mixed variant head equip slots, not item IDs");
            Equal(true, set["effects"]!.AsArray().OfType<JsonObject>().Any(x => x["nativeMember"]!.GetValue<string>() == "Terraria.Player.shadowArmor"), "literal set flag is retained, not invented movement multiplier");
        }
        // Different recognized source operations, not more repetitions of crit.
        foreach (var (type, stat, read) in new (int Type, string Stat, Func<Player, float> Read)[] {
            (ItemID.ChlorophyteHeadgear, "damage", p => p.GetDamage(DamageClass.Magic).Additive),
            (ItemID.AmethystRobe, "manaCostMultiplier", p => p.manaCost),
            (ItemID.SpookyBreastplate, "maximumMinions", p => p.maxMinions),
            (ItemID.JungleHat, "maximumMana", p => p.statManaMax2),
            (1158, "maximumMinions", p => p.maxMinions),
            (2367, "fishingPower", p => p.fishingSkill),
            (410, "pickUseTimeMultiplier", p => p.pickSpeed),
            (1159, "whipRangeMultiplier", p => p.whipRangeMultiplier),
        })
        {
            var item = new Item(type);
            var facts = GeneratorClient.CaptureNativeEquipmentReference(item)!;
            var effects = facts["equippedContributions"]!["branches"]!.AsArray().OfType<JsonObject>()
                .SelectMany(branch => branch["effects"]!.AsArray().OfType<JsonObject>());
            float expectedDelta = effects.Single(effect => effect["stat"]?.GetValue<string>() == stat)["value"]!.GetValue<float>();
            var player = new Player();
            float before = read(player);
            grant.Invoke(player, new object[] { item });
            Equal(true, Math.Abs((read(player) - before) - expectedDelta) < 0.000001f,
                "literal source addition agrees with native numeric component: " + stat);
        }
        var owner = new Player();
        owner.GetCritChance(DamageClass.Generic) = 99f;
        var input = new Item(ItemID.AncientShadowHelmet);
        var originalArmor = owner.armor;
        using var request = JsonDocument.Parse(new GeneratorClient().Prepare(input, new Item(ItemID.DirtBlock), owner).PayloadJson);
        var root = request.RootElement.GetProperty("itemA");
        string expected = root.GetProperty("nativeEquipmentReference").GetRawText();
        Equal(expected, root.GetProperty("runtimeFacts").GetProperty("nativeEquipmentReference").GetRawText(), "request runtime projection exact");
        Equal(expected, root.GetProperty("fingerprint").GetProperty("nativeEquipmentReference").GetRawText(), "request fingerprint projection exact");
        Equal(99f, owner.GetCritChance(DamageClass.Generic), "capture does not mutate player stats");
        Equal(true, ReferenceEquals(originalArmor, owner.armor), "capture does not replace inventory/equipment");
        Equal(ItemID.AncientShadowHelmet, input.type, "capture does not change parent identity");
        Equal(null, GeneratorClient.CaptureNativeEquipmentReference(new Item(ItemID.DirtBlock)), "uncovered item is unknown, not zero equipment effect");
        var catalog = typeof(GeneratorClient).GetMethod("ReadEquipmentCatalog", BindingFlags.Static | BindingFlags.NonPublic)!;
        Equal(null, catalog.Invoke(null, new object?[] { "Player.GrantArmorBenefits", "unknown:module" }), "unknown native binary declines certificate");
        var verify = typeof(GeneratorClient).GetMethod("VerifiedNativeEquipmentReference", BindingFlags.Static | BindingFlags.NonPublic)!;
        Equal(null, verify.Invoke(null, new object?[] { 956, false, 74, -1, -1, new JsonArray(), "known", new JsonArray(), "known" }), "modded host never borrows vanilla certificate");
    }

    private static void ParentArmorSetConditionsAgreeWithNativeMixedAndIncompleteSets()
    {
        using var state = new NativeActorState();
        var update = typeof(Player).GetMethod("UpdateArmorSets", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)!;
        object[] args = update.GetParameters().Select(parameter => parameter.ParameterType == typeof(int)
            ? (object)0 : throw new InvalidOperationException("Unexpected native UpdateArmorSets parameter")).ToArray();
        var source = GeneratorClient.CaptureNativeEquipmentReference(new Item(ItemID.AncientShadowHelmet))!;
        var set = source["conditionalArmorSets"]!.AsArray().OfType<JsonObject>()
            .Single(x => x["setBonusLocalizationKey"]!.GetValue<string>() == "ArmorSetBonus.ShadowScale");
        var slots = set["condition"]!["functionalEquipSlots"]!.AsObject();
        foreach (var (head, body, legs, expected) in new[] { (74,48,44,true), (74,5,44,true), (5,48,5,true), (74,48,-1,false), (-1,-1,-1,false) })
        {
            var player = new Player { head = head, body = body, legs = legs };
            update.Invoke(player, args);
            bool observed = slots["head"]!.AsArray().Any(x => x!.GetValue<int>() == head)
                && slots["body"]!.AsArray().Any(x => x!.GetValue<int>() == body)
                && slots["legs"]!.AsArray().Any(x => x!.GetValue<int>() == legs);
            Equal(expected, observed, "literal slot condition must distinguish complete/mixed/incomplete");
            Equal(expected, player.shadowArmor, "actual native set consumer agrees with source condition");
        }
        foreach (var (type, key, stat, read) in new (int Type, string Key, string Stat, Func<Player, float> Read)[]
        {
            (410, "ArmorSetBonus.Mining", "pickUseTimeMultiplier", p => p.pickSpeed),
            (1159, "ArmorSetBonus.Tiki", "whipRangeMultiplier", p => p.whipRangeMultiplier)
        })
        {
            var reference = GeneratorClient.CaptureNativeEquipmentReference(new Item(type))!;
            var numericSets = reference["conditionalArmorSets"]!.AsArray().OfType<JsonObject>()
                .Where(row => row["setBonusLocalizationKey"]!.GetValue<string>() == key).ToArray();
            Equal(true, numericSets.Length > 0, "native numeric set control must execute a matching source row: " + key);
            foreach (JsonObject row in numericSets)
            {
                var required = row["condition"]!["functionalEquipSlots"]!;
                float contribution = row["effects"]!.AsArray().OfType<JsonObject>()
                    .Single(effect => effect["stat"]?.GetValue<string>() == stat)["value"]!.GetValue<float>();
                foreach (bool complete in new[] { false, true })
                {
                    var player = new Player { head = required["head"]![0]!.GetValue<int>(),
                        body = required["body"]![0]!.GetValue<int>(), legs = complete ? required["legs"]![0]!.GetValue<int>() : -1 };
                    float before = read(player);
                    update.Invoke(player, args);
                    Equal(true, Math.Abs(read(player) - before - (complete ? contribution : 0)) < 0.000001f,
                        "new native set numeric contribution requires every functional slot: " + key);
                }
            }
        }
    }
}

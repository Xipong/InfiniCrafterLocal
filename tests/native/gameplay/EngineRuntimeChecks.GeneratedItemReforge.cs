using System;
using System.Linq;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Items;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    // Every definition below is a real registered GeneratedItem of one type.
    // A vanilla host per weapon class would hide tML's type-level cache defect.
    private static void GeneratedItemNativeReforgeSharedTypeCategories()
    {
        WithGeneratedPrefixScope(() => WithNativeChestRegisteredItem(type => WithGeneratedReforgeBridge(() => {
            var scenarios = new[] {
                (Lane: "melee", Categories: "Melee,AnyWeapon", Allowed: (int)PrefixID.Legendary, Refused: (int)PrefixID.Unreal),
                (Lane: "ranged", Categories: "Ranged,AnyWeapon", Allowed: (int)PrefixID.Unreal, Refused: (int)PrefixID.Mythical),
                (Lane: "magic", Categories: "Magic,AnyWeapon", Allowed: (int)PrefixID.Mythical, Refused: (int)PrefixID.Legendary),
                (Lane: "accessory", Categories: "Accessory", Allowed: (int)PrefixID.Warding, Refused: (int)PrefixID.Keen),
                (Lane: "accessory_generic", Categories: "Accessory", Allowed: (int)PrefixID.Warding, Refused: (int)PrefixID.Keen),
                (Lane: "accessory_melee", Categories: "Accessory", Allowed: (int)PrefixID.Warding, Refused: (int)PrefixID.Zealous),
                (Lane: "accessory_weapon", Categories: "Melee,AnyWeapon,Accessory", Allowed: (int)PrefixID.Legendary, Refused: (int)PrefixID.Unreal),
                (Lane: "accessory_utility", Categories: "Magic,AnyWeapon,Accessory", Allowed: (int)PrefixID.Adept, Refused: (int)PrefixID.Legendary),
                (Lane: "hidden_melee", Categories: "AnyWeapon", Allowed: (int)PrefixID.Godly, Refused: (int)PrefixID.Legendary),
                (Lane: "generic", Categories: "AnyWeapon", Allowed: (int)PrefixID.Demonic, Refused: (int)PrefixID.Mythical),
            };
            var sameInstance = GeneratedReforgeItem(type, GeneratedReforgeFixture("melee"));
            // Prime the shared native type before visiting every other class.
            Equal("Melee,AnyWeapon", string.Join(",", sameInstance.GetPrefixCategories()), "first generated melee category");
            foreach (var scenario in scenarios.Concat(Enumerable.Reverse(scenarios)))
            {
                var data = GeneratedReforgeFixture(scenario.Lane);
                var item = GeneratedReforgeItem(type, data);
                Equal(type, item.type, "all reforge fixtures share one registered mod type");
                Equal(scenario.Categories, string.Join(",", item.GetPrefixCategories()), scenario.Lane + " native categories after earlier class");
                Equal(true, item.Prefix(-3), scenario.Lane + " native reforge eligibility probe");
                Equal(false, item.Prefix(scenario.Refused), scenario.Lane + " refuses foreign native prefix category");
                Equal(true, item.Prefix(scenario.Allowed), scenario.Lane + " accepts own native prefix category");

                GeneratedPrefixSetData((GeneratedItem)sameInstance.ModItem, data);
                Equal(scenario.Categories, string.Join(",", sameInstance.GetPrefixCategories()), scenario.Lane + " same instance follows replaced definition");
            }
        })));
    }

    private static void GeneratedItemNativeReforgeResetAndRoll()
    {
        WithGeneratedPrefixScope(() => WithNativeChestRegisteredItem(type => WithGeneratedReforgeBridge(() => {
            using var peers = new ReviewPeers();
            foreach (string lane in new[] { "melee", "ranged", "magic", "accessory", "accessory_generic", "accessory_melee", "accessory_weapon", "accessory_utility", "hidden_melee", "generic" })
            {
                var data = GeneratedReforgeFixture(lane);
                peers.Register(data);
                var item = GeneratedReforgeItem(type, data);
                string definition = ((GeneratedItem)item.ModItem).Data.ToNetworkJson();
                int prefixedRolls = 0;
                for (int repeat = 0; repeat < 8; repeat++)
                {
                    // The actual Goblin path, including native reconstruction of
                    // ModItem state. No handmade stat reset or reroll substitutes.
                    Equal(true, ItemLoader.CanReforge(item), lane + " native CanReforge");
                    ItemLoader.PreReforge(item);
                    item.ResetPrefix();
                    Equal(0, (int)item.prefix, lane + " native reset clears previous prefix");
                    Equal(true, item.ModItem is GeneratedItem, lane + " reset reconstructs registered generated proxy");
                    Equal(definition, ((GeneratedItem)item.ModItem).Data.ToNetworkJson(), lane + " reset retains complete generated definition");
                    Equal(true, item.Prefix(-2), lane + " native Goblin roll " + repeat);
                    ItemLoader.PostReforge(item);

                    var expected = GeneratedReforgeItem(type, data);
                    // Native -2 can return true with prefix 0 after rejecting a
                    // stat-inapplicable roll. Preserve that native outcome too.
                    if (item.prefix != 0)
                    {
                        prefixedRolls++;
                        Equal(true, expected.Prefix(item.prefix), lane + " rolled prefix remains valid on an unmodified copy");
                    }
                    Equal(GeneratedPrefixStats(expected), GeneratedPrefixStats(item), lane + " repeated native reforge does not compound prefix stats " + repeat);
                    Equal(definition, ((GeneratedItem)item.ModItem).Data.ToNetworkJson(), lane + " rolling never changes authored definition");
                }
                Equal(true, prefixedRolls > 0, lane + " native reforge produced usable prefixes");
            }
        })));
    }

    private static void GeneratedItemNativeReforgeForeignItemsUnchanged()
    {
        WithGeneratedPrefixScope(() => WithNativeChestRegisteredItem(type => {
            var foreign = new Item(type);
            string before = string.Join(",", foreign.GetPrefixCategories());
            Equal("Ranged,AnyWeapon", before, "foreign ModItem native category predicate");
            var vanilla = new Item(ItemID.AmethystStaff);
            string vanillaBefore = string.Join(",", vanilla.GetPrefixCategories());
            WithGeneratedReforgeBridge(() => {
                Equal(before, string.Join(",", foreign.GetPrefixCategories()), "foreign ModItem keeps native categories");
                Equal(vanillaBefore, string.Join(",", vanilla.GetPrefixCategories()), "vanilla item keeps native categories");
                Equal(true, foreign.Prefix(PrefixID.Unreal), "foreign ModItem native prefix remains accepted");
                Equal(false, new Item(type).Prefix(PrefixID.Mythical), "foreign ModItem native refusal remains intact");
            });
        }, new GeneratedReforgeForeignItem()));
    }

    private static GeneratedItemData GeneratedReforgeFixture(string lane)
    {
        var data = GeneratedPrefixFixture(lane == "accessory_utility" ? "magic" : lane is "ranged" or "magic" ? lane : "melee");
        data.Id = "native-reforge-" + lane;
        if (lane.StartsWith("accessory", StringComparison.Ordinal))
        {
            bool active = lane is "accessory_weapon" or "accessory_utility";
            data.Gameplay.Damage = lane == "accessory_weapon" ? 12 : 0;
            data.Gameplay.DamageClass = lane == "accessory" ? "default"
                : lane == "accessory_generic" ? "generic"
                : lane == "accessory_utility" ? "magic" : "melee";
            data.Accessory.Enabled = true;
            data.Visual.EquipOverlayPath = "native_reforge_overlay.png";
            data.Visual.EquipOverlayStatus = "generated";
            var equip = new RuntimeBindingSpec { Id = "equip", Input = RuntimeInputKind.Equipped,
                Role = lane == "accessory_utility" ? RuntimeEntityRole.Secondary : RuntimeEntityRole.Primary,
                UsePolicy = new RuntimeBindingUsePolicySpec {
                    Action = new RuntimeBindingActionSpec { Kind = RuntimeBindingAction.EquipPassive, TargetId = data.RuntimeProgram.ItemEntityId },
                },
            };
            data.RuntimeProgram.Bindings = active
                ? new[] { data.RuntimeProgram.Bindings[0], equip } : new[] { equip };
        }
        if (lane == "hidden_melee") data.RuntimeProgram.ItemUse.HideUseGraphic = true;
        if (lane == "generic") data.Gameplay.DamageClass = "generic";
        return data;
    }

    private static Item GeneratedReforgeItem(int type, GeneratedItemData data)
    {
        var item = new Item(type);
        GeneratedPrefixSetData((GeneratedItem)item.ModItem, data);
        return item;
    }

    private static void WithGeneratedReforgeBridge(Action check)
    {
        // Reflection makes this exact test file buildable against the unmodified
        // source for RED. Without the fix it exercises the native shared cache.
        Type? bridgeType = typeof(GeneratedItem).Assembly.GetType("InfiniCrafterLocal.Common.Systems.GeneratedPrefixCategorySystem");
        ModSystem? bridge = bridgeType is null ? null : (ModSystem)Activator.CreateInstance(bridgeType)!;
        try { bridge?.Load(); check(); }
        finally { bridge?.Unload(); }
    }

    private sealed class GeneratedReforgeForeignItem : ModItem
    {
        public override void SetDefaults()
        {
            Item.damage = 12; Item.knockBack = 3; Item.DamageType = DamageClass.Ranged;
            Item.useTime = Item.useAnimation = 18; Item.shootSpeed = 10; Item.value = 10000;
            Item.maxStack = 1;
        }
    }
}

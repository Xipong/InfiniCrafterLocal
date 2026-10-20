#nullable enable
using System;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Systems;
using InfiniCrafterLocal.Content.Items;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private static void GeneratedQuickStackMatchesExactDefinitionNotProxyType()
    {
        GeneratedItemData data = VideoUiFixture("g_89cda498eb1f9925");
        data.Id = "quickstack-a"; data.RecipeKey = "recipe-a";
        GeneratedItem ItemFor(GeneratedItemData definition)
            => AttachItem(new GeneratedItem(), new Item(ItemID.Wood, 2) { maxStack = 99 }, definition);
        var first = ItemFor(data);
        var equal = ItemFor(GeneratedItemData.FromJson(data.ToNetworkJson())!);
        var otherDefinition = GeneratedItemData.FromJson(data.ToNetworkJson())!;
        otherDefinition.Id = "quickstack-b";
        var different = ItemFor(otherDefinition);

        Equal(true, first.CanStack(equal.Item), "same decoded definition can stack");
        Equal(false, first.CanStack(different.Item), "different generated IDs cannot stack");
        Equal(false, first.CanStackInWorld(different.Item), "world merges require same generated identity");
        // Headless integration of the actual 1.4.4 native selector used by
        // Chest.PutItemInNearbyChest and ChestUI.QuickStack.
        var owner = new GeneratedQuickStackSystem();
        try
        {
            owner.Load();
            var native = typeof(Item).GetMethod("IsTheSameAs",
                BindingFlags.NonPublic | BindingFlags.Instance, null, new[] { typeof(Item) }, null)
                ?? throw new InvalidOperationException("tML 1.4.4 native selector unavailable");
            bool Same(Item left, Item right) => (bool)native.Invoke(left, new object[] { right })!;
            Equal(true, Same(first.Item, equal.Item), "native selector accepts exact generated definition");
            Equal(false, Same(first.Item, different.Item), "native nearby selector rejects different generated definition");
            Equal(false, Same(different.Item, first.Item), "native selector rejects both directions");
            Equal(true, Same(new Item(ItemID.Wood, 1), new Item(ItemID.Wood, 1)),
                "vanilla equality remains unchanged");
            Equal(true, ItemLoader.CanStack(first.Item, equal.Item), "native stacking hook accepts exact generated identity");
            Equal(false, ItemLoader.CanStack(first.Item, different.Item), "native stacking hook rejects different generated identity");
        }
        finally { owner.Unload(); }
    }

    private static void GeneratedPeriodicActionPhaseIsStable()
    {
        Equal(671842109u, GeneratedItem.PeriodicActionOffset("periodic-craft"),
            "literal stable phase independent of randomized process string hashes");
        Equal(671842109u, GeneratedItem.PeriodicActionOffset("periodic-craft"),
            "repeat periodic action ID has identical phase");
        Equal(false, GeneratedItem.PeriodicActionOffset("periodic-craft")
            == GeneratedItem.PeriodicActionOffset("periodic-craft-2"),
            "independent actions keep independent periodic phases");
    }
}

#nullable enable
using System;
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
        Equal(false, GeneratedQuickStackSystem.HasMatchingStoredItem(first.Item,
            new[] { different.Item, new Item() }), "same proxy native type is not a matching chest item");
        Equal(true, GeneratedQuickStackSystem.HasMatchingStoredItem(first.Item,
            new[] { different.Item, equal.Item }), "exact existing identity allows quick stack");

        var changed = GeneratedItemData.FromJson(data.ToNetworkJson())!;
        changed.Name += " modified mechanics/definition";
        var edited = ItemFor(changed);
        Equal(false, first.CanStack(edited.Item), "matching ID/recipe cannot merge differing full definitions");

        Item[] inventory = new Item[60];
        for (int i = 0; i < inventory.Length; i++) inventory[i] = new Item();
        inventory[10] = first.Item;
        inventory[11] = different.Item;
        GeneratedQuickStackSystem.WithExactQuickStackCandidates(inventory,
            new[] { equal.Item }, () => {
                Equal(true, ReferenceEquals(first.Item, inventory[10]), "exact item stays available to native QuickStack");
                Equal(true, inventory[11].IsAir, "unrelated generated item hidden during native QuickStack");
            });
        Equal(true, ReferenceEquals(different.Item, inventory[11]), "native QuickStack mask restores exact instance");

        // The old native IsTheSameAs predicate only exists on older tML builds.
        // The current native chest code uses Item.CanStack; both must honor
        // the same exact generated identity without breaking vanilla items.
        var owner = new GeneratedQuickStackSystem();
        try
        {
            owner.Load();
            var legacy = typeof(Item).GetMethod("IsTheSameAs", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance,
                null, new[] { typeof(Item) }, null);
            if (legacy is not null)
            {
                bool Same(Item left, Item right) => (bool)legacy.Invoke(left, new object[] { right })!;
                Equal(true, Same(first.Item, equal.Item), "legacy native selector accepts exact generated definition");
                Equal(false, Same(first.Item, different.Item), "legacy nearby selector rejects other definition");
                Equal(false, Same(different.Item, first.Item), "legacy selector rejects both directions");
                Equal(true, Same(new Item(ItemID.Wood, 1), new Item(ItemID.Wood, 1)),
                    "legacy vanilla comparison remains native");
            }
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

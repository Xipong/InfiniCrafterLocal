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

        // Exercise the actual Item.IsTheSameAs dispatch used by nearby native
        // chests, rather than only testing a new helper never called by Terraria.
        var owner = new GeneratedQuickStackSystem();
        try
        {
            owner.Load();
            Equal(true, first.Item.IsTheSameAs(equal.Item), "native same-item accepts the same generated definition");
            Equal(false, first.Item.IsTheSameAs(different.Item), "native nearby-chest selector rejects other definition");
            Equal(false, different.Item.IsTheSameAs(first.Item), "native selector is symmetric for generated items");
            Equal(true, new Item(ItemID.Wood, 1).IsTheSameAs(new Item(ItemID.Wood, 1)),
                "unrelated vanilla matching behavior remains native");
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

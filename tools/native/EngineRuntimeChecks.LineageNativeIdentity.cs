#nullable enable
using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using InfiniCrafterLocal.Common.UI;
using InfiniCrafterLocal.Content.Items;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private sealed class LineageNativeProbe : ModItem { }

    private static void LineageNativeIdentityResolvesOnlyExactRegisteredItems()
    {
        const BindingFlags statics = BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic;
        const BindingFlags instance = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
        var samples = ContentSamples.ItemsByType.ToArray();
        // Only the test harness installs a registry fixture; production uses public lookups.
        var maps = typeof(ModTypeLookup<ModItem>).GetFields(statics)
            .Where(f => f.GetValue(null) is IDictionary)
            .Select(f => (Map: (IDictionary)f.GetValue(null)!, Rows: ((IDictionary)f.GetValue(null)!).Cast<DictionaryEntry>().ToArray())).ToArray();
        try
        {
            Equal(true, RecipeNativeItemResolver.TryGetStableName("item:Terraria/CopperPickaxe:1", out string firstKey), "full identity parses");
            Equal(true, RecipeNativeItemResolver.TryGetStableName("item:Terraria:CopperPickaxe:999999", out string secondKey), "alternate stable identity parses");
            Equal(firstKey, secondKey, "stable graph key ignores only validated runtime ID");
            Equal(false, RecipeNativeItemResolver.TryGetStableName("item:Terraria:1:copper_pickaxe", out _), "legacy display slug is not stable identity");
            Equal(false, RecipeNativeItemResolver.TryGetStableName("item:Terraria/CopperPickaxe:invalid", out _), "malformed ID cannot create stable graph key");
            var copper = new Item { type = ItemID.CopperPickaxe, stack = 1, damage = 17 };
            ContentSamples.ItemsByType[ItemID.CopperPickaxe] = copper;
            Item? found = RecipeNativeItemResolver.Resolve("item:Terraria/CopperPickaxe:" + ItemID.CopperPickaxe);
            var detail = InfiniCrafterLocal.Common.Models.GeneratedItemData.Placeholder();
            detail.RecipeMeta.ParentIdentities = new[] { "item:Terraria/CopperPickaxe:999999", "generated:unavailable" };
            Equal(ItemID.CopperPickaxe, RecipeNativeItemResolver.ResolveParent(detail, 0)?.type ?? 0,
                "recipe detail renders native ingredient using the same stable identity as lineage");
            Equal(true, RecipeNativeItemResolver.ResolveParent(detail, 1) is null, "generated ingredient does not masquerade as native");
            Equal(true, RecipeNativeItemResolver.ResolveParent(detail, 2) is null, "missing ingredient index is safe");
            Equal(ItemID.CopperPickaxe, found?.type ?? 0, "vanilla canonical identity");
            Equal(17, found?.damage ?? 0, "native sample fields preserved");
            Equal(false, ReferenceEquals(copper, found), "hover item cannot mutate shared sample");
            found!.damage = 1;
            Equal(17, copper.damage, "clone mutation remains local");
            Equal(ItemID.CopperPickaxe, RecipeNativeItemResolver.Resolve("item:Terraria:CopperPickaxe:999999")?.type ?? 0,
                "source/internal syntax and stale ID use exact stable name");
            foreach (string invalid in new[] { "", "generated:parent", "ITEM:Terraria/CopperPickaxe:1",
                "item:Terraria/CopperPickaxe", "item:Terraria/CopperPickaxe:0", "item:Terraria/CopperPickaxe:-1",
                "item:Terraria/CopperPickaxe:+1", "item:Terraria/CopperPickaxe: 1", "item:Terraria/CopperPickaxe:2147483648",
                "item:Terraria/copperpickaxe:1", "item:terraria/CopperPickaxe:1", "item:Terraria/NotRegistered:1",
                "item:Terraria/:1", "item:/CopperPickaxe:1", "item:Terraria/CopperPickaxe/Other:1",
                "item:Terraria:CopperPickaxe:extra:1", "item:Terraria:3509:copper_pickaxe",
                "item:UnloadedMod/CopperPickaxe:" + ItemID.CopperPickaxe, "item:" + new string('x', 1024) + ":1" })
                Equal(true, RecipeNativeItemResolver.Resolve(invalid) is null, "unresolved identity stays missing: " + invalid);
            ContentSamples.ItemsByType.Remove(ItemID.CopperPickaxe);
            Equal(true, RecipeNativeItemResolver.Resolve("item:Terraria/CopperPickaxe:1") is null, "unloaded sample cannot become synthetic item");
            ContentSamples.ItemsByType[ItemID.CopperPickaxe] = new Item { type = ItemID.Wood, stack = 1 };
            Equal(true, RecipeNativeItemResolver.Resolve("item:Terraria/CopperPickaxe:1") is null, "mismatched native sample rejected");

            var mod = new global::InfiniCrafterLocal.InfiniCrafterLocalMod();
            typeof(Mod).GetProperty("File", instance)!.SetValue(mod, Activator.CreateInstance(typeof(Terraria.ModLoader.Core.TmodFile),
                instance, null, new object[] { "", "LineageFixture", new Version(1, 0) }, null));
            void Register(ModItem item, int type)
            {
                var shell = new Item { type = type, stack = 1 };
                typeof(ModType).GetProperty("Mod")!.SetValue(item, mod);
                typeof(ModType<Item>).GetProperty("Entity", instance)!.SetValue(item, shell);
                typeof(Item).GetProperty("ModItem")!.SetValue(shell, item);
                typeof(ModType<Item, ModItem>).GetField("_isCloneable", instance)!.SetValue(item, true);
                typeof(ModTypeLookup<ModItem>).GetMethod("Register", statics)!.Invoke(null, new object[] { item });
                ContentSamples.ItemsByType[type] = shell;
            }
            var native = new LineageNativeProbe();
            int modType = ItemID.Count + 127;
            Register(native, modType);
            string identity = "item:" + native.FullName + ":" + ItemID.CopperPickaxe;
            found = RecipeNativeItemResolver.Resolve(identity);
            Equal(modType, found?.type ?? 0, "loaded mod resolves by registration despite reused old vanilla ID");
            Equal(native.FullName, found?.ModItem?.FullName ?? "", "mod hover retains native ModItem");
            Equal(modType, RecipeNativeItemResolver.Resolve("item:" + mod.Name + ":" + native.Name + ":1")?.type ?? 0,
                "mod source/internal identity resolves");
            Equal(true, RecipeNativeItemResolver.Resolve(identity.ToLowerInvariant()) is null, "mod identity case is exact");
            typeof(ModTypeLookup<ModItem>).GetMethod("RegisterLegacyNames", statics)!.Invoke(null, new object[] { native, new[] { "OldLineageProbe" } });
            Equal(true, RecipeNativeItemResolver.Resolve("item:" + mod.Name + "/OldLineageProbe:1") is null, "legacy alias is not an exact identity");
            var generated = new GeneratedItem();
            Register(generated, modType + 1);
            Equal(true, RecipeNativeItemResolver.Resolve("item:" + generated.FullName + ":1") is null, "generated IFC type cannot masquerade as native parent");
            ContentSamples.ItemsByType[modType] = generated.Item;
            Equal(true, RecipeNativeItemResolver.Resolve(identity) is null, "wrong current sample never accepted");
        }
        finally
        {
            ContentSamples.ItemsByType.Clear();
            foreach (var row in samples) ContentSamples.ItemsByType.Add(row.Key, row.Value);
            foreach (var map in maps) { map.Map.Clear(); foreach (var row in map.Rows) map.Map.Add(row.Key, row.Value); }
        }
    }
}

using System;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Content.Items;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private static void ParentPlacementFactsReachCraftSnapshot()
    {
        var client = new GeneratorClient();
        var owner = new Player { name = "placement_fact_probe" };
        // Discover a real loaded vanilla item with a nonzero style; never hardcode
        // a tile ID/style correspondence based on a remembered Terraria recipe.
        Item? styled = null;
        for (int type = 1; type < ItemID.Count; type++)
        {
            var item = new Item();
            item.SetDefaults(type);
            if (item.createTile >= 0 && item.placeStyle != 0)
            {
                styled = item;
                break;
            }
        }
        Equal(true, styled is not null, "real vanilla nonzero placeStyle fixture exists");
        var workbench = new Item();
        workbench.SetDefaults(ItemID.WorkBench);
        foreach (Item source in new[] { workbench, styled! })
        {
            using var request = JsonDocument.Parse(client.Prepare(source, workbench, owner).PayloadJson);
            var raw = request.RootElement.GetProperty("itemA");
            Equal(source.createTile, raw.GetProperty("createTile").GetInt32(), "vanilla tile ID is sourced");
            Equal(source.placeStyle, raw.GetProperty("placeStyle").GetInt32(), "vanilla style is exact, including zero");
            Equal(source.placeStyle, raw.GetProperty("runtimeFacts").GetProperty("placeStyle").GetInt32(), "runtime facts retain style");
            Equal(source.placeStyle, raw.GetProperty("fingerprint").GetProperty("placeStyle").GetInt32(), "fingerprint retains style");
        }

        Item Generated(int? style)
        {
            var data = GeneratedItemData.Placeholder();
            data.Id = "placement_parent_probe";
            data.Name = "Authored placer";
            data.SourceMode = "test_fixture";
            data.RuntimeProgram.ItemUse.Configured = true;
            if (style.HasValue)
                data.RuntimeProgram.Bindings = new[] { new RuntimeBindingSpec {
                    Id = "place_use", Input = RuntimeInputKind.PrimaryUse, Role = RuntimeEntityRole.Primary,
                    UsePolicy = new RuntimeBindingUsePolicySpec {
                        StackCost = 1,
                        Action = new RuntimeBindingActionSpec {
                            Kind = RuntimeBindingAction.PlaceItem,
                            TargetId = data.RuntimeProgram.ItemEntityId,
                            Placement = new RuntimePlacementSpec { TileId = workbench.createTile, WallId = -1, PlaceStyle = style.Value },
                        },
                    },
                } };
            var item = new Item();
            item.SetDefaults(ItemID.WoodenSword);
            var generated = new GeneratedItem();
            typeof(ModType<Item>).GetProperty("Entity", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)!.SetValue(generated, item);
            typeof(Item).GetProperty("ModItem")!.SetValue(item, generated);
            typeof(GeneratedItem).GetProperty("Data")!.SetValue(generated, data);
            data.ApplyToItem(item);
            item.createTile = -1;
            item.createWall = -1;
            item.placeStyle = 0;
            return item;
        }
        foreach (int style in new[] { 0, 7 })
        {
            var generated = Generated(style);
            Equal(-1, generated.createTile, "generated host really is projected nonplacing");
            using var request = JsonDocument.Parse(client.Prepare(generated, workbench, owner).PayloadJson);
            var raw = request.RootElement.GetProperty("itemA");
            Equal(workbench.createTile, raw.GetProperty("createTile").GetInt32(), "generated tile ID comes from exact authored binding");
            Equal(style, raw.GetProperty("placeStyle").GetInt32(), "generated style comes from exact authored binding");
            Equal(style, raw.GetProperty("runtimeFacts").GetProperty("placeStyle").GetInt32(), "generated runtime facts retain authored style");
            Equal(style, raw.GetProperty("fingerprint").GetProperty("placeStyle").GetInt32(), "generated fingerprint retains authored style");
            Equal(-1, generated.createTile, "source projection remains untouched");
        }
        using var missing = JsonDocument.Parse(client.Prepare(Generated(null), workbench, owner).PayloadJson);
        Equal(true, missing.RootElement.GetProperty("itemA").GetProperty("placeStyle").ValueKind == JsonValueKind.Null,
            "missing generated placement cannot turn a projected zero into a source fact");
    }
}

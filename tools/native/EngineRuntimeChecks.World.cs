using System.Collections.Generic;
using InfiniCrafterLocal.Common.Systems;
using Terraria.ModLoader.IO;

internal static partial class EngineRuntimeChecks
{
    private static void PlacementLedgerRestoresSavedLayers()
    {
        const string key = "infiniGeneratedPlacementLedgerV2";
        var ledger = new GeneratedPlacementLedgerSystem();
        int oldWidth = Terraria.Main.maxTilesX, oldHeight = Terraria.Main.maxTilesY;
        Terraria.Main.maxTilesX = Terraria.Main.maxTilesY = 100;
        try
        {
            var cells = new List<TagCompound>();
            // Include values that would alias valid byte enum members after an
            // unchecked cast. They must not become placements on load.
            int x = 20;
            foreach (int layer in new[] { 1, 2, -255, -1, 0, 3, 256, 257, 258 })
                cells.Add(new TagCompound { ["layer"] = layer, ["x"] = x++, ["y"] = 30 });
            const string definition = "{\"id\":\"saved-item\"}";
            var saved = new TagCompound { [key] = new List<TagCompound> {
                new() { ["groupId"] = "saved-group", ["generatedItemId"] = "saved-item",
                    ["definitionJson"] = definition, ["cells"] = cells },
            } };
            ledger.LoadWorldData(saved);
            Equal(true, GeneratedPlacementLedgerSystem.Contains(GeneratedPlacementLayer.Tile, 20, 30), "restored tile identity");
            Equal(true, GeneratedPlacementLedgerSystem.Contains(GeneratedPlacementLayer.Wall, 21, 30), "restored wall identity");
            var roundtrip = new TagCompound();
            ledger.SaveWorldData(roundtrip);
            var groups = roundtrip.GetList<TagCompound>(key);
            Equal(1, groups.Count, "saved group count");
            Equal(2, groups[0].GetList<TagCompound>("cells").Count, "only valid layers survive");
            Equal(definition, groups[0].GetString("definitionJson"), "exact definition retained");
            ledger.ClearWorld();
            ledger.LoadWorldData(roundtrip);
            Equal(true, GeneratedPlacementLedgerSystem.Contains(GeneratedPlacementLayer.Wall, 21, 30), "second load retains wall");
        }
        finally
        {
            ledger.ClearWorld();
            Terraria.Main.maxTilesX = oldWidth;
            Terraria.Main.maxTilesY = oldHeight;
        }
    }
}

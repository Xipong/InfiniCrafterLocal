using System;
using System.Text.Json;
using InfiniCrafterLocal.Common.Services;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    private static void ParentNativeTileStateMatchesRealCampfireToggle()
    {
        WithPlacedLedger((player, ledger) => {
            Terraria.Main.netMode = NetmodeID.SinglePlayer;
            var campfire = new Item(ItemID.Campfire);
            using var request = JsonDocument.Parse(new GeneratorClient().Prepare(campfire, new Item(ItemID.WoodenSword), player).PayloadJson);
            var root = request.RootElement.GetProperty("itemA");
            Equal(true, root.TryGetProperty("nativeTileState", out var state), "native state source reaches actual prepared request");
            Equal(TileID.Campfire, state.GetProperty("tileId").GetInt32(), "observed native tile identity");
            Equal("top_left_frame_y", state.GetProperty("selector").GetString(), "frame state is not texture animation age");
            Equal("Terraria.Wiring.ToggleCampFire", state.GetProperty("provenance").GetString(), "literal native state provenance");
            Equal(state.GetRawText(), root.GetProperty("runtimeFacts").GetProperty("nativeTileState").GetRawText(), "one capture reaches facts envelope");
            Equal(state.GetRawText(), root.GetProperty("fingerprint").GetProperty("nativeTileState").GetRawText(), "one capture reaches fingerprint");
            Equal(false, request.RootElement.GetProperty("itemB").TryGetProperty("nativeTileState", out _), "unknown tile state remains absent");
            const int left = 40, top = 40;
            for (int x = 0; x < 3; x++) for (int y = 0; y < 2; y++) {
                var tile = Terraria.Main.tile[left+x,top+y]; tile.HasTile = true; tile.TileType = TileID.Campfire;
                tile.TileFrameX = (short)(x*18); tile.TileFrameY = (short)(y*18);
            }
            int initialY = Terraria.Main.tile[left,top].TileFrameY;
            Wiring.ToggleCampFire(left,top,Terraria.Main.tile[left,top],false,false);
            int offY = Terraria.Main.tile[left,top].TileFrameY;
            Equal(initialY, state.GetProperty("onMin").GetInt32(), "actual native on-state origin");
            Equal(offY-1, state.GetProperty("onMax").GetInt32(), "actual native state boundary");
            Equal(offY, state.GetProperty("offMin").GetInt32(), "actual native off-state origin");
            Equal(offY*2-1, state.GetProperty("offMax").GetInt32(), "full two-row off range");
            Wiring.ToggleCampFire(left,top,Terraria.Main.tile[left,top],true,false);
            Equal(initialY, (int)Terraria.Main.tile[left,top].TileFrameY, "native toggle returns to original state");
            for (int x = 0; x < 3; x++) for (int y = 0; y < 2; y++) {
                var tile = Terraria.Main.tile[left+x,top+y];
                Equal(true, tile.HasTile && tile.TileType == TileID.Campfire, "observation did not replace native material");
                Equal(y*18, (int)tile.TileFrameY, "all native rows toggle coherently");
            }
        });
    }
}

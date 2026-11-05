using System;
using System.Reflection;
using System.Text.Json;
using InfiniCrafterLocal.Common.Services;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    private static void ParentAmmoInventoryObservationDistinguishesUnavailableAndEmpty()
    {
        using var state = new NativeActorState();
        Terraria.Main.netMode = NetmodeID.SinglePlayer;
        var gun = new Item(ItemID.WoodenBow);
        var capture = typeof(GeneratorClient).GetMethod("AmmoRawFromItem", BindingFlags.Static | BindingFlags.NonPublic)!;
        JsonElement Read(Player? player)
            => JsonSerializer.SerializeToElement(capture.Invoke(null, new object?[] { gun, player }));
        var unknown = Read(null);
        Equal("unavailable", unknown.GetProperty("playerInventoryObservation").GetProperty("status").GetString(), "no actor is unknown, not empty inventory");
        Equal("no_player", unknown.GetProperty("playerInventoryObservation").GetProperty("reason").GetString(), "unknown observation gives exact reason");
        Equal(JsonValueKind.Null, unknown.GetProperty("playerInventoryAmmoRaw").ValueKind, "unobserved candidates not an empty fact");
        var owner = new Player();
        var empty = Read(owner);
        Equal("observed", empty.GetProperty("playerInventoryObservation").GetProperty("status").GetString(), "real empty inventory was observed");
        Equal(0, empty.GetProperty("playerInventoryAmmoRaw").GetArrayLength(), "observed empty remains an array");
        owner.inventory[54] = new Item(ItemID.WoodenArrow, 17);
        owner.inventory[55] = new Item(ItemID.WoodenArrow, 9);
        var observed = Read(owner);
        var candidates = observed.GetProperty("playerInventoryAmmoRaw");
        Equal(2, candidates.GetArrayLength(), "duplicate item identities retain positional multiplicity");
        Equal(54, candidates[0].GetProperty("inventorySlot").GetInt32(), "first original slot");
        Equal(17, candidates[0].GetProperty("stack").GetInt32(), "first original quantity");
        Equal(9, candidates[1].GetProperty("stack").GetInt32(), "second original quantity");
        Equal(17, owner.inventory[54].stack, "capture does not consume ammo");
        using var prepared = JsonDocument.Parse(new GeneratorClient().Prepare(gun, gun, owner).PayloadJson);
        var parent = prepared.RootElement.GetProperty("itemA");
        Equal("observed", parent.GetProperty("ammoRaw").GetProperty("playerInventoryObservation").GetProperty("status").GetString(), "actual request observes its owner inventory");
        Equal("unavailable", parent.GetProperty("fingerprint").GetProperty("ammoRaw").GetProperty("playerInventoryObservation").GetProperty("status").GetString(), "player-free fingerprint does not claim an observed empty inventory");
        string? packet = Environment.GetEnvironmentVariable("INFINI_PARENT_AMMO_PACKET");
        if (!string.IsNullOrEmpty(packet))
            System.IO.File.WriteAllText(packet, prepared.RootElement.GetRawText());
        owner.inventory = null!;
        var failed = Read(owner);
        Equal("unavailable", failed.GetProperty("playerInventoryObservation").GetProperty("status").GetString(), "failed scan cannot claim a completed observation");
        Equal("inventory_scan_failed", failed.GetProperty("playerInventoryObservation").GetProperty("reason").GetString(), "failure provenance retained");
        Equal(JsonValueKind.Null, failed.GetProperty("playerInventoryAmmoRaw").ValueKind, "failed scan never returns partial facts as complete");
    }
}

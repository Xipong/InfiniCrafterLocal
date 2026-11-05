using System;
using System.Reflection;
using System.Text.Json;
using InfiniCrafterLocal.Common.Services;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    private static readonly string[] RemovedAmmoCandidateFields = {
        "playerInventoryObservation", "playerInventoryAmmoRaw", "playerInventoryProjectileRaw",
        "fallbackAmmoRaw", "fallbackProjectileRaw", "candidateProjectileBindings"
    };

    private static void AssertWeaponAmmoHasNoCandidates(JsonElement raw)
    {
        foreach (string field in RemovedAmmoCandidateFields)
            Equal(false, raw.TryGetProperty(field, out _), "weapon context never exports concrete ammo field: " + field);
    }

    private static void ParentAmmoInventoryObservationDistinguishesUnavailableAndEmpty()
    {
        using var state = new NativeActorState();
        Terraria.Main.netMode = NetmodeID.SinglePlayer;
        var gun = new Item(ItemID.WoodenBow);
        var capture = typeof(GeneratorClient).GetMethod("AmmoRawFromItem", BindingFlags.Static | BindingFlags.NonPublic)!;
        JsonElement Read(Player? player)
            => JsonSerializer.SerializeToElement(capture.Invoke(null, new object?[] { gun, player }));
        var unknown = Read(null);
        AssertWeaponAmmoHasNoCandidates(unknown);
        var owner = new Player();
        Equal(unknown.GetRawText(), Read(owner).GetRawText(), "weapon context does not depend on an empty inventory");
        owner.inventory[54] = new Item(ItemID.WoodenArrow, 17);
        owner.inventory[55] = new Item(ItemID.FlamingArrow, 9);
        Equal(unknown.GetRawText(), Read(owner).GetRawText(), "weapon context does not select examples from a populated inventory");
        Equal(17, owner.inventory[54].stack, "capture does not consume ammo");
        using var prepared = JsonDocument.Parse(new GeneratorClient().Prepare(gun, gun, owner).PayloadJson);
        var parent = prepared.RootElement.GetProperty("itemA");
        AssertWeaponAmmoHasNoCandidates(parent.GetProperty("ammoRaw"));
        Equal(parent.GetProperty("ammoRaw").GetRawText(), parent.GetProperty("fingerprint").GetProperty("ammoRaw").GetRawText(), "root and fingerprint share weapon facts, not player loadouts");
        string? packet = Environment.GetEnvironmentVariable("INFINI_PARENT_AMMO_PACKET");
        if (!string.IsNullOrEmpty(packet)) System.IO.File.WriteAllText(packet, prepared.RootElement.GetRawText());
        owner.inventory = null!;
        Equal(unknown.GetRawText(), Read(owner).GetRawText(), "even unavailable inventory is never read for weapon context");
    }
}

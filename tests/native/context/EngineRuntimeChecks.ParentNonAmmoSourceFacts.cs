using System;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Services;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    private static void ParentNonAmmoSourceFactsArePreserved()
    {
        using var state = new NativeActorState();
        Terraria.Main.netMode = NetmodeID.SinglePlayer;
        var item = new Item(ItemID.TerraBlade);
        var inspected = AmmoSemantics(item);
        var stage = inspected["stages"]!.AsArray().OfType<JsonObject>()
            .Single(row => row["method"]!.GetValue<string>() == "Player.ItemCheck_Shoot");
        Equal(true, stage["sourceVerification"] is JsonObject, "item branch source is certified before transport");
        Equal(0, stage["conditionalArithmeticVariants"]!.AsArray().Count, "fixed companion does not depend on arithmetic variant eligibility");
        Equal(true, stage["spawnSites"]!.AsArray().OfType<JsonObject>().Any(site =>
            site["projectileBasis"]?.GetValue<string>() == "fixed_projectile"
            && site["projectileId"]?.GetValue<int>() == 984), "native item branch already describes companion projectile984");

        var capture = typeof(GeneratorClient).GetMethod("AmmoRawFromItem", BindingFlags.Static | BindingFlags.NonPublic)!;
        object? result = capture.Invoke(null, new object?[] { item, null });
        Equal(true, result is not null, "non-ammo item must retain its already inspected fixed spawn source");
        var raw = JsonSerializer.SerializeToElement(result);
        AssertSource(raw);
        Equal(CanonicalParentFactJson(JsonSerializer.SerializeToElement(inspected)),
            CanonicalParentFactJson(raw.GetProperty("projectileSemanticsReference")), "source semantics survive the no-ammo gate exactly");
        foreach (int type in new[] { ItemID.SpaceGun, ItemID.WoodenSword, ItemID.DirtBlock })
            Equal(true, capture.Invoke(null, new object?[] { new Item(type), null }) is null,
                "generic selection metadata does not invent no-ammo alternatives for item " + type);

        var owner = new Player();
        owner.inventory[0] = new Item(ItemID.WoodenArrow, 17);
        owner.inventory[54] = new Item(ItemID.FlamingArrow, 9);
        owner.inventory[55] = new Item(ItemID.HolyArrow, 5);
        using var request = JsonDocument.Parse(new GeneratorClient().Prepare(item, new Item(ItemID.DaedalusStormbow), owner).PayloadJson);
        var parent = request.RootElement.GetProperty("itemA");
        AssertSource(parent.GetProperty("ammoRaw"));
        AssertSource(parent.GetProperty("fingerprint").GetProperty("ammoRaw"));
        Equal(985, parent.GetProperty("shoot").GetInt32(), "source companion does not replace the captured shoot field");
        Equal(985, parent.GetProperty("directProjectileRaw").GetProperty("type").GetInt32(), "source companion does not replace direct projectile identity");

        var bow = request.RootElement.GetProperty("itemB");
        var observed = bow.GetProperty("ammoRaw");
        Equal("observed", observed.GetProperty("playerInventoryObservation").GetProperty("status").GetString(), "ammo weapon still observes request owner inventory");
        var candidates = observed.GetProperty("playerInventoryAmmoRaw");
        Equal(3, candidates.GetArrayLength(), "main inventory and ammo-slot candidates retain separate observed entries");
        Equal("0,54,55", string.Join(",", candidates.EnumerateArray().Select(row => row.GetProperty("inventorySlot").GetInt32())), "native inventory order is preserved");
        Equal(17, owner.inventory[0].stack, "capture does not consume main inventory ammunition");
        Equal(true, observed.GetProperty("fallbackAmmoRaw").EnumerateArray().All(row => row.GetProperty("inventorySlot").GetInt32() == -1), "fallback slots remain separate from observed inventory");
        var noPlayer = bow.GetProperty("fingerprint").GetProperty("ammoRaw");
        Equal("unavailable", noPlayer.GetProperty("playerInventoryObservation").GetProperty("status").GetString(), "player-free fingerprint remains unobserved");
        Equal("no_player", noPlayer.GetProperty("playerInventoryObservation").GetProperty("reason").GetString(), "fingerprint retains missing-player provenance");
        Equal(JsonValueKind.Null, noPlayer.GetProperty("playerInventoryAmmoRaw").ValueKind, "missing player is not observed empty inventory");

        static void AssertSource(JsonElement value)
        {
            Equal("weapon_without_ammo_source_alternatives", value.GetProperty("mode").GetString(), "existing non-ammo source envelope is reused");
            foreach (string key in new[] { "ammoId", "playerInventoryObservation", "playerInventoryAmmoRaw", "playerInventoryProjectileRaw", "fallbackAmmoRaw", "fallbackProjectileRaw", "candidateProjectileBindings" })
                Equal(false, value.TryGetProperty(key, out _), "non-ammo capture must not invent " + key);
            Equal("unknown_without_gameplay_execution", value.GetProperty("projectileSemanticsReference").GetProperty("finalShotOutcome").GetString(), "source site is not a final shot");
            var companion = value.GetProperty("nativeReplacementProjectileRaw").EnumerateArray().Single(row => row.GetProperty("type").GetInt32() == 984);
            var reference = companion.GetProperty("sourceReferences").EnumerateArray().Single(row => row.GetProperty("kind").GetString() == "native_fixed_projectile_spawn");
            Equal("projectileSemanticsReference.stages[1].spawnSites[0]", reference.GetProperty("sourcePath").GetString(), "profile links to exact source site");
            Equal(23695, reference.GetProperty("sourceFact").GetProperty("sourceSpawnIlOffset").GetInt32(), "profile preserves certified spawn offset");
            Equal("source_conditions_not_evaluated", reference.GetProperty("conditionStatus").GetString(), "source condition remains unevaluated");
            Equal("source_site_only_not_guaranteed_execution", reference.GetProperty("dispatchStatus").GetString(), "source admission remains unknown");
            Equal(false, companion.TryGetProperty("itemShootSpeed", out _), "weapon speed is not asserted as companion spawn speed");
        }
    }
}

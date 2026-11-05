using System;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using InfiniCrafterLocal.Common.Services;
using MonoMod.RuntimeDetour;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    private static void WeaponAmmoContextDoesNotTraverseDefaults()
    {
        using var state = new NativeActorState();
        var first = new Item(ItemID.Boomstick);
        var second = new Item(ItemID.MoltenFury);
        var owner = new Player();
        owner.inventory[54] = new Item(ItemID.MusketBall, 99);
        owner.inventory[55] = new Item(ItemID.WoodenArrow, 88);
        int calls = 0;
        using var hook = new Hook(typeof(Item).GetMethod(nameof(Item.SetDefaults), new[] { typeof(int) })!,
            (Action<Action<Item, int>, Item, int>)((original, item, type) => { calls++; original(item, type); }));
        var capture = typeof(GeneratorClient).GetMethod("AmmoRawFromItem", BindingFlags.NonPublic | BindingFlags.Static)!;
        var raw = JsonSerializer.SerializeToElement(capture.Invoke(null, new object?[] { first, owner }));
        Equal(0, calls, "weapon ammo extraction performs no item SetDefaults or catalog traversal");
        AssertWeaponAmmoHasNoCandidates(raw);
        var replacementRaw = JsonSerializer.SerializeToElement(capture.Invoke(null, new object?[] { second, owner }));
        Equal(0, calls, "confirmed replacement profile capture does not instantiate any ammo Item");
        Equal(ProjectileID.FireArrow, replacementRaw.GetProperty("nativeReplacementProjectileRaw")[0].GetProperty("type").GetInt32(),
            "no-scan regression retains the real Molten Fury replacement profile");
        Equal(first.useAmmo, raw.GetProperty("ammoId").GetInt32(), "native ammo category retained");
        Equal(true, !string.IsNullOrEmpty(raw.GetProperty("ammoCategoryName").GetString()), "canonical category explains ammunition without examples");
        var client = new GeneratorClient();
        calls = 0;
        var sync = client.Prepare(first, second, owner);
        Equal(4, calls, "two-parent Prepare performs only bounded parent normalization/tooltip defaults");
        calls = 0;
        var deferred = client.PrepareDeferred(first, second, owner);
        Equal(4, calls, "normal craft admission does not scan any ammo catalog or inventory defaults");
        PumpParentAnalysis(Task.Run(deferred.CompleteAnalysis));
        Equal(4, calls, "source worker completion also never starts a hidden ammo scan");
        var expected = JsonNode.Parse(sync.PayloadJson)!;
        var actual = JsonNode.Parse(deferred.PayloadJson)!;
        Equal(true, JsonNode.DeepEquals(expected, actual), "both actual Prepare entrypoints deliver identical weapon context");
        foreach (var item in new[] { actual["itemA"]!, actual["itemB"]! })
        {
            using var element = JsonDocument.Parse(item["ammoRaw"]!.ToJsonString());
            AssertWeaponAmmoHasNoCandidates(element.RootElement);
            AssertParentFingerprintNativeFacts(item["ammoRaw"], item["fingerprint"]!["ammoRaw"],
                "root/fingerprint category and source conversion facts", requireRootView: true);
        }
        Equal(first.damage, actual["itemA"]!["damage"]!.GetValue<int>(), "weapon damage never includes arbitrary ammo damage");
        Equal(second.damage, actual["itemB"]!["damage"]!.GetValue<int>(), "other weapon retains its independent native damage");
        Equal(99, owner.inventory[54].stack, "no ammo consumption or inventory mutation");
    }

    private static void WeaponAmmoContextPreservesAmmoParentIdentity()
    {
        using var state = new NativeActorState();
        var arrow = new Item(ItemID.FlamingArrow, 17);
        var weapon = new Item(ItemID.WoodenBow);
        using var packet = JsonDocument.Parse(new GeneratorClient().Prepare(arrow, weapon, new Player()).PayloadJson);
        var parent = packet.RootElement.GetProperty("itemA");
        var ammo = parent.GetProperty("ammoRaw");
        Equal("this_item_is_ammo", ammo.GetProperty("mode").GetString(), "actual ammo ingredient remains a first-class parent");
        Equal(arrow.type, ammo.GetProperty("ammoItemRaw").GetProperty("type").GetInt32(), "ammo parent native identity survives");
        Equal(arrow.damage, ammo.GetProperty("ammoItemRaw").GetProperty("damage").GetInt32(), "ammo parent own damage survives");
        Equal(arrow.knockBack, ammo.GetProperty("ammoItemRaw").GetProperty("knockback").GetSingle(), "ammo parent own knockback survives");
        Equal(arrow.shoot, ammo.GetProperty("projectileRaw").GetProperty("type").GetInt32(), "ammo parent's own projectile survives");
        Equal(arrow.damage, parent.GetProperty("damage").GetInt32(), "root remains ammo's own stats");
        AssertParentFingerprintNativeFacts(ammo, parent.GetProperty("fingerprint").GetProperty("ammoRaw"),
            "ammo parent fingerprint retains full independent identity", requireRootView: true);
        AssertWeaponAmmoHasNoCandidates(packet.RootElement.GetProperty("itemB").GetProperty("ammoRaw"));
    }
}

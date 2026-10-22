using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Items;
using Mono.Cecil;
using Mono.Cecil.Cil;
using MonoMod.Cil;
using MonoMod.RuntimeDetour;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;
using Terraria.ModLoader.Default;
using Terraria.UI;

internal static partial class EngineRuntimeChecks
{
    private static readonly MethodInfo AccessoryCheckEntry = typeof(ItemSlot).GetMethod("AccCheck_ForPlayer",
        BindingFlags.Static | BindingFlags.NonPublic)!;
    private static readonly MethodInfo AccessorySwapEntry = typeof(ItemSlot).GetMethod("AccessorySwap",
        BindingFlags.Static | BindingFlags.NonPublic)!;
    private static readonly Func<Item, Item, bool> NativeAccessoryIdentity = typeof(Item).GetMethod("IsTheSameAs",
        BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)!.CreateDelegate<Func<Item, Item, bool>>();

    // Public existing APIs only: this file also compiles against pre-fix main.
    private static ModSystem? AccessoryIdentityBridge()
    {
        Type? type = typeof(GeneratedItem).Assembly.GetType("InfiniCrafterLocal.Common.Systems.GeneratedAccessoryIdentitySystem");
        return type is null ? null : (ModSystem)Activator.CreateInstance(type)!;
    }

    private sealed class AccessoryIdentityScope : IDisposable
    {
        private readonly NativeActorState actors = new();
        private readonly object? oldSlotInstance;
        private readonly int oldGameMode = Terraria.Main.GameMode;
        private readonly bool oldMenu = Terraria.Main.gameMenu;
        private readonly PropertyInfo slotInstance = typeof(ContentInstance<ModAccessorySlotPlayer>).GetProperty("Instance")!;
        private readonly System.Collections.IDictionary loaders = (System.Collections.IDictionary)typeof(LoaderManager)
            .GetField("loadersByType", BindingFlags.Static | BindingFlags.NonPublic)!.GetValue(null)!;
        private readonly object? oldLoader;
        internal readonly Player Player = new();
        internal readonly ModAccessorySlotPlayer Slots = new();
        internal readonly Item[] Extra;
        internal readonly AccessorySlotIdentityProbe[] SlotRules;
        internal AccessoryIdentityScope(int modSlots = 0)
        {
            oldSlotInstance = slotInstance.GetValue(null);
            oldLoader = loaders[typeof(AccessorySlotLoader)];
            var loader = (AccessorySlotLoader)Activator.CreateInstance(typeof(AccessorySlotLoader), nonPublic: true)!;
            SlotRules = Enumerable.Range(0, modSlots).Select(_ => new AccessorySlotIdentityProbe()).ToArray();
            var registeredSlots = (IList<ModAccessorySlot>)typeof(AccessorySlotLoader).GetField("list", TestInstance)!.GetValue(loader)!;
            foreach (var rule in SlotRules) registeredSlots.Add(rule);
            loaders[typeof(AccessorySlotLoader)] = loader;
            typeof(ModType<Player>).GetProperty("Entity", TestInstance)!.SetValue(Slots, Player);
            typeof(Player).GetField("modPlayers", TestInstance)!.SetValue(Player, new ModPlayer[] { Slots });
            slotInstance.SetValue(null, Slots);
            var slots = (Dictionary<string, int>)typeof(ModAccessorySlotPlayer).GetField("slots", TestInstance)!.GetValue(Slots)!;
            for (int i = 0; i < modSlots; i++) slots.Add("identity-test-" + i, i);
            Extra = Enumerable.Range(0, modSlots * 2).Select(_ => new Item()).ToArray();
            typeof(ModAccessorySlotPlayer).GetField("exAccessorySlot", TestInstance)!.SetValue(Slots, Extra);
            typeof(ModAccessorySlotPlayer).GetField("sharedLoadoutSlotTypes", TestInstance)!.SetValue(Slots, new bool[modSlots]);
            Terraria.Main.player[0] = Player; Terraria.Main.myPlayer = 0;
            Terraria.Main.netMode = NetmodeID.SinglePlayer;
            Terraria.Main.gameMenu = false; Terraria.Main.GameMode = 0;
        }
        internal Item[] Collection() => Player.armor.Concat(Extra).ToArray();
        internal bool Refused(Item item, int slot = 4)
            => (bool)AccessoryCheckEntry.Invoke(null, new object[] { Player, Collection(), item, slot })!;
        internal (bool Accepted, Item Returned) Swap(Item item)
        {
            object[] args = { Player, item, new Item() };
            return ((bool)AccessorySwapEntry.Invoke(null, args)!, (Item)args[2]);
        }
        public void Dispose()
        {
            slotInstance.SetValue(null, oldSlotInstance);
            if (oldLoader is null) loaders.Remove(typeof(AccessorySlotLoader));
            else loaders[typeof(AccessorySlotLoader)] = oldLoader;
            Terraria.Main.GameMode = oldGameMode; Terraria.Main.gameMenu = oldMenu;
            actors.Dispose();
        }
    }

    private sealed class AccessorySlotIdentityProbe : ModAccessorySlot
    {
        internal bool Accept = true;
        public override bool CanAcceptItem(Item item, AccessorySlotType context) => Accept;
    }

    private sealed class AccessoryIdentityProbe : GeneratedItem
    {
        internal bool DenyEquip;
        public override bool CanEquipAccessory(Player player, int slot, bool modded) => !DenyEquip;
    }

    private sealed class ForeignAccessoryIdentityProbe : ModItem
    {
        internal bool DenyPair;
        public override bool CanAccessoryBeEquippedWith(Item equippedItem, Item incomingItem, Player player)
            => !DenyPair;
    }

    private static GeneratedItem AccessoryIdentityItem(string id, int prefix = 0)
    {
        GeneratedItem fixture = NativeUtilityItem("\"defense\":1");
        fixture.Data.Id = id;
        var item = new Item { type = ItemID.ObsidianSkull, netID = ItemID.ObsidianSkull,
            accessory = true, stack = 1, maxStack = 1, prefix = prefix };
        return AttachItem(new AccessoryIdentityProbe(), item, fixture.Data);
    }

    private static Item ForeignAccessoryIdentityItem(int type, bool veto = false)
    {
        var item = new Item { type = type, netID = type, accessory = true, stack = 1, maxStack = 1 };
        var foreign = new ForeignAccessoryIdentityProbe { DenyPair = veto };
        typeof(ModType<Item>).GetProperty("Entity", TestInstance)!.SetValue(foreign, item);
        typeof(Item).GetProperty("ModItem", TestInstance)!.SetValue(item, foreign);
        return item;
    }

    private static void GeneratedAccessoryIdentityNativeAdmission()
    {
        using var scope = new AccessoryIdentityScope(1);
        ModSystem? bridge = AccessoryIdentityBridge(); bridge?.Load();
        try
        {
            foreach ((string id, int prefix, bool refused) in new[] {
                ("other", 0, false), ("other", (int)PrefixID.Warding, false),
                ("first", 0, true), ("first", (int)PrefixID.Warding, true), ("FIRST", 0, false) })
            {
                GeneratedItem equipped = AccessoryIdentityItem("first"), incoming = AccessoryIdentityItem(id, prefix);
                scope.Player.armor[3] = equipped.Item;
                Equal(true, NativeAccessoryIdentity(equipped.Item, incoming.Item), "global native proxy identity remains unchanged");
                Equal(refused, scope.Refused(incoming.Item), $"definition={id}, prefix={prefix} native drag admission");
                scope.Player.armor[3] = new Item(); scope.Extra[0] = equipped.Item;
                Equal(refused, scope.Refused(incoming.Item), "modded equipped slot uses the same exact definition identity");
                scope.Extra[0] = new Item(); scope.Player.armor[13] = equipped.Item;
                Equal(refused, scope.Refused(incoming.Item), "native all-slot duplicate scan includes vanity");
                scope.Player.armor[13] = new Item();
            }
            var first = AccessoryIdentityItem("first");
            scope.Player.armor[3] = first.Item;
            var same = AccessoryIdentityItem("first", PrefixID.Warding);
            same.Data.Name = "Different name"; same.Data.RecipeKey = "other-recipe";
            Equal(true, scope.Refused(same.Item), "name, recipe metadata and prefix cannot create a second definition ID");
            Equal(false, scope.Refused(same.Item, 3), "replacing the exact definition in its own target slot stays native");
            scope.Player.armor[4] = AccessoryIdentityItem("other").Item;
            Equal(true, scope.Refused(same.Item, 4), "different definition in target slot cannot hide a duplicate elsewhere");
        }
        finally { bridge?.Unload(); }
    }

    private static void GeneratedAccessoryIdentityNativeControls()
    {
        using var scope = new AccessoryIdentityScope();
        ModSystem? bridge = AccessoryIdentityBridge(); bridge?.Load();
        try
        {
            scope.Player.armor[3] = AccessoryIdentityItem("first").Item;
            foreach (string source in new[] { "empty-id", "whitespace-id", "unresolved", "not-accessory" })
            {
                var incoming = AccessoryIdentityItem("other");
                if (source == "empty-id") incoming.Data.Id = "";
                if (source == "whitespace-id") incoming.Data.Id = " ";
                if (source == "unresolved") incoming.Data.SourceMode = "player_save_ref";
                if (source == "not-accessory") incoming.Data.Accessory.Enabled = false;
                Equal(true, scope.Refused(incoming.Item), source + " keeps the native shared-proxy refusal");
            }
            Equal(false, scope.Refused(new Item()), "empty incoming item keeps native identity");
            // Vanilla and another mod still use the real Item.IsTheSameAs result.
            foreach (bool foreign in new[] { false, true })
            {
                Item Make(int type) => foreign ? ForeignAccessoryIdentityItem(type)
                    : new Item { type = type, netID = type, accessory = true, stack = 1 };
                scope.Player.armor[3] = Make(ItemID.ObsidianSkull);
                Equal(true, scope.Refused(Make(ItemID.ObsidianSkull)), "native/foreign same-type duplicate remains refused");
                Equal(false, scope.Refused(Make(ItemID.Aglet)), "native/foreign different type stays allowed");
                Equal(true, scope.Refused(AccessoryIdentityItem("other").Item), "mixed pair retains native identity");
            }
            scope.Player.armor[3] = ForeignAccessoryIdentityItem(ItemID.Aglet, veto: true);
            Equal(true, scope.Refused(AccessoryIdentityItem("other").Item), "foreign ModItem pair veto is not bypassed");
            scope.Player.armor[3] = AccessoryIdentityItem("first").Item;
            scope.Player.armor[3].wingSlot = 1;
            var wings = AccessoryIdentityItem("other"); wings.Item.wingSlot = 2;
            Equal(true, scope.Refused(wings.Item), "different generated definitions cannot bypass native wing exclusion");
            scope.Player.armor[3].wingSlot = 0;
            var denied = (AccessoryIdentityProbe)AccessoryIdentityItem("other"); denied.DenyEquip = true;
            Equal(true, scope.Refused(denied.Item), "native CanEquipAccessory veto is preserved");
        }
        finally { bridge?.Unload(); }
    }

    private static void GeneratedAccessoryIdentityNativeQuickEquip()
    {
        using var scope = new AccessoryIdentityScope();
        ModSystem? bridge = AccessoryIdentityBridge(); bridge?.Load();
        try
        {
            foreach (int prefix in new[] { 0, (int)PrefixID.Warding })
            {
                scope.Player.armor[3] = AccessoryIdentityItem("first").Item;
                scope.Player.armor[4] = new Item();
                var result = scope.Swap(AccessoryIdentityItem("other", prefix).Item);
                Equal(true, result.Accepted, "native quick equip succeeds");
                Equal(true, result.Returned.IsAir, "distinct generated definition uses free slot instead of replacing old item");
                Equal("first", ((GeneratedItem)scope.Player.armor[3].ModItem).Data.Id, "old accessory retained");
                Equal("other", ((GeneratedItem)scope.Player.armor[4].ModItem).Data.Id, "new accessory reaches second slot");
                var duplicate = scope.Swap(AccessoryIdentityItem("first", prefix).Item);
                Equal(true, duplicate.Accepted, "same ID quick equip still swaps existing copy");
                Equal("first", ((GeneratedItem)duplicate.Returned.ModItem).Data.Id, "same ID returns replaced copy");
                Equal(1, scope.Player.armor.Count(i => i.ModItem is GeneratedItem g && g.Data.Id == "first"),
                    "quick equip never adds a second copy of one definition");
            }
            // Native unlocked-slot selection remains responsible for Demon Heart
            // and Master slots. Fill all five normal slots with distinct IDs.
            for (int i = 3; i < 8; i++) scope.Player.armor[i] = AccessoryIdentityItem("full-" + i).Item;
            scope.Player.armor[8] = new Item(); scope.Player.armor[9] = new Item();
            scope.Player.extraAccessory = false;
            Equal(true, scope.Swap(AccessoryIdentityItem("overflow").Item).Accepted, "native full inventory replacement still works");
            Equal(true, scope.Player.armor[8].IsAir && scope.Player.armor[9].IsAir, "normal-mode locked slots remain unused");
            Terraria.Main.GameMode = 1; scope.Player.extraAccessory = true;
            Equal(true, scope.Swap(AccessoryIdentityItem("expert-slot").Item).Accepted, "native Demon Heart slot unlock works");
            Equal("expert-slot", ((GeneratedItem)scope.Player.armor[8].ModItem).Data.Id, "unlocked sixth slot selected");
            Equal(true, scope.Player.armor[9].IsAir, "Master slot remains locked in Expert");
        }
        finally { bridge?.Unload(); }
    }

    private static void GeneratedAccessoryIdentityNativeLifecycle()
    {
        using var scope = new AccessoryIdentityScope();
        ModSystem? bridge = AccessoryIdentityBridge();
        if (bridge is null) throw new InvalidOperationException("generated accessory identity bridge missing on baseline");
        scope.Player.armor[3] = AccessoryIdentityItem("first").Item;
        var incoming = AccessoryIdentityItem("other").Item;
        Equal(true, scope.Refused(incoming), "unpatched native RED control");
        try
        {
            for (int pass = 0; pass < 2; pass++)
            {
                bridge.Load();
                Equal(false, scope.Refused(incoming), "installed native GREEN");
                Equal(true, scope.Swap(incoming).Returned.IsAir, "installed quick-equip comparison uses free slot");
                scope.Player.armor[4] = new Item();
                bridge.Unload();
                Equal(true, scope.Refused(incoming), "unload restores native comparison");
                var nativeSwap = scope.Swap(incoming);
                Equal("first", ((GeneratedItem)nativeSwap.Returned.ModItem).Data.Id, "unload also restores native quick replacement");
                scope.Player.armor[3] = AccessoryIdentityItem("first").Item;
            }
            // Mutate the second method's live MonoMod chain. A failed second
            // installation must roll back the first method too, not half-patch.
            using (var mutant = new ILHook(AccessorySwapEntry, il =>
            {
                var calls = il.Body.Instructions.Where(i => i.Operand is MethodReference m
                    && m.FullName == "System.Boolean Terraria.Item::IsTheSameAs(Terraria.Item)").ToArray();
                var cursor = new ILCursor(il); cursor.Goto(calls[1]); cursor.Remove();
                cursor.EmitDelegate<Func<Item, Item, bool>>((a, b) => NativeAccessoryIdentity(a, b));
            }))
            {
                bool refused = false;
                try { bridge.Load(); }
                catch (Exception error) { refused = error.ToString().Contains("identity callsite shape mismatch", StringComparison.Ordinal); }
                Equal(true, refused, "changed native pattern fails with a clear error");
                Equal(true, scope.Refused(incoming), "second-method failure rolls back first-method patch");
            }
            bridge.Load();
            Equal(false, scope.Refused(incoming), "valid pattern installs again after failure cleanup");
        }
        finally { bridge.Unload(); }
    }

    private static void GeneratedAccessoryIdentityNativeModdedQuickEquip()
    {
        using var scope = new AccessoryIdentityScope(1);
        ModSystem? bridge = AccessoryIdentityBridge(); bridge?.Load();
        try
        {
            scope.Extra[0] = AccessoryIdentityItem("modded-first").Item;
            var distinct = scope.Swap(AccessoryIdentityItem("other").Item);
            Equal(true, distinct.Accepted, "native quick equip with modded collection succeeds");
            Equal(true, distinct.Returned.IsAir, "different definition in modded slot does not steal native free-slot selection");
            Equal("modded-first", ((GeneratedItem)scope.Extra[0].ModItem).Data.Id, "distinct modded accessory retained");
            Equal("other", ((GeneratedItem)scope.Player.armor[3].ModItem).Data.Id, "new definition uses free vanilla slot");
            var same = scope.Swap(AccessoryIdentityItem("modded-first", PrefixID.Warding).Item);
            Equal(true, same.Accepted, "same definition uses native modded-slot replacement");
            Equal("modded-first", ((GeneratedItem)same.Returned.ModItem).Data.Id, "old modded copy returned");
            Equal(1, scope.Collection().Count(i => i.ModItem is GeneratedItem g && g.Data.Id == "modded-first"),
                "modded quick replacement adds no duplicate definition");

            for (int i = 3; i < 8; i++) scope.Player.armor[i] = AccessoryIdentityItem("full-" + i).Item;
            scope.Extra[0] = new Item(); scope.SlotRules[0].Accept = false;
            Equal(true, scope.Swap(AccessoryIdentityItem("refused-slot").Item).Accepted, "native fallback replacement remains available");
            Equal(true, scope.Extra[0].IsAir, "foreign modded slot CanAcceptItem refusal remains authoritative");
            scope.SlotRules[0].Accept = true;
            Equal(true, scope.Swap(AccessoryIdentityItem("accepted-slot").Item).Accepted, "allowed modded slot receives native quick equip");
            Equal("accepted-slot", ((GeneratedItem)scope.Extra[0].ModItem).Data.Id, "native modded insertion keeps exact definition");
        }
        finally { bridge?.Unload(); }
    }
}

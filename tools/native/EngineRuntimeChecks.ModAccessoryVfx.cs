using System;
using System.Collections;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.VFX;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;
using Terraria.ModLoader.Default;

internal static partial class EngineRuntimeChecks
{
    private sealed class ModSlotProbeA : ModAccessorySlot { }
    private sealed class ModSlotProbeB : ModAccessorySlot { }
    private static void ModAccessoryItemTokenNativeSync()
    {
        using var peers = new ReviewPeers();
        using var scope = new AccessoryIdentityScope(2);
        var oldBaseline = Terraria.Main.clientPlayer;
        var cache = (IDictionary)typeof(ModContent).Assembly.GetType("Terraria.ModLoader.ContentCache")!
            .GetField("_cachedContentForAllMods", BindingFlags.Static | BindingFlags.NonPublic)!.GetValue(null)!;
        var key = typeof(ModAccessorySlot);
        bool hadCache = cache.Contains(key);
        object? oldCache = hadCache ? cache[key] : null;
        try
        {
            ModAccessorySlot[] slots = { new ModSlotProbeA(), new ModSlotProbeB() };
            var loader = LoaderManager.Get<AccessorySlotLoader>();
            var loaded = (System.Collections.Generic.IList<ModAccessorySlot>)typeof(AccessorySlotLoader).GetField("list", TestInstance)!.GetValue(loader)!;
            loaded.Clear();
            for (int i = 0; i < slots.Length; i++) {
                typeof(ModAccessorySlot).GetProperty("Type", TestInstance)!.SetValue(slots[i], i);
                loaded.Add(slots[i]);
            }
            typeof(Loader).GetField("<TotalCount>k__BackingField", TestInstance)!.SetValue(loader, slots.Length);
            cache[key] = Array.AsReadOnly(slots);
            var baselinePlayer = new Player();
            var baselineSlots = new ModAccessorySlotPlayer();
            typeof(ModType<Player>).GetProperty("Entity", TestInstance)!.SetValue(baselineSlots, baselinePlayer);
            typeof(Player).GetField("modPlayers", TestInstance)!.SetValue(baselinePlayer, new ModPlayer[] { baselineSlots });
            var baselineItems = new[] { new Item(), new Item(), new Item(), new Item() };
            typeof(ModAccessorySlotPlayer).GetField("exAccessorySlot", TestInstance)!.SetValue(baselineSlots, baselineItems);
            var player = scope.Player; player.active = true; player.whoAmI = 0;
            Terraria.Main.clientPlayer = baselinePlayer; peers.Mode(NetmodeID.MultiplayerClient, 0);
            var data = ReviewContactItemData(); data.Id = "mod_slot_sync";
            data.VfxManifest.Slots = LightManifest(data.RuntimeProgram.ItemEntityId, RuntimeEventKind.OnHit).Slots;
            data.VfxManifest.Assets = Array.Empty<InfiniCrafterLocal.Common.Models.VfxAssetSpec>(); data.Normalize(); peers.Register(data);
            var first = ReviewItem(data); var second = ReviewItem(data);
            scope.Extra[0] = first.Item; scope.Extra[1] = second.Item;
            Equal(true, ReferenceEquals(Terraria.Main.player[0],player), "fixture uses actual local player");
            Equal(true, first.HasItemEventVfx, "fixture has item event VFX");
            Equal(2, player.GetModPlayer<ModAccessorySlotPlayer>().LoadedSlotCount, "two native slots registered");
            using (new Terraria.Main.CurrentPlayerOverride(player))
                Equal(true, ReferenceEquals(slots[0].FunctionalItem, first.Item), "first native singleton accesses actual player item");
            first.Item.CopyNetStateTo(baselineItems[0]); second.Item.CopyNetStateTo(baselineItems[1]);
            var priorCurrent = new Player();
            using (new Terraria.Main.CurrentPlayerOverride(priorCurrent))
            {
                InfiniItemVfxRuntime.ObserveItemPresentationSlot(player, first.Item, true);
                Equal(true, ReferenceEquals(Terraria.Main.CurrentPlayer, priorCurrent), "first lookup restores player override");
                Equal(true, first.Item.IsNetStateDifferent(baselineItems[0]), "first singleton slot marked for sync");
                Equal(false, second.Item.IsNetStateDifferent(baselineItems[1]), "first slot does not dirty second");
                InfiniItemVfxRuntime.ObserveItemPresentationSlot(player, second.Item, true);
                Equal(true, ReferenceEquals(Terraria.Main.CurrentPlayer, priorCurrent), "second lookup restores player override");
                Equal(true, second.Item.IsNetStateDifferent(baselineItems[1]), "second singleton slot marked for sync");
                first.Item.CopyNetStateTo(baselineItems[0]); second.Item.CopyNetStateTo(baselineItems[1]);
                int version0 = first.Item.NetStateVersion, version1 = second.Item.NetStateVersion;
                InfiniItemVfxRuntime.ObserveItemPresentationSlot(player, second.Item, true);
                InfiniItemVfxRuntime.ObserveItemPresentationSlot(player, first.Item, true);
                Equal(version0, first.Item.NetStateVersion, "first stable slot stays clean");
                Equal(version1, second.Item.NetStateVersion, "second stable slot stays clean");
                Equal(false, second.Item.IsNetStateDifferent(baselineItems[0]), "replacement begins with equal baseline");
                Equal(false, first.Item.IsNetStateDifferent(baselineItems[1]), "reverse replacement begins with equal baseline");
                scope.Extra[0] = second.Item; scope.Extra[1] = first.Item;
                InfiniItemVfxRuntime.ObserveItemPresentationSlot(player, first.Item, true);
                InfiniItemVfxRuntime.ObserveItemPresentationSlot(player, second.Item, true);
                Equal(true, second.Item.IsNetStateDifferent(baselineItems[0]), "first slot replacement forces native sync");
                Equal(true, first.Item.IsNetStateDifferent(baselineItems[1]), "second slot replacement forces native sync");
                Equal(true, ReferenceEquals(Terraria.Main.CurrentPlayer, priorCurrent), "swapped lookup restores outer player override");
                second.Item.CopyNetStateTo(baselineItems[0]); first.Item.CopyNetStateTo(baselineItems[1]);
                Equal(false, first.Item.IsNetStateDifferent(baselineItems[0]), "reverse slot begins with equal baseline");
                Equal(false, second.Item.IsNetStateDifferent(baselineItems[1]), "other reverse slot begins with equal baseline");
                scope.Extra[0] = first.Item; scope.Extra[1] = second.Item;
                InfiniItemVfxRuntime.ObserveItemPresentationSlot(player, second.Item, true);
                InfiniItemVfxRuntime.ObserveItemPresentationSlot(player, first.Item, true);
                Equal(true, first.Item.IsNetStateDifferent(baselineItems[0]), "first slot reverse replacement forces sync");
                Equal(true, second.Item.IsNetStateDifferent(baselineItems[1]), "second slot reverse replacement forces sync");
            }
        }
        finally
        {
            Terraria.Main.clientPlayer = oldBaseline;
            if (hadCache) cache[key] = oldCache; else cache.Remove(key);
            InfiniItemVfxRuntime.ClearUseEventCaches();
        }
    }
}

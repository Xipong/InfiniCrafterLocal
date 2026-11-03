using System;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Content.Items;
using Terraria;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private static void WithPlayer(Action<Player, InfiniCraftPlayer> check)
    {
        var player = new Player();
        var generated = new InfiniCraftPlayer();
        typeof(ModType<Player>).GetProperty("Entity", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)!
            .SetValue(generated, player);
        typeof(Player).GetField("modPlayers", BindingFlags.Instance | BindingFlags.NonPublic)!
            .SetValue(player, new ModPlayer[] { generated });
        // Bind the real per-player implementation without running the mod loader.
        var instance = typeof(ContentInstance<InfiniCraftPlayer>).GetProperty("Instance")!;
        object? previous = instance.GetValue(null);
        instance.SetValue(null, generated);
        try { check(player, generated); }
        finally { instance.SetValue(null, previous); }
    }

    private static void StationKeyIsNotConsumed()
    {
        WithPlayer((player, _) =>
        {
            var core = new InfiniCore();
            var item = new Item { type = 1, stack = 1 };
            typeof(ModType<Item>).GetProperty("Entity", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)!
                .SetValue(core, item);
            typeof(Item).GetProperty("ModItem")!.SetValue(item, core);
            core.SetDefaults();
            Equal(false, item.consumable, "station key is not a consumable");
            Equal(true, ItemLoader.CanRightClick(item), "station key still exposes right click");
            // ItemLoader.RightClick calls this gate and decrements stack even if
            // Item.consumable is false. Exercise the actual tML dispatch.
            Equal(false, ItemLoader.ConsumeItem(item, player), "right click must not consume station key");
        });
    }

    private static void AccessoryDefenseAppliedOnce()
    {
        WithPlayer((player, _) =>
        {
            var item = new Item();
            var generated = new GeneratedItem();
            typeof(ModType<Item>).GetProperty("Entity", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)!
                .SetValue(generated, item);
            var data = GeneratedItemData.Placeholder();
            data.Accessory = new AccessorySpec { Enabled = true, Defense = 7, MaxLife = 20 };
            data.RuntimeProgram.Bindings = new[] {
                new RuntimeBindingSpec { Id = "equip", Input = RuntimeInputKind.Equipped,
                    Role = RuntimeEntityRole.Primary, UsePolicy = new RuntimeBindingUsePolicySpec {
                        Action = new RuntimeBindingActionSpec { Kind = RuntimeBindingAction.EquipPassive, TargetId = data.RuntimeProgram.ItemEntityId },
                    } },
            };
            data.ApplyToItem(item);
            typeof(GeneratedItem).GetProperty("Data")!.SetValue(generated, data);
            Equal(7, item.defense, "authored defense projects to vanilla item");
            foreach (bool hidden in new[] { false, true })
            {
                player.statDefense = new Player.DefenseStat();
                player.statDefense += 13;
                player.statLifeMax2 = 100;
                // Same order as Terraria.Player.UpdateEquips: GrantArmorBenefits
                // applies Item.defense, then the functional accessory hook runs.
                player.GrantArmorBenefits(item);
                generated.UpdateAccessory(player, hidden);
                Equal(20, (int)player.statDefense, "accessory defense applied once");
                Equal(120, player.statLifeMax2, "non-vanilla accessory effect retained");
            }
        });
    }

    private static void EquipmentVisibilityUsesArmorSlot()
    {
        WithPlayer((player, _) =>
        {
            var generated = new GeneratedItem();
            var item = new Item { type = 1, stack = 1 };
            typeof(ModType<Item>).GetProperty("Entity", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)!
                .SetValue(generated, item);
            typeof(Item).GetProperty("ModItem")!.SetValue(item, generated);
            generated.Data.Accessory.Enabled = true;
            generated.Data.ApplyToItem(item);
            var collect = typeof(GeneratedEquipOverlayDrawLayerBase).GetMethod("CollectVisibleOverlays", BindingFlags.Static | BindingFlags.NonPublic)!;
            int Count() => ((System.Collections.IList)collect.Invoke(null, new object[] { player })!).Count;
            int mode = Terraria.Main.GameMode;
            bool extraAccessory = player.extraAccessory;
            try
            {
                // This check isolates hide-flag indexing across all seven usable
                // slots. Locked-slot behavior has its own real-engine control.
                Terraria.Main.GameMode = 2;
                player.extraAccessory = true;
                for (int slot = 3; slot < 10; slot++)
                {
                    Equal(true, player.IsItemSlotUnlockedAndUsable(slot), $"fixture unlocks slot {slot}");
                    player.armor[slot] = item;
                    Equal(1, Count(), $"visible accessory slot {slot}");
                    player.hideVisibleAccessory[slot] = true;
                    Equal(0, Count(), $"hidden accessory slot {slot}");
                    player.hideVisibleAccessory[slot] = false;
                    player.hideVisibleAccessory[(slot + 1) % 10] = true;
                    Equal(1, Count(), $"unrelated hide flag must not hide slot {slot}");
                    Array.Clear(player.hideVisibleAccessory);
                    player.armor[slot] = new Item();
                }
            }
            finally { Terraria.Main.GameMode = mode; player.extraAccessory = extraAccessory; }
        });
    }

    private static void MiningBuffOrderIndependent()
    {
        foreach (float[] values in new[] {
            new[] { 2f, 3f, 0.5f }, new[] { 2f, 0.5f, 3f },
            new[] { 3f, 2f, 0.5f }, new[] { 3f, 0.5f, 2f },
            new[] { 0.5f, 2f, 3f }, new[] { 0.5f, 3f, 2f },
        })
            WithPlayer((player, generated) =>
            {
                player.active = true;
                player.pickSpeed = 3f;
                foreach (float value in values)
                    generated.ApplyGeneratedUtilityBuff(new GeneratedBuffSpec { DurationTicks = 60, MiningSpeedMultiplier = value });
                generated.PostUpdateEquips();
                Equal(1f, player.pickSpeed, $"combined mining [{string.Join(";", values)}]");
            });
    }

    private static void MovementBuffOrderIndependent()
    {
        foreach (float[] values in new[] {
            new[] { 1f, 1.5f, -0.5f }, new[] { 1f, -0.5f, 1.5f },
            new[] { 1.5f, 1f, -0.5f }, new[] { 1.5f, -0.5f, 1f },
            new[] { -0.5f, 1f, 1.5f }, new[] { -0.5f, 1.5f, 1f },
        })
            WithPlayer((player, generated) =>
            {
                player.active = true;
                player.moveSpeed = 1f;
                foreach (float value in values)
                    generated.ApplyGeneratedUtilityBuff(new GeneratedBuffSpec { DurationTicks = 60, MovementSpeed = value });
                generated.PostUpdateEquips();
                Equal(3f, player.moveSpeed, $"combined movement [{string.Join(",", values)}]");
            });
    }

    private static void BuffCapsAndRefreshRemainIntact()
    {
        foreach (bool upper in new[] { false, true })
            WithPlayer((player, generated) =>
            {
                player.active = true;
                player.moveSpeed = player.pickSpeed = 1f;
                generated.ApplyGeneratedUtilityBuff(new GeneratedBuffSpec { DurationTicks = 10,
                    MiningSpeedMultiplier = upper ? 3f : 0.25f, MovementSpeed = upper ? 1.5f : -0.5f });
                generated.ApplyGeneratedUtilityBuff(new GeneratedBuffSpec { DurationTicks = 10,
                    MiningSpeedMultiplier = upper ? 4f : 0.5f, MovementSpeed = upper ? 2f : -0.5f });
                generated.PostUpdateEquips();
                Equal(upper ? 3f : 1f - 0.8f, player.moveSpeed, "declared signed movement cap retained");
                Equal(upper ? 0.25f : 4f, player.pickSpeed, "mining cap retained");
            });
        WithPlayer((player, generated) =>
        {
            player.active = true;
            generated.ApplyGeneratedUtilityBuff(new GeneratedBuffSpec { DurationTicks = 2, MovementSpeed = 0.5f });
            generated.ApplyGeneratedUtilityBuff(new GeneratedBuffSpec { DurationTicks = 4, MovementSpeed = 0.5f });
            generated.ApplyGeneratedUtilityBuff(new GeneratedBuffSpec { DurationTicks = 1, MiningSpeedMultiplier = 2f });
            for (int sample = 1; sample <= 5; sample++)
            {
                player.moveSpeed = player.pickSpeed = 1f;
                generated.PostUpdateEquips();
                Equal(sample <= 4 ? 1.5f : 1f, player.moveSpeed, "equal-effect refresh does not double stack");
                Equal(sample == 1 ? .5f : 1f, player.pickSpeed, "distinct short effect applies once then expires independently");
            }
        });
    }
}

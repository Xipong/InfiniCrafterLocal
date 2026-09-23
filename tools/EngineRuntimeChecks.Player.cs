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

    private static void RejectedHeldPoseDoesNotLeak()
    {
        WithPlayer((player, _) =>
        {
            var clock = typeof(Terraria.Main).GetField("_gameUpdateCount", BindingFlags.Static | BindingFlags.NonPublic)!;
            object? oldClock = clock.GetValue(null);
            int oldMode = Terraria.Main.netMode, oldLocal = Terraria.Main.myPlayer;
            try
            {
                Terraria.Main.netMode = Terraria.ID.NetmodeID.MultiplayerClient;
                Terraria.Main.myPlayer = 0;
                clock.SetValue(null, 100u);
                player.whoAmI = 1;
                player.selectedItem = 0;
                var item = new Item { type = 1, stack = 1 };
                typeof(Item).GetProperty("ModItem")!.SetValue(item, new GeneratedItem());
                player.inventory[0] = player.inventory[1] = item;
                GeneratedHeldItemDrawLayer.ClearNetCaches();
                using var packet = new System.IO.MemoryStream();
                using (var writer = new System.IO.BinaryWriter(packet, System.Text.Encoding.UTF8, leaveOpen: true))
                {
                    writer.Write(4); writer.Write((byte)1); writer.Write((byte)1);
                    writer.Write("held-pose-test");
                    writer.Write(160f); writer.Write(320f); writer.Write(0.5f);
                    writer.Write(1); writer.Write(1f); writer.Write(true); writer.Write((byte)200);
                }
                packet.Position = 0;
                using var reader = new System.IO.BinaryReader(packet);
                GeneratedHeldItemDrawLayer.HandleHeldItemPresentationSyncPacket(reader, 0);
                var resolve = typeof(GeneratedHeldItemDrawLayer).GetMethod("TryGetFreshRemotePayload", BindingFlags.Static | BindingFlags.NonPublic)!;
                void AssertPose(bool accepted, string label)
                {
                    object?[] args = { player, null };
                    Equal(accepted, (bool)resolve.Invoke(null, args)!, label);
                    Equal(accepted, args[1] is not null, label + " payload availability");
                }
                AssertPose(true, "first-use grace remains valid");
                clock.SetValue(null, 131u);
                AssertPose(false, "wrong selected slot after grace");
                player.selectedItem = 1;
                AssertPose(true, "matching selected slot remains valid");
                clock.SetValue(null, 155u);
                AssertPose(false, "expired pose remains rejected");
            }
            finally
            {
                GeneratedHeldItemDrawLayer.ClearNetCaches();
                clock.SetValue(null, oldClock);
                Terraria.Main.netMode = oldMode;
                Terraria.Main.myPlayer = oldLocal;
            }
        });
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
            for (int slot = 3; slot < 10; slot++)
            {
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
                    MiningSpeedMultiplier = upper ? 4f : 0.5f, MovementSpeed = upper ? 2f : -0.25f });
                generated.PostUpdateEquips();
                Equal(upper ? 3f : 0.5f, player.moveSpeed, "movement cap retained");
                Equal(upper ? 0.25f : 4f, player.pickSpeed, "mining cap retained");
            });
        WithPlayer((player, generated) =>
        {
            player.active = true;
            generated.ApplyGeneratedUtilityBuff(new GeneratedBuffSpec { DurationTicks = 2, MovementSpeed = 0.5f });
            generated.ApplyGeneratedUtilityBuff(new GeneratedBuffSpec { DurationTicks = 4, MovementSpeed = 0.5f });
            generated.ApplyGeneratedUtilityBuff(new GeneratedBuffSpec { DurationTicks = 1, MiningSpeedMultiplier = 2f });
            var tick = typeof(InfiniCraftPlayer).GetMethod("TickGeneratedUtilityBuff", BindingFlags.Instance | BindingFlags.NonPublic)!;
            for (int elapsed = 1; elapsed <= 4; elapsed++)
            {
                tick.Invoke(generated, null);
                player.moveSpeed = player.pickSpeed = 1f;
                generated.PostUpdateEquips();
                Equal(elapsed < 4 ? 1.5f : 1f, player.moveSpeed, "equal-effect refresh does not double stack");
                Equal(1f, player.pickSpeed, "distinct short effect expires independently");
            }
        });
    }
}

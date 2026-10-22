using System;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Items;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private static void NativeQuickUseNeverSelectsNonEffectBinding()
    {
        // Production hooks are loaded explicitly in this loader-free fixture when present.
        // The pre-fix baseline has no bridge; the same native selector must expose RED.
        var bridgeType = typeof(GeneratedItem).Assembly.GetType("InfiniCrafterLocal.Common.Systems.GeneratedQuickUseSystem");
        var bridge = bridgeType is null ? null : (ModSystem)Activator.CreateInstance(bridgeType)!;
        int oldMode = Terraria.Main.netMode, oldPlayer = Terraria.Main.myPlayer;
        try
        {
            bridge?.Load();
            Terraria.Main.netMode = NetmodeID.SinglePlayer; Terraria.Main.myPlayer = 0;
            WithPlayer((player, _) =>
            {
                player.active = true; player.whoAmI = 0;
                player.statLifeMax2 = 100; player.statLife = 40;
                player.statManaMax2 = 100; player.statMana = 40;
                var data = GeneratedItemData.Placeholder();
                data.Gameplay.HealLife = 50; data.Gameplay.HealMana = 30; data.Gameplay.Potion = true;
                data.RuntimeProgram.ItemUse.Configured = true;
                string target = data.RuntimeProgram.ItemEntityId;
                data.RuntimeProgram.Bindings = new[] {
                    new RuntimeBindingSpec { Id = "primary", Input = RuntimeInputKind.PrimaryUse, Role = "primary",
                        UsePolicy = new RuntimeBindingUsePolicySpec { Action = new RuntimeBindingActionSpec { Kind = RuntimeBindingAction.UseItemBody, TargetId = target }, StackCost = 1 } },
                    new RuntimeBindingSpec { Id = "alternate", Input = RuntimeInputKind.AlternateUse, Role = "primary",
                        UsePolicy = new RuntimeBindingUsePolicySpec { Action = new RuntimeBindingActionSpec { Kind = RuntimeBindingAction.ApplyItemEffects, TargetId = target }, StackCost = 1 } },
                };
                var item = new Item(); item.SetDefaults(ItemID.WoodenSword); item.stack = 3;
                var host = new GeneratedItem();
                var entityProperty = typeof(ModType<Item>).GetProperty("Entity", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance)!;
                entityProperty.SetValue(host, item);
                typeof(Item).GetProperty("ModItem")!.SetValue(item, host);
                typeof(GeneratedItem).GetProperty("Data")!.SetValue(host, data);
                data.ApplyToItem(item); player.inventory[0] = item;
                foreach (int selector in new[] { 0, 2 })
                {
                    data.ApplyToItem(item); player.altFunctionUse = selector;
                    Equal(true, player.QuickHeal_GetItemToUse() is null, "native QuickHeal rejects non-effect primary");
                    data.ApplyToItem(item);
                    Equal(true, player.QuickMana_GetItemToUse() is null, "native QuickMana rejects non-effect primary");
                    Equal(selector, player.altFunctionUse, "native shortcuts preserve real input selector");
                    data.ApplyToItem(item); player.QuickHeal();
                    Equal(3, item.stack, "native QuickHeal cannot consume without healing");
                    Equal(40, player.statLife, "rejected QuickHeal preserves life");
                }
                player.altFunctionUse = 2;
                Equal(true, host.CanUseItem(player), "explicit manual alternate still usable");
                Equal(50, item.healLife, "manual alternate still projects healing");
                Equal(30, item.healMana, "manual alternate still projects mana");
                data.RuntimeProgram.Bindings[0].UsePolicy.Action.Kind = RuntimeBindingAction.ApplyItemEffects;
                foreach (int selector in new[] { 0, 2 })
                {
                    data.ApplyToItem(item); player.altFunctionUse = selector;
                    Equal(true, ReferenceEquals(item, player.QuickHeal_GetItemToUse()), "genuine primary healing remains eligible");
                    data.ApplyToItem(item);
                    Equal(true, ReferenceEquals(item, player.QuickMana_GetItemToUse()), "genuine primary mana remains eligible");
                    Equal(selector, player.altFunctionUse, "eligible shortcut preserves selector");
                }
                player.inventory[0] = new Item();
                var vanilla = new Item(); vanilla.SetDefaults(ItemID.LesserHealingPotion); vanilla.stack = 3;
                player.inventory[1] = vanilla;
                Equal(true, ReferenceEquals(vanilla, player.QuickHeal_GetItemToUse()), "native vanilla selection unaffected");
            });
        }
        finally { bridge?.Unload(); Terraria.Main.netMode = oldMode; Terraria.Main.myPlayer = oldPlayer; }
    }
}

using System;
using System.IO;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.Runtime;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.DataStructures;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    private static void PlayerEffectBuffReducesActualCooldownOnHit()
    {
        using var actors = new NativeActorState();
        Terraria.Main.netMode = NetmodeID.SinglePlayer;
        WithPlayer((player, effects) => {
            player.active = true; player.whoAmI = 0; player.statLife = 50;
            var modifier = new PlayerEffectSpec { HealingPotionCooldownOnHitReductionTicks = 30 };
            Equal(true, effects.ApplyGeneratedUtilityBuff(new GeneratedBuffSpec { DurationTicks = 2, PlayerEffect = modifier }), "mechanical-only buff admitted");
            effects.ResetEffects(); effects.PostUpdateEquips();
            player.potionDelay = 120; player.buffType[0] = BuffID.PotionSickness; player.buffTime[0] = 120;
            effects.OnHitNPCWithItem(new Item(), new NPC(), new NPC.HitInfo(), 1);
            Equal(90, player.potionDelay, "one real item-hit callback removes half a second");
            Equal(90, player.buffTime[0], "native Potion Sickness timer follows the same reduction");
            effects.OnHitNPCWithProj(new Projectile { owner = 0 }, new NPC(), new NPC.HitInfo(), 1);
            Equal(60, player.potionDelay, "own projectile hit uses the same primitive");
            effects.OnHitNPCWithProj(new Projectile { owner = 1 }, new NPC(), new NPC.HitInfo(), 1);
            effects.OnHitNPCWithItem(new Item(), new NPC(), new NPC.HitInfo(), 0);
            Equal(60, player.potionDelay, "foreign projectile and zero damage do not proc");
            effects.ResetEffects(); effects.PostUpdateEquips();
            effects.ResetEffects(); effects.PostUpdateEquips();
            effects.OnHitNPCWithItem(new Item(), new NPC(), new NPC.HitInfo(), 1);
            Equal(60, player.potionDelay, "expired buff no longer supplies a hit modifier");
        });
    }

    private static void PlayerEffectWeaponActionMutatesNativeTimer()
    {
        using var actors = new NativeActorState();
        Terraria.Main.netMode = NetmodeID.SinglePlayer;
        WithPlayer((player, effects) => {
            player.active = true; player.statLife = 50;
            var action = new RuntimeEventActionSpec { Id = "cooldown_hit", Event = RuntimeEventKind.OnHit,
                Action = "reduce_healing_potion_cooldown_on_event", ActionCode = RuntimeEventActionCode.ReduceHealingPotionCooldown,
                CooldownReductionTicks = 30 };
            action.NormalizeAndValidate();
            player.potionDelay = 50; player.buffType[0] = BuffID.PotionSickness; player.buffTime[0] = 50;
            RuntimeProgramExecutor.ExecuteAction(new GeneratedItemData(), Entity(), action, player,
                new EntitySource_Misc("player-effect-check"), player.Center, Vector2.UnitX, null, 1, 0, new RuntimeSpawnBudget(0));
            Equal(20, player.potionDelay, "weapon event dispatch reaches the actual owner timer");
            Equal(20, player.buffTime[0], "weapon event also changes native debuff time");
            effects.ReduceHealingPotionCooldown(30);
            Equal(0, player.potionDelay, "remaining cooldown is floored at zero");
            Equal(-1, player.FindBuffIndex(BuffID.PotionSickness), "completed sickness is removed");
            effects.ReduceHealingPotionCooldown(30);
            Equal(0, player.potionDelay, "no cooldown does not become negative");
            player.dead = true; player.potionDelay = 50;
            effects.ReduceHealingPotionCooldown(30);
            Equal(50, player.potionDelay, "dead owner does not receive a late state mutation");
        });
    }

    private static void PlayerEffectNativeEquipmentAndPickup()
    {
        using var actors = new NativeActorState();
        WithPlayer((player, effects) => {
            player.active = true; player.statLife = 50; player.velocity = Vector2.Zero;
            effects.ResetEffects();
            var item = NativeUtilityItem("\"playerEffect\":{\"condition\":\"stationary\",\"itemPickupRangePx\":48,\"heartPickupRangePx\":16,\"healingPotionCooldownReductionPercent\":20,\"healingPotionCooldownReductionTicks\":30}");
            item.UpdateAccessory(player, true);
            var hook = new GeneratedPlayerEffectItemHooks();
            int heartRange = 10, woodRange = 10, delay = 3600;
            hook.GrabRange(new Item(ItemID.Heart), player, ref heartRange);
            hook.GrabRange(new Item(ItemID.Wood), player, ref woodRange);
            hook.ModifyPotionDelay(new Item(ItemID.HealingPotion), player, ref delay);
            Equal(74, heartRange, "general and heart ranges combine in native hook units");
            Equal(58, woodRange, "ordinary item receives only general range");
            Equal(2850, delay, "percentage and flat base cooldown modifiers are independently authored");
            effects.ResetEffects(); player.velocity = Vector2.UnitX;
            item.UpdateAccessory(player, false);
            heartRange = 10; hook.GrabRange(new Item(ItemID.Heart), player, ref heartRange);
            Equal(10, heartRange, "stationary condition is evaluated by the consumer");
            delay = 3600; hook.ModifyPotionDelay(new Item(ItemID.HealingPotion), player, ref delay);
            Equal(3600, delay, "inactive component does not modify potion use");
        });
    }

    private static void PlayerEffectSnapshotRetainsNumericMechanics()
    {
        var effect = new PlayerEffectSpec { Condition = "stationary", HealingPotionCooldownOnHitReductionTicks = 30,
            ItemPickupRangePx = 48, HighlightDanger = true, LifeRegenUnits = 5 };
        using var stream = new MemoryStream();
        using (var writer = new BinaryWriter(stream, System.Text.Encoding.UTF8, true)) effect.Write(writer);
        stream.Position = 0;
        var read = PlayerEffectSpec.Read(new BinaryReader(stream));
        Equal(true, PlayerEffectSpec.SameEffect(effect, read), "typed binary snapshot preserves values and condition");
        WithPlayer((player, effects) => {
            player.active = true; player.statLife = 50;
            Equal(true, effects.ApplyGeneratedUtilityBuff(new GeneratedBuffSpec { DurationTicks = 60, PlayerEffect = effect }), "source buff accepted");
            using var packet = new MemoryStream();
            typeof(InfiniCraftPlayer).GetMethod("WriteGeneratedBuffState", BindingFlags.Instance | BindingFlags.NonPublic)!
                .Invoke(effects, new object[] { new BinaryWriter(packet) });
            packet.Position = 1; // owner byte is consumed by the outer packet handler
            typeof(InfiniCraftPlayer).GetMethod("ReadGeneratedBuffState", BindingFlags.Instance | BindingFlags.NonPublic)!
                .Invoke(effects, new object[] { new BinaryReader(packet) });
            var entries = effects.CaptureGeneratedUtilityBuffPresentation().Entries;
            Equal(1, entries.Count, "real state reader retains one buff");
            Equal(true, PlayerEffectSpec.SameEffect(effect, entries[0].PlayerEffect), "real utility state roundtrip retains modifiers");
        });
    }
}

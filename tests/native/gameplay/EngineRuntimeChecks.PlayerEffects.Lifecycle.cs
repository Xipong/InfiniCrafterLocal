using System;
using System.Reflection;
using System.IO;
using System.Linq;
using InfiniCrafterLocal.Common.Models;
using MonoMod.Cil;
using MonoMod.RuntimeDetour;
using Terraria;
using Terraria.ID;
using Terraria.DataStructures;
using InfiniCrafterLocal.Common.Players;

internal static partial class EngineRuntimeChecks
{
    private sealed class PlayerEffectAfterManaConsumption : Exception { }

    private static void PlayerEffectAutomaticManaUsesNativeLifecycle()
    {
        using var actors = new NativeActorState();
        using var scope = new MobilityConsumptionNativeScope();
        // Stop only the unrelated recipe UI refresh, after native consumption,
        // healing and Mana Sickness; the gameplay path itself stays native.
        using var stop = new ILHook(typeof(Player).GetMethod(nameof(Player.QuickMana))!, il => {
            var cursor = new ILCursor(il);
            if (!cursor.TryGotoNext(MoveType.AfterLabel, instruction => instruction.MatchCall<Recipe>(nameof(Recipe.FindRecipes))))
                throw new InvalidOperationException("Native QuickMana recipe boundary missing");
            cursor.EmitDelegate<Action>(() => throw new PlayerEffectAfterManaConsumption());
        });
        WithPlayer((player, effects) => {
            PrepareMobilityConsumptionPlayer(player);
            var auto = effects.GetType().GetMethod("AutoUseManaPotion", BindingFlags.Instance | BindingFlags.NonPublic)!;
            void Reset()
            {
                Terraria.Main.netMode = NetmodeID.SinglePlayer;
                Terraria.Main.myPlayer = player.whoAmI = 1;
                player.active = true; player.dead = false; player.statLife = 100;
                player.statMana = 0; player.statManaMax2 = 200; player.itemAnimation = 0;
                Array.Clear(player.buffType); Array.Clear(player.buffTime); effects.ResetEffects();
                for (int i = 0; i < player.inventory.Length; i++) player.inventory[i] = new Item();
                player.inventory[1] = new Item(ItemID.ManaPotion) { stack = 2 };
                effects.ApplyPlayerEffect(new PlayerEffectSpec { AutoManaPotionBelowPercent = 30 });
            }
            bool Use()
            {
                try { auto.Invoke(effects, null); return false; }
                catch (TargetInvocationException error) when (error.InnerException is PlayerEffectAfterManaConsumption) { return true; }
            }
            Reset(); int heal = player.inventory[1].healMana;
            Equal(true, Use(), "native QuickMana reaches post-consumption boundary");
            Equal(1, player.inventory[1].stack, "one real potion consumed");
            Equal(heal, player.statMana, "native mana restored");
            Equal(true, player.FindBuffIndex(BuffID.ManaSickness) >= 0, "native Mana Sickness applied");
            Equal(false, Use(), "threshold prevents duplicate potion");
            Equal(1, player.inventory[1].stack, "second query does not consume");
            Reset(); player.inventory[1] = new Item();
            Equal(false, Use(), "empty inventory has no potion"); Equal(0, player.statMana, "no invented mana");
            Reset(); effects.ResetEffects();
            Equal(false, Use(), "reset removes automation"); Equal(2, player.inventory[1].stack, "reset preserves inventory");
            Reset(); player.dead = true;
            Equal(false, Use(), "dead player cannot consume"); Equal(2, player.inventory[1].stack, "dead preserves inventory");
            Reset(); Terraria.Main.netMode = NetmodeID.MultiplayerClient; Terraria.Main.myPlayer = 2;
            Equal(false, Use(), "remote client cannot consume"); Equal(2, player.inventory[1].stack, "remote preserves inventory");
            Reset(); Terraria.Main.netMode = NetmodeID.Server;
            Equal(false, Use(), "server does not duplicate owner action"); Equal(2, player.inventory[1].stack, "server preserves inventory");
        });
    }

    private static void PlayerEffectHurtImmunityUsesActualSlot()
    {
        using var actors = new NativeActorState();
        WithPlayer((player, effects) => {
            player.active = true; player.dead = false; player.statLife = 100;
            effects.ApplyPlayerEffect(new PlayerEffectSpec { HurtInvulnerabilityBonusTicks = 20 });
            player.immuneTime = 30;
            effects.PostHurt(new Player.HurtInfo { Damage = 10, CooldownCounter = -1 });
            Equal(50, player.immuneTime, "general immunity extended");
            player.hurtCooldowns[0] = 12; player.immuneTime = 30;
            effects.PostHurt(new Player.HurtInfo { Damage = 10, CooldownCounter = 0 });
            Equal(32, player.hurtCooldowns[0], "selected hurt slot extended");
            Equal(30, player.immuneTime, "unselected immunity unchanged");
            // Native Damage setter clamps to one; default struct is actual zero.
            var zero = default(Player.HurtInfo); zero.CooldownCounter = 0;
            Equal(0, zero.Damage, "zero-damage control fixture");
            effects.PostHurt(zero); Equal(32, player.hurtCooldowns[0], "zero damage no extension");
            effects.ResetEffects(); effects.PostHurt(new Player.HurtInfo { Damage = 10, CooldownCounter = 0 });
            Equal(32, player.hurtCooldowns[0], "removed modifier no extension");
        });
    }
    private static void PlayerEffectRemotePassiveStateDoesNotExecuteActions()
    {
        using var actors = new NativeActorState();
        using var scope = new MobilityConsumptionNativeScope();
        WithPlayer((player, effects) => {
            PrepareMobilityConsumptionPlayer(player);
            Terraria.Main.netMode = NetmodeID.SinglePlayer;
            Terraria.Main.myPlayer = player.whoAmI = 1;
            player.active = true; player.dead = false; player.statLife = 100;
            Equal(true, effects.ApplyGeneratedUtilityBuff(new GeneratedBuffSpec {
                DurationTicks = 60, LifeRegen = 4,
                PlayerEffect = new PlayerEffectSpec { FishingPowerPoints = 17, NightVision = true,
                    AutoManaPotionBelowPercent = 30, HealingPotionCooldownOnHitReductionTicks = 30,
                    ItemPickupRangePx = 48, ExtraCrateChancePercent = 100 }
            }), "accepted buff before remote hydration observation");
            foreach (int mode in new[] { NetmodeID.SinglePlayer, NetmodeID.MultiplayerClient, NetmodeID.Server })
            {
                Terraria.Main.netMode = mode; Terraria.Main.myPlayer = player.whoAmI;
                for (int frame = 0; frame < 2; frame++)
                {
                    // Native ResetEffects owns clearing its public stats each frame.
                    player.fishingSkill = 0; player.nightVision = false; player.lifeRegen = 0;
                    effects.ResetEffects(); effects.PostUpdateEquips();
                    Equal(17, player.fishingSkill, "one timed component contribution per native frame");
                    Equal(4, player.lifeRegen, "existing stat applies once on owner/server");
                    int range = 10; new GeneratedPlayerEffectItemHooks().GrabRange(new Item(ItemID.Wood), player, ref range);
                    Equal(58, range, "pickup component does not accumulate across frames");
                    var attempt = new FishingAttempt(); effects.ModifyFishingAttempt(ref attempt);
                    Equal(true, attempt.crate, "native attempt consumes current crate modifier");
                }
            }
            Terraria.Main.netMode = NetmodeID.MultiplayerClient; Terraria.Main.myPlayer = 2;
            player.fishingSkill = 0; player.nightVision = false; player.lifeRegen = 0;
            player.statMana = 0; player.statManaMax2 = 200;
            player.inventory[1] = new Item(ItemID.ManaPotion) { stack = 2 };
            effects.ResetEffects(); effects.PostUpdateEquips();
            Equal(17, player.fishingSkill, "remote native passive field materializes");
            Equal(true, player.nightVision, "remote passive visibility field materializes");
            Equal(0, player.lifeRegen, "existing gameplay stat remains owner/server gated");
            effects.GetType().GetMethod("AutoUseManaPotion", BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(effects, null);
            Equal(2, player.inventory[1].stack, "remote passive state cannot consume potion");
            player.potionDelay = 120; player.buffType[0] = BuffID.PotionSickness; player.buffTime[0] = 120;
            effects.ReduceHealingPotionCooldown(30);
            Equal(120, player.potionDelay, "remote hit modifier cannot mutate native timer");
            Equal(120, player.buffTime[0], "remote hit modifier cannot mutate sickness");
            player.dead = true; player.fishingSkill = 0; player.nightVision = false;
            effects.ResetEffects(); effects.PostUpdateEquips();
            Equal(0, player.fishingSkill, "dead player gets no passive contribution");
            Equal(false, player.nightVision, "dead player gets no passive flag");
            int deadRange = 10; new GeneratedPlayerEffectItemHooks().GrabRange(new Item(ItemID.Wood), player, ref deadRange);
            Equal(10, deadRange, "dead/reset clears pickup accumulator");
            var deadAttempt = new FishingAttempt(); effects.ModifyFishingAttempt(ref deadAttempt);
            Equal(false, deadAttempt.crate, "dead/reset clears crate accumulator");
        });
    }

    private static void PlayerEffectMalformedStatePreservesAcceptedSnapshot()
    {
        using var actors = new NativeActorState();
        Terraria.Main.netMode = NetmodeID.SinglePlayer;
        WithPlayer((player, effects) => {
            player.active = true; player.dead = false; player.statLife = 100;
            Equal(true, effects.ApplyGeneratedUtilityBuff(new GeneratedBuffSpec { DurationTicks = 120,
                PlayerEffect = new PlayerEffectSpec { FishingPowerPoints = 17, NightVision = true } }), "initial state accepted");
            var write = effects.GetType().GetMethod("WriteGeneratedBuffState", BindingFlags.Instance | BindingFlags.NonPublic)!;
            var read = effects.GetType().GetMethod("ReadGeneratedBuffState", BindingFlags.Instance | BindingFlags.NonPublic)!;
            byte[] Snapshot()
            {
                using var stream = new MemoryStream(); write.Invoke(effects, new object[] { new BinaryWriter(stream) });
                return stream.ToArray();
            }
            byte[] accepted = Snapshot();
            foreach (byte version in new byte[] { 7, 8, 255 })
            {
                byte[] packet = (byte[])accepted.Clone(); packet[1] = version;
                Reject(packet);
            }
            // Every truncation boundary, including nested typed fields, must fail
            // before replacing an accepted timer/modifier table.
            for (int length = 1; length < accepted.Length; length++) Reject(accepted.Take(length).ToArray());
            void Reject(byte[] packet)
            {
                using var stream = new MemoryStream(packet); stream.Position = 1;
                bool rejected = false;
                try { read.Invoke(effects, new object[] { new BinaryReader(stream) }); }
                catch (TargetInvocationException error) when (error.InnerException is InvalidDataException or EndOfStreamException) { rejected = true; }
                Equal(true, rejected, "invalid version/truncated snapshot rejected");
                Equal(true, accepted.SequenceEqual(Snapshot()), "rejected packet leaves accepted state byte-identical");
            }
        });
    }

}

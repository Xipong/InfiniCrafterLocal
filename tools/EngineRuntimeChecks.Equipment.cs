using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Runtime;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using MonoMod.RuntimeDetour;
using Terraria;
using Terraria.DataStructures;
using Terraria.ID;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private static GeneratedItem PeriodicEquipmentItem(bool armor = false)
    {
        var data = GeneratedItemData.FromJson(File.ReadAllText(Path.Combine("tools", "fixtures", "equipment-periodic-compiled.json")))
            ?? throw new InvalidOperationException("compiler equipment fixture rejected: " + ContractJsonDiagnostics.LastError);
        if (armor)
        {
            data.Accessory.Enabled = false;
            data.Armor = new ArmorSpec { Enabled = true, Slot = "head", SetKey = "witness_set", Defense = 1 };
        }
        data = GeneratedItemData.FromJson(data.ToNetworkJson())!;
        var item = new Item { type = ItemID.CopperShortsword, stack = 1 };
        var generated = AttachItem(armor ? new GeneratedHeadArmor() : new GeneratedItem(), item, data);
        data.ApplyToItem(item);
        return generated;
    }

    private static uint PeriodicEquipmentDueTick(GeneratedItem generated)
    {
        var action = generated.Data.RuntimeProgram.TryGetEntity(generated.Data.RuntimeProgram.ItemEntityId)!.Events.Single();
        uint due = 120;
        while ((due + (ulong)action.Id.GetHashCode()) % (ulong)action.PeriodTicks != 0) due++;
        return due;
    }

    private static void EquipmentPeriodicGameplayReachesNativeSpawn()
    {
        foreach (bool armor in new[] { false, true })
        foreach (bool hidden in new[] { false, true })
        {
            using var actors = new SwarmRuntimeScope();
            WithPlayer((player, _) => {
                player.active = true; player.whoAmI = 0; player.direction = 1;
                Terraria.Main.player[0] = player;
                var generated = PeriodicEquipmentItem(armor);
                var item = generated.Item;
                player.armor[armor ? 0 : 3] = item;
                uint due = PeriodicEquipmentDueTick(generated);
                int attempts = 0;
                using var spawn = new Hook(NativeProjectileEntry(),
                    (Func<IEntitySource, Vector2, Vector2, int, int, float, int, float, float, float, Projectile>)
                    ((source, position, velocity, type, damage, knockback, owner, a, b, c) => {
                        attempts++;
                        Equal("InfiniRuntimePeriodic", source.Context, "existing periodic source provenance");
                        Equal(10, damage, "authored child damage and event multiplier reach spawn");
                        Equal(player.Center, position, "functional equipment emits at owning player");
                        Equal(new Vector2(8, 0), velocity, "authored child facing and speed are retained");
                        // Observe the native allocation boundary only. The inactive
                        // result exercises its ordinary refusal/refund path, not a game spawn.
                        return new Projectile { active = false };
                    }));
                void Functional()
                {
                    // Real native callers dispatch UpdateEquip/UpdateAccessory.
                    if (armor) player.GrantArmorBenefits(item);
                    else player.ApplyEquipFunctional(item, hidden);
                }
                MaterialClock(due - 1); Functional();
                Equal(0, attempts, "off-cadence equipment hook stays silent");
                MaterialClock(due); Functional();
                Equal(1, attempts, "equipped-only authored periodic child reaches native spawn boundary");
                Functional();
                player.inventory[0] = item; player.selectedItem = 0;
                ItemLoader.HoldItem(item, player);
                Equal(1, attempts, "repeated functional and held hooks cannot duplicate this instance/tick");
                Equal(1, item.stack, "passive event does not debit stack");
                MaterialClock(due + 6); Functional();
                Equal(2, attempts, "next authored period is not permanently suppressed");
                player.inventory[0] = new Item();
                MaterialClock(due + 12);
                ItemLoader.UpdateVanity(item, player);
                Equal(2, attempts, "vanity alone never produces gameplay");
                ItemLoader.UpdateInventory(item, player);
                Equal(2, attempts, "inventory alone never produces gameplay");
                // A second physical copy retains the existing per-instance semantics;
                // matching definition IDs are not an extra hidden gameplay cooldown.
                var copy = PeriodicEquipmentItem(armor);
                if (armor) ItemLoader.UpdateEquip(copy.Item, player);
                else ItemLoader.UpdateAccessory(copy.Item, player, hidden);
                Functional();
                Equal(4, attempts, "independent instances sharing a definition each execute once");
                var binding = generated.Data.RuntimeProgram.Bindings;
                generated.Data.RuntimeProgram.Bindings = Array.Empty<RuntimeBindingSpec>();
                MaterialClock(due + 18); Functional();
                Equal(4, attempts, "equipment without explicit equip_passive binding is inert");
                generated.Data.RuntimeProgram.Bindings = binding;
                Functional();
                Equal(5, attempts, "ineligible hook did not consume the valid same-tick opportunity");
                player.armor[armor ? 0 : 3] = new Item();
                MaterialClock(due + 24);
                ItemLoader.UpdateInventory(item, player);
                Equal(5, attempts, "unequipping stops production");
            });
        }
    }

    private static void EquipmentPeriodicGameplayKeepsAuthorityAndDelay()
    {
        foreach (var role in SwarmRoles)
        foreach (int delay in new[] { 0, 2 })
        {
            using var actors = new SwarmRuntimeScope(role.Mode, role.Local);
            WithPlayer((player, _) => {
                player.active = true; player.whoAmI = 0; player.direction = 1;
                Terraria.Main.player[0] = player;
                var generated = PeriodicEquipmentItem();
                var action = generated.Data.RuntimeProgram.TryGetEntity(generated.Data.RuntimeProgram.ItemEntityId)!.Events.Single();
                action.DelayTicks = delay;
                uint due = PeriodicEquipmentDueTick(generated);
                bool authority = role.Mode == NetmodeID.SinglePlayer || role.Mode == NetmodeID.MultiplayerClient && role.Local == 0;
                int attempts = 0;
                using var spawn = new Hook(NativeProjectileEntry(),
                    (Func<IEntitySource, Vector2, Vector2, int, int, float, int, float, float, float, Projectile>)
                    ((source, position, velocity, type, damage, knockback, owner, a, b, c) => {
                        attempts++;
                        Equal("InfiniRuntimePeriodic", source.Context, "delayed equipment retains declared Misc provenance");
                        return new Projectile { active = false };
                    }));
                MaterialClock(due);
                ItemLoader.UpdateAccessory(generated.Item, player, false);
                ItemLoader.UpdateAccessory(generated.Item, player, false);
                Equal(authority && delay == 0 ? 1 : 0, attempts, role.Name + " immediate owner boundary");
                Equal(authority && delay > 0 ? 1 : 0, PendingActions(), role.Name + " bounded delayed admission once");
                if (delay > 0)
                {
                    AdvanceRuntimeWorldTick();
                    Equal(0, attempts, role.Name + " delay is not shortened by duplicate hooks");
                    AdvanceRuntimeWorldTick();
                    Equal(authority ? 1 : 0, attempts, role.Name + " delayed owner boundary");
                    Equal(0, PendingActions(), role.Name + " pending emission retires");
                }
            });
        }
    }

    private static void LegacyUnclampedEquipmentStatsRemainIntact()
    {
        var data = GeneratedItemData.Placeholder();
        data.Accessory.Enabled = true;
        data.Accessory.MaxRunSpeed = 30f; // Legacy DTO did not clamp this field.
        data.Accessory.AttackSpeed = 4f;
        data.Normalize(); // Same legacy DTO normalization invoked by FromJson/ToNetworkJson.
        Equal(30f, data.Accessory.MaxRunSpeed, "unclamped legacy run-speed survives normalization");
        Equal(4f, data.Accessory.AttackSpeed, "unclamped legacy attack-speed survives normalization");
        var armorData = GeneratedItemData.Placeholder();
        armorData.Armor.Enabled = true;
        armorData.Armor.Slot = "head";
        armorData.Armor.SetBonusMagicDamage = 4f; // Only generic set damage was clamped.
        armorData.Normalize();
        Equal(4f, armorData.Armor.SetBonusMagicDamage, "unclamped legacy set damage survives normalization");
    }

    private static void LegacyEquipmentClampsRemainUnchanged()
    {
        var data = GeneratedItemData.Placeholder();
        data.Accessory.GenericDamage = 100f;
        data.Accessory.Defense = 1000;
        data.Accessory.Endurance = 100f;
        data.Accessory.FallDamageImmune = true;
        data.Armor.SetBonusGenericDamage = 100f;
        data.Armor.SetBonusLifeRegen = 1000;
        data.Normalize();
        Equal(3f, data.Accessory.GenericDamage, "legacy generic additive bonus capped");
        Equal(500, data.Accessory.Defense, "legacy defense cap retained");
        Equal(0.75f, data.Accessory.Endurance, "legacy endurance cap retained");
        Equal(true, data.Accessory.FallDamageImmune, "boolean immunity survives normalization");
        Equal(3f, data.Armor.SetBonusGenericDamage, "legacy set generic damage capped");
        Equal(200, data.Armor.SetBonusLifeRegen, "legacy set life regen capped");
    }

    private static void SignedAccessoryDefenseReachesPlayer()
    {
        var failures = new List<string>();
        // configure_accessory permits -50..200; Terraria owns defense addition.
        foreach (int defense in new[] { -50, -1, 0, 7, 200 })
        foreach (bool hidden in new[] { false, true })
        {
            string label = $"defense={defense}, hidden={hidden}";
            try
            {
                WithPlayer((player, _) =>
                {
                    var data = GeneratedItemData.Placeholder();
                    data.Accessory = new AccessorySpec { Enabled = true, Defense = defense, MaxLife = 1 };
                    data.RuntimeProgram.Bindings = new[] {
                        new RuntimeBindingSpec { Id = "equip", Input = RuntimeInputKind.Equipped,
                            Role = RuntimeEntityRole.Primary, UsePolicy = new RuntimeBindingUsePolicySpec {
                                Action = new RuntimeBindingActionSpec { Kind = RuntimeBindingAction.EquipPassive, TargetId = data.RuntimeProgram.ItemEntityId },
                            } },
                    };
                    string json = JsonSerializer.Serialize(data, new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase });
                    data = GeneratedItemData.FromJson(json) ?? throw new InvalidOperationException("accessory fixture rejected");
                    for (int pass = 0; pass < 2; pass++)
                    {
                        Equal(defense, data.Accessory.Defense, label + " survives DTO/network normalization");
                        var item = new Item();
                        var generated = new GeneratedItem();
                        typeof(ModType<Item>).GetProperty("Entity", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)!.SetValue(generated, item);
                        typeof(GeneratedItem).GetProperty("Data")!.SetValue(generated, data);
                        data.ApplyToItem(item);
                        data.ApplyToItem(item); // Projection is idempotent, not an accumulated bonus.
                        player.statDefense = new Player.DefenseStat();
                        player.statDefense += 100;
                        player.statLifeMax2 = 100;
                        // Actual vanilla caller order, including signed DefenseStat addition.
                        player.GrantArmorBenefits(item);
                        generated.UpdateAccessory(player, hidden);
                        Equal(100 + defense, (int)player.statDefense, label + " reaches real vanilla + mod hooks exactly once");
                        Equal(defense, item.defense, label + " remains signed on Item");
                        Equal(101, player.statLifeMax2, label + " retains unrelated bonus");
                        data = GeneratedItemData.FromJson(data.ToNetworkJson()) ?? throw new InvalidOperationException("accessory network fixture rejected");
                    }
                });
            }
            catch (Exception error) { failures.Add(label + ": " + error.Message); }
        }
        if (failures.Count > 0) throw new InvalidOperationException(string.Join(Environment.NewLine, failures));
    }

    private static void RunSpeedEquipmentAppliesAfterVanillaMovement()
    {
        WithPlayer((player, modPlayer) =>
        {
            var accessoryData = GeneratedItemData.Placeholder();
            accessoryData.Accessory = new AccessorySpec { Enabled = true, MaxRunSpeed = 4f, MovementSpeed = 0.5f };
            accessoryData.RuntimeProgram.Bindings = new[] {
                new RuntimeBindingSpec { Id = "equip", Input = RuntimeInputKind.Equipped,
                    Role = RuntimeEntityRole.Primary, UsePolicy = new RuntimeBindingUsePolicySpec {
                        Action = new RuntimeBindingActionSpec { Kind = RuntimeBindingAction.EquipPassive, TargetId = accessoryData.RuntimeProgram.ItemEntityId },
                    } },
            };
            var armorData = GeneratedItemData.FromJson(accessoryData.ToNetworkJson())!;
            armorData.Accessory.Enabled = false;
            armorData.Armor = new ArmorSpec { Enabled = true, Slot = "head", MaxRunSpeed = -1f };
            var accessory = new GeneratedItem();
            var armor = new GeneratedItem();
            foreach (var (generated, data) in new[] { (accessory, accessoryData), (armor, armorData) })
            {
                var item = new Item();
                typeof(ModType<Item>).GetProperty("Entity", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)!.SetValue(generated, item);
                typeof(GeneratedItem).GetProperty("Data")!.SetValue(generated, data);
                data.ApplyToItem(item);
            }
            modPlayer.ResetEffects();
            player.maxRunSpeed = 3f;
            player.moveSpeed = 1f;
            accessory.UpdateAccessory(player, false);
            armor.UpdateEquip(player);
            Equal(1.5f, player.moveSpeed, "movement-speed modifier remains in equip phase");
            Equal(3f, player.maxRunSpeed, "equip phase must not modify run-speed before vanilla overwrites it");
            // Installed Player.Update multiplies maxRunSpeed by moveSpeed and applies
            // terrain/mount changes before calling PlayerLoader.PostUpdateRunSpeeds.
            player.maxRunSpeed *= player.moveSpeed;
            modPlayer.PostUpdateRunSpeeds();
            Equal(7.5f, player.maxRunSpeed, "post-vanilla run speed receives accessory and armor flat bonuses");
            modPlayer.ResetEffects();
            player.maxRunSpeed = 3f;
            modPlayer.PostUpdateRunSpeeds();
            Equal(3f, player.maxRunSpeed, "unequipped bonuses expire next tick");
        });
    }

    private static void EquipmentAuthoredRangesReachPlayer()
    {
        CheckEquipmentCases(EquipmentRanges);
        // This fix widens only previously narrowing bounds. Keep finite caps,
        // including the existing broader negative regeneration boundary.
        foreach (int sign in new[] { -1, 1 })
        {
            var data = GeneratedItemData.Placeholder();
            data.Accessory.MovementSpeed = data.Armor.MovementSpeed = data.Armor.SetBonusMovementSpeed = sign * 100f;
            data.Accessory.LifeRegen = data.Accessory.ManaRegen = data.Armor.SetBonusLifeRegen = sign * 1000;
            data.Accessory.SentrySlots = sign * 1000;
            for (int pass = 0; pass < 2; pass++)
            {
                data.Normalize();
                float movementCap = sign < 0 ? -0.9f : 3f;
                int regenCap = sign < 0 ? -120 : 200;
                Equal(movementCap, data.Accessory.MovementSpeed, "accessory movement cap");
                Equal(movementCap, data.Armor.MovementSpeed, "armor movement cap");
                Equal(movementCap, data.Armor.SetBonusMovementSpeed, "set movement cap");
                Equal(regenCap, data.Accessory.LifeRegen, "accessory life regen cap");
                Equal(regenCap, data.Accessory.ManaRegen, "accessory mana regen cap");
                Equal(regenCap, data.Armor.SetBonusLifeRegen, "set life regen cap");
                Equal(sign < 0 ? 0 : 20, data.Accessory.SentrySlots, "sentry slot cap");
            }
        }
    }

    private sealed record EquipmentCase(string Group, string Field, float[] Values,
        Func<Player, float>? Observe = null, DamageClass? DamageClass = null);

    private static void CheckEquipmentCases(EquipmentCase[] cases)
    {
        foreach (var test in cases)
        foreach (float value in test.Values)
        WithPlayer((player, _) => {
            string label = test.Group + "/" + test.Field + "=" + value;
            var source = GeneratedItemData.Placeholder();
            bool range = test.Observe is not null;
            source.Accessory.Enabled = test.Group == "accessory";
            source.Armor.Enabled = !source.Accessory.Enabled;
            source.Armor.Slot = range && source.Accessory.Enabled ? "" : "head";
            source.Armor.SetKey = range ? "range_probe" : "class_damage_probe";
            if (range)
            {
                source.Id = "equipment_range_probe"; source.SourceMode = "test_fixture";
                source.Visual.EquipOverlayPath = "range_probe_overlay.png"; source.Visual.EquipOverlayStatus = "generated";
            }
            source.RuntimeProgram.Bindings = new[] { new RuntimeBindingSpec {
                Id = "equip", Input = RuntimeInputKind.Equipped, Role = RuntimeEntityRole.Primary,
                UsePolicy = new() { Action = new() { Kind = RuntimeBindingAction.EquipPassive, TargetId = source.RuntimeProgram.ItemEntityId } },
            } };
            object equipment = source.Accessory.Enabled ? source.Accessory : source.Armor;
            var field = equipment.GetType().GetProperty(test.Field)!;
            field.SetValue(equipment, Convert.ChangeType(value, field.PropertyType));
            // Raw serialization is before any normalizing writer, as in both old observers.
            var data = GeneratedItemData.FromJson(JsonSerializer.Serialize(source,
                new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase }))
                ?? throw new InvalidOperationException(label + ": fixture rejected");
            var item = new Item();
            var generated = AttachItem(new GeneratedItem(), item, data);
            if (range)
            {
                data.ApplyToItem(item);
                player.moveSpeed = 0; player.lifeRegen = player.manaRegenBonus = player.maxTurrets = 0;
            }
            float before = test.DamageClass is null ? 0 : player.GetDamage(test.DamageClass).Additive;
            float untouched = player.GetDamage(DamageClass.Throwing).Additive;
            if (test.Group == "accessory") generated.UpdateAccessory(player, false);
            else if (test.Group == "armor") generated.UpdateEquip(player);
            else generated.UpdateArmorSet(player);
            if (range)
            {
                Equal(value, test.Observe!(player), label + ": real hook projection");
                var copy = GeneratedItemData.FromJson(data.ToNetworkJson())!;
                Equal(value, Convert.ToSingle(field.GetValue(test.Group == "accessory" ? copy.Accessory : copy.Armor)), label + ": native network projection");
            }
            else
            {
                Equal(before + value, player.GetDamage(test.DamageClass!).Additive, label + ": exact selected class");
                Equal(untouched, player.GetDamage(DamageClass.Throwing).Additive, label + ": unrelated class unchanged");
            }
            Console.WriteLine("CASE PASS: Equipment/" + label);
        });
    }

    private static readonly EquipmentCase[] EquipmentRanges = {
        new("accessory", "MovementSpeed", new[] { -.9f, -.7f, 0f, 2.5f, 3f }, p => p.moveSpeed),
        new("accessory", "LifeRegen", new[] { -100f, 0f, 150f, 200f }, p => p.lifeRegen),
        new("accessory", "ManaRegen", new[] { -100f, 0f, 150f, 200f }, p => p.manaRegenBonus),
        new("accessory", "SentrySlots", new[] { 0f, 15f, 20f }, p => p.maxTurrets),
        new("armor", "MovementSpeed", new[] { -.9f, -.7f, 0f, 2.5f, 3f }, p => p.moveSpeed),
        new("set", "SetBonusMovementSpeed", new[] { -.9f, -.7f, 0f, 2.5f, 3f }, p => p.moveSpeed),
        new("set", "SetBonusLifeRegen", new[] { -100f, 0f, 150f, 200f }, p => p.lifeRegen),
    };
    private static readonly EquipmentCase[] EquipmentDamageClasses = {
        new("accessory", "GenericDamage", new[] { .15f }, DamageClass: DamageClass.Generic),
        new("accessory", "MeleeDamage", new[] { .15f }, DamageClass: DamageClass.Melee),
        new("accessory", "RangedDamage", new[] { .15f }, DamageClass: DamageClass.Ranged),
        new("accessory", "MagicDamage", new[] { .15f }, DamageClass: DamageClass.Magic),
        new("accessory", "SummonDamage", new[] { .15f }, DamageClass: DamageClass.Summon),
        new("armor", "GenericDamage", new[] { .15f }, DamageClass: DamageClass.Generic),
        new("armor", "MeleeDamage", new[] { .15f }, DamageClass: DamageClass.Melee),
        new("armor", "RangedDamage", new[] { .15f }, DamageClass: DamageClass.Ranged),
        new("armor", "MagicDamage", new[] { .15f }, DamageClass: DamageClass.Magic),
        new("armor", "SummonDamage", new[] { .15f }, DamageClass: DamageClass.Summon),
        new("set", "SetBonusGenericDamage", new[] { .15f }, DamageClass: DamageClass.Generic),
        new("set", "SetBonusMeleeDamage", new[] { .15f }, DamageClass: DamageClass.Melee),
        new("set", "SetBonusRangedDamage", new[] { .15f }, DamageClass: DamageClass.Ranged),
        new("set", "SetBonusMagicDamage", new[] { .15f }, DamageClass: DamageClass.Magic),
        new("set", "SetBonusSummonDamage", new[] { .15f }, DamageClass: DamageClass.Summon),
    };

}

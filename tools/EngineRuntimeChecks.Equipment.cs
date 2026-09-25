using System;
using System.Collections.Generic;
using System.Reflection;
using System.Text.Json;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Items;
using Terraria;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
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

    private static void EquipmentAuthoredRangesReachPlayer()
    {
        // Endpoints from configure_accessory/configure_armor in capability_registry.py.
        // No alternate stat formulas: observe the real public ModItem hooks.
        (string Group, string Field, float[] Values, Func<Player, float> Observe)[] cases = {
            ("accessory", "MovementSpeed", new[] { -0.9f, -0.7f, 0f, 2.5f, 3f }, p => p.moveSpeed),
            ("accessory", "LifeRegen", new[] { -100f, 0f, 150f, 200f }, p => p.lifeRegen),
            ("accessory", "ManaRegen", new[] { -100f, 0f, 150f, 200f }, p => p.manaRegenBonus),
            ("accessory", "SentrySlots", new[] { 0f, 15f, 20f }, p => p.maxTurrets),
            ("armor", "MovementSpeed", new[] { -0.9f, -0.7f, 0f, 2.5f, 3f }, p => p.moveSpeed),
            ("set", "SetBonusMovementSpeed", new[] { -0.9f, -0.7f, 0f, 2.5f, 3f }, p => p.moveSpeed),
            ("set", "SetBonusLifeRegen", new[] { -100f, 0f, 150f, 200f }, p => p.lifeRegen),
        };
        var failures = new List<string>();
        foreach (var test in cases)
        foreach (float value in test.Values)
        {
            string label = test.Group + "." + test.Field + "=" + value;
            try
            {
                WithPlayer((player, _) =>
                {
                    var data = GeneratedItemData.Placeholder();
                    data.Id = "equipment_range_probe";
                    data.SourceMode = "test_fixture";
                    data.Accessory.Enabled = test.Group == "accessory";
                    data.Armor.Enabled = !data.Accessory.Enabled;
                    data.Armor.Slot = data.Armor.Enabled ? "head" : "";
                    data.Armor.SetKey = "range_probe";
                    // Metadata-only fixture; no texture is opened or GPU initialized.
                    data.Visual.EquipOverlayPath = "range_probe_overlay.png";
                    data.Visual.EquipOverlayStatus = "generated";
                    data.RuntimeProgram.Bindings = new[] {
                        new RuntimeBindingSpec { Id = "equip", Input = RuntimeInputKind.Equipped,
                            Role = RuntimeEntityRole.Primary, UsePolicy = new RuntimeBindingUsePolicySpec {
                                Action = new RuntimeBindingActionSpec { Kind = RuntimeBindingAction.EquipPassive, TargetId = data.RuntimeProgram.ItemEntityId },
                            } },
                    };
                    object equipment = data.Accessory.Enabled ? data.Accessory : data.Armor;
                    var property = equipment.GetType().GetProperty(test.Field)!;
                    property.SetValue(equipment, Convert.ChangeType(value, property.PropertyType));
                    // Serialize BEFORE Normalize: ToJson would already erase the value under test.
                    string json = JsonSerializer.Serialize(data, new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase });
                    data = GeneratedItemData.FromJson(json) ?? throw new InvalidOperationException("fixture rejected before equipment hook");
                    var item = new Item();
                    var generated = new GeneratedItem();
                    typeof(ModType<Item>).GetProperty("Entity", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)!.SetValue(generated, item);
                    typeof(GeneratedItem).GetProperty("Data")!.SetValue(generated, data);
                    data.ApplyToItem(item);
                    player.moveSpeed = 0f;
                    player.lifeRegen = player.manaRegenBonus = player.maxTurrets = 0;
                    if (test.Group == "accessory") generated.UpdateAccessory(player, false);
                    else if (test.Group == "armor") generated.UpdateEquip(player);
                    else generated.UpdateArmorSet(player);
                    Equal(value, test.Observe(player), label + " reaches real hook output");
                    var roundtrip = GeneratedItemData.FromJson(data.ToNetworkJson())!;
                    object transported = test.Group == "accessory" ? roundtrip.Accessory : roundtrip.Armor;
                    Equal(value, Convert.ToSingle(property.GetValue(transported)), label + " survives network round trip");
                });
            }
            catch (Exception error) { failures.Add(label + ": " + error.Message); }
        }
        if (failures.Count > 0)
            throw new InvalidOperationException(string.Join(Environment.NewLine, failures));

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

    private static void EquipmentClassDamageReachesExactDamageClass()
    {
        (string Group, string Field, DamageClass Class)[] cases = {
            ("accessory", "GenericDamage", DamageClass.Generic),
            ("accessory", "MeleeDamage", DamageClass.Melee),
            ("accessory", "RangedDamage", DamageClass.Ranged),
            ("accessory", "MagicDamage", DamageClass.Magic),
            ("accessory", "SummonDamage", DamageClass.Summon),
            ("armor", "GenericDamage", DamageClass.Generic),
            ("armor", "MeleeDamage", DamageClass.Melee),
            ("armor", "RangedDamage", DamageClass.Ranged),
            ("armor", "MagicDamage", DamageClass.Magic),
            ("armor", "SummonDamage", DamageClass.Summon),
            ("set", "SetBonusGenericDamage", DamageClass.Generic),
            ("set", "SetBonusMeleeDamage", DamageClass.Melee),
            ("set", "SetBonusRangedDamage", DamageClass.Ranged),
            ("set", "SetBonusMagicDamage", DamageClass.Magic),
            ("set", "SetBonusSummonDamage", DamageClass.Summon),
        };
        foreach (var test in cases)
        {
            WithPlayer((player, _) =>
            {
                var data = GeneratedItemData.Placeholder();
                data.Accessory.Enabled = test.Group == "accessory";
                data.Armor.Enabled = !data.Accessory.Enabled;
                data.Armor.Slot = "head";
                data.Armor.SetKey = "class_damage_probe";
                data.RuntimeProgram.Bindings = new[] {
                    new RuntimeBindingSpec { Id = "equip", Input = RuntimeInputKind.Equipped,
                        Role = RuntimeEntityRole.Primary, UsePolicy = new RuntimeBindingUsePolicySpec {
                            Action = new RuntimeBindingActionSpec { Kind = RuntimeBindingAction.EquipPassive, TargetId = data.RuntimeProgram.ItemEntityId },
                        } },
                };
                object equipment = test.Group == "accessory" ? data.Accessory : data.Armor;
                equipment.GetType().GetProperty(test.Field)!.SetValue(equipment, 0.15f);
                string json = JsonSerializer.Serialize(data, new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase });
                data = GeneratedItemData.FromJson(json) ?? throw new InvalidOperationException("class damage fixture rejected");
                var generated = new GeneratedItem();
                var item = new Item();
                typeof(ModType<Item>).GetProperty("Entity", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)!.SetValue(generated, item);
                typeof(GeneratedItem).GetProperty("Data")!.SetValue(generated, data);
                float before = player.GetDamage(test.Class).Additive;
                float untouched = player.GetDamage(DamageClass.Throwing).Additive;
                if (test.Group == "accessory") generated.UpdateAccessory(player, false);
                else if (test.Group == "armor") generated.UpdateEquip(player);
                else generated.UpdateArmorSet(player); // tML calls this only after IsArmorSet matches.
                Equal(before + 0.15f, player.GetDamage(test.Class).Additive, test.Group + "." + test.Field + " class modifier");
                Equal(untouched, player.GetDamage(DamageClass.Throwing).Additive, "unselected class remains unchanged");
            });
        }
    }
}

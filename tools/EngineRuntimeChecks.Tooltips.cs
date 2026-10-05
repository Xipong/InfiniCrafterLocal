using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Items;
using Terraria;
using Terraria.ID;
using Terraria.Localization;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private sealed class TooltipProbeMod : Mod
    {
        public override string Name => "InfiniCrafterLocal";
    }

    // Real ModifyTooltips/TooltipLine/Language consumers. Typed CPU fixtures, not a
    // game loop, content registration, player-dependent mana calculation or GPU UI.
    // Use candidate locales with BOTH old and new linked source for paired RED/GREEN.
    public static void GeneratedTooltipsDescribeExactExecutableBindings()
    {
        const BindingFlags hidden = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
        string localeRoot = Environment.GetEnvironmentVariable("INFINI_TOOLTIP_LOCALIZATION_DIR")
            ?? Path.Combine("ModSources", "InfiniCrafterLocal", "Localization");
        LanguageManager oldLanguage = LanguageManager.Instance;
        var buffCache = typeof(Lang).GetField("_buffNameCache", BindingFlags.Static | BindingFlags.NonPublic)!;
        object oldBuffCache = buffCache.GetValue(null)!;
        CultureInfo oldCulture = CultureInfo.CurrentCulture;
        var failures = new List<string>();
        RuntimeBindingSpec Binding(string input, string action, int cost = 0) => new()
        {
            Id = "probe_" + input, Input = input, Role = RuntimeEntityRole.Primary,
            UsePolicy = new() { StackCost = cost, Action = new() {
                Kind = action, TargetId = action == RuntimeBindingAction.SpawnEntity ? "probe_projectile" : "item",
                Placement = action == RuntimeBindingAction.PlaceItem ? new() { TileId = TileID.Stone, PlaceStyle = 0 } : null,
            } },
        };
        LocalizedText Localized(string key, string value) => (LocalizedText)Activator.CreateInstance(
            typeof(LocalizedText), hidden, null, new object[] { key, value }, null)!;
        try
        {
            foreach (string locale in new[] { "en-US", "ru-RU" })
            {
                var manager = (LanguageManager)Activator.CreateInstance(typeof(LanguageManager), nonPublic: true)!;
                typeof(LanguageManager).GetProperty("ActiveCulture")!.SetValue(manager, GameCulture.FromName(locale));
                LanguageManager.Instance = manager;
                // Deliberately opposite process culture: formatting must follow UI culture.
                CultureInfo.CurrentCulture = CultureInfo.GetCultureInfo(locale == "en-US" ? "ru-RU" : "en-US");
                using var json = JsonDocument.Parse(Hjson.HjsonValue.Load(
                    Path.Combine(localeRoot, locale + "_Mods.InfiniCrafterLocal.hjson")).ToString());
                var texts = (Dictionary<string, LocalizedText>)typeof(LanguageManager).GetField("_localizedTexts", hidden)!.GetValue(manager)!;
                Equal(true, LocalizationLoader.TryGetCultureAndPrefixFromPath(locale + "_Mods.InfiniCrafterLocal.hjson", out _, out string? prefix), "native locale path parser");
                Equal("Mods.InfiniCrafterLocal", prefix!, "native locale filename prefix");
                foreach (var field in json.RootElement.GetProperty("RuntimeTooltip").EnumerateObject())
                {
                    string key = prefix + ".RuntimeTooltip." + field.Name;
                    texts.Add(key, Localized(key, field.Value.GetString()!));
                }
                // Scoped known-buff localization cache, no replacement of Lang.GetBuffName.
                var names = Enumerable.Repeat(LocalizedText.Empty, BuffLoader.BuffCount).ToArray();
                names[BuffID.Ironskin] = Localized("BuffName.Ironskin", locale == "en-US" ? "Ironskin" : "Железная кожа");
                buffCache.SetValue(null, names);
                foreach (string scenario in new[] { "split-costs", "placement", "while-selected", "equipped", "effects", "inert-effects", "bounded-hostile", "unresolved" })
                {
                    var data = GeneratedItemData.Placeholder();
                    data.RuntimeProgram.ItemEntityId = "item";
                    data.RuntimeProgram.Entities = new[] {
                        new RuntimeEntitySpec { Id = "item", Kind = RuntimeEntityKind.ItemBody },
                        new RuntimeEntitySpec { Id = "probe_projectile", Kind = RuntimeEntityKind.FreeProjectile, Spawn = new() { Count = 2 } },
                    };
                    data.Gameplay.ManaCost = 17;
                    data.RuntimeProgram.Bindings = scenario switch
                    {
                        "split-costs" => new[] { Binding(RuntimeInputKind.PrimaryUse, RuntimeBindingAction.SpawnEntity), Binding(RuntimeInputKind.AlternateUse, RuntimeBindingAction.ApplyItemEffects, 1) },
                        "placement" => new[] { Binding(RuntimeInputKind.PrimaryUse, RuntimeBindingAction.UseItemBody), Binding(RuntimeInputKind.AlternateUse, RuntimeBindingAction.PlaceItem, 1) },
                        "while-selected" => new[] { Binding(RuntimeInputKind.Hold, RuntimeBindingAction.SpawnEntity) },
                        "equipped" => new[] { Binding(RuntimeInputKind.Equipped, RuntimeBindingAction.EquipPassive) },
                        "inert-effects" => new[] { Binding(RuntimeInputKind.PrimaryUse, RuntimeBindingAction.UseItemBody) },
                        _ => new[] { Binding(RuntimeInputKind.PrimaryUse, RuntimeBindingAction.ApplyItemEffects, 1) },
                    };
                    if (scenario == "equipped") data.Accessory.Enabled = true;
                    if (scenario == "split-costs")
                    {
                        data.Gameplay.MobilityMode = "recall_home";
                        data.Gameplay.MobilityCooldownTicks = 120;
                    }
                    if (scenario is "effects" or "inert-effects" or "bounded-hostile")
                    {
                        data.Gameplay.HealLife = 40; data.Gameplay.HealMana = 12;
                        data.Gameplay.ExtraBuffs = Enumerable.Range(0, scenario == "bounded-hostile" ? 1000 : 1)
                            .Select(_ => new BuffEntrySpec { BuffCode = BuffID.Ironskin, BuffTime = 90 }).ToArray();
                        data.Gameplay.GeneratedBuff = new() { DurationTicks = 90, MiningSpeedMultiplier = 1.25f,
                            MovementSpeed = 0.25f, JumpBoost = 2f, ManaRegen = 4, LifeRegen = 2,
                            EmitLightStrength = 0.5f, LightColorName = "white", OreSenseRadiusTiles = 60 };
                        data.Gameplay.MobilityMode = "blink_to_cursor";
                        data.Gameplay.MobilityRangeTiles = 12; data.Gameplay.MobilityCooldownTicks = 120;
                        data.Gameplay.UseConditionMode = "life_above"; data.Gameplay.UseConditionMinLife = 41;
                        if (scenario == "bounded-hostile")
                        {
                            data.Gameplay.GeneratedBuff.MovementSpeed = float.NaN;
                            data.Gameplay.MobilityMode = "[i:1]\nUNTRUSTED";
                        }
                    }
                    if (scenario == "unresolved") { data.SourceMode = "player_save_ref"; data.Id = "tooltip_unresolved_probe"; }
                    var host = new GeneratedItem();
                    var item = new Item { type = ItemID.Wood, stack = 1, mana = 99, healLife = 99, createTile = -1 };
                    typeof(ModType<Item>).GetProperty("Entity", hidden)!.SetValue(host, item);
                    typeof(ModType).GetProperty("Mod", hidden)!.SetValue(host, new TooltipProbeMod());
                    typeof(GeneratedItem).GetProperty("Data", hidden)!.SetValue(host, data);
                    var vanilla = (TooltipLine)Activator.CreateInstance(typeof(TooltipLine), hidden, null,
                        new object[] { "Terraria", "Damage", "native damage control" }, null)!;
                    var lines = new List<TooltipLine> { vanilla };
                    host.ModifyTooltips(lines);
                    void Check(bool ok, string detail) { if (!ok) failures.Add(locale + "/" + scenario + ": " + detail); }
                    string Line(string name) => lines.SingleOrDefault(x => x.Name == name)?.Text ?? "";
                    Check(ReferenceEquals(vanilla, lines[0]) && vanilla.Text == "native damage control", "vanilla tooltip replaced");
                    Check(item.mana == 99 && item.healLife == 99 && item.createTile == -1 && item.stack == 1, "tooltip mutated Item");
                    Check(data.Gameplay.ManaCost == 17 && (scenario != "bounded-hostile" ||
                        (data.Gameplay.ExtraBuffs.Length == 1000 && float.IsNaN(data.Gameplay.GeneratedBuff.MovementSpeed))), "tooltip normalized/mutated DTO");
                    Check(lines.All(x => !x.Text.Contains("NaN") && !x.Text.Contains("UNTRUSTED") && !x.Text.Contains("Mods.InfiniCrafterLocal.")), "unsafe or unresolved localization output");
                    Check(lines.Count <= 65 && lines.Select(x => x.Name).Distinct().Count() == lines.Count, "unbounded or duplicate facts");
                    string mana17 = locale == "en-US" ? "base mana: 17" : "базовая мана: 17";
                    string cost0 = locale == "en-US" ? "item cost: 0" : "расход предметов: 0";
                    string cost1 = locale == "en-US" ? "item cost: 1" : "расход предметов: 1";
                    switch (scenario)
                    {
                        case "split-costs":
                        case "placement":
                            Check(Line("InfiniInputPrimary").Contains(cost0) && Line("InfiniInputPrimary").Contains(mana17), "primary zero-stack/global mana");
                            Check(Line("InfiniInputAlternate").Contains(cost1) && Line("InfiniInputAlternate").Contains(mana17), "alternate one-stack/global mana");
                            Check(scenario == "placement" ? Line("InfiniPlacementAlternate").Length > 0 : Line("InfiniMobilityAlternate").Contains("2"), "exact placement/recall feedback absent");
                            break;
                        case "while-selected":
                            Check(Line("InfiniInputHold").StartsWith(locale == "en-US" ? "While selected" : "Пока выбран"), "hold incorrectly described as held button");
                            Check(!Line("InfiniInputHold").Contains(mana17) && Line("InfiniInputPrimary").Length == 0, "hold invented use cost/input");
                            break;
                        case "equipped": Check(Line("InfiniInputEquipped").Length > 0 && Line("InfiniInputPrimary").Length == 0, "equipped binding not exposed"); break;
                        case "effects":
                            Check(Line("InfiniConditionPrimary").Contains("41"), "exact use-condition threshold");
                            Check(Line("InfiniHealLifePrimary").Contains("40") && Line("InfiniHealManaPrimary").Contains("12"), "healing values");
                            Check(Line("InfiniBuffPrimary0").Contains(locale == "en-US" ? "Ironskin" : "Железная кожа") && Line("InfiniBuffPrimary0").Contains(locale == "en-US" ? "1.5" : "1,5"), "known buff duration/culture");
                            Check(Line("InfiniMiningPrimary").Contains(locale == "en-US" ? "1.25" : "1,25"), "mining multiplier");
                            Check(Line("InfiniMovementPrimary").Contains("+25%") && Line("InfiniJumpPrimary").Contains("2"), "movement/jump magnitudes");
                            Check(Line("InfiniLifeRegenPrimary").Contains("2") && Line("InfiniManaRegenPrimary").Contains("4") &&
                                Line("InfiniLightPrimary").Contains(locale == "en-US" ? "0.5" : "0,5"), "regen/light magnitudes");
                            Check(Line("InfiniMobilityPrimary").Contains("12") && Line("InfiniMobilityPrimary").Contains("2"), "blink range/cooldown");
                            Check(Line("InfiniOreSensePrimary").Length > 0 && !Line("InfiniOreSensePrimary").Contains("60"), "invented ore-sense radius");
                            break;
                        case "inert-effects": Check(!lines.Any(x => x.Name.StartsWith("InfiniHeal") || x.Name.StartsWith("InfiniBuff") || x.Name.StartsWith("InfiniMining") || x.Name.StartsWith("InfiniMobility")), "inert gameplay effects advertised"); break;
                        case "bounded-hostile": Check(lines.Count(x => x.Name.StartsWith("InfiniBuffPrimary")) == 16 && Line("InfiniMobilityPrimary").Length == 0 && Line("InfiniMovementPrimary").Length == 0, "hostile bounded/unknown/nonfinite controls"); break;
                        case "unresolved": Check(lines.Count == 1, "unresolved save reference invented behavior"); break;
                    }
                    // Adversarial metadata cannot route inputs, effects or tooltip text.
                    string[] before = lines.Select(x => x.Name + "=" + x.Text).ToArray();
                    data.Name = "UNTRUSTED [i:1]\n"; data.Category = "potion"; data.ParentA = "UNTRUSTED";
                    data.Gameplay.Kind = "weapon";
                    var again = new List<TooltipLine> { vanilla }; host.ModifyTooltips(again);
                    Check(before.SequenceEqual(again.Select(x => x.Name + "=" + x.Text)), "metadata changed executable feedback");
                }
            }
        }
        finally
        {
            LanguageManager.Instance = oldLanguage; buffCache.SetValue(null, oldBuffCache);
            CultureInfo.CurrentCulture = oldCulture;
        }
        if (failures.Count != 0) throw new InvalidOperationException(string.Join("; ", failures));
    }
}

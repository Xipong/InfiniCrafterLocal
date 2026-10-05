#nullable enable
using System;
using System.Collections.Generic;
using System.Globalization;
using InfiniCrafterLocal.Common.Models;
using Terraria;
using Terraria.Localization;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Content.Items;

public partial class GeneratedItem
{
    private const string RuntimeTooltipKey = "Mods.InfiniCrafterLocal.RuntimeTooltip.";
    private const int MaxRuntimeTooltipFacts = 64;

    /// <summary>
    /// Read-only inventory feedback from the same exact bindings consumed by the
    /// use/hold/equipment hooks. Never hydrate, normalize, project Item fields or
    /// echo authored name/category/realization/selfEvaluation as instructions.
    /// </summary>
    public override void ModifyTooltips(List<TooltipLine> tooltips)
    {
        GeneratedItemData data = PresentationData();
        if (GeneratedItemData.IsPlayerSaveReferenceOnly(data)) return;
        RuntimeProgramSpec program = data.RuntimeProgram;
        int added = 0;
        void Add(string name, string key, params object[] args)
        {
            if (added >= MaxRuntimeTooltipFacts) return;
            tooltips.Add(new TooltipLine(Mod, "Infini" + name, RuntimeTooltipText(key, args)));
            added++;
        }
        // This is display order, not a chooser: BindingForInput is the canonical
        // consumer, including its first-owner semantics for equipped bindings.
        foreach (string input in new[] { RuntimeInputKind.PrimaryUse, RuntimeInputKind.AlternateUse, RuntimeInputKind.Hold, RuntimeInputKind.Equipped })
        {
            RuntimeBindingSpec? binding = program.BindingForInput(input);
            if (binding is null || !RuntimeBindingAction.IsAllowed(input, binding.UsePolicy.Action.Kind)) continue;
            RuntimeBindingActionSpec action = binding.UsePolicy.Action;
            RuntimeEntitySpec? target = program.TryGetEntity(action.TargetId);
            if (target is null || binding.UsePolicy.StackCost is not (0 or 1)) continue;
            bool active = input is RuntimeInputKind.PrimaryUse or RuntimeInputKind.AlternateUse;
            if (!active && binding.UsePolicy.StackCost != 0) continue;
            string suffix = input switch
            {
                RuntimeInputKind.PrimaryUse => "Primary",
                RuntimeInputKind.AlternateUse => "Alternate",
                RuntimeInputKind.Hold => "Hold",
                RuntimeInputKind.Equipped => "Equipped",
                _ => "",
            };
            string label = RuntimeTooltipText("Input" + suffix);
            string description;
            switch (action.Kind)
            {
                case RuntimeBindingAction.SpawnEntity:
                    if (!RuntimeEntityKind.IsBindingSpawnable(target.Kind)) continue;
                    description = RuntimeTooltipText("Spawn", RuntimeTooltipNumber(RootBindingSpawnCapacity(target)));
                    break;
                case RuntimeBindingAction.UseItemBody:
                case RuntimeBindingAction.ApplyItemEffects:
                case RuntimeBindingAction.PlaceItem:
                case RuntimeBindingAction.EquipPassive:
                    if (target.Kind != RuntimeEntityKind.ItemBody) continue;
                    if (action.Kind == RuntimeBindingAction.PlaceItem && action.Placement is null) continue;
                    if (action.Kind == RuntimeBindingAction.EquipPassive && !data.Accessory.Enabled && !data.Armor.Enabled) continue;
                    description = RuntimeTooltipText(action.Kind switch
                    {
                        RuntimeBindingAction.UseItemBody => "UseItem",
                        RuntimeBindingAction.ApplyItemEffects => "ApplyEffects",
                        RuntimeBindingAction.PlaceItem => "Place",
                        RuntimeBindingAction.EquipPassive => "Equip",
                        _ => "",
                    });
                    break;
                default: continue;
            }
            if (active)
            {
                // Active-use projection installs Gameplay.ManaCost for either
                // input. Item.mana may still reflect a previous projection; the
                // displayed base cost intentionally excludes player reductions.
                Add("Input" + suffix, "ActiveBinding", label, description,
                    RuntimeTooltipNumber(binding.UsePolicy.StackCost), RuntimeTooltipNumber(Math.Max(0, data.Gameplay.ManaCost)));
                AddRuntimeUseCondition(data.Gameplay, suffix, label, Add);
            }
            else
                Add("Input" + suffix, "PassiveBinding", label, description);
            if (action.Kind == RuntimeBindingAction.PlaceItem)
                Add("Placement" + suffix, "PlacementAvailability", label);
            if (active && action.Kind == RuntimeBindingAction.ApplyItemEffects)
                AddRuntimeUseEffects(data.Gameplay, suffix, label, Add);
        }
    }

    private static void AddRuntimeUseCondition(GameplaySpec gp, string suffix, string input, Action<string, string, object[]> add)
    {
        switch (gp.UseConditionMode)
        {
            case "grounded": add("Condition" + suffix, "Grounded", new object[] { input }); break;
            case "not_wet": add("Condition" + suffix, "NotWet", new object[] { input }); break;
            case "life_above": add("Condition" + suffix, "MinimumLife", new object[] { input, RuntimeTooltipNumber(gp.UseConditionMinLife) }); break;
            case "mana_above": add("Condition" + suffix, "MinimumMana", new object[] { input, RuntimeTooltipNumber(gp.UseConditionMinMana) }); break;
        }
    }

    private static void AddRuntimeUseEffects(GameplaySpec gp, string suffix, string input, Action<string, string, object[]> add)
    {
        if (gp.HealLife > 0) add("HealLife" + suffix, "HealLife", new object[] { input, RuntimeTooltipNumber(gp.HealLife) });
        if (gp.HealMana > 0) add("HealMana" + suffix, "HealMana", new object[] { input, RuntimeTooltipNumber(gp.HealMana) });
        void Buff(string name, int id, int ticks)
        {
            if (id <= 0 || id >= BuffLoader.BuffCount || ticks <= 0) return;
            // Only a loaded engine buff name, never an authored effect label.
            string buffName = Lang.GetBuffName(id);
            if (string.IsNullOrEmpty(buffName)) return;
            // Bound even a foreign mod's localized name; remove chat markup and
            // control characters rather than treating it as tooltip syntax.
            var safeName = new System.Text.StringBuilder(96);
            for (int i = 0; i < Math.Min(96, buffName.Length); i++)
            {
                char c = buffName[i];
                if (!char.IsControl(c) && c is not ('[' or ']')) safeName.Append(c);
            }
            if (safeName.Length == 0) return;
            add(name, "Buff", new object[] { input, safeName.ToString(), RuntimeTooltipTime(ticks) });
        }
        Buff("VanillaBuff" + suffix, gp.BuffCode, gp.BuffTime);
        BuffEntrySpec[] buffs = gp.ExtraBuffs ?? Array.Empty<BuffEntrySpec>();
        for (int i = 0; i < Math.Min(16, buffs.Length); i++)
            if (buffs[i] is { } buff) Buff("Buff" + suffix + i.ToString(CultureInfo.InvariantCulture), buff.BuffCode, buff.BuffTime);
        GeneratedBuffSpec? generated = gp.GeneratedBuff;
        if (generated?.HasAnyEffect == true && generated.DurationTicks is > 0 and <= 21600)
        {
            string duration = RuntimeTooltipTime(generated.DurationTicks);
            void Effect(string name, string key, object value) => add(name + suffix, key, new object[] { input, value, duration });
            if (RuntimeTooltipFinite(generated.MiningSpeedMultiplier, 0.25f, 4f) && generated.MiningSpeedMultiplier != 1f)
                Effect("Mining", "Mining", RuntimeTooltipNumber(generated.MiningSpeedMultiplier));
            if (RuntimeTooltipFinite(generated.MovementSpeed, -0.5f, 2f) && generated.MovementSpeed != 0f)
                Effect("Movement", "Movement", RuntimeTooltipSignedPercent(generated.MovementSpeed));
            if (RuntimeTooltipFinite(generated.JumpBoost, 0f, 8f) && generated.JumpBoost > 0f)
                Effect("Jump", "Jump", RuntimeTooltipNumber(generated.JumpBoost));
            if (generated.ManaRegen is > 0 and <= 120) Effect("ManaRegen", "ManaRegen", RuntimeTooltipNumber(generated.ManaRegen));
            if (generated.LifeRegen is > 0 and <= 120) Effect("LifeRegen", "LifeRegen", RuntimeTooltipNumber(generated.LifeRegen));
            if (RuntimeTooltipFinite(generated.EmitLightStrength, 0f, 1.5f) && generated.EmitLightStrength > 0f)
                Effect("Light", "Light", RuntimeTooltipNumber(generated.EmitLightStrength));
            // The executable effect sets findTreasure, not a radius-limited scan.
            if (generated.OreSenseEnabled) add("OreSense" + suffix, "OreSense", new object[] { input, duration });
        }
        string cooldown = RuntimeTooltipTime(Math.Clamp(gp.MobilityCooldownTicks, 0, 36000));
        switch (gp.MobilityMode)
        {
            case "recall_home": add("Mobility" + suffix, "Recall", new object[] { input, cooldown }); break;
            case "blink_to_cursor" when gp.MobilityRangeTiles > 0:
                add("Mobility" + suffix, "Blink", new object[] { input, RuntimeTooltipNumber(Math.Clamp(gp.MobilityRangeTiles, 1, 120)), cooldown,
                    gp.MobilitySafeTileOnly ? RuntimeTooltipText("SafeDestination") : "" });
                break;
        }
    }

    private static string RuntimeTooltipText(string key, params object[] args)
        => Language.GetTextValue(RuntimeTooltipKey + key, args);
    private static CultureInfo RuntimeTooltipCulture => Language.ActiveCulture.CultureInfo;
    private static string RuntimeTooltipNumber(int value) => value.ToString(RuntimeTooltipCulture);
    private static string RuntimeTooltipNumber(float value) => value.ToString("G9", RuntimeTooltipCulture);
    private static bool RuntimeTooltipFinite(float value, float min, float max) => float.IsFinite(value) && value >= min && value <= max;
    private static string RuntimeTooltipSignedPercent(float value)
        => (value > 0f ? "+" : "") + ((double)value * 100d).ToString("G9", RuntimeTooltipCulture);
    private static string RuntimeTooltipTime(int ticks)
    {
        // Tick count is authoritative. Seconds are a compact readout, with an
        // approximation mark whenever millisecond rounding would lose a fraction.
        decimal seconds = ticks / 60m;
        string display = seconds.ToString("0.###", RuntimeTooltipCulture);
        if (decimal.Round(seconds, 3) != seconds) display = "≈" + display;
        return RuntimeTooltipText("Time", display, RuntimeTooltipNumber(ticks));
    }
}

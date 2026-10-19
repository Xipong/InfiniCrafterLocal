#nullable enable
using System;
using System.Collections.Generic;
using System.Globalization;
using Terraria.GameContent;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Common.UI;
using Terraria;
using Terraria.Localization;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Content.Items;

public partial class GeneratedItem
{
    private const string RuntimeTooltipKey = "Mods.InfiniCrafterLocal.RuntimeTooltip.";
    private const int MaxRuntimeTooltipFacts = 64;
    private const int MaxRuntimeTooltipWidth = 720;

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
            string text = RuntimeTooltipText(key, args);
            IReadOnlyList<string> rows = Main.dedServ || FontAssets.MouseText?.IsLoaded != true
                ? new[] { text }
                : WrapRuntimeTooltipLines(text, RuntimeTooltipWidthLimit(Main.screenWidth, Main.UIScale),
                    value => FontAssets.MouseText.Value.MeasureString(value).X);
            for (int i = 0; i < rows.Count; i++)
                tooltips.Add(new TooltipLine(Mod, "Infini" + name
                    + (i == 0 ? "" : "Wrap" + i.ToString(CultureInfo.InvariantCulture)), rows[i]));
            added++;
        }
        // Exact live player table + existing registry definition identity. Never
        // infer a global block from any other item, slot, name or buff texture.
        if (!Main.dedServ && !Main.gameMenu && GeneratedItemRegistryService.IsCurrentWorldData(data)
            && Main.LocalPlayer is { active: true } player)
        {
            InfiniCraftPlayer owner = player.GetModPlayer<InfiniCraftPlayer>();
            int mobilityTicks = owner.GeneratedMobilityCooldownTicks;
            // Only disclose the shared countdown on an executable mobility input;
            // a mining-only primary action remains unrelated and usable.
            foreach (string input in new[] { RuntimeInputKind.PrimaryUse, RuntimeInputKind.AlternateUse })
            {
                RuntimeBindingSpec? binding = program.BindingForInput(input);
                if (mobilityTicks > 0 && binding?.UsePolicy.Action.Kind == RuntimeBindingAction.ApplyItemEffects
                    && program.TryGetEntity(binding.UsePolicy.Action.TargetId)?.Kind == RuntimeEntityKind.ItemBody
                    && (data.EffectsForBinding(binding).MobilityMode is "recall_home" or "blink_to_cursor"))
                {
                    Add("MobilityCooldownRemaining", "MobilityCooldownRemaining", RuntimeTooltipTime(mobilityTicks));
                    break;
                }
            }
            IReadOnlyList<GeneratedItemExhaustionStatus> exhausted = owner.CaptureGeneratedItemExhaustion();
            if (exhausted.Count > 0)
            {
                string definition = GeneratedItemRegistryService.DefinitionIdentity(data);
                foreach (GeneratedItemExhaustionStatus entry in exhausted)
                {
                    if (entry.RemainingTicks <= 0 || !string.Equals(entry.ItemId, data.Id, StringComparison.Ordinal)
                        || !string.Equals(entry.DefinitionIdentity, definition, StringComparison.Ordinal)) continue;
                    Add("ExhaustionRemaining", "ExhaustionRemaining", RuntimeTooltipTime(entry.RemainingTicks));
                    break;
                }
            }
        }
        AddRuntimeEquipmentStats(data, Add);
        if (program.TryGetEffectGroup(program.HeldEffectGroupId)?.GeneratedBuff is { } held)
            AddRuntimeExhaustion(held, "Hold", RuntimeTooltipText("InputHold"), Add);
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
                AddRuntimeUseEffects(data.EffectsForBinding(binding), suffix, label, Add);
        }
        AddRuntimeSecondaryCombat(data, Add);
    }

    // Terraria lays out TooltipLine rows independently. Split overwide localized
    // facts into real rows BEFORE native tooltip box measurement; no custom
    // drawer/tooltip facade and no mutation of authored gameplay or source text.
    internal static int RuntimeTooltipWidthLimit(int screenWidth, float uiScale)
    {
        float scale = float.IsFinite(uiScale) && uiScale > 0f ? uiScale : 1f;
        return Math.Clamp((int)(screenWidth / scale) - 96, 128, MaxRuntimeTooltipWidth);
    }

    // Inject a width measurer for headless regression checks. In the game this
    // is the same loaded MouseText font Terraria uses for item tooltips.
    // Unicode text elements keep surrogate pairs/combining marks together
    // when a single unusually long word needs a hard break.
    internal static IReadOnlyList<string> WrapRuntimeTooltipLines(string text, float maxWidth,
        Func<string, float> measure)
    {
        if (string.IsNullOrEmpty(text) || !float.IsFinite(maxWidth) || maxWidth <= 0f)
            return new[] { text };
        var result = new List<string>();
        foreach (string paragraph in text.Replace("\r\n", "\n").Split('\n'))
        {
            string remaining = paragraph;
            while (remaining.Length > 0 && measure(remaining) > maxWidth)
            {
                var boundaries = new List<int>();
                var elements = StringInfo.GetTextElementEnumerator(remaining);
                while (elements.MoveNext())
                    boundaries.Add(elements.ElementIndex + elements.GetTextElement().Length);
                if (boundaries.Count == 0) break;
                int lo = 0, hi = boundaries.Count - 1, fitted = -1;
                while (lo <= hi)
                {
                    int middle = lo + (hi - lo) / 2;
                    if (measure(remaining[..boundaries[middle]]) <= maxWidth)
                    {
                        fitted = middle;
                        lo = middle + 1;
                    }
                    else hi = middle - 1;
                }
                int end = boundaries[Math.Max(0, fitted)];
                int space = -1;
                for (int i = end - 1; i > 0; i--)
                    if (char.IsWhiteSpace(remaining[i])) { space = i; break; }
                if (space > 0)
                {
                    string prefix = remaining[..space].TrimEnd();
                    if (prefix.Length > 0)
                    {
                        result.Add(prefix);
                        remaining = remaining[(space + 1)..].TrimStart();
                        continue;
                    }
                }
                result.Add(remaining[..end]);
                remaining = remaining[end..].TrimStart();
            }
            if (remaining.Length != 0 || paragraph.Length == 0)
                result.Add(remaining);
        }
        return result;
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

    private static void AddRuntimeExhaustion(GeneratedBuffSpec? buff, string suffix, string input,
        Action<string, string, object[]> add)
    {
        if (buff?.HasAnyEffect == true && buff.DurationTicks is > 0 and <= 21600
            && buff.ExhaustionTicks is > 0 and <= 21600)
            add("Exhaustion" + suffix, "ExhaustionDeclared",
                new object[] { input, RuntimeTooltipTime(buff.ExhaustionTicks.Value) });
    }

    private static void AddRuntimeUseEffects(IItemEffectsSpec gp, string suffix, string input, Action<string, string, object[]> add)
    {
        AddRuntimeExhaustion(gp.GeneratedBuff, suffix, input, add);
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
                Effect("Jump", "Jump", RuntimeTooltipNumber(PlayerDisplayUnits.BlocksPerSecond(generated.JumpBoost)));
            if (generated.ManaRegen is > 0 and <= 120) Effect("ManaRegen", "ManaRegen", RuntimeTooltipNumber(generated.ManaRegen));
            if (generated.LifeRegen is > 0 and <= 120) Effect("LifeRegen", "LifeRegen", RuntimeTooltipNumber(generated.LifeRegen / 2f));
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
    private static string RuntimeTooltipNumber(float value) => value.ToString("G7", RuntimeTooltipCulture);
    private static bool RuntimeTooltipFinite(float value, float min, float max) => float.IsFinite(value) && value >= min && value <= max;
    private static string RuntimeTooltipSignedPercent(float value)
        => (value > 0f ? "+" : "") + ((double)value * 100d).ToString("G7", RuntimeTooltipCulture);
    private static string RuntimeTooltipTime(int ticks)
    {
        // Display-only seconds: authoritative/debug data keeps its exact ticks.
        // Mark fractional rounding without exposing implementation units in UI.
        decimal seconds = ticks / 60m;
        string display = seconds.ToString("0.###", RuntimeTooltipCulture);
        if (decimal.Round(seconds, 3) != seconds) display = "≈" + display;
        return RuntimeTooltipText("Time", display);
    }
}

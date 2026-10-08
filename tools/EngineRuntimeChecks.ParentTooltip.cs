using System;
using System.Collections.Generic;
using System.Reflection;
using System.Text.Json;
using InfiniCrafterLocal.Common.Services;
using Terraria;
using Terraria.ID;
using Terraria.Localization;
using Terraria.UI;

internal static partial class EngineRuntimeChecks
{
    private static void LiteralParentTooltipReachesRealCraftSnapshot()
    {
        const BindingFlags hidden = BindingFlags.Instance | BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic;
        var oldLanguage = LanguageManager.Instance;
        var cacheField = typeof(Lang).GetField("_itemTooltipCache", hidden)!;
        var oldCache = cacheField.GetValue(null);
        try
        {
            foreach (string locale in new[] { "en-US", "ru-RU" })
            {
                var manager = (LanguageManager)Activator.CreateInstance(typeof(LanguageManager), nonPublic: true)!;
                typeof(LanguageManager).GetProperty("ActiveCulture")!.SetValue(manager, GameCulture.FromName(locale));
                LanguageManager.Instance = manager;
                var cache = new ItemTooltip[ItemID.Count];
                Array.Fill(cache, ItemTooltip.None);
                string literal = locale == "ru-RU" ? "Увеличивает скорость добычи на 25%\n  буквальная строка  " : "Increases mining speed by 25%\n  literal line  ";
                var text = (LocalizedText)Activator.CreateInstance(typeof(LocalizedText), hidden, null,
                    new object[] { "ItemTooltip.MiningPotion", literal }, null)!;
                cache[ItemID.MiningPotion] = ItemTooltip.FromLocalization(text);
                cacheField.SetValue(null, cache);
                var item = new Item(); item.SetDefaults(ItemID.MiningPotion); item.stack = 3;
                var stone = new Item(); stone.SetDefaults(ItemID.StoneBlock);
                string before = item.type + "/" + item.stack + "/" + item.buffType + "/" + item.buffTime;
                using var request = JsonDocument.Parse(new GeneratorClient().Prepare(item, stone, new Player()).PayloadJson);
                var parent = request.RootElement.GetProperty("itemA");
                Equal(literal.Split('\n')[0], parent.GetProperty("tooltipLines")[0].GetString()!, "literal tooltip source first line");
                Equal(literal.Split('\n')[1], parent.GetProperty("tooltipLines")[1].GetString()!, "literal whitespace preserved");
                var provenance = parent.GetProperty("tooltipSource");
                Equal(locale, provenance.GetProperty("language").GetString()!, "actual active UI language");
                Equal("Terraria/MiningPotion", provenance.GetProperty("fullName").GetString()!, "exact source identity");
                Equal("Lang.GetTooltip", provenance.GetProperty("source").GetString()!, "real native producer");
                Equal(before, item.type + "/" + item.stack + "/" + item.buffType + "/" + item.buffTime, "request does not mutate parent");
                Equal(0, request.RootElement.GetProperty("itemB").GetProperty("tooltipLines").GetArrayLength(), "no tooltip remains empty");
                foreach (var bound in new[] { (Raw: string.Join('\n', new string[65]), Status: "refused_line_bound"),
                    (Raw: new string('x', 16_385), Status: "refused_character_bound") })
                {
                    var oversized = (LocalizedText)Activator.CreateInstance(typeof(LocalizedText), hidden, null,
                        new object[] { "ItemTooltip.MiningPotion", bound.Raw }, null)!;
                    cache[ItemID.MiningPotion] = ItemTooltip.FromLocalization(oversized);
                    using var refused = JsonDocument.Parse(new GeneratorClient().Prepare(item, stone, new Player()).PayloadJson);
                    var source = refused.RootElement.GetProperty("itemA");
                    Equal(0, source.GetProperty("tooltipLines").GetArrayLength(), "whole observation refused, not clipped");
                    Equal(bound.Status, source.GetProperty("tooltipSource").GetProperty("status").GetString()!, "bound refusal retains provenance");
                }
            }
        }
        finally { cacheField.SetValue(null, oldCache); LanguageManager.Instance = oldLanguage; }
    }
}

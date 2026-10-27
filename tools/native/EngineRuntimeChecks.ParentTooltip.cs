using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using InfiniCrafterLocal.Common.Services;
using Terraria;
using Terraria.ID;
using Terraria.Localization;
using Terraria.ModLoader;
using Terraria.UI;

internal static partial class EngineRuntimeChecks
{
    private static TooltipLine ProbeLine(string name, string text) => (TooltipLine)Activator.CreateInstance(
        typeof(TooltipLine), RootPrivate, null, new object[] { "Probe", name, text }, null)!;
    private sealed class TooltipProbeItem : ModItem
    {
        internal int State;
        internal static bool ThrowAfterChange;
        internal static int Calls;
        internal static int ExtraLines;
        internal static int ExtraChars;
        public override void ModifyTooltips(List<TooltipLine> lines)
        {
            Calls++;
            var first = lines.FirstOrDefault(line => line.Name == "Tooltip0");
            if (first != null) first.Text = "item-" + State;
            for(int i=0;i<ExtraLines;i++) lines.Add(ProbeLine("bulk"+i, "bulk"));
            if(ExtraChars>0) lines.Add(ProbeLine("big", new string('a', ExtraChars)));
            lines.Add(ProbeLine("extra", "added-" + State));
            if (ThrowAfterChange) throw new InvalidOperationException("fixture");
            Item.stack = 99;
        }
    }
    private sealed class TooltipProbeGlobal : GlobalItem
    {
        internal static bool ChangeDamage;
        internal static bool Disable;
        public override void ModifyTooltips(Item item, List<TooltipLine> lines)
        {
            if (Disable) return;
            var first = lines.FirstOrDefault(line => line.Name == "Tooltip0");
            if (first != null) first.Text += "-global";
            var damage = lines.FirstOrDefault(line => line.Name == "Damage");
            if (ChangeDamage && damage != null) damage.Text += "-hooked-display";
            lines.RemoveAll(line => line.Name == "extra");
            lines.Add(ProbeLine("global", "global-added"));
        }
    }
    private static void ParentTooltipRunsNativeHooks()
    {
        using var actors = new NativeActorState();
        Terraria.Main.netMode=NetmodeID.SinglePlayer; Terraria.Main.dedServ=false; Terraria.Main.myPlayer=0;
        var player=Terraria.Main.player[0]=new Player { whoAmI=0, active=true };
        var oldLanguage=LanguageManager.Instance;
        var prefix=(LocalizedText[])Lang.prefix.Clone(); var tips=(LocalizedText[])Lang.tip.Clone();
        var tooltipCacheField=typeof(Lang).GetField("_itemTooltipCache",RootPrivate)!;
        var cache=(ItemTooltip[])tooltipCacheField.GetValue(null)!;
        var oldTooltip=cache[ItemID.Wood];
        var globalField=typeof(ItemLoader).GetField("HookModifyTooltips",RootPrivate)!;
        object oldHook=globalField.GetValue(null)!;
        try
        {
            var manager=(LanguageManager)Activator.CreateInstance(typeof(LanguageManager),true)!;
            typeof(LanguageManager).GetProperty("ActiveCulture")!.SetValue(manager,GameCulture.FromName("en-US")); LanguageManager.Instance=manager;
            for(int i=0;i<Lang.prefix.Length;i++) Lang.prefix[i] ??= LocalizedText.Empty;
            for(int i=0;i<Lang.tip.Length;i++) Lang.tip[i] ??= LocalizedText.Empty;
            var text=(LocalizedText)Activator.CreateInstance(typeof(LocalizedText),RootPrivate,null,new object[]{"probe","[DYNAMIC]"},null)!;
            cache[ItemID.Wood]=ItemTooltip.FromLocalization(text);
            var hook=typeof(object).GetMethod("MemberwiseClone",RootPrivate)!.Invoke(oldHook,null)!;
            var template=new TooltipProbeGlobal();
            typeof(GlobalType<GlobalItem>).GetProperty("PerEntityIndex",RootPrivate)!.SetValue(template,(short)-1);
            var hookType=globalField.FieldType;
            hookType.GetField("hookGlobals",RootPrivate)!.SetValue(hook,new GlobalItem[]{template});
            hookType.GetField("hookGlobalsByType",RootPrivate)!.SetValue(hook,Enumerable.Range(0,ItemLoader.ItemCount).Select(_=>new GlobalItem[]{template}).ToArray());
            globalField.SetValue(null,hook);
            var item=new Item(ItemID.Wood); item.stack=3;
            var mod=new TooltipProbeItem { State=7 };
            typeof(ModType<Item>).GetProperty("Entity",RootPrivate)!.SetValue(mod,item);
            typeof(Item).GetProperty("ModItem",RootPrivate)!.SetValue(item,mod);
            var result=GeneratorClient.CaptureLiteralParentTooltip(item,null,"Probe/Wood",player);
            var source=JsonSerializer.SerializeToElement(result.Source);
            Equal("observed_local_hooks",source.GetProperty("status").GetString()!,"native hook result");
            Equal("item-7-global,global-added",string.Join(",",result.Lines),"ModItem then GlobalItem changes/add/remove");
            Equal(3,item.stack,"original stack untouched");
            Equal(7,mod.State,"original mod state untouched");
            // UI-calculated damage is not duplicated into the prompt unless a
            // hook deliberately changes the display line; raw stats remain base.
            var weapon=new Item(ItemID.CopperShortsword); int rawDamage=weapon.damage;
            TooltipProbeGlobal.ChangeDamage=false;
            var unchangedWeapon=GeneratorClient.CaptureLiteralParentTooltip(weapon,null,"Terraria/CopperShortsword",player);
            Equal("observed_local_hooks",JsonSerializer.SerializeToElement(unchangedWeapon.Source).GetProperty("status").GetString()!,"weapon UI source ready");
            Equal(false,unchangedWeapon.Lines.Any(line=>line.Contains("damage",StringComparison.OrdinalIgnoreCase)),"unchanged UI damage omitted");
            TooltipProbeGlobal.ChangeDamage=true;
            var changedWeapon=GeneratorClient.CaptureLiteralParentTooltip(weapon,null,"Terraria/CopperShortsword",player);
            Equal(true,changedWeapon.Lines.Any(line=>line.EndsWith("-hooked-display",StringComparison.Ordinal)),"changed display damage retained");
            Equal(rawDamage,weapon.damage,"original weapon damage untouched");
            using(var weaponRequest=JsonDocument.Parse(new GeneratorClient().Prepare(weapon,new Item(ItemID.DirtBlock),player).PayloadJson))
            {
                var projected=weaponRequest.RootElement.GetProperty("itemA");
                Equal(rawDamage,projected.GetProperty("damage").GetInt32(),"raw base damage not replaced by display text");
                Equal(true,projected.GetProperty("tooltipLines").EnumerateArray().Any(x=>x.GetString()!.EndsWith("-hooked-display",StringComparison.Ordinal)),"changed display text reaches request");
            }

            Equal("player_adjusted_display_text_not_base_item_stats",JsonSerializer.SerializeToElement(changedWeapon.Source).GetProperty("modifiedNativeLines").GetString()!,"display values have explicit scope");
            TooltipProbeGlobal.ChangeDamage=false;

            using(var request=JsonDocument.Parse(new GeneratorClient().Prepare(item,new Item(ItemID.DirtBlock),player).PayloadJson))
            {
                var root=request.RootElement.GetProperty("itemA");
                Equal("item-7-global,global-added",string.Join(",",root.GetProperty("tooltipLines").EnumerateArray().Select(x=>x.GetString())),"Prepare forwards native hook text");
                Equal("observed_local_hooks",root.GetProperty("tooltipSource").GetProperty("status").GetString()!,"Prepare forwards provenance");
                Equal(3,item.stack,"Prepare preserves original");
            }
            // Empty literal sources may gain meaningful mod tooltip lines.
            cache[ItemID.Wood]=ItemTooltip.None; item.RebuildTooltip();
            var blank=new Item(ItemID.Wood); TooltipProbeGlobal.Disable=true;
            var empty=GeneratorClient.CaptureLiteralParentTooltip(blank,null,"Terraria/Wood",player);
            Equal(0,empty.Lines.Length,"no descriptions and no hook additions remain empty");
            Equal("observed_local_hooks",JsonSerializer.SerializeToElement(empty.Source).GetProperty("status").GetString()!,"empty completed hook observation is explicit");
            TooltipProbeGlobal.Disable=false;
            var added=GeneratorClient.CaptureLiteralParentTooltip(item,null,"Probe/Wood",player);
            Equal("global-added",string.Join(",",added.Lines),"hooks may add text to empty literal tooltip");
            cache[ItemID.Wood]=ItemTooltip.FromLocalization(text); item.RebuildTooltip();
            TooltipProbeItem.ExtraLines=65;
            var tooMany=GeneratorClient.CaptureLiteralParentTooltip(item,null,"Probe/Wood",player);
            Equal(0,tooMany.Lines.Length,"overlong output is never truncated");
            Equal("refused_line_bound",JsonSerializer.SerializeToElement(tooMany.Source).GetProperty("status").GetString()!,"line bound provenance");
            TooltipProbeItem.ExtraLines=0; TooltipProbeItem.ExtraChars=16_385;
            var tooLong=GeneratorClient.CaptureLiteralParentTooltip(item,null,"Probe/Wood",player);
            Equal(0,tooLong.Lines.Length,"oversized output is never truncated");
            Equal("refused_character_bound",JsonSerializer.SerializeToElement(tooLong.Source).GetProperty("status").GetString()!,"character bound provenance");
            TooltipProbeItem.ExtraChars=0;
            typeof(LanguageManager).GetProperty("ActiveCulture")!.SetValue(manager,GameCulture.FromName("ru-RU"));
            var russian=GeneratorClient.CaptureLiteralParentTooltip(item,null,"Probe/Wood",player);
            Equal("ru-RU",JsonSerializer.SerializeToElement(russian.Source).GetProperty("language").GetString()!,"active UI locale recorded");
            int calls=TooltipProbeItem.Calls;
            var foreign=GeneratorClient.CaptureLiteralParentTooltip(item,null,"Probe/Wood",new Player{active=true});
            Equal("unavailable",JsonSerializer.SerializeToElement(foreign.Source).GetProperty("hookContext").GetString()!,"foreign player is not substituted");
            Equal(calls,TooltipProbeItem.Calls,"foreign context never invokes local hooks");

            Terraria.Main.netMode=NetmodeID.MultiplayerClient;
            var captured = GeneratorClient.CaptureClientTooltip(item, player);
            Equal("item-7-global,global-added", string.Join(",", captured!.Lines), "client captures actual hook output");
            Equal("ru-RU", captured.Language, "client capture records locale");
            Equal(true, GeneratorClient.CaptureClientTooltip(item, new Player{active=true}) is null, "foreign client context is never captured");

            TooltipProbeItem.ThrowAfterChange=true;
            var failed=GeneratorClient.CaptureLiteralParentTooltip(item,null,"Probe/Wood",player);
            Equal("[DYNAMIC]",string.Join(",",failed.Lines),"failed hook preserves only the untouched literal, not partial mutations");
            Equal("observed_literal_hook_failed",JsonSerializer.SerializeToElement(failed.Source).GetProperty("status").GetString()!,"failure provenance");
            TooltipProbeItem.ThrowAfterChange=false;
            Terraria.Main.netMode=NetmodeID.Server;
            var server=GeneratorClient.CaptureLiteralParentTooltip(item,null,"Probe/Wood",player);
            Equal(true, GeneratorClient.CaptureClientTooltip(item, player) is null, "server cannot impersonate client capture");
            Equal("[DYNAMIC]",string.Join(",",server.Lines),"server observes literal without calling client hooks");
            Equal("unavailable",JsonSerializer.SerializeToElement(server.Source).GetProperty("hookContext").GetString()!,"server context honest");
            int serverBaseDamage = item.damage;
            var clientReport = new ClientTooltipObservation(new[] { "client-observed" }, "ru-RU");
            using (var report = JsonDocument.Parse(new GeneratorClient().Prepare(item, new Item(ItemID.DirtBlock), player,
                "", false, clientReport, null).PayloadJson))
            {
                var root = report.RootElement.GetProperty("itemA");
                Equal("client-observed", string.Join(",", root.GetProperty("tooltipLines").EnumerateArray().Select(x => x.GetString())), "admitted report reaches author");
                var provenance = root.GetProperty("tooltipSource");
                Equal("client_reported", provenance.GetProperty("source").GetString()!, "client report is not called a server observation");
                Equal(false, provenance.GetProperty("verified").GetBoolean(), "client report is explicitly unverified");
                Equal("ru-RU", provenance.GetProperty("language").GetString()!, "client language preserved");
                Equal(serverBaseDamage, root.GetProperty("damage").GetInt32(), "server native facts unchanged");
            }
            using (var report = JsonDocument.Parse(new GeneratorClient().Prepare(item, new Item(ItemID.DirtBlock), player,
                "", false, new ClientTooltipObservation(Array.Empty<string>(), "en-US"), null).PayloadJson))
            {
                var root = report.RootElement.GetProperty("itemA");
                Equal(0, root.GetProperty("tooltipLines").GetArrayLength(), "intentionally empty client tooltip is retained");
                Equal("client_reported", root.GetProperty("tooltipSource").GetProperty("status").GetString()!, "empty report is not replaced with a server literal");
            }
            using (var report = JsonDocument.Parse(new GeneratorClient().Prepare(item, new Item(ItemID.DirtBlock), player,
                "", false, new ClientTooltipObservation(Array.Empty<string>(), "en-US", "refused_utf8_bound"), null).PayloadJson))
            {
                var root = report.RootElement.GetProperty("itemA");
                Equal("[DYNAMIC]", string.Join(",", root.GetProperty("tooltipLines").EnumerateArray().Select(x => x.GetString())), "refused client report keeps the independent server literal");
                Equal("refused_utf8_bound", root.GetProperty("tooltipSource").GetProperty("clientObservationStatus").GetString()!, "wire-size refusal is visible");
            }
        }
        finally
        {
            TooltipProbeGlobal.ChangeDamage=TooltipProbeGlobal.Disable=false; TooltipProbeItem.ThrowAfterChange=false; TooltipProbeItem.Calls=0; TooltipProbeItem.ExtraLines=TooltipProbeItem.ExtraChars=0; globalField.SetValue(null,oldHook); cache[ItemID.Wood]=oldTooltip;
            Array.Copy(prefix,Lang.prefix,prefix.Length); Array.Copy(tips,Lang.tip,tips.Length); LanguageManager.Instance=oldLanguage;
        }
    }
}

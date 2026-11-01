using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text.Json;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using Mono.Cecil.Cil;
using MonoMod.Cil;
using MonoMod.RuntimeDetour;
using ReLogic.Content;
using ReLogic.Graphics;
using Terraria;
using Terraria.GameContent;
using Terraria.ID;
using Terraria.Localization;
using Terraria.ModLoader;
using Terraria.UI.Chat;

internal static partial class EngineRuntimeChecks
{
    // Parent-owned native compilation only. These tests compile against the old
    // product; new presentation helpers are reflected so RED is a missing behavior.
    private static Type VideoUiView => typeof(GeneratedItem).Assembly.GetType(
        "InfiniCrafterLocal.Common.UI.GeneratedStatusTooltipView")
        ?? throw new InvalidOperationException("VFUI03: generated status hover needs bounded native text layout");
    private static MethodInfo VideoUiMethod(string method) => VideoUiView.GetMethod(method,
        BindingFlags.Static | BindingFlags.NonPublic) ?? throw new InvalidOperationException("missing status helper: " + method);
    private static GeneratedItemData VideoUiFixture(string id)
    {
        string raw = File.ReadAllText("tools/fixtures/video-ui-buffs/" + id + ".json");
        Equal(true, GeneratedItemData.FromJson(raw) is null, "captured retired visibility is refused");
        var control = System.Text.Json.Nodes.JsonNode.Parse(raw)!;
        Equal("", control["gameplay"]!["releaseTiming"]!.GetValue<string>(), "captured inherited gameplay visibility");
        Equal("", control["runtimeProgram"]!["itemUse"]!["releaseTiming"]!.GetValue<string>(), "captured inherited item visibility");
        // Named test counterpart: remove only obsolete empty presentation leaves.
        control["gameplay"]!.AsObject().Remove("releaseTiming");
        control["runtimeProgram"]!["itemUse"]!.AsObject().Remove("releaseTiming");
        return GeneratedItemData.FromJson(control.ToJsonString())
            ?? throw new InvalidOperationException("native reader refused current UI-buff control " + id);
    }
    private static string VideoUiSnapshot(GeneratedItemData data) => JsonSerializer.Serialize(data);

    public static void VFUI03StatusHoverWrapsWholeBlockForNativeClamp()
    {
        // Same title + multiline description the final native cursorText path
        // must measure together, NOT separate buffTooltip (whose bottom clamp
        // excludes the title height in the installed Terraria consumer).
        Func<string, Vector2> measure = text => {
            string[] rows = text.Split('\n');
            return new Vector2(rows.Max(row => new StringInfo(row).LengthInTextElements) * 8f, rows.Length * 24f);
        };
        string Wrap(string label, string body, int width, int height) => (string)VideoUiMethod("Wrap")
            .Invoke(null, new object[] { label, body, width, height, measure })!;
        foreach (int width in new[] { 320, 640, 1280 })
        foreach (int height in new[] { 240, 720 })
        {
            const string name = "Истощение: Медовый бочонок-диспенсер";
            const string body = "До конца истощения предмета: 17 с; блокируется только повторное применение сгенерированного усиления этого предмета. Все копии и группы делят таймер; другие предметы независимы.";
            string text = Wrap(name, body, width, height);
            Vector2 size = measure(text);
            Equal(true, size.X <= Math.Min(480, width - 48), "status title AND body fit bounded native text width");
            Equal(true, size.Y <= height - 48, "whole status block fits viewport before native bottom clamp");
            Equal(false, text.Contains('\r'), "normalized line endings in display copy only");
        }
        const string fullName = "Mobility cooldown";
        const string fullBody = "Remaining: 17 s. Attacks and mining are unaffected.";
        Equal(fullName + " " + fullBody, Wrap(fullName, fullBody, 1280, 720).Replace('\n', ' '), "ordinary hover preserves all prose and values");
        string large = Wrap("Status", string.Join("\n", Enumerable.Repeat("Active contribution: +0.1 — 30 s", 64)), 640, 240);
        Equal(true, large.EndsWith("…", StringComparison.Ordinal), "oversize contribution list discloses presentation truncation");
        Equal(true, measure(large).Y <= 192, "oversize list cannot push block above viewport");
        string unicode = string.Concat(Enumerable.Repeat("меч👩‍🚀", 30));
        string unicodeWrapped = Wrap("Status", unicode, 320, 2160);
        Equal("Status" + unicode, unicodeWrapped.Replace("\n", ""), "unspaced graphemes survive display wrapping");
    }

    public static void VFUI04StatusCountdownIsStableWholeSecondsAndNumbersStayNonzero()
    {
        WithForgePresentationLanguages(locale => {
            CultureInfo culture = Language.ActiveCulture.CultureInfo;
            string Countdown(int ticks) => (string)VideoUiMethod("CountdownSeconds").Invoke(null, new object[] { ticks, culture })!;
            Equal("17", Countdown(1020), "exact second countdown");
            Equal("17", Countdown(974), "no 16.233 frame-by-frame decimal jitter");
            Equal("17", Countdown(961), "same display throughout one second");
            Equal("16", Countdown(960), "one update per second at boundary");
            Equal("1", Countdown(1), "active last tick cannot display zero seconds");
            Equal("0", Countdown(0), "zero control");
            Type mobility = typeof(GeneratedItem).Assembly.GetType("InfiniCrafterLocal.Common.UI.GeneratedMobilityCooldownStatusView")!;
            MethodInfo build = mobility.GetMethod("Build", BindingFlags.Static | BindingFlags.NonPublic)!;
            string Tip(int ticks) {
                object row = build.Invoke(null, new object[] { ticks, culture })!;
                Equal(ticks, (int)row.GetType().GetProperty("RemainingTicks")!.GetValue(row)!, "row retains exact authoritative ticks");
                return (string)row.GetType().GetProperty("Tooltip")!.GetValue(row)!;
            }
            Equal(Tip(1020), Tip(974), "actual mobility status text stable throughout the second");
            Equal(false, Tip(974).Contains("≈") || Tip(974).Contains("233"), "no approximate fractions in live countdown");
            string Number(double value) => (string)VideoUiMethod("Number").Invoke(null, new object[] { value, culture })!;
            Equal(locale == "ru-RU" ? "33,333" : "33.333", Number((double).33333334f * 100d), "bounded display precision");
            Equal(false, Number(.0000004f) is "0" or "-0", "real small nonzero contribution stays visible");
            var data = MobilityConsumptionFixture("", 0);
            data.Gameplay.GeneratedBuff = new GeneratedBuffSpec { DurationTicks = 90, MovementSpeed = .33333334f };
            var host = AttachItem(new GeneratedItem(), new Item { type = ItemID.Wood, stack = 1 }, data);
            typeof(ModType).GetProperty("Mod", TestInstance)!.SetValue(host, new TooltipProbeMod());
            string before = VideoUiSnapshot(host.Data);
            var lines = new List<TooltipLine>(); host.ModifyTooltips(lines);
            string line = lines.Single(row => row.Name == "InfiniMovementPrimary").Text;
            Equal(true, line.Contains(locale == "ru-RU" ? "+33,333%" : "+33.333%"), "actual inventory percentage uses compact display");
            Equal(before, VideoUiSnapshot(host.Data), "display never rewrites authored float or ticks");
            Equal(true, line.Contains(locale == "ru-RU" ? "1,5" : "1.5"), "configured non-countdown duration retains fractional precision");
        });
    }

    public static void VFUI03NativeWholeCursorBlockClampsAtAllEdges()
    {
        // Deterministic font-metrics + final paint boundary only. The actual
        // installed Main.MouseText -> cache -> MouseTextInner clamp executes.
        // Native CPU geometry evidence, NOT actual glyph/GPU acceptance.
        Func<string, Vector2> measure = text => {
            string[] rows = text.Split('\n');
            return new Vector2(rows.Max(row => new StringInfo(row).LengthInTextElements) * 8f, rows.Length * 24f);
        };
        var oldFont = FontAssets.MouseText;
        var font = (DynamicSpriteFont)RuntimeHelpers.GetUninitializedObject(typeof(DynamicSpriteFont));
        var asset = (Asset<DynamicSpriteFont>)RuntimeHelpers.GetUninitializedObject(typeof(Asset<DynamicSpriteFont>));
        foreach (FieldInfo field in asset.GetType().GetFields(TestInstance))
            if (field.FieldType == typeof(DynamicSpriteFont)) field.SetValue(asset, font);
        asset.GetType().GetProperty("State")!.SetValue(asset, AssetState.Loaded);
        var main = Terraria.Main.instance ?? (Terraria.Main)RuntimeHelpers.GetUninitializedObject(typeof(Terraria.Main));
        FieldInfo cache = typeof(Terraria.Main).GetField("_mouseTextCache", TestInstance)!;
        object? oldCache = cache.GetValue(main);
        int oldNpc = main.mouseNPCType, oldWidth = Terraria.Main.screenWidth, oldHeight = Terraria.Main.screenHeight;
        int oldX = Terraria.Main.mouseX, oldY = Terraria.Main.mouseY;
        Item oldItem = Terraria.Main.mouseItem, oldHover = Terraria.Main.HoverItem;
        var paints = new List<(string Text, Vector2 Position)>();
        MethodInfo sizeMethod = typeof(ChatManager).GetMethods().Single(method => method.Name == "GetStringSize"
            && method.GetParameters().Length == 4 && method.GetParameters()[1].ParameterType == typeof(string));
        MethodInfo paintMethod = typeof(ChatManager).GetMethods().Single(method => method.Name == "DrawColorCodedStringWithShadow"
            && method.GetParameters().Length == 10 && method.GetParameters()[2].ParameterType == typeof(string));
        using var sizeBoundary = new ILHook(sizeMethod, il => {
            il.Body.Instructions.Clear(); il.Body.ExceptionHandlers.Clear();
            var cursor = new ILCursor(il); cursor.Emit(OpCodes.Ldarg_1);
            cursor.EmitDelegate<Func<string, Vector2>>(text => measure(text)); cursor.Emit(OpCodes.Ret);
        });
        using var paintBoundary = new ILHook(paintMethod, il => {
            il.Body.Instructions.Clear(); il.Body.ExceptionHandlers.Clear();
            var cursor = new ILCursor(il); cursor.Emit(OpCodes.Ldarg_2); cursor.Emit(OpCodes.Ldarg_3);
            cursor.EmitDelegate<Action<string, Vector2>>((text, position) => paints.Add((text, position)));
            cursor.EmitDelegate<Func<Vector2>>(() => Vector2.Zero); cursor.Emit(OpCodes.Ret);
        });
        try
        {
            FontAssets.MouseText = asset; main.mouseNPCType = -1;
            Terraria.Main.mouseItem = new Item(); Terraria.Main.HoverItem = new Item();
            Terraria.Main.screenWidth = 320; Terraria.Main.screenHeight = 240;
            string text = (string)VideoUiMethod("Wrap").Invoke(null, new object[] {
                "Истощение предмета", "До конца: 17 с. Общий таймер сгенерированных действий перемещения; остальные действия не меняются.",
                320, 240, measure })!;
            MethodInfo inner = typeof(Terraria.Main).GetMethod("MouseTextInner", TestInstance)!;
            foreach (int x in new[] { 0, 319 })
            foreach (int y in new[] { 0, 239 })
            {
                cache.SetValue(main, Activator.CreateInstance(cache.FieldType));
                Terraria.Main.mouseX = x; Terraria.Main.mouseY = y; paints.Clear();
                main.MouseText(text, "");
                inner.Invoke(main, new[] { cache.GetValue(main) });
                Equal(1, paints.Count, "whole cursorText has one final native text paint");
                Equal(text, paints[0].Text, "native consumer receives complete wrapped block");
                Vector2 end = paints[0].Position + measure(paints[0].Text);
                Equal(true, paints[0].Position.X >= 0 && paints[0].Position.Y >= 0
                    && end.X <= 320 && end.Y <= 240, "native clamp contains whole block at each screen corner");
            }
        }
        finally
        {
            FontAssets.MouseText = oldFont; cache.SetValue(main, oldCache); main.mouseNPCType = oldNpc;
            Terraria.Main.screenWidth = oldWidth; Terraria.Main.screenHeight = oldHeight;
            Terraria.Main.mouseX = oldX; Terraria.Main.mouseY = oldY;
            Terraria.Main.mouseItem = oldItem; Terraria.Main.HoverItem = oldHover;
        }
    }

    public static void VFUI14CapturedCrystalUsesMultiplierNotFiveFlatMana()
    {
        using var peers = new ReviewPeers();
        WithPlayer((player, _) => {
            PrepareMobilityConsumptionPlayer(player);
            var crystal = VideoUiFixture("g_9ea7b3af556e6125"); peers.Register(crystal);
            var host = AttachItem(new GeneratedItem(), new Item { type = ItemID.Wood, stack = 1 }, crystal);
            Equal(.05f, host.Data.Accessory.ManaCostReduction, "captured reduction is 0.05 coefficient, not 5 mana");
            Equal(40, host.Data.Accessory.MaxMana, "captured maximum mana contribution");
            string before = VideoUiSnapshot(host.Data);
            player.manaCost = 1f; player.statManaMax2 = 200;
            host.UpdateAccessory(player, false);
            Equal(.95f, player.manaCost, "actual equipment subtracts five percentage points from native manaCost");
            Equal(240, player.statManaMax2, "actual maximum mana contribution applied");
            int[] bases = { 1, 5, 10, 20, 100 }, costs = { 0, 4, 9, 19, 95 };
            for (int i = 0; i < bases.Length; i++)
                Equal(costs[i], player.GetManaCost(new Item { type = ItemID.Wood, mana = bases[i] }), "native GetManaCost truncation base=" + bases[i]);
            player.manaCost = .8f; host.UpdateAccessory(player, false);
            Equal(.75f, player.manaCost, "generated reduction is additive to preexisting native coefficient");
            Equal(15, player.GetManaCost(new Item { type = ItemID.Wood, mana = 20 }), "native cost after combined modifier");
            player.manaCost = .12f; host.UpdateAccessory(player, false);
            Equal(.1f, player.manaCost, "existing generated equipment floor is coefficient 0.1, not minimum one mana");
            Equal(0, player.GetManaCost(new Item { type = ItemID.Wood, mana = 1 }), "native integer truncation can still produce zero cost");
            // Exercise the actual inventory tooltip consumer, not just the
            // localization templates. The saved +0.05 reduction must render -5%.
            typeof(ModType).GetProperty("Mod", TestInstance)!.SetValue(host, new TooltipProbeMod());
            WithForgePresentationLanguages(locale => {
                var lines = new List<TooltipLine>();
                host.ModifyTooltips(lines);
                var manaLines = lines.Where(row => row.Name.StartsWith("InfiniEquipmentManaCost", StringComparison.Ordinal)).ToArray();
                Equal(true,manaLines.Length > 0,locale + " actual equipment tooltip line emitted");
                string rendered = string.Join(" ",manaLines.Select(row => row.Text));
                Equal(true,rendered.Contains("-5%",StringComparison.Ordinal),locale + " actual tooltip shows negative five percent");
                Equal(false,rendered.Contains("+5%",StringComparison.Ordinal),locale + " positive reduction sign is never displayed");
                Equal(false,rendered.Contains("native minimum",StringComparison.OrdinalIgnoreCase)
                    || rendered.Contains("минимума движка",StringComparison.OrdinalIgnoreCase),
                    locale + " tooltip never invents a native minimum mana cost");
                Equal(true,rendered.Contains(locale == "ru-RU" ? "расход маны" : "mana cost",StringComparison.OrdinalIgnoreCase),
                    locale + " exact mana-cost label is used");
            });
            Equal(before, VideoUiSnapshot(host.Data), "audit does not rebalance saved crystal");
        });
    }

    public static void VFUI17DistinctBuffsAggregateAndExpireInEitherOrder()
    {
        foreach (bool reverse in new[] { false, true })
        WithPlayer((player, owner) => {
            PrepareMobilityConsumptionPlayer(player);
            var shortBuff = new GeneratedBuffSpec { DurationTicks = 60, MovementSpeed = .1f, LifeRegen = 1 };
            var longBuff = new GeneratedBuffSpec { DurationTicks = 120, MovementSpeed = .2f, ManaRegen = 10 };
            owner.ApplyGeneratedUtilityBuff(reverse ? longBuff : shortBuff);
            owner.ApplyGeneratedUtilityBuff(reverse ? shortBuff : longBuff);
            var snapshot = owner.CaptureGeneratedUtilityBuffPresentation();
            Equal(2, snapshot.Entries.Count, "distinct mechanical contributions are not merged");
            Equal(.1f + .2f, snapshot.Current.MovementSpeed, "sum independent of arrival order");
            player.moveSpeed = 0f; player.lifeRegen = player.manaRegenBonus = 0;
            owner.PostUpdateEquips();
            Equal(snapshot.Current.MovementSpeed, player.moveSpeed, "native player hook consumes canonical sum");
            Equal(1, player.lifeRegen, "actual half-HP/second contribution"); Equal(10, player.manaRegenBonus, "actual raw manaRegenBonus points");
            // Exact repeat refreshes existing effect, not additive duplicated stats.
            owner.ApplyGeneratedUtilityBuff(shortBuff);
            Equal(2, owner.CaptureGeneratedUtilityBuffPresentation().Entries.Count, "same-effect refresh is intentionally nonstacking");
            for (int tick = 0; tick < 60; tick++) Float32BuffTick.Invoke(owner, null);
            var after = owner.CaptureGeneratedUtilityBuffPresentation();
            Equal(1, after.Entries.Count, "short contribution expires independently");
            Equal(.2f, after.Current.MovementSpeed, "long contribution survives exactly");
        });
    }

    public static void VFUI18CapturedKegDoesNotRemoveInvisibilityBuff()
    {
        using var peers = new ReviewPeers();
        WithPlayer((player, owner) => {
            PrepareMobilityConsumptionPlayer(player);
            var data = VideoUiFixture("g_89cda498eb1f9925"); peers.Register(data);
            Equal(0, data.Gameplay.ExtraBuffs.Length, "captured keg adds no native buff slots");
            var host = AttachItem(new GeneratedItem(), new Item { type = ItemID.Wood, stack = 1 }, data);
            player.inventory[0] = host.Item; player.selectedItem = 0; player.altFunctionUse = 0;
            player.buffType[0] = BuffID.Invisibility; player.buffTime[0] = 600;
            int[] ids = (int[])player.buffType.Clone(), times = (int[])player.buffTime.Clone();
            Equal(true, host.CanUseItem(player), "captured keg primary admitted");
            host.UseItem(player);
            Equal(true, ids.SequenceEqual(player.buffType), "real keg use preserves native buff IDs");
            Equal(true, times.SequenceEqual(player.buffTime), "real keg use preserves invisibility time");
            Equal(600, owner.CaptureGeneratedUtilityBuffPresentation().Current.RemainingTicks, "actual generated keg contribution active independently");
            player.invis = true; player.itemAnimation = 30;
            Equal(false, player.ShouldNotDraw, "native invisibility does not hide player during any item animation");
            player.itemAnimation = 0;
            Equal(true, player.ShouldNotDraw, "native visual invisibility returns at idle without removing buff");
        });
    }

    public static void VFUI19CapturedActionsKeepAuthoredManaAndSeparateStackCosts()
    {
        // This headless locale scope owns mod text, not Terraria's content-loaded
        // buff cache. Keep the real Lang.GetBuffName reader with an initialized
        // cache; vanilla buff names are not what this cost-label check asserts.
        var buffCache = typeof(Lang).GetField("_buffNameCache", BindingFlags.Static | BindingFlags.NonPublic)!;
        object? oldBuffNames = buffCache.GetValue(null);
        try
        {
        buffCache.SetValue(null, Enumerable.Repeat(LocalizedText.Empty, BuffLoader.BuffCount).ToArray());
        WithForgePresentationLanguages(locale => {
            var parent = VideoUiFixture("g_4efc7c05f7b078e0");
            var child = VideoUiFixture("g_17d5099f992a900b");
            Equal(5, parent.Gameplay.ManaCost, "captured parent base cost"); Equal(10, child.Gameplay.ManaCost, "captured author intentionally doubled base cost");
            foreach (var data in new[] { parent, child })
            {
                var host = AttachItem(new GeneratedItem(), new Item { type = ItemID.Wood, stack = 1, mana = 77 }, data);
                typeof(ModType).GetProperty("Mod", TestInstance)!.SetValue(host, new TooltipProbeMod());
                string before = VideoUiSnapshot(host.Data);
                foreach (string input in new[] { RuntimeInputKind.PrimaryUse, RuntimeInputKind.AlternateUse })
                {
                    var binding = host.Data.RuntimeProgram.BindingForInput(input)!;
                    typeof(GeneratedItem).GetMethod("ApplyActiveUseProjection", BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(host, new object[] { binding });
                    Equal(data.Gameplay.ManaCost, host.Item.mana, "both native active inputs use same authored global mana cost");
                }
                var lines = new List<TooltipLine>(); host.ModifyTooltips(lines);
                foreach (string suffix in new[] { "Primary", "Alternate" })
                    Equal(true, lines.Single(row => row.Name == "InfiniInput" + suffix).Text.Contains((locale == "ru-RU" ? "базовая мана: " : "base mana: ") + data.Gameplay.ManaCost), "read-only tooltip labels authored BASE cost on each input");
                Equal(before, VideoUiSnapshot(host.Data), "no saved action reauthoring");
            }
        });
        }
        finally { buffCache.SetValue(null, oldBuffNames); }
    }

    public static void VFUI20StackIdentityUsesIdAndRecipeNotName()
    {
        // An empty mobility fixture has an effect binding with no executable
        // effect and cannot round-trip. Use an actually admitted definition.
        var data = VideoUiFixture("g_89cda498eb1f9925");
        data.Id = "stack-a"; data.RecipeKey = "recipe-a";
        var a = AttachItem(new GeneratedItem(), new Item { type = ItemID.Wood, stack = 1 }, data);
        GeneratedItem B(GeneratedItemData other) => AttachItem(new GeneratedItem(), new Item { type = ItemID.Wood, stack = 1 }, other);
        var same = GeneratedItemData.FromJson(data.ToNetworkJson())!;
        Equal(true, a.CanStack(B(same).Item), "independently decoded same generated identity can stack if native maxStack permits");
        same.Id = "stack-b";
        Equal(false, a.CanStack(B(same).Item), "same name but different generated ID cannot stack");
        same.Id = data.Id; same.RecipeKey = "recipe-b";
        Equal(false, a.CanStack(B(same).Item), "different recipe identity cannot stack");
        // Definition hash is NOT currently consulted here. This audit intentionally
        // does not turn a hypothetical same-ID conflicting payload into a proven
        // played-session defect or widen source ownership to GeneratedItem.cs.
    }
}

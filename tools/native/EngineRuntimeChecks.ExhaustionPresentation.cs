using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Common.UI;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Mono.Cecil;
using Mono.Cecil.Cil;
using MonoMod.Cil;
using MonoMod.RuntimeDetour;
using ReLogic.Content;
using Terraria;
using Terraria.GameContent;
using Terraria.Localization;
using Terraria.ModLoader;
using Terraria.UI;

internal static partial class EngineRuntimeChecks
{
    // All candidate APIs are reflected, so the unchanged production baseline can
    // compile these checks and fail on a missing behavior/API, not a C# symbol.
    private static MethodInfo PresentationExhaustionMethod(Type type, string name, bool isStatic = false)
        => type.GetMethod(name, (isStatic ? BindingFlags.Static : BindingFlags.Instance)
            | BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.DeclaredOnly)
            ?? throw new InvalidOperationException("exhaustion presentation missing native consumer: " + type.Name + "." + name);
    private static Type PresentationExhaustionView => typeof(GeneratedItem).Assembly.GetType(
        "InfiniCrafterLocal.Common.UI.GeneratedItemExhaustionStatusView")
        ?? throw new InvalidOperationException("exhaustion presentation must map each native item status, not one global buff");
    private static object PresentationExhaustionCapture(InfiniCraftPlayer owner)
        => PresentationExhaustionMethod(typeof(InfiniCraftPlayer), "CaptureGeneratedItemExhaustion").Invoke(owner, null)!;
    private static object[] PresentationExhaustionRows(InfiniCraftPlayer owner)
        => ((IEnumerable)PresentationExhaustionMethod(PresentationExhaustionView, "Build", true).Invoke(null,
            new[] { PresentationExhaustionCapture(owner), Language.ActiveCulture.CultureInfo })!).Cast<object>().ToArray();
    private static T PresentationExhaustionValue<T>(object row, string property)
        => (T)(row.GetType().GetProperty(property)?.GetValue(row)
            ?? throw new InvalidOperationException("missing exhaustion status property: " + property));
    private static void PresentationExhaustionPolicy(GeneratedBuffSpec spec, int ticks)
    {
        PropertyInfo property = typeof(GeneratedBuffSpec).GetProperty("ExhaustionTicks")
            ?? throw new InvalidOperationException("missing exhaustion policy on native generated buff");
        property.SetValue(spec, ticks);
    }
    private static bool PresentationExhaustionApply(InfiniCraftPlayer owner, GeneratedItemData data)
    {
        MethodInfo apply = typeof(InfiniCraftPlayer).GetMethods().SingleOrDefault(m =>
            m.Name == "ApplyGeneratedUtilityBuff" && m.GetParameters().Length == 4)
            ?? throw new InvalidOperationException("missing source-aware native generated-buff admission");
        return (bool)apply.Invoke(owner, new object?[] { data.Gameplay.GeneratedBuff, false, data, null })!;
    }
    private static GeneratedItemData PresentationExhaustionData(int index, int ticks)
    {
        var data = MobilityConsumptionFixture("", 0);
        data.Id = "exhaustion-presentation-" + index.ToString(CultureInfo.InvariantCulture);
        data.SourceMode = "test_fixture";
        data.Name = new[] { "Copper Lantern", "Moss Tonic", "Cloud Charm", "Amber Flask", "Stone Bell" }[index];
        data.Gameplay.GeneratedBuff = new GeneratedBuffSpec { DurationTicks = 600, JumpBoost = 1f };
        PresentationExhaustionPolicy(data.Gameplay.GeneratedBuff, ticks);
        return data;
    }

    public static void ExhaustionPresentationFiveDefinitionsKeepOwnNamesAndTicks()
    {
        _ = PresentationExhaustionView; // Expected baseline RED is behavioral, never a compile error.
        using var peers = new ReviewPeers();
        WithForgePresentationLanguages(locale => WithPlayer((player, owner) =>
        {
            PrepareMobilityConsumptionPlayer(player); MaterialClock(100);
            int[] ticks = { 61, 122, 183, 244, 305 };
            var data = ticks.Select((time, index) => PresentationExhaustionData(index, time)).ToArray();
            foreach (GeneratedItemData item in data) peers.Register(item);
            foreach (GeneratedItemData item in data) Equal(true, PresentationExhaustionApply(owner, item), "independent source accepted");
            // A second physical copy / independently hydrated definition cannot add a row.
            var copy = GeneratedItemData.FromJson(data[0].ToNetworkJson())!;
            Equal(false, PresentationExhaustionApply(owner, copy), "same-definition copy remains blocked");
            object[] rows = PresentationExhaustionRows(owner);
            Equal(5, rows.Length, locale + " five definitions must produce five independent statuses");
            for (int i = 0; i < data.Length; i++)
            {
                object row = rows.Single(r => PresentationExhaustionValue<string>(r, "ItemId") == data[i].Id);
                Equal(data[i].Name, PresentationExhaustionValue<string>(row, "ItemName"), "each status retains its own plain name");
                Equal(GeneratedItemRegistryService.DefinitionIdentity(data[i]), PresentationExhaustionValue<string>(row, "DefinitionIdentity"), "existing exact definition owner");
                Equal(ticks[i], PresentationExhaustionValue<int>(row, "RemainingTicks"), "own exact countdown, never maximum or sum");
                Equal("InfiniCrafterLocal/Assets/Exhaustion", PresentationExhaustionValue<string>(row, "IconPath"), "approved custom icon, not TextureAssets.Buff");
                Equal(true, PresentationExhaustionValue<string>(row, "Label").Contains(data[i].Name), "own hover name");
                string tip = PresentationExhaustionValue<string>(row, "Tooltip");
                Equal(true, tip.Contains(((ticks[i] + 59) / 60).ToString(Language.ActiveCulture.CultureInfo))
                    && !tip.Contains("ticks") && !tip.Contains("тиков") && !tip.Contains("Mods.InfiniCrafterLocal."), "localized own seconds; exact ticks stay in row");
                Equal(true, tip.Length < 100, "live fatigue feedback stays a short countdown, not a policy manual");
            }
            string[] before = rows.Select(r => PresentationExhaustionValue<string>(r, "Tooltip")).ToArray();
            Equal(true, before.SequenceEqual(PresentationExhaustionRows(owner).Select(r => PresentationExhaustionValue<string>(r, "Tooltip"))), "reading presentation cannot advance timers");
            // Status names are untrusted prose; formatting must not rewrite the owner record.
            object capture = PresentationExhaustionCapture(owner);
            Type status = capture.GetType().GetInterfaces().Concat(new[] { capture.GetType() })
                .First(t => t.IsGenericType && t.GetGenericTypeDefinition() == typeof(IReadOnlyList<>)).GetGenericArguments()[0];
            string hostile = "[i:1]\n" + new string('x', 200) + "\u0001";
            Array hostileRows = Array.CreateInstance(status, 1);
            hostileRows.SetValue(Activator.CreateInstance(status, data[0].Id, GeneratedItemRegistryService.DefinitionIdentity(data[0]), hostile, 61), 0);
            object safe = ((IEnumerable)PresentationExhaustionMethod(PresentationExhaustionView, "Build", true).Invoke(null,
                new object[] { hostileRows, Language.ActiveCulture.CultureInfo })!).Cast<object>().Single();
            string name = PresentationExhaustionValue<string>(safe, "ItemName");
            Equal(true, name.Length <= 192 && !name.Contains('[') && !name.Contains(']') && !name.Any(char.IsControl), "bounded literal name, no chat markup/control injection");
            Equal(hostile, (string)status.GetProperty("ItemName")!.GetValue(hostileRows.GetValue(0))!, "UI never rewrites source name");
            string supplementary = string.Concat(Enumerable.Repeat("🜁", 97));
            hostileRows.SetValue(Activator.CreateInstance(status, data[0].Id, GeneratedItemRegistryService.DefinitionIdentity(data[0]), supplementary, 61), 0);
            object unicode = ((IEnumerable)PresentationExhaustionMethod(PresentationExhaustionView, "Build", true).Invoke(null,
                new object[] { hostileRows, Language.ActiveCulture.CultureInfo })!).Cast<object>().Single();
            Equal(string.Concat(Enumerable.Repeat("🜁", 96)), PresentationExhaustionValue<string>(unicode, "ItemName"), "name bound counts Unicode scalars, not half-surrogates");
        }));
    }

    public static void ExhaustionPresentationTooltipsAreExactLocalizedAndDefinitionScoped()
    {
        using var peers = new ReviewPeers();
        WithForgePresentationLanguages(locale => WithPlayer((player, owner) =>
        {
            PrepareMobilityConsumptionPlayer(player); MaterialClock(100);
            bool menu = Terraria.Main.gameMenu, dedicated = Terraria.Main.dedServ;
            Terraria.Main.gameMenu = false; Terraria.Main.dedServ = false;
            try
            {
                var a = PresentationExhaustionData(0, 61); var b = PresentationExhaustionData(1, 122);
                peers.Register(a); peers.Register(b);
                Equal(true, PresentationExhaustionApply(owner, a), "A starts its own timer");
                List<TooltipLine> Lines(GeneratedItemData data)
                {
                    var host = AttachItem(new GeneratedItem(), new Item { type = 9, stack = 3, mana = 77 }, data);
                    typeof(ModType).GetProperty("Mod", TestInstance)!.SetValue(host, new TooltipProbeMod());
                    string before = data.ToNetworkJson();
                    var lines = new List<TooltipLine>(); host.ModifyTooltips(lines);
                    Equal(before, data.ToNetworkJson(), "tooltip does not normalize data or invent policy");
                    Equal(3, host.Item.stack, "tooltip leaves stack untouched"); Equal(77, host.Item.mana, "tooltip leaves native mana untouched");
                    Equal(true, lines.Count <= 64 && lines.All(l => !l.Text.Contains("Mods.InfiniCrafterLocal.")), "bounded localized runtime facts");
                    return lines;
                }
                string Line(List<TooltipLine> lines, string name) => lines.SingleOrDefault(l => l.Name == name)?.Text ?? "";
                string Time(int ticks)
                {
                    decimal seconds = ticks / 60m;
                    return Language.GetTextValue("Mods.InfiniCrafterLocal.RuntimeTooltip.Time",
                        (decimal.Round(seconds, 3) == seconds ? "" : "≈")
                        + seconds.ToString("0.###", Language.ActiveCulture.CultureInfo));
                }
                var aLines = Lines(a); var bLines = Lines(b);
                // Data remains plain owner state; a tooltip cannot use authored name,
                // category or mana as a lockout route or change other effect owners.
                var vanilla = (TooltipLine)Activator.CreateInstance(typeof(TooltipLine), TestInstance, null,
                    new object[] { "Terraria", "Damage", "native damage control" }, null)!;
                var nativeHost = AttachItem(new GeneratedItem(), new Item { type = 9, stack = 3, mana = 77 }, a);
                typeof(ModType).GetProperty("Mod", TestInstance)!.SetValue(nativeHost, new TooltipProbeMod());
                var nativeLines = new List<TooltipLine> { vanilla }; nativeHost.ModifyTooltips(nativeLines);
                Equal(true, ReferenceEquals(vanilla, nativeLines[0]) && vanilla.Text == "native damage control", "exhaustion never replaces native hit feedback");
                Equal(Language.GetTextValue("Mods.InfiniCrafterLocal.RuntimeTooltip.ExhaustionRemaining", Time(61)),
                    Line(aLines, "InfiniExhaustionRemaining"), locale + " exact localized current timer and block meaning");
                Equal("", Line(bLines, "InfiniExhaustionRemaining"), "A exhaustion must not advertise B as blocked");
                Equal(Language.GetTextValue("Mods.InfiniCrafterLocal.RuntimeTooltip.ExhaustionDeclared",
                    Language.GetTextValue("Mods.InfiniCrafterLocal.RuntimeTooltip.InputPrimary"), Time(122)),
                    Line(bLines, "InfiniExhaustionPrimary"), "B own declared policy, independent of A countdown");
                // Same Id with a different real definition hash is not the exhausted item.
                var changed = GeneratedItemData.FromJson(a.ToNetworkJson())!;
                changed.Gameplay.GeneratedBuff!.JumpBoost = 2f;
                Equal("", Line(Lines(changed), "InfiniExhaustionRemaining"), "exact definition hash prevents same-Id false block");
                // Named-group and held-group source selection, not legacy default gameplay.
                b.RuntimeProgram.EffectGroups = new[] { new RuntimeItemEffectGroupSpec { Id = "selected", GeneratedBuff = new GeneratedBuffSpec { DurationTicks = 600, JumpBoost = 2f } } };
                PresentationExhaustionPolicy(b.RuntimeProgram.EffectGroups[0].GeneratedBuff!, 183);
                b.RuntimeProgram.Bindings[0].UsePolicy.Action.EffectGroupId = "selected";
                b.RuntimeProgram.HeldEffectGroupId = "selected";
                var selected = Lines(b);
                Equal(true, Line(selected, "InfiniExhaustionPrimary").Contains(Time(183)) && !Line(selected, "InfiniExhaustionPrimary").Contains(Time(122)), "exact named group, not default policy");
                Equal(true, Line(selected, "InfiniExhaustionHold").Contains(Time(183)), "actual held generated group is disclosed");
                PresentationExhaustionPolicy(b.RuntimeProgram.EffectGroups[0].GeneratedBuff!, 0);
                Equal(false, Lines(b).Any(l => l.Name.StartsWith("InfiniExhaustion")), "zero policy invents neither lockout nor countdown");
                b = PresentationExhaustionData(1, 122); b.Gameplay.GeneratedBuff = new GeneratedBuffSpec { DurationTicks = 600, JumpBoost = 1f };
                Equal(false, Lines(b).Any(l => l.Name.StartsWith("InfiniExhaustion")), "historical absent policy stays absent");
            }
            finally { Terraria.Main.gameMenu = menu; Terraria.Main.dedServ = dedicated; }
        }));
    }

    // Replace only final content/font/draw boundaries in the REAL UI consumer.
    // This is a CPU observer, not fake UI output or a GraphicsDevice/game run.
    private static void PresentationExhaustionStoreCall(ILContext il, ILCursor cursor, MethodReference call, Action<VariableDefinition[]> observe)
    {
        var types = (call.HasThis ? new[] { call.DeclaringType } : Array.Empty<TypeReference>())
            .Concat(call.Parameters.Select(p => p.ParameterType)).ToArray();
        var locals = types.Select(t => new VariableDefinition(t)).ToArray();
        foreach (var local in locals) il.Body.Variables.Add(local);
        cursor.Remove();
        for (int i = locals.Length - 1; i >= 0; i--) cursor.Emit(OpCodes.Stloc, locals[i]);
        observe(locals);
        if (call.ReturnType.FullName == typeof(Vector2).FullName)
        {
            var result = new VariableDefinition(call.ReturnType); il.Body.Variables.Add(result);
            cursor.Emit(OpCodes.Ldloca, result); cursor.Emit(OpCodes.Initobj, call.ReturnType); cursor.Emit(OpCodes.Ldloc, result);
        }
        else if (call.ReturnType.FullName != "System.Void") throw new InvalidOperationException("unexpected UI boundary return " + call);
    }

    public static void ExhaustionPresentationReachesRealHudAndInventoryDrawBoundary()
    {
        Type ui = typeof(GeneratedUtilityBuffUISystem);
        MethodInfo load = PresentationExhaustionMethod(ui, "Load"), draw = PresentationExhaustionMethod(ui, "DrawStatuses", true);
        MethodInfo drawStatus = PresentationExhaustionMethod(ui, "DrawStatus", true);
        FieldInfo icon = ui.GetField("_exhaustionIcon", BindingFlags.Static | BindingFlags.NonPublic)
            ?? throw new InvalidOperationException("missing one shared exhaustion texture asset owner");
        using var state = new NativeActorState(); using var peers = new ReviewPeers();
        var nativeAsset = CpuTextureAsset(CpuTexture(32, 32)); var approvedAsset = CpuTextureAsset(CpuTexture(32, 32));
        object? oldIcon = icon.GetValue(null);
        var oldBuffs = TextureAssets.Buff; var oldBatch = Terraria.Main.spriteBatch;
        bool oldMenu = Terraria.Main.gameMenu, oldInventory = Terraria.Main.playerInventory, oldHide = Terraria.Main.hideUI;
        bool oldOptions = Terraria.Main.ingameOptionsWindow, oldFancy = Terraria.Main.inFancyUI, oldMap = Terraria.Main.mapFullscreen;
        int oldPage = Terraria.Main.EquipPage, oldWidth = Terraria.Main.screenWidth, oldHeight = Terraria.Main.screenHeight, oldMapStyle = Terraria.Main.mapStyle;
        int oldMouseX = Terraria.Main.mouseX, oldMouseY = Terraria.Main.mouseY;
        string oldHover = Terraria.Main.hoverItemName; Item oldHoverItem = Terraria.Main.HoverItem;
        FieldInfo offset = typeof(Terraria.Main).GetField("mH", BindingFlags.Static | BindingFlags.NonPublic)!;
        object? oldOffset = offset.GetValue(null);
        var drawn = new List<(Texture2D Texture, Vector2 Point)>(); var durations = new List<string>();
        var hovers = new List<(string Name, string Text)>(); string requested = "";
        using var loadBoundary = new ILHook(load, il =>
        {
            var cursor = new ILCursor(il); int hits = 0;
            while (cursor.TryGotoNext(i => i.Operand is MethodReference m && m.DeclaringType.FullName == typeof(ModContent).FullName && m.Name == "Request"))
            {
                cursor.Remove(); cursor.EmitDelegate<Func<string, AssetRequestMode, Asset<Texture2D>>>((path, mode) => { requested = path; return approvedAsset; }); hits++;
            }
            Equal(1, hits, "one real ModContent.Request loading boundary");
        });
        using var paintBoundary = new ILHook(drawStatus, il =>
        {
            il.Body.InitLocals = true;
            var cursor = new ILCursor(il); int paints = 0, times = 0, tips = 0;
            while (cursor.TryGotoNext(i => i.Operand is MethodReference m &&
                ((m.DeclaringType.FullName == typeof(SpriteBatch).FullName && m.Name == "Draw")
                || (m.DeclaringType.FullName == typeof(Utils).FullName && m.Name == "DrawBorderString")
                || (m.DeclaringType.FullName == typeof(Terraria.Main).FullName && m.Name == "MouseText"))))
            {
                var call = (MethodReference)cursor.Next!.Operand;
                PresentationExhaustionStoreCall(il, cursor, call, locals =>
                {
                    if (call.Name == "Draw")
                    {
                        cursor.Emit(OpCodes.Ldloc, locals[1]); cursor.Emit(OpCodes.Ldloc, locals[2]);
                        cursor.EmitDelegate<Action<Texture2D, Vector2>>((texture, point) => drawn.Add((texture, point))); paints++;
                    }
                    else if (call.Name == "DrawBorderString")
                    {
                        cursor.Emit(OpCodes.Ldloc, locals[1]); cursor.EmitDelegate<Action<string>>(text => durations.Add(text)); times++;
                    }
                    else
                    {
                        cursor.Emit(OpCodes.Ldloc, locals[1]); cursor.Emit(OpCodes.Ldloc, locals[2]);
                        cursor.EmitDelegate<Action<string, string>>((name, text) => hovers.Add((name, text))); tips++;
                    }
                });
            }
            Equal(1, paints, "one native SpriteBatch.Draw boundary"); Equal(1, times, "one native duration boundary"); Equal(1, tips, "one native MouseText boundary");
        });
        try
        {
            Terraria.Main.dedServ = false;
            load.Invoke(new GeneratedUtilityBuffUISystem(), null);
            Equal("InfiniCrafterLocal/Assets/Exhaustion", requested, "actual shared texture request selects approved asset");
            TextureAssets.Buff = Enumerable.Repeat(nativeAsset, Terraria.ID.BuffID.Count).ToArray();
            Terraria.Main.spriteBatch = null!; // Every final paint/font boundary is intercepted above.
            Terraria.Main.gameMenu = Terraria.Main.hideUI = Terraria.Main.ingameOptionsWindow = Terraria.Main.inFancyUI = Terraria.Main.mapFullscreen = false;
            Equal(false, Terraria.GameInput.PlayerInput.IgnoreMouseInterface, "CPU observer starts on native mouse input route");
            Terraria.Main.screenWidth = 1280; Terraria.Main.screenHeight = 800; Terraria.Main.mapStyle = 0; offset.SetValue(null, 13);
            WithForgePresentationLanguages(locale => WithPlayer((player, owner) =>
            {
                PrepareMobilityConsumptionPlayer(player); MaterialClock(100); Terraria.Main.dedServ = false;
                // The native mouse UI intentionally ignores hover during item animation.
                // Observe the ordinary idle HUD route, without detouring that guard.
                player.itemAnimation = 0;
                Equal(false, Terraria.GameInput.PlayerInput.IgnoreMouseInterface, "idle native mouse route");
                var items = new[] { 61, 122, 183, 244, 305 }.Select((t, i) => PresentationExhaustionData(i, t)).ToArray();
                foreach (var item in items)
                {
                    item.Gameplay.GeneratedBuff!.DurationTicks = 3;
                    peers.Register(item); Equal(true, PresentationExhaustionApply(owner, item), "native UI fixture admits definition");
                }
                // All same-effect definitions still have one existing jump row, then five exhaustion rows.
                player.buffType[0] = Terraria.ID.BuffID.Ironskin;
                int[] slots = (int[])player.buffType.Clone();
                var layers = new List<GameInterfaceLayer> { new LegacyGameInterfaceLayer("Vanilla: Inventory", () => true, InterfaceScaleType.UI) };
                new GeneratedUtilityBuffUISystem().ModifyInterfaceLayers(layers);
                Equal("InfiniCrafterLocal: Generated Utility Status", layers[1].Name, "existing native interface-layer placement preserved");
                foreach (bool inventory in new[] { false, true })
                {
                    Terraria.Main.playerInventory = inventory; Terraria.Main.EquipPage = 2;
                    Terraria.Main.mouseX = Terraria.Main.mouseY = -100;
                    drawn.Clear(); durations.Clear(); hovers.Clear();
                    draw.Invoke(null, null);
                    Equal(6, drawn.Count, "existing utility plus five independent exhaustion icons");
                    Equal(true, ReferenceEquals(nativeAsset.Value, drawn[0].Texture), "original utility keeps TextureAssets.Buff icon first");
                    Equal(true, drawn.Skip(1).All(d => ReferenceEquals(approvedAsset.Value, d.Texture)), "every definition draws same custom PNG texture");
                    Equal(6, durations.Count, "each row reaches the existing native duration consumer");
                    for (int i = 0; i < items.Length; i++)
                    {
                        Point position = GeneratedUtilityBuffStatusView.IconPosition(i + 2, inventory, 1280, 800, inventory ? 13 : 0, 0);
                        Equal(position.ToVector2(), drawn[i + 1].Point, "appends without changing native or utility grid positions");
                        Equal(Lang.LocalizedDuration(new TimeSpan(0, 0, new[] { 61, 122, 183, 244, 305 }[i] / 60), true, false), durations[i + 1], "each actual drawn countdown is its own");
                        Terraria.Main.mouseX = position.X + 1; Terraria.Main.mouseY = position.Y + 1;
                        hovers.Clear(); draw.Invoke(null, null);
                        Equal(1, hovers.Count, "one actual hover target");
                        Equal(true, hovers[0].Name.Contains(items[i].Name) && hovers[0].Name.Contains(((new[] { 61, 122, 183, 244, 305 }[i] + 59) / 60).ToString(Language.ActiveCulture.CultureInfo)), "actual native cursorText gets this definition name and own whole-second countdown");
                        Equal("", hovers[0].Text, "whole block uses native cursorText measurement, not title-excluding buffTooltip clamp");
                    }
                }
                Equal(true, slots.SequenceEqual(player.buffType), "presentation never creates gameplay buff slots");
                Terraria.Main.playerInventory = true; Terraria.Main.EquipPage = 0; drawn.Clear(); draw.Invoke(null, null);
                Equal(0, drawn.Count, "no icons on other inventory pages");
                Terraria.Main.playerInventory = false; Terraria.Main.hideUI = true; draw.Invoke(null, null);
                Equal(0, drawn.Count, "native hide-UI gate preserved"); Terraria.Main.hideUI = false;
                // No positive generated utility contribution required: icon stays until its own timer ends.
                // Expire only the three-tick generated buff through its native owner;
                // even a tick-based exhaustion implementation still has >=58 left.
                for (int tick = 0; tick < 3; tick++)
                    PresentationExhaustionMethod(typeof(InfiniCraftPlayer), "TickGeneratedUtilityBuff").Invoke(owner, null);
                drawn.Clear(); draw.Invoke(null, null);
                Equal(5, drawn.Count, "exhaustion UI does not depend on HasBuff/global utility status");
                string[] afterExpiry = PresentationExhaustionRows(owner).Select(r => PresentationExhaustionValue<int>(r, "RemainingTicks").ToString()).ToArray();
                draw.Invoke(null, null);
                Equal(true, afterExpiry.SequenceEqual(PresentationExhaustionRows(owner).Select(r => PresentationExhaustionValue<int>(r, "RemainingTicks").ToString())), "actual HUD consumer cannot advance exhaustion");
                MaterialClock(1000);
                drawn.Clear(); draw.Invoke(null, null);
                Equal(0, drawn.Count, "expired item timers disappear without a global status leftover");
                // Mobility-only recall creates no generated buff/exhaustion, but must
                // still reach the exact same HUD + inventory duration/hover boundary.
                Equal(true, owner.TryReserveGeneratedMobilityCooldown(121), "mobility-only cooldown starts");
                foreach (bool inventory in new[] { false, true })
                {
                    Terraria.Main.playerInventory = inventory; Terraria.Main.EquipPage = 2;
                    Terraria.Main.mouseX = Terraria.Main.mouseY = -100;
                    drawn.Clear(); durations.Clear(); hovers.Clear(); draw.Invoke(null, null);
                    Equal(1, drawn.Count, "mobility-only timer has its own HUD/inventory moodle");
                    Equal(true, ReferenceEquals(nativeAsset.Value, drawn[0].Texture), "mobility borrows native texture, never Exhaustion PNG");
                    Equal(1, durations.Count, "mobility reaches real countdown draw");
                    Point point = GeneratedUtilityBuffStatusView.IconPosition(1, inventory, 1280, 800, inventory ? 13 : 0, 0);
                    Equal(point.ToVector2(), drawn[0].Point, "mobility appends after native buff slots");
                    Terraria.Main.mouseX = point.X + 1; Terraria.Main.mouseY = point.Y + 1;
                    draw.Invoke(null, null);
                    Equal(1, hovers.Count, "mobility reaches native hover boundary");
                    Equal(true, hovers[0].Name.StartsWith(Language.GetTextValue("Mods.InfiniCrafterLocal.RuntimeTooltip.MobilityCooldownStatus") + "\n"), "mobility label is distinct from fatigue in whole native text block");
                    Equal(true, hovers[0].Name.Contains(locale == "en-US" ? "3 s" : "3 с")
                        && !hovers[0].Name.Contains("121"), "mobility hover uses stable whole seconds");
                    Equal("", hovers[0].Text, "mobility body joins whole native cursorText clamp");
                    Equal(121, owner.GeneratedMobilityCooldownTicks, "HUD draw leaves mobility timer untouched");
                }
                Equal(false, owner.TryReserveGeneratedMobilityCooldown(1800), "failed repeat does not restart HUD timer");
                Equal(121, owner.GeneratedMobilityCooldownTicks, "failed repeat cannot extend countdown");
                Equal(true, slots.SequenceEqual(player.buffType), "mobility moodle never installs ChaosState or other buffs");
            }));
        }
        finally
        {
            icon.SetValue(null, oldIcon); TextureAssets.Buff = oldBuffs; Terraria.Main.spriteBatch = oldBatch;
            Terraria.Main.gameMenu = oldMenu; Terraria.Main.playerInventory = oldInventory; Terraria.Main.hideUI = oldHide;
            Terraria.Main.ingameOptionsWindow = oldOptions; Terraria.Main.inFancyUI = oldFancy; Terraria.Main.mapFullscreen = oldMap;
            Terraria.Main.EquipPage = oldPage; Terraria.Main.screenWidth = oldWidth; Terraria.Main.screenHeight = oldHeight; Terraria.Main.mapStyle = oldMapStyle;
            Terraria.Main.mouseX = oldMouseX; Terraria.Main.mouseY = oldMouseY; Terraria.Main.hoverItemName = oldHover; Terraria.Main.HoverItem = oldHoverItem;
            offset.SetValue(null, oldOffset);
        }
    }
}

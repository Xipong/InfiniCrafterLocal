using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Text.Json;
using System.Threading.Tasks;
using InfiniCrafterLocal.Common.Commands;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.Services;
using Terraria;
using Terraria.Localization;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    // Actual native HJSON filename parser and Language lookups. No fake fonts,
    // content registration, world, graphics device, provider or socket.
    private static void WithForgePresentationLanguages(Action<string> observe)
    {
        const BindingFlags instance = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
        string root = Environment.GetEnvironmentVariable("INFINI_FORGE_LOCALIZATION_DIR")
            ?? Path.Combine("ModSources", "InfiniCrafterLocal", "Localization");
        LanguageManager oldLanguage = LanguageManager.Instance;
        CultureInfo oldCulture = CultureInfo.CurrentCulture;
        try
        {
            foreach (string locale in new[] { "en-US", "ru-RU" })
            {
                var manager = (LanguageManager)Activator.CreateInstance(typeof(LanguageManager), nonPublic: true)!;
                typeof(LanguageManager).GetProperty("ActiveCulture")!.SetValue(manager, GameCulture.FromName(locale));
                LanguageManager.Instance = manager;
                CultureInfo.CurrentCulture = CultureInfo.GetCultureInfo(locale == "en-US" ? "ru-RU" : "en-US");
                string filename = locale + "_Mods.InfiniCrafterLocal.hjson";
                Equal(true, LocalizationLoader.TryGetCultureAndPrefixFromPath(filename, out _, out string? prefix), "forge native filename parser");
                Equal("Mods.InfiniCrafterLocal", prefix!, "forge native prefix, no duplicate Mods root");
                using var json = JsonDocument.Parse(Hjson.HjsonValue.Load(Path.Combine(root, filename)).ToString());
                var texts = (Dictionary<string, LocalizedText>)typeof(LanguageManager).GetField("_localizedTexts", instance)!.GetValue(manager)!;
                void Add(JsonElement element, string key)
                {
                    foreach (JsonProperty field in element.EnumerateObject())
                    {
                        string child = key + "." + field.Name;
                        if (field.Value.ValueKind == JsonValueKind.Object) Add(field.Value, child);
                        else if (field.Value.ValueKind == JsonValueKind.String)
                            texts.Add(child, (LocalizedText)Activator.CreateInstance(typeof(LocalizedText), instance, null,
                                new object[] { child, field.Value.GetString()! }, null)!);
                    }
                }
                Add(json.RootElement, prefix!);
                observe(locale);
            }
        }
        finally { LanguageManager.Instance = oldLanguage; CultureInfo.CurrentCulture = oldCulture; }
    }

    public static void ForgePresentationLocalizationUsesNativePrefix()
    {
        WithForgePresentationLanguages(locale =>
        {
            bool ru = locale == "ru-RU";
            string Text(string key, params object[] args) => args.Length == 0
                ? Language.GetText("Mods.InfiniCrafterLocal.StationUI." + key).Value
                : Language.GetTextValue("Mods.InfiniCrafterLocal.StationUI." + key, args);
            foreach (var pair in new[] {
                ("Title", ru ? "Кузня чудес" : "Wonder Forge"),
                ("Lane", ru ? "Горн {0}" : "Hearth {0}"),
                ("Craft", ru ? "Сковать" : "Forge"),
                ("Busy", ru ? "Ковка" : "Forging"),
                ("Retrieve", ru ? "Забрать" : "Retrieve"),
                ("Idle", ru ? "Два предмета — один сплав" : "Two items, one alloy"),
            }) Equal(pair.Item2, Text(pair.Item1), locale + " forge " + pair.Item1);
            Equal(ru ? "Горн 3" : "Hearth 3", Text("Lane", 3), locale + " real Language formatting");
            Equal(ru ? "Сердце кузни" : "Forge Heart", Language.GetTextValue("Mods.InfiniCrafterLocal.Items.InfiniCore.DisplayName"), locale + " core real root");
            Equal(ru ? "{0}: нужна твёрдая опора со стороны притяжения" : "{0}: requires solid support in the direction of gravity",
                Language.GetTextValue("Mods.InfiniCrafterLocal.RuntimeTooltip.Grounded"), locale + " grounded native support fact and placeholder");
            string tooltip = Language.GetTextValue("Mods.InfiniCrafterLocal.Items.InfiniCore.Tooltip");
            Equal(true, tooltip.Contains(ru ? "Кузню чудес" : "Wonder Forge") && tooltip.Contains(ru ? "материалы вернутся" : "ingredients are returned"), locale + " core controls and refund fact");
            string[] keys = { "Title", "Lane", "Craft", "Busy", "Retrieve", "Idle", "Ready", "NeedInputs", "Retry", "Waiting", "Countdown", "Host", "Committing",
                "FooterSingle", "FooterMultiple", "LaneBusy", "Item", "CoreOpened", "CommandDescription", "CommandUsage", "CommandBlocked", "CommandSingle", "CommandMultiple",
                "CommandPairs", "HearthsOpened", "LaneHost", "LaneFailed", "LaneRestored", "LaneResult", "Result" };
            foreach (string key in keys)
            {
                string text = Text(key);
                Equal(false, text.StartsWith("Mods."), locale + " missing key " + key);
                AssertForgeNoImplementationJargon(text, locale + "/" + key);
            }
            AssertForgeNoImplementationJargon(tooltip, locale + " core tooltip");
            var command = new MultiDevCraftCommand();
            Equal("multidevcraft", command.Command, "legacy command token preserved");
            Equal("/multidevcraft [2|3|off]", command.Usage, "legacy arguments preserved");
            Equal(Text("CommandDescription"), command.Description, locale + " command native description");
        });
    }

    private static void AssertForgeNoImplementationJargon(string text, string caseName)
    {
        // The literal /multidevcraft usage is retained for command compatibility.
        foreach (string term in new[] { "LLM", "llm_", "LocalGenerator", "127.0.0.1", "localhost", "MULTI-DEV", "Admin", "profile", "GUI", "durable", "backend" })
            Equal(false, text.Contains(term, StringComparison.OrdinalIgnoreCase), caseName + " visible jargon " + term);
    }

    public static void ForgePresentationCraftNoticesUseLocalizedText()
    {
        // Inspect compiled callsites, not regex source strings or a fake PostUpdate.
        using var module = Mono.Cecil.ModuleDefinition.ReadModule(typeof(InfiniCraftPlayer).Assembly.Location);
        var playerType = System.Linq.Enumerable.Single(module.Types, type => type.FullName == typeof(InfiniCraftPlayer).FullName);
        foreach (var pair in new[] {
            ("BeginCraft", "Started"), ("StartGenerationTask", "Attempt"),
            ("ScheduleEarlyRetry", "Recovery"), ("ScheduleGeneratorOfflineRetry", "Offline"),
            ("PostUpdate", "HostWorking"), ("PostUpdate", "HostDelayed"),
            ("PostUpdate", "CountdownNotice"), ("PostUpdate", "LateNotice"),
        })
        {
            var method = System.Linq.Enumerable.Single(playerType.Methods, method => method.Name == pair.Item1);
            Equal(true, System.Linq.Enumerable.Any(method.Body.Instructions, instruction => instruction.OpCode == Mono.Cecil.Cil.OpCodes.Ldstr && Equals(instruction.Operand, pair.Item2)), pair.Item1 + " exact notice key " + pair.Item2);
            Equal(true, System.Linq.Enumerable.Any(method.Body.Instructions, instruction => instruction.Operand is Mono.Cecil.MethodReference target && target.Name == "ForgePresentationText"), pair.Item1 + " native localization consumer");
        }
        WithForgePresentationLanguages(locale => {
            string prefix = "Mods.InfiniCrafterLocal.StationUI.";
            foreach (string key in new[] { "Started", "Attempt", "Recovery", "Offline", "HostWorking", "HostDelayed", "CountdownNotice", "LateNotice" })
            {
                var text = Language.GetText(prefix + key);
                Equal(false, text.Value.StartsWith("Mods."), locale + " craft notice resolved " + key);
                AssertForgeNoImplementationJargon(text.Value, locale + " craft notice " + key);
                string formatted = text.Format(7);
                if (key is "Attempt" or "Recovery" or "Offline" or "CountdownNotice")
                    Equal(true, formatted.Contains("7"), locale + " real notice numeric placeholder " + key);
            }
        });
    }

    public static void ForgePresentationLaneStatusPreservesTimersAndHostFacts()
    {
        const BindingFlags fields = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
        int oldNetMode = Terraria.Main.netMode;
        Terraria.Main.netMode = 0;
        try
        {
            WithForgePresentationLanguages(locale =>
            {
                bool ru = locale == "ru-RU";
                string Ready = ru ? "Готово к ковке" : "Ready to forge";
                string Need = ru ? "Нужны два предмета" : "Need two items";
                string Waiting = ru ? "Сплав ещё зреет" : "Alloy still forming";
                string Host = ru ? "Ждём хозяина мира" : "Awaiting world host";
                string Commit = ru ? "Завершаем ковку" : "Finishing the forge";
                string Countdown = ru ? "Ковка · 3 с" : "Forging · 3 s";
                var player = new InfiniCraftPlayer();
                void Set(string name, object? value) => typeof(InfiniCraftPlayer).GetField(name, fields)!.SetValue(player, value);
                for (int lane = 0; lane < 3; lane++) Equal(Need, player.CraftLaneStatus(lane), locale + " empty lane " + lane);
                Equal(ru ? "Горн 1" : "Hearth 1", player.CraftLaneLabel(0), locale + " first fallback label");
                Equal(ru ? "Горн 2" : "Hearth 2", player.CraftLaneLabel(1), locale + " extra fallback label");
                Equal(true, player.TrySetMultiDevWindowCount(3, syncServer: false), "open three local lanes without a socket");
                foreach (string name in new[] { "InputA", "InputB", "InputC", "InputD", "InputE", "InputF" })
                    Set(name, new Item { type = Terraria.ID.ItemID.Wood, stack = 1 });
                for (int lane = 0; lane < 3; lane++) Equal(Ready, player.CraftLaneStatus(lane), locale + " ready lane " + lane);
                Set("_request", new GeneratorClient.PreparedGenerationRequest());
                Set("_ticksLeft", 121);
                Equal(Countdown, player.CraftLaneStatus(0), locale + " ceil 121 native ticks");
                Equal(121, player.TicksLeft, "presentation does not advance timer");
                Set("_elapsedTicks", InfiniCraftPlayer.CraftDurationTicks);
                Equal(Waiting, player.CraftLaneStatus(0), locale + " timer complete but work pending");
                Set("_retryWaitTicks", 61); Set("_generationAttempt", 2);
                Equal(ru ? "Попытка 3 через 2 с" : "Attempt 3 in 2 s", player.CraftLaneStatus(0), locale + " next attempt and rounded retry delay");
                Equal(2, player.GenerationAttempt, "presentation does not retry");
                Set("_awaitingServerCommit", true);
                Equal(Host, player.CraftLaneStatus(0), locale + " host wait is not local model wait");
                Set("_awaitingServerCommit", false); Set("_retryWaitTicks", 0);
                Set("_task", Task.FromResult<GeneratedItemData?>(null));
                Equal(Commit, player.CraftLaneStatus(0), locale + " completed work awaiting commit");
                Set("_label", "Saved parent A + Saved parent B");
                Equal("Saved parent A + Saved parent B", player.CraftLaneLabel(0), "accepted parent names not rewritten");
                Type jobType = typeof(InfiniCraftPlayer).GetNestedType("MultiDevCraftJob", BindingFlags.NonPublic)!;
                var jobs = (Array)typeof(InfiniCraftPlayer).GetField("_multiDevJobs", fields)!.GetValue(player)!;
                for (int lane = 1; lane < 3; lane++)
                {
                    object job = Activator.CreateInstance(jobType, nonPublic: true)!;
                    void JobSet(string name, object? value) => jobType.GetField(name, fields)!.SetValue(job, value);
                    JobSet("ElapsedTicks", InfiniCraftPlayer.CraftDurationTicks - 121);
                    JobSet("Label", "Saved extra A + Saved extra B"); jobs.SetValue(job, lane - 1);
                    Equal(Countdown, player.CraftLaneStatus(lane), locale + " extra countdown " + lane);
                    Equal("Saved extra A + Saved extra B", player.CraftLaneLabel(lane), "extra parent names preserved");
                    JobSet("ElapsedTicks", InfiniCraftPlayer.CraftDurationTicks);
                    Equal(Waiting, player.CraftLaneStatus(lane), locale + " extra pending " + lane);
                    JobSet("AwaitingServerCommit", true);
                    Equal(Host, player.CraftLaneStatus(lane), locale + " extra host " + lane);
                    JobSet("AwaitingServerCommit", false); JobSet("Task", Task.FromResult<GeneratedItemData?>(null));
                    Equal(Commit, player.CraftLaneStatus(lane), locale + " extra commit " + lane);
                    Equal(InfiniCraftPlayer.CraftDurationTicks, (int)jobType.GetField("ElapsedTicks", fields)!.GetValue(job)!, "extra presentation does not advance clock");
                }
            });
        }
        finally { Terraria.Main.netMode = oldNetMode; }
    }
}

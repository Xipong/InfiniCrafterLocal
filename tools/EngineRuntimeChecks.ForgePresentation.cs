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
            Equal(ru ? "Таймер ковки · 3 с" : "Craft timer · 3 s", Text("Countdown", 3), "countdown is explicitly timer not model ETA");
            Equal(false, Text("Started").Contains(ru ? "до 240" : "up to 240"), "start notice cannot promise completion bound");
            foreach (string key in new[] { "TransferPending", "StationUnavailable", "LaneHidden", "Elapsed", "TimerDetail", "TimerNotProgress", "StartFailed", "InputPair", "Empty" })
                Equal(false, Text(key).StartsWith("Mods."), locale + " resolved QoL key " + key);
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

    public static void ForgeQolReadinessReportsEscrowNotMissingMaterials()
    {
        const BindingFlags fields = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
        int oldNetMode = Terraria.Main.netMode;
        Terraria.Main.netMode = 0;
        try
        {
            WithForgePresentationLanguages(locale =>
            {
                var player = new InfiniCraftPlayer();
                player.TrySetMultiDevWindowCount(3, syncServer: false);
                foreach (string name in new[] { "InputA", "InputB", "InputC", "InputD", "InputE", "InputF" })
                    typeof(InfiniCraftPlayer).GetField(name, fields)!.SetValue(player, new Item { type = Terraria.ID.ItemID.Wood, stack = 1 });
                typeof(InfiniCraftPlayer).GetField("_pendingStationEscrowOperationId", fields)!.SetValue(player, new string('a', 32));
                for (int lane = 0; lane < 3; lane++)
                {
                    Equal(false, player.CanStartStationCraftLane(lane), "pending transfer still blocks admission");
                    Equal(locale == "ru-RU" ? "Ждём подтверждения переноса" : "Awaiting item transfer confirmation",
                        player.CraftLaneStatus(lane), locale + " full inputs cannot be mislabeled missing " + lane);
                    Equal(1, player.StationInput(lane * 2).stack, "status preserves first material");
                    Equal(1, player.StationInput(lane * 2 + 1).stack, "status preserves second material");
                    Equal(false, player.TryStartCraftFromStation(lane), "blocked start keeps same admission");
                }
                typeof(InfiniCraftPlayer).GetField("_pendingStationEscrowOperationId", fields)!.SetValue(player, "");
                Equal(true, player.CanStartStationCraftLane(0), "cleared transfer admits full pair");
                player.InputB.TurnToAir();
                Equal(false, player.CanStartStationCraftLane(0), "missing second unit still refuses");
                Equal(locale == "ru-RU" ? "Нужны два предмета" : "Need two items", player.StationCraftReadinessText(0), "real missing inputs");
                player.InputB = new Item { type = Terraria.ID.ItemID.Wood, stack = 1 };
                typeof(InfiniCraftPlayer).GetField("_request", fields)!.SetValue(player, new GeneratorClient.PreparedGenerationRequest());
                Equal(false, player.CanStartStationCraftLane(0), "pending lane still refuses");
                Equal(true, player.CanStartStationCraftLane(1), "other full lane remains independent");
                Equal(locale == "ru-RU" ? "Этот горн занят" : "This hearth is busy", player.StationCraftReadinessText(0), "busy canonical reason");
                foreach (int invalid in new[] { -1, 3, int.MaxValue })
                    Equal(false, player.CanStartStationCraftLane(invalid), "invalid lane remains refused without indexing inputs");
                typeof(InfiniCraftPlayer).GetField("_stationEscrowUsesRemoteAuthority", fields)!.SetValue(player, true);
                Equal(locale == "ru-RU" ? "Нет доступа к материалам станции" : "Station authority unavailable", player.StationCraftReadinessText(1), "unavailable is not missing inputs");
                Equal(false, player.CanStartStationCraftLane(1), "remote material cannot admit locally");
                Equal(1, player.InputC.stack, "unavailable material mirror unchanged");
                for (int lane = 1; lane < 3; lane++)
                {
                    Equal(1, player.StationInput(lane * 2 + 1).stack, "other material unchanged");
                }
            });
        }
        finally { Terraria.Main.netMode = oldNetMode; }
    }

    public static void ForgeQolAuthorityObservationCannotParkOrRestoreClaims()
    {
        const BindingFlags fields = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
        FieldInfo scopeField = typeof(InfiniCrafterLocal.Common.Systems.GeneratedStationEscrowStateSystem).GetField("_authorityScope", BindingFlags.Static | BindingFlags.NonPublic)!;
        string oldScope = (string)scopeField.GetValue(null)!;
        int oldNetMode = Terraria.Main.netMode; Terraria.Main.netMode = Terraria.ID.NetmodeID.MultiplayerClient;
        try
        {
            WithForgePresentationLanguages(_ =>
            {
                var player = new InfiniCraftPlayer();
                void Set(string name, object? value) => typeof(InfiniCraftPlayer).GetField(name, fields)!.SetValue(player, value);
                string scope = new string('a', 32);
                scopeField.SetValue(null, "");
                Equal(InfiniCraftPlayer.StationCraftReadiness.StationUnavailable, player.GetStationCraftReadiness(0), "missing host scope is unavailable");
                scopeField.SetValue(null, scope);
                player.InputA = new Item { type = Terraria.ID.ItemID.Wood, stack = 1 };
                player.InputB = new Item { type = Terraria.ID.ItemID.StoneBlock, stack = 1 };
                Equal(InfiniCraftPlayer.StationCraftReadiness.Ready, player.GetStationCraftReadiness(0), "fresh host scope admits existing pair");
                Set("_stationEscrowUsesRemoteAuthority", true); Set("_stationEscrowOriginScope", new string('b', 32));
                var request = new GeneratorClient.PreparedGenerationRequest(); Set("_request", request);
                Item mirror = player.InputA;
                _ = player.CraftLaneDetails(0);
                Equal(InfiniCraftPlayer.StationCraftReadiness.StationUnavailable, player.GetStationCraftReadiness(0), "foreign active mirror cannot be current material");
                Equal(true, ReferenceEquals(mirror, player.InputA), "observe foreign origin never parks material");
                Equal(false, request.CancellationToken.IsCancellationRequested, "observe foreign origin never cancels worker");
                Equal(new string('b', 32), (string)typeof(InfiniCraftPlayer).GetField("_stationEscrowOriginScope", fields)!.GetValue(player)!, "origin cannot be rewritten by status");
                Set("_request", null); Set("_stationEscrowUsesRemoteAuthority", false);
                var claim = new Terraria.ModLoader.IO.TagCompound { ["infiniStationEscrowOriginScopeV1"] = scope };
                Set("_readOnlyRemoteStationClaim", claim);
                Equal(InfiniCraftPlayer.StationCraftReadiness.StationUnavailable, player.GetStationCraftReadiness(0), "matching dormant claim and fresh material remain ambiguous");
                Set("_readOnlyRemoteStationClaim", new Terraria.ModLoader.IO.TagCompound { ["infiniStationEscrowOriginScopeV1"] = new string('c', 32) });
                Equal(InfiniCraftPlayer.StationCraftReadiness.Ready, player.GetStationCraftReadiness(0), "unrelated dormant claim does not block fresh material");
                Equal(true, player.CanStartStationCraftLane(0), "canonical admission keeps foreign dormant positive control");
            });
        }
        finally { Terraria.Main.netMode = oldNetMode; scopeField.SetValue(null, oldScope); }
    }

    public static void ForgeQolPanelFitsWhenViewportCanContainIt()
    {
        foreach (var viewport in new[] { (1280, 480), (800, 480), (400, 720), (430, 410), (454, 434), (1920, 1080) })
        {
            var bounds = InfiniCrafterLocal.Common.UI.InfiniCraftStationUISystem.StationPanelBounds(viewport.Item1, viewport.Item2, 3);
            Equal(true, bounds.Left >= 0 && bounds.Top >= 0 && bounds.Right <= viewport.Item1 && bounds.Bottom <= viewport.Item2,
                $"full three-lane panel fits {viewport}: actual {bounds}");
            for (int lane = 0; lane < 3; lane++)
            {
                var layout = InfiniCrafterLocal.Common.UI.InfiniCraftStationUISystem.StationLaneBounds(bounds, lane);
                foreach (var control in new[] { layout.SlotA, layout.SlotB, layout.CraftButton, layout.Details, layout.Timer })
                    Equal(true, bounds.Contains(control), "draw and hit-test control fits actual panel");
                Equal(true, layout.CraftButton.Contains(layout.CraftButton.Center), "same rectangle accepts button center");
                Equal(false, layout.SlotA.Intersects(layout.SlotB) || layout.SlotB.Intersects(layout.CraftButton), "input hit targets do not overlap");
            }
        }
    }

    public static void ForgeQolDetailsAreCompleteAndReadOnly()
    {
        const BindingFlags fields = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
        MethodInfo? details = typeof(InfiniCraftPlayer).GetMethod("CraftLaneDetails");
        Equal(true, details is not null, "full read-only lane details are available");
        int oldNetMode = Terraria.Main.netMode; Terraria.Main.netMode = 0;
        try
        {
            WithForgePresentationLanguages(locale =>
            {
                bool ru = locale == "ru-RU";
                var player = new InfiniCraftPlayer();
                void Set(string name, object? value) => typeof(InfiniCraftPlayer).GetField(name, fields)!.SetValue(player, value);
                string Detail(int lane) => (string)details!.Invoke(player, new object[] { lane })!;
                string parents = "A very long saved parent name that exceeds thirty-one characters + Another full parent name";
                var request = new GeneratorClient.PreparedGenerationRequest();
                var work = new TaskCompletionSource<GeneratedItemData?>();
                Set("_request", request); Set("_task", work.Task); Set("_label", parents);
                Set("_elapsedTicks", InfiniCraftPlayer.CraftDurationTicks); Set("_totalCraftTicks", InfiniCraftPlayer.CraftDurationTicks + 121);
                string text = Detail(0);
                Equal(true, text.Contains(parents), "hover preserves complete accepted names");
                Equal(true, text.Contains(player.CraftLaneStatus(0)), "hover contains real current stage");
                Equal(true, text.Contains(ru ? "Прошло: 242 с" : "Elapsed: 242 s"), "elapsed is real total ticks, not capped bar");
                Equal(true, text.Contains(ru ? "не прогресс генерации" : "not generation progress"), "timer completion does not claim model completion");
                Equal(false, text.Contains("%"), "no fabricated model percent");
                Equal(false, request.CancellationToken.IsCancellationRequested, "hover does not cancel captured worker");
                Equal(false, work.Task.IsCompleted, "hover does not complete work");
                Equal(InfiniCraftPlayer.CraftDurationTicks + 121, (int)typeof(InfiniCraftPlayer).GetField("_totalCraftTicks", fields)!.GetValue(player)!, "hover cannot tick clock");
                Set("_awaitingServerCommit", true);
                Equal(true, Detail(0).Contains(player.CraftLaneStatus(0)), "host stage comes from canonical lane status");
                Set("_awaitingServerCommit", false); Set("_task", Task.FromResult<GeneratedItemData?>(null));
                Equal(true, Detail(0).Contains(player.CraftLaneStatus(0)), "commit stage comes from canonical lane status");
                // Existing admission refresh can park a remote mirror. Merely reading
                // status/details in single player must leave it and the worker intact.
                Set("_stationEscrowUsesRemoteAuthority", true);
                Item material = new Item { type = Terraria.ID.ItemID.Wood, stack = 1 }; player.InputA = material;
                _ = Detail(0); _ = player.CraftLaneStatus(0);
                Equal(true, ReferenceEquals(material, player.InputA), "hover does not retire remote material mirror");
                Equal(false, request.CancellationToken.IsCancellationRequested, "read-only unavailable status keeps cancellation owner");
                Set("_stationEscrowUsesRemoteAuthority", false); player.TrySetMultiDevWindowCount(3, syncServer: false);
                Type jobType = typeof(InfiniCraftPlayer).GetNestedType("MultiDevCraftJob", BindingFlags.NonPublic)!;
                var jobs = (Array)typeof(InfiniCraftPlayer).GetField("_multiDevJobs", fields)!.GetValue(player)!;
                for (int lane = 1; lane < 3; lane++)
                {
                    object job = Activator.CreateInstance(jobType, nonPublic: true)!;
                    var extraRequest = new GeneratorClient.PreparedGenerationRequest();
                    foreach (var field in new[] { ("Label", (object)parents), ("ElapsedTicks", (object)(InfiniCraftPlayer.CraftDurationTicks + 121)), ("Request", (object)extraRequest) })
                        jobType.GetField(field.Item1, fields)!.SetValue(job, field.Item2);
                    jobs.SetValue(job, lane - 1);
                    string extra = Detail(lane);
                    Equal(true, extra.Contains(parents) && extra.Contains(ru ? "Прошло: 242 с" : "Elapsed: 242 s"), "extra hover full labels and actual elapsed");
                    Equal(true, extra.Contains(player.CraftLaneStatus(lane)), "extra hover real waiting stage");
                    Equal(false, extraRequest.CancellationToken.IsCancellationRequested, "extra hover cannot cancel independent worker");
                }
            });
        }
        finally { Terraria.Main.netMode = oldNetMode; }
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
                string Countdown = ru ? "Таймер ковки · 3 с" : "Craft timer · 3 s";
                var player = new InfiniCraftPlayer();
                void Set(string name, object? value) => typeof(InfiniCraftPlayer).GetField(name, fields)!.SetValue(player, value);
                Equal(Need, player.CraftLaneStatus(0), locale + " empty visible lane");
                for (int lane = 1; lane < 3; lane++) Equal(ru ? "Этот горн закрыт" : "This hearth is closed", player.CraftLaneStatus(lane), locale + " closed lane " + lane);
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

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



}

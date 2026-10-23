#nullable enable
using System;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using Terraria;
using Terraria.ID;
using Terraria.Localization;

namespace InfiniCrafterLocal.Common.UI;

internal static class DefinitionRecoveryView
{
    internal readonly record struct Status(string Key, bool CanRecover, int RetryTicks, int Received, int Total);
    internal static Status Classify(GeneratedItemData data, string world, int netMode, GeneratedItemRegistryService.DefinitionReadiness state)
    {
        if (!data.RecipeMeta.WorldScoped || data.RecipeMeta.WorldId != world) return new("OtherWorld", false, 0, 0, 0);
        if (!GeneratedItemData.IsPlayerSaveReferenceOnly(data)) return new("Ready", false, 0, 0, 0);
        if (state.Cached) return new("Cached", true, 0, 0, 0);
        if (netMode != NetmodeID.MultiplayerClient) return new("MissingLocal", false, 0, 0, 0);
        if (state.Pending && state.RetryTicks > 0) return new("Receiving", false, state.RetryTicks, state.ReceivedChunks, state.TotalChunks);
        return new("MissingServer", true, state.RetryTicks, 0, 0);
    }
    internal static Status Capture(GeneratedItemData data)
        => Classify(data, Main.worldID.ToString(), Main.netMode,
            InfiniCrafterLocalMod.GeneratedItems?.ReadDefinitionReadiness(data.Id) ?? default);
    internal static string Describe(GeneratedItemData data)
    {
        var state = Capture(data);
        string text = Text(state.Key);
        if (state.RetryTicks > 0) text += " " + Text("RetryAfter", (int)Math.Ceiling(state.RetryTicks / 60d));
        if (state.Total > 0) text += " " + Text("Transfer", state.Received, state.Total);
        return text;
    }
    internal static string Text(string key, params object[] args)
        => Language.GetTextValue("Mods.InfiniCrafterLocal.DefinitionRecovery." + key, args);
}

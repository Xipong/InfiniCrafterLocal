#nullable enable
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Common.UI;
using Terraria.ID;
internal static partial class EngineRuntimeChecks
{
    private static void DefinitionRecovery()
    {
        var data = GeneratedItemData.Placeholder(); data.Id = "recovery"; data.RecipeMeta.WorldScoped = true; data.RecipeMeta.WorldId = "42";
        var reference = GeneratedItemData.FromPlayerSaveJson(data.ToPlayerSaveJson())!;
        var before = reference.ToNetworkJson();
        Equal("OtherWorld", DefinitionRecoveryView.Classify(reference, "43", NetmodeID.MultiplayerClient, new(true, false, 0, 0, 0)).Key, "world fence precedes cached id");
        Equal("MissingLocal", DefinitionRecoveryView.Classify(reference, "42", NetmodeID.SinglePlayer, default).Key, "offline reference cannot regenerate recipe");
        Equal("MissingServer", DefinitionRecoveryView.Classify(reference, "42", NetmodeID.MultiplayerClient, default).Key, "online missing state is actionable");
        var pending = DefinitionRecoveryView.Classify(reference, "42", NetmodeID.MultiplayerClient, new(false, true, 70, 2, 5));
        Equal(false, pending.CanRecover, "pending request cannot bypass throttle"); Equal(2, pending.Received, "per-item progress");
        Equal(true, DefinitionRecoveryView.Classify(reference, "42", NetmodeID.MultiplayerClient, new(false, true, 0, 0, 0)).CanRecover, "retry enabled after native window");
        Equal("Cached", DefinitionRecoveryView.Classify(reference, "42", NetmodeID.SinglePlayer, new(true, false, 0, 0, 0)).Key, "cached reference can hydrate locally");
        Equal("Ready", DefinitionRecoveryView.Classify(data, "42", NetmodeID.SinglePlayer, default).Key, "full definition ready");
        Equal(before, reference.ToNetworkJson(), "recovery inspection has no mutation or hydration side effect");
    }
}

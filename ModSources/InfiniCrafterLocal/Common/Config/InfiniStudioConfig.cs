#nullable enable
using System;
using InfiniCrafterLocal.Common.Services;
using Newtonsoft.Json;
using Terraria;
using Terraria.Localization;
using Terraria.ModLoader.Config;
using Terraria.ModLoader.Config.UI;
using Terraria.UI;

namespace InfiniCrafterLocal.Common.Config;

public sealed class InfiniStudioConfig : ModConfig
{
    public override ConfigScope Mode => ConfigScope.ClientSide;

    [JsonIgnore, ShowDespiteJsonIgnore, CustomModConfigItem(typeof(OpenStudioElement))]
    public bool OpenStudio;
}

public sealed class OpenStudioElement : ConfigElement
{
    private const string TextPrefix = "Mods.InfiniCrafterLocal.Studio.";

    public override void OnBind()
    {
        base.OnBind();
        Func<string>? description = TooltipFunction;
        TextDisplayFunction = () => StudioBrowserAction.Opening ? Language.GetTextValue(TextPrefix + "Starting") : Label;
        TooltipFunction = () => StudioBrowserAction.Status ?? description?.Invoke() ?? "";
    }

    public override void LeftClick(UIMouseEvent evt)
    {
        base.LeftClick(evt);
        StudioBrowserAction.TryOpen();
    }
}

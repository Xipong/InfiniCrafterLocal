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
    private bool _opening;
    private string? _status;

    public override void OnBind()
    {
        base.OnBind();
        Func<string>? description = TooltipFunction;
        TextDisplayFunction = () => _opening ? Language.GetTextValue(TextPrefix + "Starting") : Label;
        TooltipFunction = () => _status ?? description?.Invoke() ?? "";
    }

    public override async void LeftClick(UIMouseEvent evt)
    {
        base.LeftClick(evt);
        if (_opening || Main.dedServ)
            return;
        if (!BundledStudio.IsSupported)
        {
            _status = Language.GetTextValue(TextPrefix + "UnsupportedPlatform");
            return;
        }
        BundledStudio? studio = InfiniCrafterLocalMod.Studio;
        if (studio == null)
            return;
        _opening = true;
        _status = Language.GetTextValue(TextPrefix + "Starting");
        try
        {
            Uri url = await studio.StartAsync();
            Main.QueueMainThreadAction(() =>
            {
                if (!ReferenceEquals(InfiniCrafterLocalMod.Studio, studio))
                    return;
                try
                {
                    Utils.OpenToURL(url.AbsoluteUri);
                    _status = Language.GetTextValue(TextPrefix + "Opened");
                }
                catch (Exception exception)
                {
                    _status = Language.GetTextValue(TextPrefix + "Failed", exception.Message);
                    InfiniCrafterLocalMod.Instance.Logger.Warn("Could not open the Studio browser.", exception);
                }
                _opening = false;
            });
        }
        catch (OperationCanceledException)
        {
            // Mod unloading cancels startup and invalidates this configuration page.
            _opening = false;
        }
        catch (Exception exception)
        {
            Main.QueueMainThreadAction(() =>
            {
                if (!ReferenceEquals(InfiniCrafterLocalMod.Studio, studio))
                    return;
                _status = Language.GetTextValue(TextPrefix + "Failed", exception.Message);
                _opening = false;
                InfiniCrafterLocalMod.Instance.Logger.Warn("Could not start bundled Studio.", exception);
            });
        }
    }
}

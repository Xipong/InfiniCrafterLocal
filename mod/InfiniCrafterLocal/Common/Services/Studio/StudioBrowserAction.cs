#nullable enable
using System;
using Terraria;
using Terraria.Localization;

namespace InfiniCrafterLocal.Common.Services;

// One UI action shared by the menu icon and settings. BundledStudio remains the process owner.
internal static class StudioBrowserAction
{
    private const string Prefix = "Mods.InfiniCrafterLocal.Studio.";
    private static int _generation;
    private static long _nextOpen;
    internal static bool Opening { get; private set; }
    internal static string? Status { get; private set; }

    internal static bool TryBegin(long now, bool allowed)
    {
        if (!allowed || Opening || now < _nextOpen) return false;
        _generation++;
        Opening = true;
        _nextOpen = now + 2000;
        return true;
    }

    internal static int Generation => _generation;
    internal static bool Finish(int generation)
    {
        if (generation != _generation) return false;
        Opening = false;
        return true;
    }

    internal static bool CompleteRequest(BundledStudio studio, int generation, Action completion)
    {
        if (!Opening || generation != _generation || !ReferenceEquals(InfiniCrafterLocalMod.Studio, studio)) return false;
        try { completion(); }
        finally { Finish(generation); }
        return true;
    }

    internal static void Reset()
    {
        _generation++;
        Opening = false;
        _nextOpen = 0;
        Status = null;
    }

    internal static bool TryOpen()
    {
        if (Main.dedServ) return false;
        if (!BundledStudio.IsSupported)
        {
            Status = Language.GetTextValue(Prefix + "UnsupportedPlatform");
            return false;
        }
        BundledStudio? studio = InfiniCrafterLocalMod.Studio;
        if (!TryBegin(Environment.TickCount64, studio is not null)) return false;
        Status = Language.GetTextValue(Prefix + "Starting");
        OpenAsync(studio!, _generation);
        return true;
    }

    private static async void OpenAsync(BundledStudio studio, int generation)
    {
        try
        {
            Uri url = await studio.StartAsync();
            Main.QueueMainThreadAction(() => CompleteRequest(studio, generation, () =>
            {
                try
                {
                    Utils.OpenToURL(url.AbsoluteUri);
                    Status = Language.GetTextValue(Prefix + "Opened");
                }
                catch (Exception exception)
                {
                    Status = Language.GetTextValue(Prefix + "Failed", exception.Message);
                    InfiniCrafterLocalMod.Instance.Logger.Warn("Could not open the Studio browser.", exception);
                }
            }));
        }
        catch (OperationCanceledException)
        {
            Main.QueueMainThreadAction(() => CompleteRequest(studio, generation, () => { }));
        }
        catch (Exception exception)
        {
            Main.QueueMainThreadAction(() => CompleteRequest(studio, generation, () =>
            {
                Status = Language.GetTextValue(Prefix + "Failed", exception.Message);
                InfiniCrafterLocalMod.Instance.Logger.Warn("Could not start bundled Studio.", exception);
            }));
        }
    }
}

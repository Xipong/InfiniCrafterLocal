using System;
using System.Linq;
using System.Reflection;
using InfiniCrafterLocal;
using Terraria.GameInput;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Common.UI;
using Microsoft.Xna.Framework;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    private static void StudioMenuAdmission()
    {
        static void Require(bool value, string message) { if (!value) throw new InvalidOperationException(message); }
        Require(StudioMainMenuSystem.Visible(false, true, 0), "Root menu icon must be available");
        Require(!StudioMainMenuSystem.Visible(true, true, 0), "Dedicated server has no menu UI");
        Require(!StudioMainMenuSystem.Visible(false, false, 0), "Gameplay has no menu overlay");
        Require(!StudioMainMenuSystem.Visible(false, true, 1), "Character selection is not the root menu");
        var flags = BindingFlags.Static | BindingFlags.NonPublic | BindingFlags.Public;
        string[] mainFields = { "screenWidth", "screenHeight", "mouseX", "mouseY", "lastMouseX", "lastMouseY" };
        var savedMain = mainFields.ToDictionary(n => n, n => typeof(Terraria.Main).GetField(n, flags)!.GetValue(null));
        string[] inputFields = { "_originalScreenWidth", "_originalScreenHeight", "_originalMouseX", "_originalMouseY" };
        var savedInput = inputFields.ToDictionary(n => n, n => typeof(PlayerInput).GetField(n, flags)!.GetValue(null));
        try
        {
            foreach (float scale in new[] { 0.75f, 1f, 1.5f, 2f })
            {
                var expected = StudioMainMenuSystem.Bounds((int)(1920 / scale));
                typeof(PlayerInput).GetField("_originalScreenWidth", flags)!.SetValue(null, 1920);
                typeof(PlayerInput).GetField("_originalScreenHeight", flags)!.SetValue(null, 1080);
                typeof(PlayerInput).GetField("_originalMouseX", flags)!.SetValue(null, (int)(expected.Center.X * scale));
                typeof(PlayerInput).GetField("_originalMouseY", flags)!.SetValue(null, (int)(expected.Center.Y * scale));
                // Same native conversion called by PreDrawMenu, not a test approximation.
                typeof(PlayerInput).GetMethod("SetZoom_Scaled", flags)!.Invoke(null, new object[] { 1f / scale });
                Rectangle bounds = StudioMainMenuSystem.Bounds(Terraria.Main.screenWidth);
                Require(bounds.Contains(new Point(Terraria.Main.mouseX, Terraria.Main.mouseY)), "Native scaled mouse must hit the icon without a second inverse transform");
                Require(Math.Abs((bounds.Right + 20) * scale - 1920) < scale, "Right margin must follow native UI scale");
                Require(!bounds.Contains(new Point(bounds.Left - 1, bounds.Top)), "Outside pointer is not a click");
            }
        }
        finally
        {
            foreach (var pair in savedMain) typeof(Terraria.Main).GetField(pair.Key, flags)!.SetValue(null, pair.Value);
            foreach (var pair in savedInput) typeof(PlayerInput).GetField(pair.Key, flags)!.SetValue(null, pair.Value);
        }
        StudioBrowserAction.Reset();
        try
        {
            Require(!StudioBrowserAction.TryBegin(100, false), "Unavailable launch must not enter pending state");
            Require(!StudioBrowserAction.Opening, "Refusal cannot leave a stuck spinner");
            Require(StudioBrowserAction.TryBegin(100, true), "First launch is accepted");
            int old = StudioBrowserAction.Generation;
            Require(!StudioBrowserAction.TryBegin(5000, true), "Pending launch blocks even after debounce expires");
            Require(StudioBrowserAction.Finish(old), "Current completion clears pending state");
            Require(!StudioBrowserAction.TryBegin(2099, true), "Fast repeated clicks cannot reopen the browser");
            Require(StudioBrowserAction.TryBegin(2100, true), "Explicit later click can reopen Studio");
            StudioBrowserAction.Reset();
            Require(StudioBrowserAction.TryBegin(0, true), "Reload starts a fresh UI lifecycle");
            Require(!StudioBrowserAction.Finish(old) && StudioBrowserAction.Opening, "Stale completion cannot release a new launch");
            StudioBrowserAction.Reset();
            bool dedicated = Terraria.Main.dedServ;
            try
            {
                Terraria.Main.dedServ = true;
                Require(!StudioBrowserAction.TryOpen() && !StudioBrowserAction.Opening, "Actual dedicated-server action must not start a process or browser");
            }
            finally { Terraria.Main.dedServ = dedicated; }
        }
        finally { StudioBrowserAction.Reset(); }
        var studioField = typeof(InfiniCrafterLocalMod).GetField("<Studio>k__BackingField", flags)!;
        object? originalStudio = studioField.GetValue(null);
        using var owner = new BundledStudio(null!, "unused-test-path");
        using var replacement = new BundledStudio(null!, "unused-test-path");
        int callbacks = 0;
        try
        {
            studioField.SetValue(null, owner);
            StudioBrowserAction.TryBegin(0, true);
            int generation = StudioBrowserAction.Generation;
            Action queuedSuccess = () => StudioBrowserAction.CompleteRequest(owner, generation, () => callbacks++);
            Action queuedFailure = () => StudioBrowserAction.CompleteRequest(owner, generation, () => callbacks += 100);
            StudioBrowserAction.Reset();
            StudioBrowserAction.TryBegin(0, true);
            queuedSuccess(); queuedFailure();
            Require(callbacks == 0 && StudioBrowserAction.Opening, "Unloaded queued success/failure cannot open a browser or mutate new pending UI");
            generation = StudioBrowserAction.Generation;
            studioField.SetValue(null, replacement);
            Require(!StudioBrowserAction.CompleteRequest(owner, generation, () => callbacks++), "Replaced process owner must reject a late browser callback");
            studioField.SetValue(null, owner);
            Require(StudioBrowserAction.CompleteRequest(owner, generation, () => callbacks++), "Current queued success must execute exactly once");
            Require(callbacks == 1 && !StudioBrowserAction.Opening, "Current completion releases shared launch admission");
            Require(!StudioBrowserAction.CompleteRequest(owner, generation, () => callbacks++), "Repeated completion cannot reopen browser");
            StudioBrowserAction.TryBegin(2000, true);
            generation = StudioBrowserAction.Generation;
            try { StudioBrowserAction.CompleteRequest(owner, generation, () => throw new InvalidOperationException("controlled completion failure")); }
            catch (InvalidOperationException) { }
            Require(!StudioBrowserAction.Opening, "Completion failure cannot leave launch admission stuck");
        }
        finally { studioField.SetValue(null, originalStudio); StudioBrowserAction.Reset(); }
    }
}

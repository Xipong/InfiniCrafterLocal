#nullable enable
using System;
using System.IO;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Services;
using Terraria;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Commands;

public sealed partial class InfiniDumpCommand
{
    private static RuntimeDumpExport? activeExport;
    private static DateTime nextProgressAt;
    private static bool notifyCompletion = true;

    internal static void UpdateExport()
    {
        if (activeExport is not { } export) return;
        if (!export.Completion.IsCompleted)
        {
            export.Pump();
            if (notifyCompletion && DateTime.UtcNow >= nextProgressAt)
            {
                Main.NewText("InfiniCraft dump: " + export.Progress, 120, 220, 255);
                nextProgressAt = DateTime.UtcNow.AddSeconds(5);
            }
            return;
        }
        activeExport = null;
        try
        {
            JsonObject manifest = export.Completion.GetAwaiter().GetResult();
            if (notifyCompletion)
            {
                string root = Path.Combine(Main.SavePath, "InfiniCrafterLocal");
                Main.NewText($"InfiniCraft snapshot: {Path.Combine(root, DumpManifestName)}", 120, 220, 255);
                foreach (string kind in new[] { "items", "projectiles" })
                    Main.NewText(Path.Combine(root, manifest["files"]![kind]!["path"]!.GetValue<string>()), 120, 220, 255);
                Main.NewText("Restart generator to read this snapshot; previous snapshots were kept.", 120, 220, 255);
            }
        }
        catch (OperationCanceledException)
        {
            if (notifyCompletion)
            {
                Main.NewText("InfiniCraft dump cancelled; previous complete snapshot kept.", 255, 200, 120);
                ReportIncompleteExport(export);
            }
        }
        catch (Exception error)
        {
            ModContent.GetInstance<InfiniCrafterLocalMod>().Logger.Error(
                $"Runtime dump export failed; previous snapshot kept. Incomplete attempt: {export.IncompleteDirectory ?? "not created"}", error);
            if (notifyCompletion)
            {
                Main.NewText($"InfiniCraft dump failed ({error.GetType().Name}); previous complete snapshot kept. See client.log.", 255, 140, 120);
                ReportIncompleteExport(export);
            }
        }
        finally { notifyCompletion = true; }
    }

    private static void ReportIncompleteExport(RuntimeDumpExport export)
    {
        if (export.IncompleteDirectory is { } path)
            Main.NewText("Incomplete diagnostic files kept (not a complete snapshot): " + path, 255, 200, 120);
    }

    internal static void CancelExport(bool notify)
    {
        if (activeExport is not { } export)
        { if (notify) Main.NewText("InfiniCraft: no dump is running.", 120, 220, 255); return; }
        notifyCompletion = notify;
        if (notify)
        { export.Cancel(); }
        else export.RequestCancellation(); // Unload can run on the loader thread.
        if (notify) Main.NewText("InfiniCraft dump: cancelling. Previous snapshots are retained.", 255, 200, 120);
    }

    internal static void UnloadExport()
    {
        CancelExport(notify: false);
        // Observe eventual export failures without calling any game API
        // after unload. Never wait/join a disk worker from the game thread.
        if (activeExport is { } export)
            _ = export.Completion.ContinueWith(task => { _ = task.Exception; },
                System.Threading.Tasks.TaskContinuationOptions.OnlyOnFaulted);
        activeExport = null;
        notifyCompletion = true;
    }
}

public sealed class InfiniDumpSystem : ModSystem
{
    public override void PostUpdateEverything()
    {
        GeneratorClient.ParentAnalysis.Pump();
        InfiniDumpCommand.UpdateExport();
    }
    public override void OnWorldUnload()
    {
        InfiniDumpCommand.CancelExport(notify: false);
        GeneratorClient.ParentAnalysis.Invalidate();
    }
    public override void Unload()
    {
        InfiniDumpCommand.UnloadExport();
        GeneratorClient.ParentAnalysis.Invalidate();
    }
}

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using InfiniCrafterLocal.Common.Commands;

internal static partial class EngineRuntimeChecks
{
    private static JsonObject DumpTestEnvironment() => new()
    {
        ["mods"] = new JsonArray(), ["tModLoader"] = new JsonObject(), ["exporter"] = new JsonObject()
    };

    private static void RuntimeDumpIncrementalCaptureAndPublication()
    {
        string root = Directory.CreateTempSubdirectory("ifc-dump-incremental-").FullName;
        try
        {
            int thread = Environment.CurrentManagedThreadId, captures = 0;
            var identities = new List<string>();
            JsonObject? Capture(int type, bool items)
            {
                Equal(thread, Environment.CurrentManagedThreadId, "definition/defaults/hooks always stay on producer thread");
                captures++; identities.Add((items ? "item:" : "projectile:") + type);
                if (items && type == 3) return null;
                if (items && type == 4) throw new InvalidOperationException("private hook detail");
                return new JsonObject { ["type"] = type, ["damage"] = 0, ["source"] = new string('x', 8192) };
            }
            var job = new RuntimeDumpExport(root, 11, 7, t => Capture(t, true), t => Capture(t, false), DumpTestEnvironment());
            Equal(0, captures, "starting export never captures the entire catalog synchronously");
            job.Pump();
            Equal(true, captures > 0 && captures <= RuntimeDumpExport.RecordsPerUpdate,
                "one update performs only its bounded slice, not all 16 definitions");
            bool rejected = false;
            try { Task.Run(job.Pump).GetAwaiter().GetResult(); }
            catch (InvalidOperationException) { rejected = true; }
            Equal(true, rejected, "background game capture is rejected, not merely discouraged");
            var elapsed = Stopwatch.StartNew();
            while (!job.Completion.IsCompleted && elapsed.Elapsed < TimeSpan.FromSeconds(10))
            {
                int before = captures;
                job.Pump();
                Equal(true, captures - before <= RuntimeDumpExport.RecordsPerUpdate, "each update remains bounded under writer pressure");
                Thread.Sleep(1);
            }
            Equal(true, job.Completion.IsCompleted, "writer completes after producer finishes");
            JsonObject manifest = job.Completion.GetAwaiter().GetResult();
            Equal(16, captures, "each loaded definition captured once with no skips at queue transitions");
            Equal(string.Join(",", Enumerable.Range(1, 10).Select(t => "item:" + t).Concat(Enumerable.Range(1, 6).Select(t => "projectile:" + t))),
                string.Join(",", identities), "ordered item/projectile boundaries survive incremental scheduling");
            string[] items = File.ReadAllLines(Path.Combine(root, manifest["files"]!["items"]!["path"]!.GetValue<string>()));
            Equal(9, items.Length, "air/null row skipped while failed row retained");
            JsonObject failed = JsonNode.Parse(items[2])!.AsObject();
            Equal(4, failed["type"]!.GetValue<int>(), "failed type retained");
            Equal(true, failed["unavailable"]!.GetValue<bool>(), "failed hook remains explicitly unavailable");
            Equal(false, items[2].Contains("private hook detail", StringComparison.Ordinal), "exception details not exported");
            Equal(1, manifest["files"]!["items"]!["unavailableRows"]!.GetValue<int>(), "manifest retains exact failed-row count");
            Equal(6, manifest["files"]!["projectiles"]!["rows"]!.GetValue<int>(), "projectile channel boundary not lost");
            Equal(false, manifest.ToJsonString().Contains("captureFile", StringComparison.Ordinal), "internal hash paths never published");
        }
        finally { Directory.Delete(root, true); }
    }

    private static void RuntimeDumpIncrementalBudgetCancellationAndFailure()
    {
        string root = Directory.CreateTempSubdirectory("ifc-dump-cancel-").FullName;
        try
        {
            InfiniDumpCommand.PublishSnapshot(root, w => w.WriteLine("{\"type\":1}"), w => w.WriteLine("{\"type\":1}"), DumpTestEnvironment());
            string path = Path.Combine(root, InfiniDumpCommand.DumpManifestName);
            string original = File.ReadAllText(path);
            int captures = 0;
            var job = new RuntimeDumpExport(root, 100, 100, type =>
            {
                captures++; Thread.Sleep(10); // Models a slow indivisible native/mod hook.
                return new JsonObject { ["type"] = type };
            }, type => new JsonObject { ["type"] = type }, DumpTestEnvironment());
            job.Pump();
            Equal(1, captures, "soft time budget stops before the next definition after one slow hook");
            Task.Run(job.RequestCancellation).GetAwaiter().GetResult();
            job.Pump();
            Equal(1, captures, "cancelled job never invokes further native hooks");
            bool cancelled = false;
            try { job.Completion.GetAwaiter().GetResult(); }
            catch (OperationCanceledException) { cancelled = true; }
            Equal(true, cancelled, "cancellation is terminal and visible to completion owner");
            Equal(original, File.ReadAllText(path), "cancelled partial export cannot replace accepted manifest");
            Equal(1, Directory.GetDirectories(Path.Combine(root, "runtime_dump_snapshots")).Length,
                "cancelled export does not enter complete snapshot namespace");
            Equal(true, job.IncompleteDirectory is not null && Directory.Exists(job.IncompleteDirectory), "cancelled output remains inspectable");
            var state = JsonNode.Parse(File.ReadAllText(Path.Combine(job.IncompleteDirectory!, InfiniDumpCommand.DumpIncompleteStateName)))!;
            Equal("cancelled", state["status"]!.GetValue<string>(), "cancellation marker cannot be confused with a completed pair");
            string blocked = Path.Combine(root, "not-a-directory"); File.WriteAllText(blocked, "occupied");
            var failed = new RuntimeDumpExport(blocked, 2, 2, _ => null, _ => null, DumpTestEnvironment());
            bool ioFailure = false;
            try { failed.Completion.GetAwaiter().GetResult(); }
            catch (IOException) { ioFailure = true; }
            Equal(true, ioFailure, "writer failure is surfaced without waiting for more capture");
            failed.Pump();
            Equal(original, File.ReadAllText(path), "writer failure cannot alter previous published snapshot");
        }
        finally { Directory.Delete(root, true); }
    }
}

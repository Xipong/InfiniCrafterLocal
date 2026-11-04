#nullable enable
using System;
using System.Diagnostics;
using System.IO;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Channels;
using System.Threading.Tasks;

namespace InfiniCrafterLocal.Common.Commands;

// Main-thread producer, bounded pure-data handoff, file-only consumer. Never
// put SetDefaults, native hooks, Main, ModContent or GPU access in Task.Run.
internal sealed class RuntimeDumpExport
{
    internal const int QueueCapacity = 4;
    internal const int RecordsPerUpdate = 16;
    internal static readonly TimeSpan CaptureBudget = TimeSpan.FromMilliseconds(2);
    private readonly int captureThread = Environment.CurrentManagedThreadId;
    private readonly int itemCount, projectileCount;
    private readonly Func<int, JsonObject?> captureItem, captureProjectile;
    private readonly Channel<Record> rows = Channel.CreateBounded<Record>(new BoundedChannelOptions(QueueCapacity)
    { SingleReader = true, SingleWriter = true, FullMode = BoundedChannelFullMode.Wait });
    private readonly CancellationTokenSource cancellation = new();
    private int item = 1, projectile = 1, stage;
    private Record? pending;
    private sealed record Record(JsonObject? Snapshot, bool EndStage);
    internal Task<JsonObject> Completion { get; }
    internal int CapturedItems => item - 1;
    internal int CapturedProjectiles => projectile - 1;
    internal bool CaptureFinished => stage == 2 && pending is null;
    internal string Progress => cancellation.IsCancellationRequested ? "cancelling"
        : CaptureFinished ? "writing and verifying files"
        : $"items {CapturedItems}/{Math.Max(0, itemCount - 1)}, projectiles {CapturedProjectiles}/{Math.Max(0, projectileCount - 1)}";

    internal RuntimeDumpExport(string root, int itemCount, int projectileCount,
        Func<int, JsonObject?> captureItem, Func<int, JsonObject?> captureProjectile, JsonObject environment)
    {
        this.itemCount = itemCount; this.projectileCount = projectileCount;
        this.captureItem = captureItem; this.captureProjectile = captureProjectile;
        // These locals, not game-state callbacks, are the worker's inputs.
        ChannelReader<Record> reader = rows.Reader;
        CancellationToken token = cancellation.Token;
        Completion = Task.Run(() =>
        {
            InfiniDumpCommand.CompleteDumpEnvironmentFileHashes(environment);
            void Drain(TextWriter writer)
            {
                while (true)
                {
                    Record row = reader.ReadAsync(token).AsTask().GetAwaiter().GetResult();
                    token.ThrowIfCancellationRequested();
                    if (row.EndStage) return;
                    if (row.Snapshot is not null) writer.WriteLine(row.Snapshot.ToJsonString());
                }
            }
            return InfiniDumpCommand.PublishSnapshot(root, Drain, Drain, environment, token);
        });
    }

    internal void Pump()
    {
        RequireCaptureThread();
        if (Completion.IsCompleted || cancellation.IsCancellationRequested || CaptureFinished) return;
        var elapsed = Stopwatch.StartNew();
        for (int n = 0; n < RecordsPerUpdate && (n == 0 || elapsed.Elapsed < CaptureBudget); n++)
        {
            if (pending is not null)
            {
                if (!rows.Writer.TryWrite(pending)) return;
                pending = null;
                if (stage == 2) { rows.Writer.TryComplete(); return; }
                // A full queue must yield rather than block the game thread.
                if (rows.Reader.Count >= QueueCapacity) return;
            }
            if (rows.Reader.Count >= QueueCapacity || Completion.IsCompleted) return;
            if (stage == 0 && item < itemCount)
                pending = new Record(Capture(item++, captureItem), false);
            else if (stage == 1 && projectile < projectileCount)
                pending = new Record(Capture(projectile++, captureProjectile), false);
            else
            { stage++; pending = new Record(null, true); }
            if (!rows.Writer.TryWrite(pending)) return;
            pending = null;
            if (stage == 2) { rows.Writer.TryComplete(); return; }
        }
    }

    internal void Cancel()
    {
        RequireCaptureThread();
        RequestCancellation();
        pending = null;
    }

    // Mod unloading may occur on the loader thread. Cancellation never waits
    // for the file worker or touches pending native capture state.
    internal void RequestCancellation()
    {
        cancellation.Cancel();
        rows.Writer.TryComplete();
    }

    private void RequireCaptureThread()
    {
        if (Environment.CurrentManagedThreadId != captureThread)
            throw new InvalidOperationException("Runtime dump capture must stay on its originating game thread.");
    }

    private static JsonObject? Capture(int type, Func<int, JsonObject?> capture)
    {
        try { return capture(type); }
        catch (Exception error) when (error is not OutOfMemoryException)
        { return new JsonObject { ["type"] = type, ["unavailable"] = true, ["captureError"] = error.GetType().Name }; }
    }
}

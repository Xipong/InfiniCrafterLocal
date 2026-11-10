#nullable enable
using System;
using System.Diagnostics;
using System.IO;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Channels;
using System.Threading.Tasks;
using InfiniCrafterLocal.Common.Services;

namespace InfiniCrafterLocal.Common.Commands;

// Main-thread producer, bounded snapshot handoff, source-analysis/file consumer.
// Live dependency snapshots return through ParentAnalysis.Pump; workers never
// execute SetDefaults/native hooks or access Main, ModContent or GPU state.
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
    private sealed record Record(JsonObject? Snapshot, bool EndStage, GeneratorClient.ParentAnalysis? Analysis = null);
    internal Task<JsonObject> Completion { get; }
    internal string? IncompleteDirectory { get; private set; }
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
            void Drain(TextWriter writer)
            {
                while (true)
                {
                    Record row = reader.ReadAsync(token).AsTask().GetAwaiter().GetResult();
                    using (row.Analysis)
                    {
                        token.ThrowIfCancellationRequested();
                        if (row.EndStage) return;
                        if (row.Snapshot is not null)
                            writer.WriteLine((row.Analysis?.Resolve(row.Snapshot, token) ?? row.Snapshot).ToJsonString());
                    }
                }
            }
            try
            {
                InfiniDumpCommand.CompleteDumpEnvironmentFileHashes(environment);
                return InfiniDumpCommand.PublishSnapshot(root, Drain, Drain, environment, token,
                    path => IncompleteDirectory = path);
            }
            finally
            {
                cancellation.Cancel();
                rows.Writer.TryComplete();
                Interlocked.Exchange(ref pending, null)?.Analysis?.Dispose();
                while (reader.TryRead(out var abandoned)) abandoned.Analysis?.Dispose();
            }
        });
    }

    internal void Pump()
    {
        RequireCaptureThread();
        if (Completion.IsCompleted || cancellation.IsCancellationRequested || CaptureFinished) return;
        var elapsed = Stopwatch.StartNew();
        for (int n = 0; n < RecordsPerUpdate && (n == 0 || elapsed.Elapsed < CaptureBudget); n++)
        {
            Record? row = Interlocked.Exchange(ref pending, null);
            if (row is not null)
            {
                if (!TryWrite(row)) return;
                if (stage == 2) { rows.Writer.TryComplete(); return; }
                if (rows.Reader.Count >= QueueCapacity) return;
            }
            if (rows.Reader.Count >= QueueCapacity || Completion.IsCompleted || cancellation.IsCancellationRequested) return;
            if (stage == 0 && item < itemCount)
                row = CaptureRecord(item++, captureItem);
            else if (stage == 1 && projectile < projectileCount)
                row = CaptureRecord(projectile++, captureProjectile);
            else
            { stage++; row = new Record(null, true); }
            if (!TryWrite(row)) return;
            if (stage == 2) { rows.Writer.TryComplete(); return; }
        }
    }

    private bool TryWrite(Record row)
    {
        if (rows.Writer.TryWrite(row)) return true;
        // Publish only a finished main-thread capture. Cancellation can safely
        // take this slot without touching an in-progress hook or snapshot.
        Interlocked.Exchange(ref pending, row)?.Analysis?.Dispose();
        if (cancellation.IsCancellationRequested || Completion.IsCompleted)
            Interlocked.Exchange(ref pending, null)?.Analysis?.Dispose();
        return false;
    }

    internal void Cancel()
    {
        RequireCaptureThread();
        RequestCancellation();
    }

    // Loader/world cancellation never waits for the capture thread or worker.
    internal void RequestCancellation()
    {
        cancellation.Cancel();
        rows.Writer.TryComplete();
        Interlocked.Exchange(ref pending, null)?.Analysis?.Dispose();
    }

    private void RequireCaptureThread()
    {
        if (Environment.CurrentManagedThreadId != captureThread)
            throw new InvalidOperationException("Runtime dump capture must stay on its originating game thread.");
    }

    private Record CaptureRecord(int type, Func<int, JsonObject?> capture)
    {
        var analysis = new GeneratorClient.ParentAnalysis(cancellation.Token);
        try
        {
            using var scope = analysis.Enter();
            return new Record(capture(type), false, analysis);
        }
        catch (Exception error) when (error is not OutOfMemoryException)
        {
            analysis.Dispose();
            return new Record(new JsonObject { ["type"] = type, ["unavailable"] = true, ["captureError"] = error.GetType().Name }, false);
        }
    }
}

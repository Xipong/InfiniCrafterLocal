using System.Diagnostics;
using System.Globalization;
using System.IO.Compression;
using System.Reflection;
using System.Runtime;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Analysis;

internal static class Program
{
    private const string BaselineCommit = "c4a7bc7995dd99c28a589a582d7c5e381720edf7";
    private const int MaximumEntryBytes = 4 * 1024 * 1024;
    private const int MaximumArchiveBytes = 128 * 1024 * 1024;
    private const int TextUtf8Bytes = 1024 * 1024;
    private const string TextMotif = "// source: Привет 日本語 😀\nreturn value + 1;\n";
    private const string ProjectionPrefix = "projectile_method\n11111111-2222-3333-4444-555555555555\n100663297\n"
        + "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\n";
    private const string ProjectionJson = """{"type":950,"style":1,"capturedReceiverBound":true,"windows":[],"linkOffsets":[12,48]}""";

    private static int Main(string[] args)
    {
        try
        {
            if (args.Length == 1 && args[0] is "--help" or "-h")
            {
                Console.WriteLine("Usage: SourceAnalysisBuffers.Benchmarks <real-pack.zip> [--samples 8] [--target-ms 100] [--validate-only]");
                return 0;
            }
            var options = Options.Parse(args);
#if DEBUG
            throw new InvalidOperationException("Build this benchmark with --configuration Release.");
#else
            Run(options);
            return 0;
#endif
        }
        catch (Exception error)
        {
            Console.Error.WriteLine(error);
            return 1;
        }
    }

    private static void Run(Options options)
    {
        DateTimeOffset started = DateTimeOffset.UtcNow;
        var file = new FileInfo(options.PackPath);
        if (file.Length > MaximumArchiveBytes) throw new InvalidDataException("The source pack exceeds 128 MiB.");
        byte[] archiveBytes = File.ReadAllBytes(file.FullName);
        using var archiveStream = new MemoryStream(archiveBytes, writable: false);
        using var archive = new ZipArchive(archiveStream, ZipArchiveMode.Read);
        var manifestEntry = archive.GetEntry("manifest.json") ?? throw new InvalidDataException("Missing manifest.json.");
        byte[] manifestBytes = BaselineReadEntry(manifestEntry, MaximumEntryBytes, default);
        var manifest = JsonNode.Parse(manifestBytes)!.AsObject();
        var rows = manifest["entries"]!.AsArray();
        var blobs = manifest["blobs"]!.AsArray();
        string expectedIndex = manifest["indexSha256"]!.GetValue<string>();
        var largest = archive.Entries.Where(entry => !entry.FullName.EndsWith('/'))
            .OrderByDescending(entry => entry.Length).ThenBy(entry => entry.FullName, StringComparer.Ordinal).First();
        var projection = JsonNode.Parse(ProjectionJson)!;
        string text = CreateText();
        if (Encoding.UTF8.GetByteCount(text) != TextUtf8Bytes) throw new InvalidOperationException("Text fixture size mismatch.");

        var cases = new[]
        {
            new BenchmarkCase("manifest_index_hash", new
            {
                source = "real_pack", rows = rows.Count, blobs = blobs.Count,
                expectedSha256 = expectedIndex,
                hashedUtf8Bytes = Encoding.UTF8.GetByteCount(rows.ToJsonString()) + 1 + Encoding.UTF8.GetByteCount(blobs.ToJsonString())
            }, () => BaselineIndexHash(rows, blobs), () => SourceAnalysisBuffers.HashJsonPair(rows, blobs)),
            new BenchmarkCase("largest_zip_entry_read", new
            {
                source = "real_pack", entry = largest.FullName, uncompressedBytes = largest.Length,
                compressedBytes = largest.CompressedLength, includesManifestInSelection = true,
                timedScope = "entry.Open, decompression, bounded read, exact owned byte[]; compressed input already in memory"
            }, () => BaselineReadEntry(largest, MaximumEntryBytes, default), () => ReadEntry(largest)),
            new BenchmarkCase("tiny_projection_key", new
            {
                source = "representative_literal", prefix = ProjectionPrefix, json = ProjectionJson,
                hashedUtf8Bytes = Encoding.UTF8.GetByteCount(ProjectionPrefix + projection.ToJsonString()),
                timedScope = "JSON serialization, prefix concatenation or streaming, UTF8 SHA256, lowercase hex; identity prefix precomputed"
            }, () => BaselineUtf8Hash(ProjectionPrefix + projection.ToJsonString()),
                () => SourceAnalysisBuffers.HashUtf8AndJson(ProjectionPrefix, projection, default)),
            new BenchmarkCase("one_mib_utf8_text_hash", new
            {
                source = "synthetic", utf8Bytes = TextUtf8Bytes, utf16Characters = text.Length,
                motif = TextMotif, construction = "repeat motif, then ASCII x padding to exactly 1 MiB UTF8"
            }, () => BaselineUtf8Hash(text), () => SourceAnalysisBuffers.HashUtf8(text))
        };

        // All comparisons happen before warmup and timing. Do not include
        // validation, input construction, hashes of fixtures, or JSON reporting
        // in either variant's measurements.
        var validation = cases.Select(Validate).ToArray();
        if (validation[0].ResultSha256 != expectedIndex)
            throw new InvalidDataException("The real manifest index does not match indexSha256.");
        var results = new List<object>();
        for (int index = 0; index < cases.Length; index++)
        {
            var item = cases[index];
            if (options.ValidateOnly)
                results.Add(new { item.Name, item.Input, validation = validation[index] });
            else
            {
                Console.Error.WriteLine($"Measuring {item.Name} ({options.Samples} alternating AB/BA samples).");
                results.Add(Benchmark(item, validation[index], options));
            }
        }

        var assembly = Assembly.GetExecutingAssembly();
        var report = new
        {
            schemaVersion = 1, benchmark = "source_analysis_buffers", baselineCommit = BaselineCommit,
            startedUtc = started, completedUtc = DateTimeOffset.UtcNow,
            measurementPerformed = !options.ValidateOnly,
            runtime = new
            {
                framework = RuntimeInformation.FrameworkDescription, version = Environment.Version.ToString(),
                runtimeIdentifier = RuntimeInformation.RuntimeIdentifier, os = RuntimeInformation.OSDescription,
                architecture = RuntimeInformation.ProcessArchitecture.ToString(), processorCount = Environment.ProcessorCount,
                is64BitProcess = Environment.Is64BitProcess, serverGc = GCSettings.IsServerGC,
                gcLatencyMode = GCSettings.LatencyMode.ToString(), stopwatchFrequency = Stopwatch.Frequency,
                stopwatchIsHighResolution = Stopwatch.IsHighResolution,
                controls = new[] { "DOTNET_TieredCompilation", "COMPlus_TieredCompilation", "DOTNET_TieredPGO", "COMPlus_TieredPGO",
                    "DOTNET_ReadyToRun", "COMPlus_ReadyToRun", "DOTNET_gcServer", "COMPlus_gcServer" }
                    .ToDictionary(name => name, Environment.GetEnvironmentVariable)
            },
            build = new
            {
                configuration = "Release", assemblySha256 = FileHash(assembly.Location),
                linkedHelperSourceSha256 = ResourceHash(assembly, "SourceAnalysisBuffers.source.cs"),
                benchmarkSourceSha256 = ResourceHash(assembly, "Benchmark.source.cs")
            },
            input = new
            {
                packFileName = file.Name, archiveBytes = archiveBytes.Length, archiveSha256 = Hash(archiveBytes),
                archiveEntryCount = archive.Entries.Count, manifestBytes = manifestBytes.Length,
                manifestSha256 = Hash(manifestBytes), manifestVersion = manifest["version"]?.GetValue<int>(),
                manifestIndexSha256 = expectedIndex
            },
            method = new
            {
                samplesPerVariant = options.ValidateOnly ? 0 : options.Samples,
                targetSampleMilliseconds = options.TargetMilliseconds,
                sameOperationsPerVariant = true, order = "A=baseline, B=optimized; sample 1 AB, sample 2 BA, repeat",
                warmup = "at least 32 operations per variant and at least 250 ms total per case",
                calibration = "8 operations per variant after warmup; one common iteration count based on slower variant",
                forcedGc = false, allocationMetric = "GC.GetAllocatedBytesForCurrentThread delta, divided by operations",
                timeMetric = "Stopwatch elapsed ticks, converted to ns/op",
                scope = "single-process warmed microbenchmark, not cold startup or end-to-end parent analysis",
                excluded = "file IO, ZIP directory parsing, JsonNode parsing, fixtures, correctness comparisons, report serialization",
                limits = "managed allocation is not retained memory or peak RSS; elapsed time includes natural GC; concurrent CPU work and tiered JIT can affect samples"
            },
            cases = results
        };
        Console.WriteLine(JsonSerializer.Serialize(report, new JsonSerializerOptions
        {
            WriteIndented = true, PropertyNamingPolicy = JsonNamingPolicy.CamelCase
        }));
    }

    private static Validation Validate(BenchmarkCase item)
    {
        object baseline = item.Baseline();
        object optimized = item.Optimized();
        if (baseline is string expected && optimized is string actual && expected == actual)
            return new Validation(true, "SHA256 digest and lowercase hex are identical", expected);
        if (baseline is byte[] expectedBytes && optimized is byte[] actualBytes && expectedBytes.AsSpan().SequenceEqual(actualBytes))
            return new Validation(true, "every returned byte is identical", Hash(expectedBytes));
        throw new InvalidOperationException($"Baseline and optimized outputs differ: {item.Name}.");
    }

    private static object Benchmark(BenchmarkCase item, Validation validation, Options options)
    {
        var warmup = Stopwatch.StartNew();
        int warmupOperations = 0;
        do
        {
            GC.KeepAlive(item.Baseline());
            GC.KeepAlive(item.Optimized());
            warmupOperations++;
        } while (warmupOperations < 32 || warmup.ElapsedMilliseconds < 250);

        Measurement calibrationA = Measure(item.Baseline, 8);
        Measurement calibrationB = Measure(item.Optimized, 8);
        double slowerNs = Math.Max(calibrationA.NanosecondsPerOperation, calibrationB.NanosecondsPerOperation);
        int operations = (int)Math.Clamp(Math.Ceiling(options.TargetMilliseconds * 1_000_000.0 / Math.Max(slowerNs, 1)), 1, 1_000_000);
        var samples = new List<Sample>(options.Samples);
        for (int sample = 0; sample < options.Samples; sample++)
        {
            Measurement a, b;
            if (sample % 2 == 0) { a = Measure(item.Baseline, operations); b = Measure(item.Optimized, operations); }
            else { b = Measure(item.Optimized, operations); a = Measure(item.Baseline, operations); }
            samples.Add(new Sample(sample + 1, sample % 2 == 0 ? "AB" : "BA", a, b));
        }
        return new
        {
            item.Name, item.Input, validation, warmupOperationsPerVariant = warmupOperations,
            calibration = new { baseline = calibrationA, optimized = calibrationB }, operationsPerSample = operations,
            summary = new { baseline = Summarize(samples.Select(sample => sample.Baseline)), optimized = Summarize(samples.Select(sample => sample.Optimized)) },
            samples
        };
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static Measurement Measure(Func<object> operation, int operations)
    {
        int gen0 = GC.CollectionCount(0), gen1 = GC.CollectionCount(1), gen2 = GC.CollectionCount(2);
        object? lastResult = null;
        long before = GC.GetAllocatedBytesForCurrentThread();
        long started = Stopwatch.GetTimestamp();
        for (int index = 0; index < operations; index++) lastResult = operation();
        long ticks = Stopwatch.GetTimestamp() - started;
        long allocated = GC.GetAllocatedBytesForCurrentThread() - before;
        GC.KeepAlive(lastResult);
        return new Measurement(operations, ticks, allocated, GC.CollectionCount(0) - gen0,
            GC.CollectionCount(1) - gen1, GC.CollectionCount(2) - gen2);
    }

    private static object Summarize(IEnumerable<Measurement> values)
    {
        Measurement[] samples = values.ToArray();
        return new
        {
            medianNanosecondsPerOperation = Median(samples.Select(value => value.NanosecondsPerOperation)),
            minNanosecondsPerOperation = samples.Min(value => value.NanosecondsPerOperation),
            maxNanosecondsPerOperation = samples.Max(value => value.NanosecondsPerOperation),
            medianAllocatedBytesPerOperation = Median(samples.Select(value => value.AllocatedBytesPerOperation)),
            minAllocatedBytesPerOperation = samples.Min(value => value.AllocatedBytesPerOperation),
            maxAllocatedBytesPerOperation = samples.Max(value => value.AllocatedBytesPerOperation)
        };
    }

    private static double Median(IEnumerable<double> values)
    {
        double[] sorted = values.Order().ToArray();
        return (sorted[(sorted.Length - 1) / 2] + sorted[sorted.Length / 2]) / 2;
    }

    private static string CreateText()
    {
        int motifBytes = Encoding.UTF8.GetByteCount(TextMotif);
        var text = new StringBuilder(TextUtf8Bytes);
        for (int index = 0; index < TextUtf8Bytes / motifBytes; index++) text.Append(TextMotif);
        return text.Append('x', TextUtf8Bytes % motifBytes).ToString();
    }

    private static string FileHash(string path) { using var input = File.OpenRead(path); return Convert.ToHexString(SHA256.HashData(input)).ToLowerInvariant(); }
    private static string ResourceHash(Assembly assembly, string name)
    {
        using var input = assembly.GetManifestResourceStream(name) ?? throw new InvalidOperationException($"Missing embedded source: {name}.");
        return Convert.ToHexString(SHA256.HashData(input)).ToLowerInvariant();
    }
    private static string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();

    // Exact relevant PR339 operations; only the precomputed reflection identity
    // prefix is outside the tiny projection-key timing for both variants.
    private static string BaselineUtf8Hash(string text) => Hash(Encoding.UTF8.GetBytes(text));
    private static string BaselineIndexHash(JsonArray rows, JsonArray blobs)
        => Hash(Encoding.UTF8.GetBytes(rows.ToJsonString() + "\n" + blobs.ToJsonString()));

    private static byte[] BaselineReadEntry(ZipArchiveEntry entry, int maximum, CancellationToken cancellation)
    {
        if (entry.Length < 0 || entry.Length > maximum) throw new InvalidDataException("native_source_pack_entry_size");
        using var input = entry.Open();
        using var output = new MemoryStream((int)entry.Length);
        byte[] buffer = new byte[16384];
        int count;
        while ((count = input.Read(buffer, 0, buffer.Length)) != 0)
        {
            cancellation.ThrowIfCancellationRequested();
            if (output.Length + count > maximum) throw new InvalidDataException("native_source_pack_entry_size");
            output.Write(buffer, 0, count);
        }
        cancellation.ThrowIfCancellationRequested();
        if (output.Length != entry.Length) throw new InvalidDataException("native_source_pack_entry_length");
        return output.ToArray();
    }

    private static byte[] ReadEntry(ZipArchiveEntry entry)
    {
        if (entry.Length < 0 || entry.Length > MaximumEntryBytes) throw new InvalidDataException("native_source_pack_entry_size");
        using var input = entry.Open();
        return SourceAnalysisBuffers.ReadExact(input, (int)entry.Length, MaximumEntryBytes, default);
    }

    private sealed record BenchmarkCase(string Name, object Input, Func<object> Baseline, Func<object> Optimized);
    private sealed record Validation(bool Equal, string Comparison, string ResultSha256);
    private sealed record Sample(int Number, string Order, Measurement Baseline, Measurement Optimized);
    private readonly record struct Measurement(int Operations, long StopwatchTicks, long AllocatedBytes,
        int Gen0Collections, int Gen1Collections, int Gen2Collections)
    {
        public double NanosecondsPerOperation => StopwatchTicks * (1_000_000_000.0 / Stopwatch.Frequency) / Operations;
        public double AllocatedBytesPerOperation => (double)AllocatedBytes / Operations;
    }

    private sealed record Options(string PackPath, int Samples, int TargetMilliseconds, bool ValidateOnly)
    {
        internal static Options Parse(string[] args)
        {
            if (args.Length == 0 || args[0].StartsWith('-')) throw new ArgumentException("A real native-source-pack.zip path is required. Use --help.");
            int samples = 8, target = 100;
            bool validateOnly = false;
            for (int index = 1; index < args.Length; index++)
            {
                string arg = args[index];
                if (arg == "--validate-only") { validateOnly = true; continue; }
                if (++index == args.Length) throw new ArgumentException($"Missing value for {arg}.");
                int value = int.Parse(args[index], CultureInfo.InvariantCulture);
                switch (arg)
                {
                    case "--samples": samples = value; break;
                    case "--target-ms": target = value; break;
                    default: throw new ArgumentException($"Unknown option: {arg}.");
                }
            }
            if (samples < 5 || samples > 1000) throw new ArgumentOutOfRangeException(nameof(samples), "Use 5 to 1000 samples; an even count balances AB/BA.");
            if (target < 10 || target > 10000) throw new ArgumentOutOfRangeException(nameof(target), "Use a target sample duration of 10 to 10000 ms.");
            return new Options(Path.GetFullPath(args[0]), samples, target, validateOnly);
        }
    }
}

using System.Diagnostics;
using System.Numerics;
using System.Reflection;
using System.Runtime;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text.Json;
using InfiniCrafterLocal.Common.Analysis;

internal static class Program
{
    private sealed class Node
    {
        internal readonly List<int> Next = new();
    }

    private sealed record Graph(string Name, int[] Nodes, Dictionary<int, int> Indices,
        Dictionary<int, Node> Blocks, Dictionary<int, int> Joins);
    private sealed record Sample(double ElapsedMilliseconds, long AllocatedBytes, ulong Checksum);

    private static int Main(string[] args)
    {
        int repetitions = 9;
        bool verifyOnly = false;
        for (int index = 0; index < args.Length; index++)
        {
            if (args[index] == "--verify-only") verifyOnly = true;
            else if (args[index] == "--repetitions" && index + 1 < args.Length && int.TryParse(args[++index], out int count) && count is >= 3 and <= 31)
                repetitions = count;
            else throw new ArgumentException("Expected --verify-only or --repetitions <3..31>.");
        }
        Graph[] graphs = {
            Create("chain_64", 64, "chain"), Create("chain_2048", 2048, "chain"),
            Create("early_returns_2047", 2047, "early_returns"),
            Create("diamonds_1024", 1024, "diamonds"),
            Create("loop_exit_2048", 2048, "loop_exit"),
            Create("duplicate_edges_2048", 2048, "duplicates")
        };
        var results = new List<object>();
        foreach (Graph graph in graphs)
        {
            ulong[][] expected = BuildAllRows(graph, compact: false);
            ulong[][] actual = BuildAllRows(graph, compact: true);
            if (expected.Length != actual.Length || expected.Where((row, index) => !row.SequenceEqual(actual[index])).Any())
                throw new InvalidOperationException("Byte-different compact row in " + graph.Name);
            if (verifyOnly) continue;
            // Both exact functions and delegate call sites are warmed before
            // measurement. Alternate order to reduce consistent first-run bias.
            for (int warmup = 0; warmup < 2; warmup++)
            {
                Consume(BuildAllRows(graph, compact: false));
                Consume(BuildAllRows(graph, compact: true));
            }
            var legacy = new List<Sample>();
            var production = new List<Sample>();
            for (int repetition = 0; repetition < repetitions; repetition++)
            {
                if ((repetition & 1) == 0)
                {
                    legacy.Add(Measure(graph, compact: false));
                    production.Add(Measure(graph, compact: true));
                }
                else
                {
                    production.Add(Measure(graph, compact: true));
                    legacy.Add(Measure(graph, compact: false));
                }
            }
            if (legacy.Concat(production).Select(sample => sample.Checksum).Distinct().Count() != 1)
                throw new InvalidOperationException("Measured row checksum changed in " + graph.Name);
            double oldTime = Median(legacy.Select(sample => sample.ElapsedMilliseconds));
            double newTime = Median(production.Select(sample => sample.ElapsedMilliseconds));
            double oldBytes = Median(legacy.Select(sample => (double)sample.AllocatedBytes));
            double newBytes = Median(production.Select(sample => (double)sample.AllocatedBytes));
            results.Add(new {
                graph.Name, NodeCount = graph.Nodes.Length, RowCount = actual.Length,
                EdgeCount = graph.Blocks.Values.Sum(node => node.Next.Count),
                FinalPayloadBytes = actual.Sum(row => row.LongLength * sizeof(ulong)),
                ByteEqualRows = true,
                Legacy = new { MedianElapsedMilliseconds = oldTime, MedianAllocatedBytes = oldBytes, Samples = legacy },
                Production = new { MedianElapsedMilliseconds = newTime, MedianAllocatedBytes = newBytes, Samples = production },
                ElapsedReductionPercent = (oldTime - newTime) / oldTime * 100,
                AllocationReductionPercent = (oldBytes - newBytes) / oldBytes * 100
            });
        }
        var report = new {
            Schema = "indexed_bitset_all_rows_v1", VerifiedGraphs = graphs.Length,
            VerifiedRows = graphs.Sum(graph => 2 * graph.Nodes.Length), VerifiedAllRows = true,
            Scope = "All reach and control rows, shared input/index map, fixed precomputed joins; excludes IL decoding, postdominator solving, memo wrappers and process RSS.",
            Baseline = "Previous HashSet traversal followed by conversion into final ulong[] rows.",
            Production = "Direct calls to source-linked production IndexedBitSet Reach/ControlledRegion/Singleton.",
            Runtime = RuntimeInformation.FrameworkDescription, RuntimeVersion = Environment.Version.ToString(),
            Architecture = RuntimeInformation.ProcessArchitecture.ToString(), ServerGc = GCSettings.IsServerGC,
            Stopwatch.Frequency, Environment.ProcessorCount, Repetitions = verifyOnly ? 0 : repetitions,
            TieredCompilation = Environment.GetEnvironmentVariable("DOTNET_TieredCompilation") ?? "runtime default",
            ProductionSourceSha256 = ResourceHash("IndexedBitSet.source.cs"),
            BenchmarkSourceSha256 = ResourceHash("Benchmark.source.cs"),
            ProjectSha256 = ResourceHash("Benchmark.project.xml"),
            Results = results
        };
        Console.WriteLine(JsonSerializer.Serialize(report, new JsonSerializerOptions { WriteIndented = true }));
        return 0;
    }

    private static Graph Create(string name, int count, string shape)
    {
        int[] nodes = Enumerable.Range(0, count).Select(index => 1001 + (count - index) * 17).ToArray();
        var blocks = nodes.ToDictionary(node => node, _ => new Node());
        var indices = nodes.Select((node, index) => (node, index)).ToDictionary(pair => pair.node, pair => pair.index);
        var joins = nodes.ToDictionary(node => node, _ => -1);
        void Edge(int from, int to) => blocks[nodes[from]].Next.Add(nodes[to]);
        switch (shape)
        {
            case "early_returns":
                for (int index = 0; index + 2 < count; index += 2) { Edge(index, index + 2); Edge(index, index + 1); }
                break;
            case "diamonds":
                for (int index = 0; index + 3 < count; index += 4)
                {
                    Edge(index, index + 1); Edge(index, index + 2);
                    Edge(index + 1, index + 3); Edge(index + 2, index + 3);
                    joins[nodes[index]] = nodes[index + 3];
                    if (index + 4 < count) Edge(index + 3, index + 4);
                }
                break;
            case "loop_exit":
                for (int index = 0; index + 1 < count; index++) Edge(index, index + 1);
                Edge(count - 2, 0);
                joins[nodes[count - 2]] = nodes[count - 1];
                break;
            default:
                for (int index = 0; index + 1 < count; index++)
                {
                    Edge(index, index + 1);
                    if (shape == "duplicates") Edge(index, index + 1);
                }
                break;
        }
        return new Graph(name, nodes, indices, blocks, joins);
    }

    private static ulong[][] BuildAllRows(Graph graph, bool compact)
    {
        var rows = new ulong[2 * graph.Nodes.Length][];
        for (int index = 0; index < graph.Nodes.Length; index++)
        {
            int start = graph.Nodes[index];
            rows[index * 2] = compact
                ? IndexedBitSet.Reach(start, graph.Indices, graph.Blocks, static node => node.Next)
                : LegacyReach(graph, start);
            bool branching = graph.Blocks[start].Next.Distinct().Count() >= 2;
            rows[index * 2 + 1] = compact
                ? branching
                    ? IndexedBitSet.ControlledRegion(start, graph.Joins[start], graph.Indices, graph.Blocks, static node => node.Next)
                    : IndexedBitSet.Singleton(start, graph.Indices)
                : LegacyControl(graph, start, branching);
        }
        return rows;
    }

    private static ulong[] LegacyReach(Graph graph, int start)
    {
        var reached = new HashSet<int>(); var pending = new Stack<int>(); pending.Push(start);
        while (pending.Count > 0)
        {
            int next = pending.Pop(); if (!reached.Add(next)) continue;
            foreach (int target in graph.Blocks[next].Next) pending.Push(target);
        }
        return LegacyPack(graph, reached);
    }

    private static ulong[] LegacyControl(Graph graph, int start, bool branching)
    {
        var region = new HashSet<int> { start };
        if (!branching) return LegacyPack(graph, region);
        int join = graph.Joins[start];
        var pending = new Stack<int>(graph.Blocks[start].Next);
        while (pending.Count > 0)
        {
            int next = pending.Pop(); if (next == join || !region.Add(next)) continue;
            foreach (int successor in graph.Blocks[next].Next) pending.Push(successor);
        }
        return LegacyPack(graph, region);
    }

    private static ulong[] LegacyPack(Graph graph, HashSet<int> facts)
    {
        var words = new ulong[(graph.Nodes.Length + 63) / 64];
        foreach (int node in facts)
        {
            int bit = graph.Indices[node];
            words[bit >> 6] |= 1UL << (bit & 63);
        }
        return words;
    }

    private static Sample Measure(Graph graph, bool compact)
    {
        GC.Collect(); GC.WaitForPendingFinalizers(); GC.Collect();
        long beforeBytes = GC.GetAllocatedBytesForCurrentThread();
        long beforeTicks = Stopwatch.GetTimestamp();
        ulong[][] rows = BuildAllRows(graph, compact);
        ulong checksum = Consume(rows);
        long elapsedTicks = Stopwatch.GetTimestamp() - beforeTicks;
        long bytes = GC.GetAllocatedBytesForCurrentThread() - beforeBytes;
        GC.KeepAlive(rows);
        return new Sample((double)elapsedTicks / Stopwatch.Frequency * 1000, bytes, checksum);
    }

    private static ulong Consume(ulong[][] rows)
    {
        ulong result = 0;
        foreach (ulong[] row in rows)
            foreach (ulong word in row) result += (ulong)BitOperations.PopCount(word);
        return result;
    }

    private static double Median(IEnumerable<double> values)
    {
        double[] ordered = values.Order().ToArray();
        int middle = ordered.Length / 2;
        return (ordered.Length & 1) != 0 ? ordered[middle] : (ordered[middle - 1] + ordered[middle]) / 2;
    }

    private static string ResourceHash(string name)
    {
        using Stream stream = Assembly.GetExecutingAssembly().GetManifestResourceStream(name)!;
        return Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant();
    }
}

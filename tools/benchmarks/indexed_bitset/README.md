# Indexed bit set construction benchmark

This standalone .NET 8 executable source-links the production `IndexedBitSet`
helper. It needs no NuGet packages, Terraria, tModLoader or native-check output.
The project requires the exact .NET 8.0.0 runtime with roll-forward disabled.

```sh
dotnet build tools/benchmarks/indexed_bitset/IndexedBitSet.Benchmarks.csproj -c Release --configfile tools/benchmarks/indexed_bitset/NuGet.Config
dotnet tools/benchmarks/indexed_bitset/bin/Release/net8.0/IndexedBitSet.Benchmarks.dll --verify-only
dotnet tools/benchmarks/indexed_bitset/bin/Release/net8.0/IndexedBitSet.Benchmarks.dll --repetitions 9 > indexed-bitset-results.json
```

If the SDK host lacks runtime 8.0.0, use its `dotnet` executable for the build
and an exact-runtime host for the two executable commands. Keep the runtime,
GC/tiering settings, executable and machine unchanged when comparing runs.

Each case builds **every reachability and control-region row** for its graph.
The legacy side retains the previous `HashSet<int>` traversal and subsequent
conversion into `ulong[]`. The new side calls the same production helper used
by `ParentSourceMethod`, without copying its implementation into the harness.
Both sides produce and retain the same final rows through the measured pass.
All words are compared before timings, and each timed pass consumes every word.

Cases cover chains, overlapping early returns, diamonds, a loop with an exit
and repeated switch-like edges, at sizes up to the production 2048-block bound.
Joins are fixed inputs appropriate to each graph; the unchanged postdominator
solver, IL decoding, dictionary layout creation and memo wrapper allocation are
outside this measurement. Native integration checks cover those owners.

The JSON contains raw samples, medians, graph sizes, final payload sizes,
allocated bytes from `GC.GetAllocatedBytesForCurrentThread`, wall-clock elapsed
time and SHA-256 digests of the embedded production source, harness and project.
Measurements alternate implementation order after warmup; collection occurs
outside the measured interval. Final bit-array payload is unchanged by design.
This benchmark measures transient allocation and elapsed time, **not process
RSS, peak memory or end-to-end craft performance**. Those require a separate
native workload comparison.

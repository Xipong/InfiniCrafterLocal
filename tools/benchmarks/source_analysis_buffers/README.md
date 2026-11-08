# SourceAnalysisBuffers: isolated .NET 8 microbenchmark

This executable links the production `SourceAnalysisBuffers.cs` directly. It has
no NuGet package dependencies and compares the relevant BCL operations from
PR339 at `c2ac5107b825598eb3b8e1477b6c7c7b2edd17e2` with that linked implementation.
It requires an actual version 2 native source pack. The manifest index must match
its declared `indexSha256` before validation or measurement can continue.

The benchmark was adapted from the earlier `906a32b` experiment. It measures only
the two APIs retained in the current helper: `ReadExact` and `HashUtf8`. There are
no JSON streaming hash APIs, pooled buffers, or JSON serialization benchmark cases.
In particular, the tiny hash scenario is a prebuilt string, not projection-key
assembly or JSON serialization. Its result is not an end-to-end projection-key
performance result.

## Build and run

From the repository root, using a .NET 8 SDK:

```bash
dotnet build tools/benchmarks/source_analysis_buffers/SourceAnalysisBuffers.Benchmarks.csproj --configuration Release
dotnet tools/benchmarks/source_analysis_buffers/bin/Release/net8.0/SourceAnalysisBuffers.Benchmarks.dll /absolute/path/native-source-pack.zip > source-analysis-buffers.json
```

The executable requests .NET **8.0.0** with roll-forward disabled, matching the
PR339 measurements. Use a host containing that exact runtime. To deliberately
compare another installed .NET 8 patch, pass `dotnet --roll-forward LatestPatch`
before the DLL path; the report always records the actual runtime. Build and run
are separate so SDK/runtime startup and compilation do not enter measurements.

Options are `--samples 8`, `--target-ms 100`, and `--validate-only`. At least five
samples are required; the default eight balance AB/BA order. Validation-only
checks the pack index and all outputs without warmup or timed measurements.
Results go to stdout as JSON, progress and failures go to stderr. A mismatch exits
unsuccessfully before any timing; there are no performance assertions.

For example, after generating the real baseline pack:

```bash
dotnet tools/benchmarks/source_analysis_buffers/bin/Release/net8.0/SourceAnalysisBuffers.Benchmarks.dll artifacts/native-baseline/Data/native-source-pack.zip --validate-only > source-analysis-validation.json
```

## What is measured

| Scenario | Input | Timed work |
| --- | --- | --- |
| Largest ZIP entry read | Largest uncompressed entry of the real pack, including `manifest.json` in selection | Open entry, decompress, read into owned result bytes, validate length |
| Tiny UTF-8 text hash | Prebuilt representative method-identity text with Unicode | UTF-8 encoding, SHA256, lowercase hex |
| 1 MiB UTF-8 text hash | Deterministic multilingual text with emoji and ASCII padding | UTF-8 encoding, SHA256, lowercase hex |

Archive loading, ZIP directory parsing, manifest parsing and checksum validation,
JSON serialization, fixture construction, correctness comparisons, fixture hashing,
and reporting are outside measurements. Both variants share the same compressed
archive held in memory. This isolates entry decoding and buffer work from disk
effects. Byte-array outputs are compared byte for byte; hash outputs must have
identical digests and hexadecimal spelling. The exact tiny input and the recipe
for the 1 MiB text are recorded in the report.

Each scenario first warms both variants for at least 32 operations each and
250 ms total. An eight-operation probe chooses one common iteration count from
the slower variant's time. Measured samples alternate baseline/optimized and
optimized/baseline. The report includes every raw sample (operations, elapsed
ticks, allocated bytes, natural GC counts), ns/op and bytes/op, median/min/max,
runtime configuration, and pack/manifest/result hashes. No `GC.Collect` is called.

## Provenance and limits

The baseline reader is the `ReadNativeSourcePackEntry` implementation from the
pinned commit's `GeneratorClient.NativeSourcePack.cs`. The baseline text hash is
that commit's `CSharpHash(Encoding.UTF8.GetBytes(text))` operation. The report
links both source files. The candidate is compiled from the production helper,
not a benchmark-local copy. Embedded SHA256 hashes identify the exact helper,
benchmark source, and project bytes used for the build; the executable hash is
also recorded. This remains accurate when the working tree is uncommitted.

Run measurements only after other CPU-heavy work, builds, and source collection
have stopped. These are warmed, single-process microbenchmarks; natural GC and
tiered JIT can still affect timings. Allocation measures managed bytes allocated
by the current thread, not retained bytes or process RSS. The results do not
establish cold startup, complete parent-analysis latency, whole-game memory,
or a 200 MiB process limit. Use separate process measurements for those claims.

Behavioral tests live in
`tests/native/context/EngineRuntimeChecks.SourceAnalysisBuffers.cs`: malformed
UTF-16 fuzzing and surrogate boundaries, nonseekable short reads, length and size
refusals, real compressed ZIP entries, cancellation at EOF/probe boundaries,
independent ownership, and parallel calls.

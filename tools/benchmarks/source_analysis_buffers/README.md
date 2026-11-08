# SourceAnalysisBuffers: isolated .NET 8 microbenchmark

This executable links the production `SourceAnalysisBuffers.cs` directly. It has
no NuGet package dependencies and compares the relevant original PR339 code at
`c4a7bc7995dd99c28a589a582d7c5e381720edf7` with that linked implementation.
It requires an actual version 2 native source pack, not a generated benchmark
substitute. The manifest index must match its declared `indexSha256`.

The final runtime integration retains the original manifest-index hash path
because the fully streaming integration raised whole-process peak RSS in the
mixed scenario. `HashJsonPair` is still a separately tested library API: its
microbenchmark gain must not be presented as a gain in the active index loader.
See the [integration measurements and limits](../../../docs/development/pipeline/CSHARP_ANALYSIS_MEMORY_20261108_RU.md).

## Run

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
checks all outputs without warmup or timed measurements. Results go to stdout as
JSON, progress and failures go to stderr. A result mismatch exits unsuccessfully
before any timing; there are no performance assertions.

## What is measured

| Scenario | Input | Timed work |
| --- | --- | --- |
| Manifest index hash | Actual pack `entries` and `blobs` | Compact JSON serialization, UTF-8 SHA256, lowercase hex |
| Largest ZIP entry read | Largest uncompressed entry, including `manifest.json` in selection | Open entry, decompress, read into owned result bytes, validate length |
| Tiny projection key | Literal method identity prefix and representative projection JSON | Serialize JSON, combine prefix, UTF-8 SHA256, lowercase hex |
| 1 MiB UTF-8 text | Deterministic multilingual text with emoji and ASCII padding | UTF-8 encoding, SHA256, lowercase hex |

Archive loading, ZIP directory parsing, JSON parsing, reflection identity prefix
construction, validation, fixture hashing, and reporting are outside measurements.
Both variants share the same compressed archive held in memory. This isolates
entry decoding and buffer work from disk effects. Byte-array outputs are compared
byte for byte; hash outputs must have identical digests and hexadecimal spelling.

Each scenario first warms both variants for at least 32 operations each and
250 ms total. An eight-operation probe chooses one common iteration count from
the slower variant's time. Measured samples alternate baseline/optimized and
optimized/baseline. The report includes every raw sample (operations, elapsed
ticks, allocated bytes, natural GC counts), ns/op and bytes/op, median/min/max,
runtime configuration, pack/manifest/result hashes, and hashes of the actual
embedded source files compiled into the executable. No `GC.Collect` is called.

Run when other CPU-heavy work has stopped. These are warmed, single-process
microbenchmarks; GC and tiered JIT can still affect timings. Allocation measures
managed bytes allocated by the current thread, not retained bytes or process RSS.
They do not establish end-to-end parent-analysis speed or memory consumption.

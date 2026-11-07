using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using InfiniCrafterLocal.Common.Services;
using Terraria;
using Terraria.ID;
using ProgramCapture = InfiniCrafterLocal.Common.Services.GeneratorClient.ProjectileAttackCapture;
using ProgramCache = InfiniCrafterLocal.Common.Services.GeneratorClient.ProjectileAttackProgramCache;

internal static partial class EngineRuntimeChecks
{
    private static ProgramCapture SizedSourceProgram(int characters)
    {
        var source = new JsonObject { ["text"] = "" };
        var spawns = new JsonArray();
        int overhead = source.ToJsonString().Length + spawns.ToJsonString().Length;
        source["text"] = new string('x', characters - overhead);
        return new ProgramCapture(source, spawns);
    }

    private static void SourceProgramsEvictLeastRecentlyUsed()
    {
        var builds = new Dictionary<(int, int), int>();
        var cache = new ProgramCache((type, style) =>
        {
            var key = (type, style);
            builds[key] = builds.GetValueOrDefault(key) + 1;
            return new ProgramCapture(new JsonObject { ["type"] = type, ["style"] = style }, new JsonArray());
        }, () => { });
        for (int type = 0; type < ProgramCache.EntryLimit; type++) cache.Get(type, 0);
        var hot = cache.Get(0, 0);
        cache.Get(0, 1); // Style participates in identity and crosses the count bound.
        Equal(true, ReferenceEquals(hot, cache.Get(0, 0)), "count pressure preserves the recently used entry");
        cache.Get(2, 0);
        Equal(1, builds[(2, 0)], "count pressure evicts one oldest entry, not all programs");
        cache.Get(1, 0);
        Equal(2, builds[(1, 0)], "least recently used identity is recomputed");
        Equal(1, builds[(0, 1)], "distinct style is built independently");

        builds.Clear();
        cache = new ProgramCache((type, style) =>
        {
            builds[(type, style)] = builds.GetValueOrDefault((type, style)) + 1;
            return SizedSourceProgram(type == 99 ? (int)ProgramCache.CharacterLimit + 1 : (int)ProgramCache.CharacterLimit / 4);
        }, () => { });
        for (int type = 0; type < 4; type++) cache.Get(type, 0);
        hot = cache.Get(0, 0);
        Equal(ProgramCache.CharacterLimit / 4, hot.Characters, "serialized character accounting includes both trees exactly");
        cache.Get(4, 0);
        Equal(true, ReferenceEquals(hot, cache.Get(0, 0)), "character pressure preserves the hot program");
        cache.Get(2, 0);
        Equal(1, builds[(2, 0)], "character pressure evicts only enough oldest programs");
        cache.Get(1, 0);
        Equal(2, builds[(1, 0)], "character pressure evicts the LRU program at the exact bound");
        cache.Get(99, 0);
        cache.Get(99, 0);
        Equal(2, builds[(99, 0)], "oversized complete programs are returned but not retained");
        Equal(true, ReferenceEquals(hot, cache.Get(0, 0)), "oversized program does not flush unrelated retained programs");
        cache.Clear();
        cache.Get(0, 0);
        Equal(2, builds[(0, 0)], "clear resets both entry and character accounting");
    }

    private static void SourceProgramsFenceLateCompletion()
    {
        using var started = new ManualResetEventSlim();
        using var release = new ManualResetEventSlim();
        int builds = 0;
        var cache = new ProgramCache((_, _) =>
        {
            int attempt = Interlocked.Increment(ref builds);
            if (attempt == 1)
            {
                started.Set();
                if (!release.Wait(TimeSpan.FromSeconds(10))) throw new TimeoutException("late completion release");
            }
            return new ProgramCapture(new JsonObject { ["attempt"] = attempt }, new JsonArray());
        }, () => { });
        var old = Task.Run(() => cache.Get(1, 0));
        try
        {
            Equal(true, started.Wait(TimeSpan.FromSeconds(10)), "first source build is in flight");
            cache.Clear();
            var replacement = cache.Get(1, 0);
            release.Set();
            Equal(true, old.Wait(TimeSpan.FromSeconds(10)), "detached source build completes");
            Equal(1, old.Result.CloneSource()["attempt"]!.GetValue<int>(), "original borrower may finish with its own complete source");
            Equal(true, ReferenceEquals(replacement, cache.Get(1, 0)), "late completion cannot replace the new epoch entry");
            Equal(2, builds, "late completion cannot trigger a third build or recache old source");
        }
        finally { release.Set(); old.GetAwaiter().GetResult(); }

        // Count eviction has the same identity fence as explicit invalidation.
        started.Reset(); release.Reset(); builds = 0;
        cache.Clear();
        old = Task.Run(() => cache.Get(1, 0));
        try
        {
            Equal(true, started.Wait(TimeSpan.FromSeconds(10)), "eviction source build is in flight");
            for (int type = 2; type <= ProgramCache.EntryLimit + 1; type++) cache.Get(type, 0);
            release.Set();
            old.GetAwaiter().GetResult();
            int before = builds;
            cache.Get(1, 0);
            Equal(before + 1, builds, "evicted in-flight completion is not reinserted");
        }
        finally { release.Set(); old.GetAwaiter().GetResult(); }
    }

    private static void SourceProgramsRetryCancelledOwnersAndBorrowers()
    {
        foreach (bool cancelOwner in new[] { true, false })
        {
            using var started = new ManualResetEventSlim();
            using var release = new ManualResetEventSlim();
            using var ownerCancellation = new CancellationTokenSource();
            using var borrowerCancellation = new CancellationTokenSource();
            using var context = new ThreadLocal<CancellationToken>();
            int builds = 0;
            var cache = new ProgramCache((_, _) =>
            {
                if (Interlocked.Increment(ref builds) == 1)
                {
                    started.Set();
                    if (!release.Wait(TimeSpan.FromSeconds(10))) throw new TimeoutException("cancel source release");
                }
                // Simulates a projection swallowing cancellation into a refusal.
                return new ProgramCapture(new JsonObject { ["partial"] = context.Value.IsCancellationRequested }, new JsonArray());
            }, () => context.Value.ThrowIfCancellationRequested());
            Exception? ownerError = null, borrowerError = null;
            ProgramCapture? ownerResult = null, borrowerResult = null;
            var owner = new Thread(() =>
            {
                context.Value = ownerCancellation.Token;
                try { ownerResult = cache.Get(1, 0); } catch (Exception error) { ownerError = error; }
            });
            var borrower = new Thread(() =>
            {
                context.Value = borrowerCancellation.Token;
                try { borrowerResult = cache.Get(1, 0); } catch (Exception error) { borrowerError = error; }
            });
            owner.Start();
            try
            {
                Equal(true, started.Wait(TimeSpan.FromSeconds(10)), "owner begins one shared Lazy build");
                borrower.Start();
                Equal(true, SpinWait.SpinUntil(() => (borrower.ThreadState & ThreadState.WaitSleepJoin) != 0,
                    TimeSpan.FromSeconds(10)), "borrower is waiting on the in-flight Lazy");
                (cancelOwner ? ownerCancellation : borrowerCancellation).Cancel();
            }
            finally
            {
                release.Set();
                Equal(true, owner.Join(TimeSpan.FromSeconds(10)), "owner terminates");
                if ((borrower.ThreadState & ThreadState.Unstarted) == 0)
                    Equal(true, borrower.Join(TimeSpan.FromSeconds(10)), "borrower terminates");
            }
            Equal(true, (cancelOwner ? ownerError : borrowerError) is OperationCanceledException, "cancelled caller exits");
            Equal<Exception?>(null, cancelOwner ? borrowerError : ownerError, "live caller succeeds");
            var live = cancelOwner ? borrowerResult! : ownerResult!;
            Equal(false, live.CloneSource()["partial"]!.GetValue<bool>(), "cancelled refusal partial is never published or cached");
            Equal(cancelOwner ? 2 : 1, builds, "live borrower retries only a cancelled owner, never duplicates healthy in-flight work");
            Equal(true, ReferenceEquals(live, cache.Get(1, 0)), "cancelled borrower does not remove a healthy owner's cached program");
        }
    }

    private static void SourceProgramsCloneIsolation()
    {
        var source = JsonNode.Parse("{\"identity\":{\"type\":17,\"style\":0},\"code\":\"a\\n\\\"b\\\"\",\"null\":null,\"numbers\":[-0,1.00,1e-30,9007199254740993],\"mechanicsSource\":{\"records\":[{\"code\":\"original\"}],\"unresolved\":[]}}")!.AsObject();
        var spawns = JsonNode.Parse("[{\"projectileTypes\":[1,2],\"at\":0},null]")!.AsArray();
        string expected = source.ToJsonString(), expectedSpawns = spawns.ToJsonString();
        var capture = new ProgramCapture(source, spawns);
        source.Clear(); spawns.Clear();
        Equal(expected, capture.CloneSource().ToJsonString(), "immutable snapshot preserves text, order, nulls and numeric spelling even after builder mutation");
        Equal(expectedSpawns, capture.CloneSpawns().ToJsonString(), "spawn source preserves order and explicit null");
        Equal(expected.Length + (long)expectedSpawns.Length, capture.Characters, "old serialized-text accounting is unchanged");
        capture.CloneSource()["identity"]!["type"] = -1;
        capture.CloneSource()["mechanicsSource"]!["records"]![0]!["code"] = "full source mutation";
        capture.CloneMechanics()!["records"]![0]!["code"] = "mechanics mutation";
        capture.CloneSpawns()[0]!["projectileTypes"]![0] = -1;
        Equal(expected, capture.CloneSource().ToJsonString(), "all consumers get isolated nested source trees");
        Equal(expectedSpawns, capture.CloneSpawns().ToJsonString(), "spawn mutation cannot poison future consumers");
        Equal("original", capture.CloneMechanics()!["records"]![0]!["code"]!.GetValue<string>(), "mechanics subset remains isolated");
        Equal<JsonObject?>(null, new ProgramCapture(new JsonObject(), new JsonArray()).CloneMechanics(), "absent mechanics remains absent for existing caller refusal");
        Equal<JsonObject?>(null, new ProgramCapture(new JsonObject { ["mechanicsSource"] = null }, new JsonArray()).CloneMechanics(), "explicit null mechanics retains the existing absence semantics");
        Parallel.For(0, 32, _ =>
        {
            var copy = capture.CloneSource(); copy["numbers"]!.AsArray().Clear();
            capture.CloneMechanics()!.Clear(); capture.CloneSpawns().Clear();
        });
        Equal(expected, capture.CloneSource().ToJsonString(), "concurrent clones do not mutate cached state");

        using var state = new NativeActorState();
        var projectile = new Projectile(); projectile.SetDefaults(ProjectileID.Bullet);
        var get = typeof(GeneratorClient).GetMethod("ProjectileAttackSource", BindingFlags.NonPublic | BindingFlags.Static)!;
        var native = (ProgramCapture)get.Invoke(null, new object[] { projectile.type, projectile.aiStyle })!;
        string nativeBefore = native.CloneSource().ToJsonString();
        var strict = GeneratorClient.CaptureProjectileAttackReference(projectile);
        var expectedStrict = JsonNode.Parse(nativeBefore)!.AsObject();
        expectedStrict.Remove("mechanicsSource");
        expectedStrict["admission"] = strict["admission"]!.DeepClone();
        Equal(expectedStrict.ToJsonString(), strict.ToJsonString(), "strict consumer equals the old parse projection byte for byte");
        Equal(false, strict.ContainsKey("mechanicsSource"), "strict reference excludes approximate mechanics");
        strict.Clear(); native.CloneMechanics()?.Clear(); native.CloneSpawns().Clear();
        Equal(nativeBefore, native.CloneSource().ToJsonString(), "actual native capture remains unchanged after all consumer mutations");
        Equal(true, ReferenceEquals(native, get.Invoke(null, new object[] { projectile.type, projectile.aiStyle })), "native consumers reuse one captured source");
        var refused = GeneratorClient.VerifiedProjectileAttackReference(projectile, false);
        Equal(false, refused.ContainsKey("identityPredicates"), "module refusal never exposes cached strict source");

        // Real captured native source, same three consumer projections. Include
        // serialized delivery separately; fewer Parse calls alone is not proof.
        foreach (int type in new[] { ProjectileID.Bullet, ProjectileID.LastPrismLaser })
        {
            projectile.SetDefaults(type);
            native = (ProgramCapture)get.Invoke(null, new object[] { projectile.type, projectile.aiStyle })!;
            string text = native.CloneSource().ToJsonString(), spawnText = native.CloneSpawns().ToJsonString();
            JsonNode?[] Previous()
            {
                var full = JsonNode.Parse(text)!.AsObject(); full.Remove("mechanicsSource");
                return new JsonNode?[] { full, JsonNode.Parse(text)!["mechanicsSource"]?.DeepClone(), JsonNode.Parse(spawnText) };
            }
            JsonNode?[] Current()
            {
                var full = native.CloneSource(); full.Remove("mechanicsSource");
                return new JsonNode?[] { full, native.CloneMechanics(), native.CloneSpawns() };
            }
            // The rejected eager-tree approach is measured too, not assumed fast.
            var eager = JsonNode.Parse(text)!; var eagerSpawns = JsonNode.Parse(spawnText)!;
            void Materialize(JsonNode? node)
            {
                if (node is JsonObject obj) foreach (var pair in obj) Materialize(pair.Value);
                else if (node is JsonArray array) foreach (var child in array) Materialize(child);
            }
            Materialize(eager); Materialize(eagerSpawns);
            JsonNode?[] Eager()
            {
                var full = eager.DeepClone().AsObject(); full.Remove("mechanicsSource");
                return new JsonNode?[] { full, eager["mechanicsSource"]?.DeepClone(), eagerSpawns.DeepClone() };
            }
            Equal(string.Join("\n", Previous().Select(n => n?.ToJsonString())), string.Join("\n", Current().Select(n => n?.ToJsonString())), "actual native three-consumer delivery is byte-identical to prior parsing");
            foreach (bool serialize in new[] { false, true })
                foreach (var mode in new (string Name, Func<JsonNode?[]> Read)[] { ("parse", Previous), ("eager", Eager), ("immutable", Current) })
                {
                    for (int warmup = 0; warmup < 3; warmup++) foreach (var node in mode.Read()) if (serialize) _ = node?.ToJsonString();
                    long before = GC.GetAllocatedBytesForCurrentThread();
                    var timer = System.Diagnostics.Stopwatch.StartNew();
                    for (int iteration = 0; iteration < 20; iteration++)
                        foreach (var node in mode.Read())
                            if (serialize) GC.KeepAlive(node?.ToJsonString()); else GC.KeepAlive(node);
                    timer.Stop();
                    Console.WriteLine($"SOURCE_PROGRAM_PERF type={type} chars={native.Characters} serialize={serialize} mode={mode.Name} iterations=20 allocated={GC.GetAllocatedBytesForCurrentThread() - before} elapsedMs={timer.Elapsed.TotalMilliseconds:F3}");
                }
        }
    }
}

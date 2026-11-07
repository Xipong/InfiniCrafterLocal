using System;
using System.Collections;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using InfiniCrafterLocal.Common.Services;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    private static void ParentSourceProjectionMemoPreservesExactOutput()
    {
        Type type = typeof(GeneratorClient).GetNestedType("ParentSourceMethod", BindingFlags.NonPublic)!;
        MethodInfo method = typeof(GraphItem).GetMethod("OnHitNPC")!;
        object body = Activator.CreateInstance(type, BindingFlags.Instance | BindingFlags.NonPublic, null,
            new object?[] { method, null, null, null }, null)!;
        var statements = (IList)type.GetField("Statements", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(body)!;
        var reversed = (IList)Activator.CreateInstance(statements.GetType())!;
        foreach (object value in statements.Cast<object>().Reverse()) reversed.Add(value);
        MethodInfo project = type.GetMethod("Project", BindingFlags.Instance | BindingFlags.NonPublic)!;
        JsonObject Project(object source, IList roots, int limit) => (JsonObject)project.Invoke(source, new object[] { roots, limit })!;
        using var cache = new GeneratorClient.ParentSourceGraphCache();
        foreach (IList roots in new[] { statements, reversed })
            foreach (int limit in new[] { 64, 8, 0 })
            {
                JsonObject expected = Project(body, roots, limit);
                using var scope = cache.Enter();
                JsonObject first = Project(body, roots, limit), second = Project(body, roots, limit);
                Equal(true, JsonNode.DeepEquals(expected, first), "memo miss preserves every source field");
                Equal(true, JsonNode.DeepEquals(expected, second), "memo hit preserves roots order and control limit");
                first.Clear(); second["values"]!.AsObject().Clear();
                Equal(true, JsonNode.DeepEquals(expected, Project(body, roots, limit)), "caller compaction cannot mutate retained projections");
            }
        using var slicedCache = new GeneratorClient.ParentSourceGraphCache();
        object code = type.GetField("Code", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(body)!;
        object sliced = Activator.CreateInstance(type, BindingFlags.Instance | BindingFlags.NonPublic, null,
            new object?[] { method, code, null, null }, null)!;
        var slicedRoots = (IList)type.GetField("Statements", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(sliced)!;
        JsonObject expectedSlice = Project(sliced, slicedRoots, 64);
        using (slicedCache.Enter())
        {
            _ = Project(body, statements, 64);
            Equal(true, JsonNode.DeepEquals(expectedSlice, Project(sliced, slicedRoots, 64)), "identity slice retains its own unresolved CFG provenance");
        }
        string key = "64:" + string.Join(",", statements.Cast<object>().Select(value =>
            type.GetNestedType("Value", BindingFlags.NonPublic)!.GetField("Id", BindingFlags.NonPublic | BindingFlags.Instance)!.GetValue(value)));
        // The complete-body call above populates its key. A fresh slice-only
        // scope must never populate or read a complete-body projection entry.
        using var sliceOnly = new GeneratorClient.ParentSourceGraphCache();
        using (sliceOnly.Enter()) _ = Project(sliced, slicedRoots, 64);
        Equal(false, sliceOnly.TryGetProjection(method, key, out _), "native slices cannot enter complete-method memo");
        ParentSourceGraphProjectionSlicesStayIsolated();
    }


    private static void SourceProjectionIsolationFixture(bool guard, Player player)
    {
        if (guard) player.statDefense += 1;
        else player.statDefense += 2;
    }

    private static void ParentSourceGraphProjectionSlicesStayIsolated()
    {
        Type type = typeof(GeneratorClient).GetNestedType("ParentSourceMethod", BindingFlags.NonPublic)!;
        const BindingFlags fields = BindingFlags.Instance | BindingFlags.NonPublic;
        MethodInfo method = typeof(EngineRuntimeChecks).GetMethod(nameof(SourceProjectionIsolationFixture), BindingFlags.Static | BindingFlags.NonPublic)!;
        object Create(object? slice = null, object? next = null, object? selected = null) =>
            Activator.CreateInstance(type, fields, null, new object?[] { method, slice, next, selected }, null)!;
        object complete = Create();
        var code = (IList)type.GetField("Code", fields)!.GetValue(complete)!;
        int Offset(object instruction) => (int)instruction.GetType().GetProperty("Offset")!.GetValue(instruction)!;
        string Op(object instruction) => (string)instruction.GetType().GetProperty("Op")!.GetValue(instruction)!;
        var next = code.Cast<object>().Zip(code.Cast<object>().Skip(1), (a, b) => (At: Offset(a), Next: Offset(b)))
            .ToDictionary(pair => pair.At, pair => pair.Next);
        var slice = (IList)Activator.CreateInstance(code.GetType())!;
        foreach (object instruction in code) if (Op(instruction) == "ret") slice.Add(instruction);
        Equal(true, slice.Count > 0 && slice.Count < code.Count, "identity test slice genuinely omits instructions");
        var blocks = (IDictionary)type.GetField("Blocks", fields)!.GetValue(complete)!;
        object branch = blocks.Values.Cast<object>().First(block =>
            ((IList)block.GetType().GetField("Next", fields)!.GetValue(block)!).Count == 2);
        int branchAt = (int)branch.GetType().GetField("Start", fields)!.GetValue(branch)!;
        int successor = (int)((IList)branch.GetType().GetField("Next", fields)!.GetValue(branch)!)[0]!;
        var selected = new Dictionary<int, int> { [branchAt] = successor };
        MethodInfo project = type.GetMethod("ProjectForGraph", fields)!;
        var completeValues = (IDictionary)type.GetField("Values", fields)!.GetValue(complete)!;
        string Id(object value) => (string)value.GetType().GetField("Id", fields)!.GetValue(value)!;
        GeneratorClient.SourceGraphProjection Project(object body, IList roots) =>
            (GeneratorClient.SourceGraphProjection)project.Invoke(body, new object[] { roots, 64 })!;
        string Materialize(GeneratorClient.SourceGraphProjection projection)
        {
            var ids = new Dictionary<MemberInfo, int>();
            int Register(MemberInfo member)
            { if (!ids.TryGetValue(member, out int id)) ids.Add(member, id = ids.Count); return id; }
            return projection.Materialize(projection.Bind(Register).Members).ToJsonString();
        }
        foreach (var variant in new[] { (Name: "identity slice with sourceNext", Body: Create(slice, next)),
            (Name: "sourceNext only", Body: Create(next: next)),
            (Name: "selectedSuccessors only", Body: Create(selected: selected)) })
        {
            var roots = (IList)type.GetField("Statements", fields)!.GetValue(variant.Body)!;
            var completeRoots = (IList)Activator.CreateInstance(roots.GetType())!;
            foreach (object root in roots) completeRoots.Add(completeValues[Id(root)]!);
            string key = "64:" + string.Join(",", roots.Cast<object>().Select(Id));
            string expected = Materialize(Project(variant.Body, roots));
            string expectedComplete = Materialize(Project(complete, completeRoots));
            using var cache = new GeneratorClient.ParentSourceGraphCache();
            using (cache.Enter())
            {
                Equal(expectedComplete, Materialize(Project(complete, completeRoots)), variant.Name + " complete miss");
                Equal(true, cache.TryGetGraphProjection(method, key, out _), variant.Name + " colliding complete key is warm");
                Equal(expected, Materialize(Project(variant.Body, roots)), variant.Name + " ignores complete graph cache hit");
                Equal(expectedComplete, Materialize(Project(complete, completeRoots)), variant.Name + " leaves complete template intact");
            }
            using var sliceOnly = new GeneratorClient.ParentSourceGraphCache();
            using (sliceOnly.Enter()) Equal(expected, Materialize(Project(variant.Body, roots)), variant.Name + " uncached result stays exact");
            Equal(false, sliceOnly.TryGetGraphProjection(method, key, out _), variant.Name + " cannot populate graph memo");
        }
    }

    private static void ParentSourceProjectionTemplateUsesExactGraphIndices()
    {
        Type type = typeof(GeneratorClient).GetNestedType("ParentSourceMethod", BindingFlags.NonPublic)!;
        MethodInfo method = typeof(GraphItem).GetMethod("OnHitNPC")!;
        object body = Activator.CreateInstance(type, BindingFlags.Instance | BindingFlags.NonPublic, null,
            new object?[] { method, null, null, null }, null)!;
        object statements = type.GetField("Statements", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(body)!;
        MethodInfo raw = type.GetMethod("Project", BindingFlags.Instance | BindingFlags.NonPublic)!;
        MethodInfo compact = typeof(GeneratorClient).GetMethod("CompactSourceMethod", BindingFlags.Static | BindingFlags.NonPublic)!;
        MethodInfo templateMethod = type.GetMethod("ProjectForGraph", BindingFlags.Instance | BindingFlags.NonPublic)!;
        using var cache = new GeneratorClient.ParentSourceGraphCache();
        using var scope = cache.Enter();
        foreach (int limit in new[] { 64, 8, 0 })
            foreach (int start in new[] { 0, 9, 99, 999 })
            {
                var directMembers = new System.Collections.Generic.Dictionary<MemberInfo, int>();
                int Direct(MemberInfo member)
                { if (!directMembers.TryGetValue(member, out int id)) directMembers[member] = id = start + directMembers.Count; return id; }
                JsonObject original = (JsonObject)raw.Invoke(body, new[] { statements, limit })!;
                JsonObject expected = (JsonObject)compact.Invoke(null, new object[] { original, method, body, (Func<MemberInfo, int>)Direct })!;
                var template = (GeneratorClient.SourceGraphProjection)templateMethod.Invoke(body, new[] { statements, limit })!;
                var rebound = new System.Collections.Generic.Dictionary<MemberInfo, int>();
                int Bind(MemberInfo member)
                { if (!rebound.TryGetValue(member, out int id)) rebound[member] = id = start + rebound.Count; return id; }
                var bound = template.Bind(Bind);
                JsonObject actual = template.Materialize(bound.Members);
                Equal(expected.ToJsonString(), actual.ToJsonString(), "template preserves exact property order, fields and graph indices");
                Equal((long)actual.ToJsonString().Length, bound.Characters, "digit count is exact across 9/10 and 99/100 boundaries");
                Equal(true, directMembers.SequenceEqual(rebound), "rejected candidates register every member in original order");
                actual.Clear();
                Equal(expected.ToJsonString(), template.Materialize(bound.Members).ToJsonString(), "template cannot be changed by a previous materialization");
            }
        const string prefix = "{\"method\":0,\"values\":{},\"padding\":\"";
        const string suffix = "\"}";
        string atLimit = prefix + new string('x', 6500 - prefix.Length - suffix.Length) + suffix;
        var boundary = new GeneratorClient.SourceGraphProjection(atLimit, new MemberInfo[] { method }, new[] { 1 });
        Equal(6500L, boundary.Bind(_ => 9).Characters, "exact accepted character bound");
        Equal(6501L, boundary.Bind(_ => 10).Characters, "next graph index can cross the refused character bound");
        var rejected = new GeneratorClient.SourceGraphProjection(prefix + new string('x', 100000) + suffix,
            new MemberInfo[] { method }, new[] { 1 });
        Equal(true, rejected.RetainedBytes < 1024, "rejected oversized JSON does not evict useful projections");
        Equal(true, rejected.Bind(_ => 9).Characters > GeneratorClient.SourceGraphProjection.CharacterLimit,
            "discarded payload keeps its exact rejection length");

        // Newly reconstructed coverage: existing graph IDs can be narrower than
        // template IDs, so exact rebinding must allow negative digit deltas.
        MemberInfo[] localMembers = typeof(string).GetMethods().Take(11).Cast<MemberInfo>().ToArray();
        var localValues = new JsonObject();
        int[] localUses = Enumerable.Repeat(1, 11).ToArray();
        for (int index = 1; index <= 10; index++)
            localValues[index.ToString()] = new JsonArray(JsonValue.Create("call"), new JsonObject { ["member"] = index });
        localValues["repeat"] = new JsonArray(JsonValue.Create("call"), new JsonObject { ["member"] = 10 });
        localUses[10]++;
        var localRow = new JsonObject { ["method"] = 0, ["values"] = localValues, ["padding"] = "" };
        localRow["padding"] = new string('x', 6501 - localRow.ToJsonString().Length);
        var narrower = new GeneratorClient.SourceGraphProjection(localRow.ToJsonString(), localMembers, localUses);
        var existingIds = localMembers.Select((member, index) => (member, Id: 10 - index)).ToDictionary(pair => pair.member, pair => pair.Id);
        var narrowerBound = narrower.Bind(member => existingIds[member]);
        Equal(6500L, narrowerBound.Characters, "negative digit delta can turn a 6501-character template into an accepted row");
        JsonObject narrowerRow = narrower.Materialize(narrowerBound.Members);
        Equal(6500, narrowerRow.ToJsonString().Length, "negative delta matches actual serialized JSON");
        Equal(10, narrowerRow["method"]!.GetValue<int>(), "root method can rebind to a wider existing graph ID");
        Equal(0, narrowerRow["values"]!["10"]![1]!["member"]!.GetValue<int>(), "wide local member can rebind to narrow existing graph ID");
    }

    private static void ParentSourceProjectionMemoIsBoundedAndRetired()
    {
        MethodInfo method = typeof(GraphConsumer).GetMethod("UpdateLifeRegen")!;
        using var cache = new GeneratorClient.ParentSourceGraphCache(shared: true);
        using (var recent = new GeneratorClient.ParentSourceGraphCache(shared: true))
        {
            for (int index = 0; index < 2048; index++) recent.RememberProjection(method, "key" + index, "{}");
            Equal(true, recent.TryGetProjection(method, "key0", out _), "projection hit refreshes its retention");
            recent.RememberProjection(method, "extra", "{}");
            Equal(true, recent.TryGetProjection(method, "key0", out _), "projection count pressure retains a recently used old key");
            Equal(false, recent.TryGetProjection(method, "key1", out _), "projection count pressure evicts the least recent key");
            Equal(1L, recent.Snapshot().ProjectionEvictions, "one new projection evicts exactly one entry");
        }
        for (int index = 0; index < 2049; index++) cache.RememberProjection(method, "key" + index, "{}");
        Equal(false, cache.TryGetProjection(method, "key0", out _), "projection entry count evicts old keys");
        Equal(true, cache.TryGetProjection(method, "key2048", out _), "latest projection remains available");
        string sizable = new('x', 1024 * 1024);
        for (int index = 0; index < 9; index++) cache.RememberProjection(method, "large" + index, sizable);
        Equal(false, cache.TryGetProjection(method, "large0", out _), "UTF16 byte budget evicts old strings");
        Equal(true, cache.TryGetProjection(method, "large8", out _), "bounded cache admits recent strings");
        long bytes = (long)typeof(GeneratorClient.ParentSourceGraphCache).GetField("projectionBytes", BindingFlags.NonPublic | BindingFlags.Instance)!.GetValue(cache)!;
        Equal(true, bytes <= GeneratorClient.ParentSourceGraphCache.ProjectionByteLimit, "retained keys and JSON fit the byte budget");
        Parallel.For(0, 32, index => { cache.RememberProjection(method, "concurrent" + index, "{}"); cache.TryGetProjection(method, "large8", out _); });
        cache.Dispose();
        cache.RememberProjection(method, "after", "{}");
        Equal(false, cache.TryGetProjection(method, "after", out _), "retired workers cannot repopulate old projection memo");
        Equal(false, cache.TryGetProjection(method, "large8", out _), "retirement releases cached source metadata");

        // Newly reconstructed coverage: stop both workers after the initial
        // cancellation check, while roots are being enumerated, then retire the
        // context. No scheduler timing or sleeps establish this ordering.
        Type sourceType = typeof(GeneratorClient).GetNestedType("ParentSourceMethod", BindingFlags.NonPublic)!;
        MethodInfo sourceMethod = typeof(GraphItem).GetMethod("OnHitNPC")!;
        object source = Activator.CreateInstance(sourceType, BindingFlags.Instance | BindingFlags.NonPublic, null,
            new object?[] { sourceMethod, null, null, null }, null)!;
        var roots = (IEnumerable)sourceType.GetField("Statements", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(source)!;
        string sourceKey = "64:" + string.Join(",", roots.Cast<object>().Select(value =>
            value.GetType().GetField("Id", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(value)));
        MethodInfo project = sourceType.GetMethod("ProjectForGraph", BindingFlags.Instance | BindingFlags.NonPublic)!;
        MethodInfo gatedRoots = typeof(EngineRuntimeChecks).GetMethod(nameof(SourceProjectionGatedRoots), BindingFlags.Static | BindingFlags.NonPublic)!
            .MakeGenericMethod(sourceType.GetNestedType("Value", BindingFlags.NonPublic)!);
        var expected = (GeneratorClient.SourceGraphProjection)project.Invoke(source, new object[] { roots, 64 })!;
        string Materialize(GeneratorClient.SourceGraphProjection projection)
        {
            var ids = new Dictionary<MemberInfo, int>();
            int Register(MemberInfo member)
            { if (!ids.TryGetValue(member, out int id)) ids.Add(member, id = ids.Count); return id; }
            return projection.Materialize(projection.Bind(Register).Members).ToJsonString();
        }
        string expectedJson = Materialize(expected);
        // Warm hits must honor cancellation that happens during root enumeration,
        // after the entry check but before lookup. Both calls deterministically
        // fail without a post-enumeration cancellation check; no timing is involved.
        foreach (string projectionName in new[] { "Project", "ProjectForGraph" })
        {
            using var cancellation = new CancellationTokenSource();
            using var analysis = new GeneratorClient.ParentAnalysis(cancellation.Token);
            using var warmCache = new GeneratorClient.ParentSourceGraphCache();
            using var context = analysis.Enter();
            using var cacheScope = warmCache.Enter();
            MethodInfo warmProject = sourceType.GetMethod(projectionName, BindingFlags.Instance | BindingFlags.NonPublic)!;
            _ = warmProject.Invoke(source, new object[] { roots, 64 });
            Equal(true, projectionName == "Project"
                ? warmCache.TryGetProjection(sourceMethod, sourceKey, out _)
                : warmCache.TryGetGraphProjection(sourceMethod, sourceKey, out _), projectionName + " cancellation test starts with warm key");
            object cancellingRoots = gatedRoots.Invoke(null, new object[] { roots, (Action)cancellation.Cancel })!;
            bool cancelled = false;
            try { warmProject.Invoke(source, new object[] { cancellingRoots, 64 }); }
            catch (TargetInvocationException error) when (error.InnerException is OperationCanceledException) { cancelled = true; }
            Equal(true, cancelled, projectionName + " warm hit propagates cancellation during root enumeration");
        }
        foreach (bool invalidate in new[] { false, true })
        {
            GeneratorClient.ParentAnalysis.Invalidate();
            using var cancellation = new CancellationTokenSource();
            using var analysis = new GeneratorClient.ParentAnalysis(cancellation.Token);
            var oldCache = analysis.SourceCache;
            using var entered = new CountdownEvent(2);
            using var release = new ManualResetEventSlim();
            var workers = new List<Task<bool>>();
            try
            {
                for (int index = 0; index < 2; index++)
                    workers.Add(Task.Run(() =>
                    {
                        using var context = analysis.Enter();
                        Action gate = () => { entered.Signal(); release.Wait(); };
                        object gated = gatedRoots.Invoke(null, new object[] { roots, gate })!;
                        try { project.Invoke(source, new object[] { gated, 64 }); return false; }
                        catch (TargetInvocationException error) when (error.InnerException is OperationCanceledException) { return true; }
                    }));
                Equal(true, entered.Wait(TimeSpan.FromSeconds(30)), "both projections reach deterministic retirement gate");
                if (invalidate) GeneratorClient.ParentAnalysis.Invalidate();
                else cancellation.Cancel();
                release.Set();
                Equal(true, Task.WhenAll(workers).GetAwaiter().GetResult().All(value => value), "every interrupted projection propagates cancellation");
                Equal(false, oldCache.TryGetGraphProjection(sourceMethod, sourceKey, out _), "cancelled construction never publishes a partial template");
                using var fresh = new GeneratorClient.ParentAnalysis();
                if (invalidate)
                    Equal(false, ReferenceEquals(oldCache, fresh.SourceCache), "invalidation replaces the cache used by later captures");
                using (fresh.Enter())
                {
                    var recovered = (GeneratorClient.SourceGraphProjection)project.Invoke(source, new object[] { roots, 64 })!;
                    Equal(expectedJson, Materialize(recovered), "later capture recovers complete template after cancellation or retirement");
                    Equal(true, fresh.SourceCache.TryGetGraphProjection(sourceMethod, sourceKey, out _), "only complete fresh template is published");
                }
                if (invalidate)
                    Equal(false, oldCache.TryGetGraphProjection(sourceMethod, sourceKey, out _), "retired cache stays empty after fresh publication");
            }
            finally
            {
                cancellation.Cancel();
                release.Set();
                Task.WhenAll(workers).GetAwaiter().GetResult();
            }
        }
    }

    private static IEnumerable<T> SourceProjectionGatedRoots<T>(IEnumerable roots, Action gate)
    {
        gate();
        foreach (object value in roots) yield return (T)value;
    }

    private static void ParentSourceRevisitsPreserveEdgesWithoutFrameWaits()
    {
        using var state = new NativeActorState();
        var queue = (ConcurrentQueue<Action>)typeof(GeneratorClient.ParentAnalysis)
            .GetField("mainWork", BindingFlags.Static | BindingFlags.NonPublic)!.GetValue(null)!;
        (JsonNode Result, int Requests) Resolve(int count, bool mixedReceivers)
        {
            using var cancellation = new CancellationTokenSource();
            using var analysis = new GeneratorClient.ParentAnalysis(cancellation.Token);
            var facts = new JsonArray();
            for (int index = 0; index < count; index++) facts.Add(new JsonObject { ["buffId"] = BuffID.Poisoned,
                ["receiver"] = mixedReceivers && index % 2 != 0 ? "player" : "npc" });
            JsonObject marker;
            using (analysis.Enter()) marker = GeneratorClient.CaptureParentSourceGraph(new Item(ItemID.Wood), new JsonObject { ["facts"] = facts });
            var worker = Task.Run(() => analysis.Resolve(marker));
            try
            {
                int requests = 0;
                var elapsed = System.Diagnostics.Stopwatch.StartNew();
                while (!worker.IsCompleted && elapsed.Elapsed < TimeSpan.FromSeconds(60))
                {
                    if (queue.TryDequeue(out var work)) { requests++; work(); }
                    else Thread.Yield();
                }
                Equal(true, worker.IsCompleted, "real repeated source observations finish");
                return (worker.GetAwaiter().GetResult()!, requests);
            }
            finally
            {
                cancellation.Cancel();
                try { worker.GetAwaiter().GetResult(); }
                catch (OperationCanceledException) { }
            }
        }
        var single = Resolve(1, false); var repeated = Resolve(32, false);
        Equal(true, JsonNode.DeepEquals(single.Result, repeated.Result), "repeated identical observations preserve the exact graph");
        Equal(single.Requests, repeated.Requests, "visited buffs add no extra game-thread round trips");
        var mixed = Resolve(32, true);
        var edges = mixed.Result["edges"]!.AsArray().OfType<JsonObject>().Where(edge => edge["kind"]?.GetValue<string>() == "buff_request").ToArray();
        Equal(true, edges.Any(edge => edge["context"]?["receiver"]?.GetValue<string>() == "npc"), "NPC buff request remains");
        Equal(true, edges.Any(edge => edge["context"]?["receiver"]?.GetValue<string>() == "player"), "same-ID player buff request remains independent");
        Equal(true, mixed.Requests <= single.Requests * 2, "each receiver is captured only once within its graph");

        // Newly reconstructed coverage: unavailable samples are retryable, but
        // successful identities retain all subsequent callsite edges without
        // another sample read, even when the sample is then unavailable.
        Type graphType = typeof(GeneratorClient).GetNestedType("ParentSourceGraph", BindingFlags.NonPublic)!;
        object graph = Activator.CreateInstance(graphType, nonPublic: true)!;
        MethodInfo follow = graphType.GetMethod("Projectile", BindingFlags.Instance | BindingFlags.NonPublic)!;
        var visited = (HashSet<int>)graphType.GetField("projectiles", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(graph)!;
        var projectileEdges = (JsonArray)graphType.GetField("edges", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(graph)!;
        int projectileId = ProjectileID.WoodenArrowFriendly;
        bool hadSample = ContentSamples.ProjectilesByType.TryGetValue(projectileId, out Projectile? originalSample);
        void Follow(int from, int at, string kind) => follow.Invoke(graph, new object[] { projectileId, from, at, kind });
        try
        {
            ContentSamples.ProjectilesByType.Remove(projectileId);
            Follow(11, 101, "missing_first"); Follow(12, 102, "missing_again");
            Equal(false, visited.Contains(projectileId), "missing sample never poisons the visited identity set");
            Equal(2, projectileEdges.OfType<JsonObject>().Count(edge => edge["unresolved"]?.GetValue<string>() == "registered_projectile_sample_unavailable"),
                "each unavailable callsite is observed as unavailable, not already visited");
            var child = new Projectile { type = projectileId };
            typeof(Projectile).GetProperty(nameof(Projectile.ModProjectile))!.SetValue(child, new GraphChild());
            ContentSamples.ProjectilesByType[projectileId] = child;
            Follow(13, 103, "sample_restored");
            Equal(true, visited.Contains(projectileId), "same identity retries and observes newly available sample");
            Equal(true, projectileEdges.OfType<JsonObject>().Any(edge => edge["kind"]?.GetValue<string>() == "sample_restored" && edge["to"] is not null),
                "retry discovers the actual projectile implementation");
            ContentSamples.ProjectilesByType.Remove(projectileId);
            Follow(14, 104, "repeat_alpha"); Follow(15, 105, "repeat_beta");
            foreach (var expectedEdge in new[] { (From: 14, At: 104, Kind: "repeat_alpha"), (From: 15, At: 105, Kind: "repeat_beta") })
            {
                var edge = projectileEdges.OfType<JsonObject>().Single(value => value["kind"]?.GetValue<string>() == expectedEdge.Kind);
                Equal(expectedEdge.From, edge["from"]!.GetValue<int>(), "repeated projectile preserves caller node");
                Equal(expectedEdge.At, edge["at"]!.GetValue<int>(), "repeated projectile preserves callsite offset");
                Equal(projectileId, edge["context"]!.GetValue<int>(), "repeated projectile preserves requested identity context");
                Equal("already_visited_projectile_identity", edge["unresolved"]!.GetValue<string>(), "successful revisit uses original snapshot without new sample lookup");
            }
        }
        finally
        {
            if (hadSample) ContentSamples.ProjectilesByType[projectileId] = originalSample!;
            else ContentSamples.ProjectilesByType.Remove(projectileId);
        }
    }
}

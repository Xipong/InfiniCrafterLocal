using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Services;

internal static partial class EngineRuntimeChecks
{
    private static object CreateSourceExportFixture()
    {
        const BindingFlags fields = BindingFlags.Instance | BindingFlags.NonPublic;
        Type type = typeof(GeneratorClient).GetNestedType("ParentSourceGraph", BindingFlags.NonPublic)!;
        object graph = Activator.CreateInstance(type, nonPublic: true)!;
        JsonArray Rows(string name) => (JsonArray)type.GetField(name, fields)!.GetValue(graph)!;
        for (int index = 0; index < 12; index++) Rows("modules").Add(new JsonObject { ["name"] = "module " + index, ["tag"] = "😀日本語" });
        for (int index = 0; index < 132; index++) Rows("members").Add(new JsonObject { ["module"] = index % 12, ["name"] = "member\"" + index });
        var projections = (IDictionary)type.GetField("projections", fields)!.GetValue(graph)!;
        object projection = Activator.CreateInstance(projections.GetType().GetGenericArguments()[1])!;
        for (int index = 0; index < 128; index++)
        {
            Rows("nodes").Add(new JsonObject
            {
                ["id"] = index, ["method"] = index, ["receiverType"] = 131 - index,
                ["originReceiverType"] = index % 13,
                ["values"] = new JsonObject { ["0"] = new JsonArray("ldfld", new JsonObject { ["member"] = (index + 11) % 132 }, new JsonArray(), 0) },
                ["statements"] = new JsonArray("0"), ["blocks"] = new JsonArray(), ["label"] = "a\\b\"c\n😀" + index,
            });
            if (index % 5 == 0) Rows("nodes")[index]!.AsObject().Remove("values");
            if (index % 3 == 0) Rows("nodes")[index]!["omittedStatementCount"] = index;
            projections.Add(index, projection);
            Rows("roots").Add(new JsonObject { ["node"] = index, ["role"] = "root" + index });
            foreach (int offset in new[] { 0, 7, 8 })
                Rows("edges").Add(new JsonObject
                {
                    ["from"] = index, ["to"] = (index + 1) % 128, ["kind"] = "call", ["at"] = offset,
                    ["context"] = new JsonObject { ["value"] = index % 3, ["text"] = "😀" },
                    ["unresolved"] = offset == 8 ? "unknown_identity" : null,
                });
            Rows("edges").Add(new JsonObject { ["from"] = null, ["to"] = index, ["kind"] = "dispatch", ["context"] = index });
            Rows("edges").Add(new JsonObject { ["from"] = index, ["kind"] = "unknown", ["at"] = 8,
                ["sourceCoverage"] = "existing_reason", ["context"] = "not_identity", ["unresolved"] = "unknown_receiver" });
        }
        Rows("gaps").Add("precise_refusal");
        return graph;
    }

    private static void ParentSourceExportPlanMatchesCloneOracle()
    {
        const BindingFlags fields = BindingFlags.Instance | BindingFlags.NonPublic;
        object graph = CreateSourceExportFixture();
        Type type = graph.GetType();
        JsonArray Rows(string name) => (JsonArray)type.GetField(name, fields)!.GetValue(graph)!;
        var planner = type.GetMethod("PlanExport", fields)!;
        object measurements = Activator.CreateInstance(type.GetNestedType("ExportMeasurements", BindingFlags.NonPublic)!, nonPublic: true)!;
        int compared = 0;
        foreach (int count in new[] { 0, 1, 9, 10, 11, 31, 32 })
        {
            var chosen = Enumerable.Range(0, count).Select(index => (index * 7 + 9) % 128)
                .ToDictionary(index => index, index => Rows("nodes")[index]!.AsObject());
            foreach (int budget in new[] { 2000, 9999, 10000, 15000, 30000, 50000 })
            {
                object plan = planner.Invoke(graph, new object[] { chosen, budget, measurements })!;
                JsonObject Materialize() => (JsonObject)plan.GetType().GetMethod("Materialize", fields)!.Invoke(plan, null)!;
                string expected = SourceExportCloneOracle(graph, chosen, budget).ToJsonString();
                JsonObject result = Materialize();
                Equal(expected, result.ToJsonString(), $"export bytes count={count} budget={budget}");
                Equal(expected.Length, (int)plan.GetType().GetField("Characters", fields)!.GetValue(plan)!, "count exactly equals serialized UTF-16 length");
                result["nodes"]!.AsArray().Clear();
                Equal(expected, Materialize().ToJsonString(), "materialization cannot mutate frozen rows or later trials");
                compared++;
            }
        }
        Equal(42, compared, "all graph-index and budget cases ran");
    }

    // Independent pre-optimization transport oracle. Preserve the clone/serialize
    // implementation here to exercise exact index remapping and edge admission.
        private static JsonObject SourceExportCloneOracle(object graph, Dictionary<int, JsonObject> chosen, int characterBudget)
        {
            const BindingFlags fields = BindingFlags.Instance | BindingFlags.NonPublic;
            Type graphType = graph.GetType();
            JsonArray Rows(string name) => (JsonArray)graphType.GetField(name, fields)!.GetValue(graph)!;
            int Limit(string name) => (int)graphType.GetField(name, BindingFlags.Static | BindingFlags.NonPublic)!.GetRawConstantValue()!;
            var nodes = Rows("nodes"); var members = Rows("members"); var modules = Rows("modules");
            var roots = Rows("roots"); var edges = Rows("edges"); var gaps = Rows("gaps");
            var projections = (IDictionary)graphType.GetField("projections", fields)!.GetValue(graph)!;
            int omittedDiscoveryRoots = (int)graphType.GetField("omittedDiscoveryRoots", fields)!.GetValue(graph)!;
            int NodeLimit = Limit("NodeLimit"), EdgeLimit = Limit("EdgeLimit"), DepthLimit = Limit("DepthLimit");
            int CharacterLimit = Limit("CharacterLimit"), CatalogCoverageReserve = Limit("CatalogCoverageReserve");
            int DiscoveryNodeLimit = Limit("DiscoveryNodeLimit"), DiscoveryEdgeLimit = Limit("DiscoveryEdgeLimit");
            var nodeIds = chosen.Keys.OrderBy(id => id).Select((id, next) => (id, next)).ToDictionary(p => p.id, p => p.next);
            var exportedNodes = new JsonArray();
            var usedMembers = new HashSet<int>();
            foreach (int id in nodeIds.Keys)
            {
                var row = chosen[id].DeepClone().AsObject();
                row["id"] = nodeIds[id];
                usedMembers.Add(row["method"]!.GetValue<int>());
                foreach (string context in new[] { "receiverType", "originReceiverType" })
                    if (row[context] is JsonNode type) usedMembers.Add(type.GetValue<int>());
                if (row["values"] is JsonObject values)
                    foreach (var value in values)
                        if (value.Value?[1] is JsonObject operand && operand["member"] is JsonNode member) usedMembers.Add(member.GetValue<int>());
                exportedNodes.Add(row);
            }
            var memberIds = usedMembers.OrderBy(id => id).Select((id, next) => (id, next)).ToDictionary(p => p.id, p => p.next);
            var exportedMembers = new JsonArray();
            var usedModules = usedMembers.Select(id => members[id]!["module"]!.GetValue<int>()).Distinct().OrderBy(id => id).ToArray();
            var moduleIds = usedModules.Select((id, next) => (id, next)).ToDictionary(p => p.id, p => p.next);
            foreach (int id in memberIds.Keys)
            {
                var row = members[id]!.DeepClone().AsObject();
                row["module"] = moduleIds[row["module"]!.GetValue<int>()];
                exportedMembers.Add(row);
            }
            foreach (JsonObject row in exportedNodes.OfType<JsonObject>())
            {
                row["method"] = memberIds[row["method"]!.GetValue<int>()];
                foreach (string context in new[] { "receiverType", "originReceiverType" })
                    if (row[context] is JsonNode type) row[context] = memberIds[type.GetValue<int>()];
                if (row["values"] is JsonObject values)
                    foreach (var value in values)
                        if (value.Value?[1] is JsonObject operand && operand["member"] is JsonNode member)
                            operand["member"] = memberIds[member.GetValue<int>()];
            }
            var exportedRoots = new JsonArray();
            foreach (var root in roots.OfType<JsonObject>())
                if (root["node"] is JsonNode id && nodeIds.TryGetValue(id.GetValue<int>(), out int mapped))
                {
                    var row = root.DeepClone().AsObject(); row["node"] = mapped; exportedRoots.Add(row);
                }
            var exportedEdges = new JsonArray();
            var candidateEdges = new List<JsonObject>();
            foreach (var edge in edges.OfType<JsonObject>())
            {
                int? from = edge["from"]?.GetValue<int>(), to = edge["to"]?.GetValue<int>();
                if (from is int source && !chosen.ContainsKey(source)) continue;
                if (from is null && to is int destination && !chosen.ContainsKey(destination)) continue;
                var row = edge.DeepClone().AsObject();
                if (from is int f)
                {
                    row["from"] = nodeIds[f];
                    if (edge["at"] is JsonNode at && (chosen[f]["values"] is not JsonObject values
                        || !values.ContainsKey(at.GetValue<int>().ToString(CultureInfo.InvariantCulture))))
                        row["sourceCoverage"] = "callsite_omitted_from_source_slice";
                }
                if (to is int t)
                {
                    if (nodeIds.TryGetValue(t, out int mapped)) row["to"] = mapped;
                    else { row.Remove("to"); row["unresolved"] = "source_character_bound"; }
                }
                candidateEdges.Add(row);
            }
            int omittedNodes = nodes.Count - chosen.Count;
            int omittedRoots = roots.Count - exportedRoots.Count + omittedDiscoveryRoots;
            int omittedBodies = chosen.Count(p => projections.Contains(p.Key) && p.Value["values"] is null);
            bool partial = gaps.Count > 0 || omittedNodes > 0 || omittedRoots > 0 || omittedBodies > 0
                || chosen.Values.Any(row => row["omittedStatementCount"] is not null || row["unresolvedEnclosingBranchCount"] is not null
                    || row["unresolvedLocalDependencyCount"] is not null || row["unresolved"] is JsonArray unknown && unknown.Count > 0);
            var unresolved = gaps.DeepClone().AsArray();
            if (omittedNodes > 0 || omittedBodies > 0) unresolved.Add("source_character_bound");
            if (chosen.Count == NodeLimit && omittedNodes > 0) unresolved.Add("node_limit");
            if (candidateEdges.Count > 0) unresolved.Add("edge_export_bound");
            var result = new JsonObject
            {
                ["source"] = "parent_reachable_compiled_source_graph", ["version"] = 1,
                ["roots"] = exportedRoots, ["nodes"] = exportedNodes, ["members"] = exportedMembers,
                ["modules"] = new JsonArray(usedModules.Select(id => modules[id]!.DeepClone()).ToArray()),
                ["edges"] = exportedEdges, ["unresolved"] = unresolved,
                ["scope"] = "Read-only source, never inherited execution or final stats/DPS. values: [IL opcode, operand, input IDs, block]. {member:N}/node.method/receiverType/originReceiverType reference members[N]; module references modules[N]. blocks: [offset, successors, branch-value ID, required enclosing branch IDs]; targets outside this slice stay unresolved. ldloc/predecessor definitions are alternatives, not independent rolls. Helpers bind caller inputs to argument slots (instance this=0). All statements require control to reach their offsets. Roots, virtual bodies and registered globals/players are dispatch candidates; current immunity registrations are not target admission. nativeIdentity distinguishes certified identity CFG from conditional source windows; live predicates are never evaluated. Native units/operators are not final stat multipliers. No hooks/helpers/getters/constructors ran. Runtime detours, missing edges and omitted source remain unknown. Discovery is independent of export; sourceCoverage marks edges whose callsite is not in the exported slice.",
                ["limits"] = new JsonObject { ["nodes"] = NodeLimit, ["edges"] = EdgeLimit, ["helperDepth"] = DepthLimit,
                    ["characters"] = CharacterLimit, ["allocatedCharacters"] = characterBudget + CatalogCoverageReserve,
                    ["reservedCatalogCoverageCharacters"] = CatalogCoverageReserve, ["discoveryNodes"] = DiscoveryNodeLimit, ["discoveryEdges"] = DiscoveryEdgeLimit },
                ["externalPlayerContext"] = new JsonObject { ["unlinkedHookCount"] = 0,
                    ["scope"] = "Unlinked registered player effects are outside parent-owned mechanics, not proven inactive. Hook outputs, item/projectile-conditioned candidates and parent-state consumers remain conditional source." },
                ["omittedNodeCount"] = omittedNodes, ["omittedRootCount"] = omittedRoots, ["omittedBodyCount"] = omittedBodies,
                ["omittedEdgeCount"] = candidateEdges.Count,
                ["completeness"] = "partial_source_graph",
            };
            // Count metadata/refusals first, then allocate remaining transport
            // to edges. Edge-heavy discovery must not reject every method.
            // Retained causal links precede out-of-slice and standalone edges.
            int characters = result.ToJsonString().Length + 64; // Final status/count changes must fit too.
            var linked = new HashSet<int>();
            var orderedEdges = candidateEdges.Select(edge => (Edge: edge,
                Priority: edge["to"] is JsonNode target && linked.Add(target.GetValue<int>()) ? 0
                    : edge["from"] is not null && edge["to"] is not null ? 1 : edge["to"] is not null ? 2 : 3));
            var opaqueLinks = new HashSet<(int? From, int? To, string Kind, string Reason, string Identity)>();
            foreach (var candidate in orderedEdges.OrderBy(candidate => candidate.Priority))
            {
                if (exportedEdges.Count >= EdgeLimit) break;
                var edge = candidate.Edge;
                if (edge["sourceCoverage"] is not null)
                {
                    // One explicit unresolved anchor preserves reachability.
                    // Repeated calls absent from the retained source are not a
                    // useful substitute for the omitted body and its guards.
                    string identity = edge["context"] is JsonObject || edge["context"] is JsonValue literal && literal.TryGetValue<int>(out _)
                        ? edge["context"]!.ToJsonString() : "";
                    var key = (edge["from"]?.GetValue<int>(), edge["to"]?.GetValue<int>(), edge["kind"]?.GetValue<string>() ?? "",
                        edge["unresolved"]?.GetValue<string>() ?? "", identity);
                    // A missing destination can carry the only precise refusal
                    // (unknown virtual receiver, identity, native window, etc.).
                    // Keep one such witness instead of erasing its reason.
                    if (!opaqueLinks.Add(key)) continue;
                }
                int cost = edge.ToJsonString().Length + (exportedEdges.Count > 0 ? 1 : 0);
                if (characters + cost > characterBudget) continue;
                exportedEdges.Add(edge); characters += cost;
            }
            int omittedEdges = candidateEdges.Count - exportedEdges.Count;
            result["omittedEdgeCount"] = omittedEdges;
            if (candidateEdges.Count > 0 && omittedEdges == 0) unresolved.RemoveAt(unresolved.Count - 1);
            result["completeness"] = partial || omittedEdges > 0 ? "partial_source_graph" : "bounded_source_graph; runtime_dispatch_unknown";
            return result;
        }
}

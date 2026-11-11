#nullable enable
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text.Json.Nodes;

namespace InfiniCrafterLocal.Common.Services;

public sealed partial class GeneratorClient
{
    private sealed partial class ParentSourceGraph
    {
        // Exact transport normalization: remap only graph indices. Nothing here
        // changes source selection, admission budgets or the edge ranking policy.
        private static int IndexCharacters(int value) => value.ToString(CultureInfo.InvariantCulture).Length;

        private sealed class ExportMeasurements
        {
            private readonly Dictionary<JsonNode, int> lengths = new(ReferenceEqualityComparer.Instance);
            private readonly Dictionary<JsonObject, int[]> memberReferences = new(ReferenceEqualityComparer.Instance);

            internal int Length(JsonNode? row)
            {
                if (row is null) return 4;
                if (!lengths.TryGetValue(row, out int length)) lengths.Add(row, length = row.ToJsonString().Length);
                return length;
            }

            internal int[] Members(JsonObject row)
            {
                if (memberReferences.TryGetValue(row, out var retained)) return retained;
                var references = new List<int> { row["method"]!.GetValue<int>() };
                foreach (string context in new[] { "receiverType", "originReceiverType" })
                    if (row[context] is JsonNode type) references.Add(type.GetValue<int>());
                if (row["values"] is JsonObject values)
                    foreach (var value in values)
                        if (value.Value?[1] is JsonObject operand && operand["member"] is JsonNode member)
                            references.Add(member.GetValue<int>());
                memberReferences.Add(row, retained = references.ToArray());
                return retained;
            }
        }

        private sealed class ExportEdge
        {
            internal readonly JsonObject Source;
            internal readonly int? From, To;
            internal readonly bool OmittedCallsite, OmittedTarget;
            internal ExportEdge(JsonObject source, int? from, int? to, bool omittedCallsite, bool omittedTarget)
            { Source = source; From = from; To = to; OmittedCallsite = omittedCallsite; OmittedTarget = omittedTarget; }

            internal int Characters(Dictionary<int, int> nodeIds, ExportMeasurements measurements)
            {
                int length = measurements.Length(Source), count = Source.Count;
                void Replace(string key, int replacementLength)
                {
                    if (Source.TryGetPropertyValue(key, out var prior)) length += replacementLength - measurements.Length(prior);
                    else { length += key.Length + 3 + replacementLength + (count > 0 ? 1 : 0); count++; }
                }
                if (From is int from) Replace("from", IndexCharacters(nodeIds[from]));
                if (OmittedCallsite) Replace("sourceCoverage", "\"callsite_omitted_from_source_slice\"".Length);
                if (To is int to) Replace("to", IndexCharacters(nodeIds[to]));
                else if (OmittedTarget)
                {
                    length -= "to".Length + 3 + measurements.Length(Source["to"]) + (count > 1 ? 1 : 0);
                    count--;
                    Replace("unresolved", "\"source_character_bound\"".Length);
                }
                return length;
            }

            internal JsonObject Materialize(Dictionary<int, int> nodeIds)
            {
                var row = Source.DeepClone().AsObject();
                if (From is int from) row["from"] = nodeIds[from];
                if (OmittedCallsite) row["sourceCoverage"] = "callsite_omitted_from_source_slice";
                if (To is int to) row["to"] = nodeIds[to];
                else if (OmittedTarget) { row.Remove("to"); row["unresolved"] = "source_character_bound"; }
                return row;
            }
        }

        private sealed class ExportPlan
        {
            internal readonly JsonObject Header;
            internal readonly KeyValuePair<int, JsonObject>[] Nodes, Members;
            internal readonly JsonNode[] Modules;
            internal readonly JsonObject[] Roots;
            internal readonly List<ExportEdge> Edges;
            internal readonly Dictionary<int, int> NodeIds, MemberIds, ModuleIds;
            internal readonly int Characters;

            internal ExportPlan(JsonObject header, KeyValuePair<int, JsonObject>[] nodes,
                KeyValuePair<int, JsonObject>[] members, JsonNode[] modules, JsonObject[] roots, List<ExportEdge> edges,
                Dictionary<int, int> nodeIds, Dictionary<int, int> memberIds, Dictionary<int, int> moduleIds, int characters)
            {
                Header = header; Nodes = nodes; Members = members; Modules = modules; Roots = roots; Edges = edges;
                NodeIds = nodeIds; MemberIds = memberIds; ModuleIds = moduleIds; Characters = characters;
            }

            internal bool RetainsRootPaths(HashSet<int> discoveryRoots)
            {
                var reached = Roots.Select(root => root["node"]!.GetValue<int>()).ToHashSet();
                var outgoing = new Dictionary<int, List<int>>();
                foreach (var edge in Edges)
                {
                    if (edge.To is not int to) continue;
                    if (edge.From is not int from) { if (discoveryRoots.Contains(to)) reached.Add(to); continue; }
                    if (!outgoing.TryGetValue(from, out var next)) outgoing[from] = next = new();
                    next.Add(to);
                }
                var work = new Queue<int>(reached);
                while (work.Count > 0)
                    if (outgoing.TryGetValue(work.Dequeue(), out var next))
                        foreach (int to in next) if (reached.Add(to)) work.Enqueue(to);
                // A local incoming edge cannot keep an unrooted cycle alive.
                return reached.Count == Nodes.Length;
            }

            internal JsonObject Materialize()
            {
                currentParentAnalysis?.ThrowIfCancelled();
                var result = Header.DeepClone().AsObject();
                foreach (var (id, source) in Nodes)
                {
                    var row = source.DeepClone().AsObject();
                    row["id"] = NodeIds[id]; row["method"] = MemberIds[row["method"]!.GetValue<int>()];
                    foreach (string context in new[] { "receiverType", "originReceiverType" })
                        if (row[context] is JsonNode type) row[context] = MemberIds[type.GetValue<int>()];
                    if (row["values"] is JsonObject values)
                        foreach (var value in values)
                            if (value.Value?[1] is JsonObject operand && operand["member"] is JsonNode member)
                                operand["member"] = MemberIds[member.GetValue<int>()];
                    result["nodes"]!.AsArray().Add(row);
                }
                foreach (var (_, source) in Members)
                {
                    var row = source.DeepClone().AsObject();
                    row["module"] = ModuleIds[row["module"]!.GetValue<int>()]; result["members"]!.AsArray().Add(row);
                }
                foreach (var module in Modules) result["modules"]!.AsArray().Add(module.DeepClone());
                foreach (var source in Roots)
                {
                    var row = source.DeepClone().AsObject();
                    row["node"] = NodeIds[row["node"]!.GetValue<int>()]; result["roots"]!.AsArray().Add(row);
                }
                foreach (var edge in Edges) result["edges"]!.AsArray().Add(edge.Materialize(NodeIds));
                return result;
            }
        }

        private ExportPlan PlanExport(Dictionary<int, JsonObject> chosen, int characterBudget, ExportMeasurements measurements)
        {
            currentParentAnalysis?.ThrowIfCancelled();
            var nodeIds = chosen.Keys.OrderBy(id => id).Select((id, next) => (id, next)).ToDictionary(p => p.id, p => p.next);
            var sourceNodes = nodeIds.Keys.Select(id => new KeyValuePair<int, JsonObject>(id, chosen[id])).ToArray();
            var usedMembers = sourceNodes.SelectMany(pair => measurements.Members(pair.Value)).ToHashSet();
            var memberIds = usedMembers.OrderBy(id => id).Select((id, next) => (id, next)).ToDictionary(p => p.id, p => p.next);
            var sourceMembers = memberIds.Keys.Select(id => new KeyValuePair<int, JsonObject>(id, members[id]!.AsObject())).ToArray();
            var usedModules = usedMembers.Select(id => members[id]!["module"]!.GetValue<int>()).Distinct().OrderBy(id => id).ToArray();
            var moduleIds = usedModules.Select((id, next) => (id, next)).ToDictionary(p => p.id, p => p.next);
            var sourceModules = usedModules.Select(id => modules[id]!).ToArray();
            var sourceRoots = roots.OfType<JsonObject>().Where(root => root["node"] is JsonNode id && nodeIds.ContainsKey(id.GetValue<int>())).ToArray();
            int arrayCharacters = Math.Max(0, sourceNodes.Length - 1) + Math.Max(0, sourceMembers.Length - 1)
                + Math.Max(0, sourceModules.Length - 1) + Math.Max(0, sourceRoots.Length - 1);
            foreach (var (id, row) in sourceNodes)
            {
                arrayCharacters += measurements.Length(row) + IndexCharacters(nodeIds[id]) - measurements.Length(row["id"]);
                foreach (int member in measurements.Members(row))
                    arrayCharacters += IndexCharacters(memberIds[member]) - IndexCharacters(member);
            }
            foreach (var (_, row) in sourceMembers)
                arrayCharacters += measurements.Length(row) + IndexCharacters(moduleIds[row["module"]!.GetValue<int>()]) - measurements.Length(row["module"]);
            foreach (var row in sourceModules) arrayCharacters += measurements.Length(row);
            foreach (var row in sourceRoots)
                arrayCharacters += measurements.Length(row) + IndexCharacters(nodeIds[row["node"]!.GetValue<int>()]) - measurements.Length(row["node"]);
            var candidateEdges = new List<ExportEdge>();
            foreach (var edge in edges.OfType<JsonObject>())
            {
                int? from = edge["from"]?.GetValue<int>(), to = edge["to"]?.GetValue<int>();
                if (from is int source && !chosen.ContainsKey(source)) continue;
                if (from is null && to is int destination && !chosen.ContainsKey(destination)) continue;
                bool omittedCallsite = from is int f && edge["at"] is JsonNode at && (chosen[f]["values"] is not JsonObject values
                    || !values.ContainsKey(at.GetValue<int>().ToString(CultureInfo.InvariantCulture)));
                bool omittedTarget = to is int t && !nodeIds.ContainsKey(t);
                candidateEdges.Add(new ExportEdge(edge, from, omittedTarget ? null : to, omittedCallsite, omittedTarget));
            }
            int omittedNodes = nodes.Count - chosen.Count;
            int omittedRoots = roots.Count - sourceRoots.Length + omittedDiscoveryRoots;
            int omittedBodies = chosen.Count(p => projections.ContainsKey(p.Key) && p.Value["values"] is null);
            bool partial = gaps.Count > 0 || omittedNodes > 0 || omittedRoots > 0 || omittedBodies > 0
                || chosen.Values.Any(row => row["omittedStatementCount"] is not null || row["unresolvedEnclosingBranchCount"] is not null
                    || row["unresolvedLocalDependencyCount"] is not null || row["unresolved"] is JsonArray unknown && unknown.Count > 0);
            var unresolved = gaps.DeepClone().AsArray();
            if (omittedNodes > 0 || omittedBodies > 0) unresolved.Add("source_character_bound");
            if (chosen.Count == NodeLimit && omittedNodes > 0) unresolved.Add("node_limit");
            if (candidateEdges.Count > 0) unresolved.Add("edge_export_bound");
            var header = new JsonObject
            {
                ["source"] = "parent_reachable_compiled_source_graph", ["version"] = 1,
                ["roots"] = new JsonArray(), ["nodes"] = new JsonArray(), ["members"] = new JsonArray(),
                ["modules"] = new JsonArray(), ["edges"] = new JsonArray(), ["unresolved"] = unresolved,
                ["scope"] = "Read-only source, never inherited execution or final stats/DPS. values: [IL opcode, operand, input IDs, block]. {member:N}/node.method/receiverType/originReceiverType reference members[N]; module references modules[N]. blocks: [offset, successors, branch-value ID, required enclosing branch IDs]; targets outside this slice stay unresolved. ldloc/predecessor definitions are alternatives, not independent rolls. Helpers bind caller inputs to argument slots (instance this=0). All statements require control to reach their offsets. Roots, virtual bodies and registered globals/players are dispatch candidates; current immunity registrations are not target admission. nativeIdentity distinguishes certified identity CFG from conditional source windows; live predicates are never evaluated. Native units/operators are not final stat multipliers. No hooks/helpers/getters/constructors ran. Runtime detours, missing edges and omitted source remain unknown. Discovery is independent of export; sourceCoverage marks edges whose callsite is not in the exported slice.",
                ["limits"] = new JsonObject { ["nodes"] = NodeLimit, ["edges"] = EdgeLimit, ["helperDepth"] = DepthLimit,
                    ["characters"] = CharacterLimit, ["allocatedCharacters"] = characterBudget + CatalogCoverageReserve,
                    ["reservedCatalogCoverageCharacters"] = CatalogCoverageReserve, ["discoveryNodes"] = DiscoveryNodeLimit, ["discoveryEdges"] = DiscoveryEdgeLimit },
                ["omittedNodeCount"] = omittedNodes, ["omittedRootCount"] = omittedRoots, ["omittedBodyCount"] = omittedBodies,
                ["omittedEdgeCount"] = candidateEdges.Count, ["completeness"] = "partial_source_graph",
            };
            int characters = header.ToJsonString().Length + arrayCharacters + 64;
            var linked = new HashSet<int>();
            var orderedEdges = candidateEdges.Select(edge => (Edge: edge,
                Priority: edge.To is int target && linked.Add(target) ? 0
                    : edge.From is not null && edge.To is not null ? 1 : edge.To is not null ? 2 : 3));
            var opaqueLinks = new HashSet<(int? From, int? To, string Kind, string Reason, string Identity)>();
            var retainedEdges = new List<ExportEdge>();
            int edgeCharacters = 0;
            foreach (var candidate in orderedEdges.OrderBy(candidate => candidate.Priority))
            {
                if (retainedEdges.Count >= EdgeLimit) break;
                var edge = candidate.Edge;
                if (edge.OmittedCallsite || edge.Source["sourceCoverage"] is not null)
                {
                    string identity = edge.Source["context"] is JsonObject || edge.Source["context"] is JsonValue literal && literal.TryGetValue<int>(out _)
                        ? edge.Source["context"]!.ToJsonString() : "";
                    var key = (edge.From, edge.To, edge.Source["kind"]?.GetValue<string>() ?? "",
                        edge.OmittedTarget ? "source_character_bound" : edge.Source["unresolved"]?.GetValue<string>() ?? "", identity);
                    if (!opaqueLinks.Add(key)) continue;
                }
                int cost = edge.Characters(nodeIds, measurements) + (retainedEdges.Count > 0 ? 1 : 0);
                if (characters + cost > characterBudget) continue;
                retainedEdges.Add(edge); characters += cost; edgeCharacters += cost;
            }
            int omittedEdges = candidateEdges.Count - retainedEdges.Count;
            header["omittedEdgeCount"] = omittedEdges;
            if (candidateEdges.Count > 0 && omittedEdges == 0) unresolved.RemoveAt(unresolved.Count - 1);
            header["completeness"] = partial || omittedEdges > 0 ? "partial_source_graph" : "bounded_source_graph; runtime_dispatch_unknown";
            return new ExportPlan(header, sourceNodes, sourceMembers, sourceModules, sourceRoots, retainedEdges,
                nodeIds, memberIds, moduleIds, header.ToJsonString().Length + arrayCharacters + edgeCharacters);
        }
    }
}

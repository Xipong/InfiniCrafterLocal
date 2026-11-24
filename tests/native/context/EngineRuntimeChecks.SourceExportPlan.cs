using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Services;

internal static partial class EngineRuntimeChecks
{
    private static void ParentSourceExportPreservesResolvableReferences()
    {
        // Inject source rows only to isolate export from IL-discovery variation.
        // Assert what the wire consumer sees, not the old clone implementation.
        const BindingFlags fields = BindingFlags.Instance | BindingFlags.NonPublic;
        Type type = typeof(GeneratorClient).GetNestedType("ParentSourceGraph", BindingFlags.NonPublic)!;
        object graph = Activator.CreateInstance(type, nonPublic: true)!;
        JsonArray Rows(string name) => (JsonArray)type.GetField(name, fields)!.GetValue(graph)!;

        foreach (string name in new[] { "unused", "Vanilla", "AddOn" })
            Rows("modules").Add(new JsonObject { ["name"] = name });
        foreach (var (module, name) in new[] { (0, "unused"), (1, "parent"), (0, "omitted"), (2, "helper") })
            Rows("members").Add(new JsonObject { ["module"] = module, ["name"] = name });

        var parent = new JsonObject { ["id"] = 0, ["method"] = 1, ["receiverType"] = 1,
            ["values"] = new JsonObject { ["7"] = new JsonArray("call", new JsonObject { ["member"] = 3 }, new JsonArray(), 0) } };
        var helper = new JsonObject { ["id"] = 2, ["method"] = 3, ["originReceiverType"] = 1, ["label"] = "a\"😀" };
        foreach (var node in new[] { parent, new JsonObject { ["id"] = 1, ["method"] = 2 }, helper })
            Rows("nodes").Add(node);
        Rows("roots").Add(new JsonObject { ["node"] = 2, ["role"] = "fixture" });
        foreach (int target in new[] { 2, 1, 1 })
            Rows("edges").Add(new JsonObject { ["from"] = 0, ["to"] = target, ["kind"] = "call", ["at"] = target == 2 ? 7 : 8 });
        Rows("gaps").Add("fixture_refusal");

        object measurements = Activator.CreateInstance(type.GetNestedType("ExportMeasurements", BindingFlags.NonPublic)!, nonPublic: true)!;
        var chosen = new Dictionary<int, JsonObject> { [2] = helper, [0] = parent };
        const int budget = 5000;
        object plan = type.GetMethod("PlanExport", fields)!.Invoke(graph, new object[] { chosen, budget, measurements })!;
        JsonObject Materialize() => (JsonObject)plan.GetType().GetMethod("Materialize", fields)!.Invoke(plan, null)!;
        JsonObject exported = Materialize();

        string MemberName(JsonNode? index) => exported["members"]![index!.GetValue<int>()]!["name"]!.GetValue<string>();
        string ModuleName(JsonNode? index)
        {
            JsonNode member = exported["members"]![index!.GetValue<int>()]!;
            return exported["modules"]![member["module"]!.GetValue<int>()]!["name"]!.GetValue<string>();
        }
        var nodes = exported["nodes"]!.AsArray();
        Equal("0,1", string.Join(",", nodes.Select(node => node!["id"]!.GetValue<int>())), "consumer uses compact node indexes");
        Equal(1, exported["roots"]![0]!["node"]!.GetValue<int>(), "root keeps its actual target");
        Equal("parent", MemberName(nodes[0]!["method"]), "node resolves original source identity");
        Equal("Vanilla", ModuleName(nodes[0]!["receiverType"]), "receiver resolves the original module");
        Equal("parent", MemberName(nodes[1]!["originReceiverType"]), "origin receiver retains the parent member");
        Equal("helper", MemberName(nodes[0]!["values"]!["7"]![1]!["member"]), "call operand resolves the original helper");
        Equal("AddOn", ModuleName(nodes[1]!["method"]), "helper resolves the original module");
        Equal(2, exported["modules"]!.AsArray().Count, "unused modules need not be emitted");
        var edges = exported["edges"]!.AsArray();
        Equal(2, edges.Count, "duplicate opaque edge uses one witness");
        Equal(1, edges.Single(edge => edge!["to"] is not null)!["to"]!.GetValue<int>(), "resolved edge still points to helper");
        var omitted = edges.Single(edge => edge!["to"] is null)!;
        Equal("source_character_bound", omitted["unresolved"]!.GetValue<string>(), "omitted target remains explicitly unknown");
        Equal("callsite_omitted_from_source_slice", omitted["sourceCoverage"]!.GetValue<string>(), "unavailable callsite is not silently claimed");
        Equal(true, exported["unresolved"]!.AsArray().Any(row => row!.GetValue<string>() == "fixture_refusal"), "prior refusal survives export");
        string packet = exported.ToJsonString();
        Equal(true, packet.Length <= budget, "serialized graph fits the transport budget");
        exported["nodes"]!.AsArray().Clear();
        Equal(packet, Materialize().ToJsonString(), "one consumer cannot corrupt a later materialization");
    }
}

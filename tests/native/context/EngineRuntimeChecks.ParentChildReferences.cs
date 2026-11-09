using System;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Services;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    private static int ChildReferenceFixtureExecutions;
    private static void ChildReferenceFixture(Projectile p)
    {
        ChildReferenceFixtureExecutions++;
        if(p.active)Projectile.NewProjectile(null,p.position,p.velocity,617,7,0);
        if(p.friendly)Projectile.NewProjectile(null,p.position,p.velocity,617,11,0);
        Projectile.NewProjectile(null,p.position,p.velocity,(int)p.ai[0],13,0);
    }
    private static JsonArray ChildReferenceSource(MethodInfo method)
    {
        const BindingFlags any=BindingFlags.Public|BindingFlags.NonPublic|BindingFlags.Instance|BindingFlags.Static;
        var sourceType=typeof(GeneratorClient).GetNestedType("ParentSourceMethod",BindingFlags.NonPublic)!;
        var body=Activator.CreateInstance(sourceType,any,null,new object?[]{method,null,null,null},null)!;
        var observerType=typeof(GeneratorClient).GetNestedType("AttackSourceObservation",BindingFlags.NonPublic)!;
        var observer=Activator.CreateInstance(observerType,any,null,new object?[]{body,"dispatch",null,null},null)!;
        var program=(JsonObject)observerType.GetMethod("Finish",any)!.Invoke(observer,null)!;
        return (JsonArray)observerType.GetMethod("LiteralProjectileSpawns",any)!.Invoke(observer,new object[]{program})!;
    }
    private static JsonObject? ExpandChildReferenceFixture(JsonArray calls)
        => (JsonObject?)typeof(GeneratorClient).GetMethod("ReferencedProjectileSnapshots",BindingFlags.NonPublic|BindingFlags.Static)!.Invoke(null,new object[]{calls});
    private static JsonObject ChildSnapshot(int id,bool include=true)
        => JsonSerializer.SerializeToNode(GeneratorClient.ProjectileRawSnapshot(id,19f,"native-test",null,-1,include))!.AsObject();
    private static void ParentBoundedProjectileReferences()
    {
        var spawnReader=typeof(GeneratorClient).GetMethod("ProjectileSpawnReferences",BindingFlags.NonPublic|BindingFlags.Static)!;
        foreach(int type in new[]{0,Terraria.ID.ProjectileID.Count})
            Equal(0,((JsonArray)spawnReader.Invoke(null,new object[]{new Projectile{type=type,aiStyle=123}})!).Count,
                "child references share native identity admission even without a ModProjectile instance");
        ChildReferenceFixtureExecutions=0;
        var calls=ChildReferenceSource(typeof(EngineRuntimeChecks).GetMethod(nameof(ChildReferenceFixture),BindingFlags.NonPublic|BindingFlags.Static)!);
        Equal(0,ChildReferenceFixtureExecutions,"source extraction does not execute inspected fixture");
        Equal(3,calls.Count,"all conditional and dynamic callsites retained");
        Equal(true,calls.Take(2).All(c=>c!["requiredPredicates"]!.AsArray().Count>0),"literal candidates retain conditional source links");
        Equal(0,calls[2]!["projectileTypes"]!.AsArray().Count,"dynamic type is not guessed");
        Equal(true,calls[2]!["unresolved"] is JsonValue,"dynamic type refusal visible");
        var merged=ExpandChildReferenceFixture(calls)!;
        Equal(1,merged["references"]!.AsArray().Count,"one profile serves duplicate conditional references");
        Equal(2,merged["references"]![0]!["sourceCallIndices"]!.AsArray().Count,"both literal callsites preserved");
        Equal(true,merged["references"]![0]!["profile"]!.AsObject().ContainsKey("referencedProjectiles"),"connected child source expands its own referenced defaults");
        foreach(var pair in new[]{(Parent:617,Child:618),(Parent:643,Child:644)})
        {
            var snapshot=ChildSnapshot(pair.Parent);var related=snapshot["referencedProjectiles"]!.AsObject();
            var refs=related["references"]!.AsArray();var sourceCalls=related["sourceCalls"]!.AsArray();
            // 617 also has two conditional Kill callsites for 620. This is
            // lifecycle source, not an extra AI sibling or an executed spawn.
            Equal(pair.Parent==617 ? "618,620" : "644",
                string.Join(",",refs.Select(r=>r!["type"]!.GetValue<int>()).Order()),"exact native child roster excludes unrelated siblings");
            foreach(var reference in refs)
            {
                int childType=reference!["type"]!.GetValue<int>();
                var indices=reference["sourceCallIndices"]!.AsArray().Select(i=>i!.GetValue<int>()).ToArray();
                Equal(childType==pair.Child ? 1 : 2,indices.Length,"all native child callsites retained");
                Equal(string.Join(",",sourceCalls.Select((call,index)=>(call,index))
                    .Where(v=>v.call!["projectileTypes"]!.AsArray().Any(id=>id!.GetValue<int>()==childType)).Select(v=>v.index)),
                    string.Join(",",indices),"child links exactly its literal source callsites");
                foreach(int index in indices)
                    Equal(childType==pair.Child ? "Terraria.Projectile.VanillaAI" : "Terraria.Projectile.Kill",
                        sourceCalls[index]!["method"]!.GetValue<string>(),"known AI child and new lifecycle child retain distinct callers");
                var child=reference["profile"]!.AsObject();
                Equal(childType,child["type"]!.GetValue<int>(),"profile retains the referenced native identity");
                Equal(0,child["sourceItemType"]!.GetValue<int>(),"child defaults not attributed to parent item");
                Equal(0,child["sourceItemDamage"]!.GetValue<int>(),"child snapshot does not invent actual spawn damage");
                Equal(0f,child["itemShootSpeed"]!.GetValue<float>(),"child defaults do not invent actual spawn velocity");
            }
            foreach(var group in sourceCalls.GroupBy(call=>call!["method"]!.GetValue<string>()))
            {
                var method=typeof(Projectile).GetMethod(group.Key.Split('.').Last(),BindingFlags.Instance|BindingFlags.Public|BindingFlags.NonPublic)!;
                var code=((System.Collections.IEnumerable)typeof(GeneratorClient).GetMethod("AttackCode",BindingFlags.NonPublic|BindingFlags.Static)!
                    .Invoke(null,new object[]{method})!).Cast<object>().ToArray();
                foreach(var call in group)
                {
                    Equal(method.Module.ModuleVersionId.ToString(),call!["sourceModuleVersionId"]!.GetValue<string>(),"call binds actual native module");
                    Equal(Convert.ToHexString(SHA256.HashData(method.GetMethodBody()!.GetILAsByteArray()!)).ToLowerInvariant(),
                        call["sourceMethodSha256"]!.GetValue<string>(),"call binds actual caller IL");
                    var instruction=code.Single(i=>(int)i.GetType().GetProperty("Offset")!.GetValue(i)! == call["at"]!.GetValue<int>());
                    Equal("call",(string)instruction.GetType().GetProperty("Op")!.GetValue(instruction)!,"source offset is an actual call");
                    var callee=(MethodInfo)instruction.GetType().GetProperty("Arg")!.GetValue(instruction)!;
                    Equal(typeof(Projectile),callee.DeclaringType!,"spawn callee belongs to native Projectile");
                    Equal("NewProjectile",callee.Name,"source link points to the actual spawn callee");
                    Equal(true,call["requiredPredicates"]!.AsArray().Count>0,"spawn remains conditional source");
                    if(method.Name!="Kill")continue;
                    var record=snapshot["attackReference"]!["lifecycle"]!["records"]!.AsArray()
                        .Single(r=>r!["spawnSites"]!.AsArray().Any(site=>JsonNode.DeepEquals(site,call)))!;
                    Equal("type == 617",record["entryCondition"]!.GetValue<string>(),"lifecycle child belongs to the selected parent source region");
                    Equal("conditional_closed_lexical_region",record["coverage"]!.GetValue<string>(),"lifecycle region remains conditional");
                    Equal(true,record["code"]!.GetValue<string>().Contains("Main.myPlayer == owner",StringComparison.Ordinal),"lifecycle owner guard retained");
                    foreach(var predicate in call["requiredPredicates"]!.AsArray())
                        Equal(true,record["locations"]!.AsArray().Any(location=>"b"+location!["ilOffset"]!.GetValue<int>()==predicate!.GetValue<string>()),
                            "lifecycle predicate links its retained source location");
                    Equal(true,call["unresolved"]!.GetValue<string>().Contains("enclosing_flow_hooks_and_entry_identity_unknown; not_an_executed_spawn",StringComparison.Ordinal),
                        "lifecycle candidate never claims entry identity or execution");
                }
            }
            int knownCall=refs.Single(r=>r!["type"]!.GetValue<int>()==pair.Child)!["sourceCallIndices"]![0]!.GetValue<int>();
            sourceCalls[knownCall]!["projectileTypes"]![0]=1;
            Equal(pair.Child,ChildSnapshot(pair.Parent)["referencedProjectiles"]!["sourceCalls"]![knownCall]!["projectileTypes"]![0]!.GetValue<int>(),"mutating a snapshot cannot poison cached source refs");
            Equal(false,ChildSnapshot(pair.Parent,false).ContainsKey("referencedProjectiles"),"base capture cache not poisoned by expanded snapshot");
        }
        // Direct candidates have priority under the shared whole-profile budget;
        // every uncaptured identity still retains its source links and reason.
        var bounded=new JsonArray();
        foreach(int id in new[]{617,643,618,644,1,2,3,4,5,-1})
            bounded.Add(new JsonObject{["projectileTypes"]=new JsonArray(id),["at"]=0,["requiredPredicates"]=new JsonArray()});
        var limited=ExpandChildReferenceFixture(bounded)!;
        Equal(10,limited["sourceCalls"]!.AsArray().Count,"source work bound does not drop callsites");
        var limitedRefs=limited["references"]!.AsArray();
        Equal(8,limitedRefs.Count(r=>r!["profile"] is JsonObject),"whole-profile work bound");
        Equal(1,limitedRefs.Count(r=>r!["unresolved"]?.GetValue<string>()=="projectile_reference_profile_count_bound"),"overflow explicit rather than partial profile");
        Equal(1,limitedRefs.Count(r=>r!["unresolved"]?.GetValue<string>()=="spawn_projectile_identity_not_registered"),"invalid identity refused before native defaults");
        // Deterministic source graphs exercise cycles and bounds independently
        // of native IDs. The production callback is the only native capture.
        JsonArray Links(params int[] ids) => new(new JsonObject { ["projectileTypes"] = new JsonArray(ids.Select(id => (JsonNode?)JsonValue.Create(id)).ToArray()) });
        var graph = GeneratorClient.BuildReferencedProjectileSnapshots(Links(101, 102), (id, allowed) =>
            (true, allowed ? new JsonObject { ["type"] = id } : null,
             allowed ? id == 101 ? Links(101, 102, 103) : id == 102 ? Links(101, 103) : Links(101) : null))!;
        var first = graph["references"]![0]!["profile"]!["referencedProjectiles"]!["references"]!.AsArray();
        Equal(101, first[0]!["profileRefType"]!.GetValue<int>(), "self cycle links an already captured identity");
        Equal(102, first[1]!["profileRefType"]!.GetValue<int>(), "cross-edge links the existing sibling profile");
        Equal(103, first[2]!["profile"]!["type"]!.GetValue<int>(), "diamond child captured once");
        Equal(103, graph["references"]![1]!["profile"]!["referencedProjectiles"]!["references"]![1]!["profileRefType"]!.GetValue<int>(), "diamond revisit links the first complete profile");
        var depth = GeneratorClient.BuildReferencedProjectileSnapshots(Links(101), (id, allowed) =>
            (true, allowed ? new JsonObject { ["type"] = id } : null, allowed ? Links(id + 1) : null))!;
        JsonObject edge = depth["references"]![0]!.AsObject();
        for (int n = 1; n < 5; n++) edge = edge["profile"]!["referencedProjectiles"]!["references"]![0]!.AsObject();
        Equal("projectile_reference_depth_bound", edge["unresolved"]!.GetValue<string>(), "deep chain retains the bounded edge without recursing");
        foreach (var chain in new[] { new[] {237, 238, 239}, new[] {377, 378, 379} })
        {
            var parent = ChildSnapshot(chain[0]);
            var child = parent["referencedProjectiles"]!["references"]!.AsArray().Single(r => r!["type"]!.GetValue<int>() == chain[1]);
            var grandchild = child!["profile"]!["referencedProjectiles"]!["references"]!.AsArray().Single(r => r!["type"]!.GetValue<int>() == chain[2]);
            Equal(chain[2], grandchild!["profile"]!["type"]!.GetValue<int>(), "native two-edge spawn chain reaches complete grandchild profile");
            Equal(true, grandchild["sourceCallIndices"]!.AsArray().Count > 0, "grandchild retains its own parent's exact callsites");
        }
    }
}

using System;
using System.Linq;
using System.Reflection;
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
    private static void ParentSingleHopProjectileReferences()
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
        Equal("0,1",string.Join(",",merged["references"]![0]!["sourceCallIndices"]!.AsArray().Select(index=>index!.GetValue<int>())),"both literal callsites preserved exactly, not dynamic site2");
        Equal(false,merged["references"]![0]!["profile"]!.AsObject().ContainsKey("referencedProjectiles"),"one-hop child never expands its own children");
        foreach(var pair in new[]{(Parent:617,Child:618),(Parent:643,Child:644)})
        {
            var snapshot=ChildSnapshot(pair.Parent);var related=snapshot["referencedProjectiles"]!.AsObject();
            var refs=related["references"]!.AsArray();var sourceCalls=related["sourceCalls"]!.AsArray();
            Equal("native_single_hop_projectile_references",related["source"]!.GetValue<string>(),"child envelope is conditional native source, not executed spawns");
            var aiCalls=sourceCalls.Where(call=>call!["method"]!.GetValue<string>()!="Terraria.Projectile.Kill").ToArray();
            Equal(pair.Child.ToString(),string.Join(",",aiCalls.SelectMany(call=>call!["projectileTypes"]!.AsArray()).Select(id=>id!.GetValue<int>()).Distinct().Order()),
                "selected AI source retains its child without borrowing an AI sibling");
            // Kill is a separate conditional source root. Its candidates must not
            // be discarded merely because the selected AI has one child identity.
            var lifecycleSites=snapshot["attackReference"]!["lifecycle"]!["records"]!.AsArray()
                .SelectMany(record=>record!["spawnSites"]!.AsArray()).ToArray();
            Equal(string.Join("\n",lifecycleSites.Select(site=>CanonicalParentFactJson(JsonSerializer.SerializeToElement(site)))),
                string.Join("\n",sourceCalls.Where(call=>call!["method"]!.GetValue<string>()=="Terraria.Projectile.Kill")
                    .Select(call=>CanonicalParentFactJson(JsonSerializer.SerializeToElement(call)))),
                "all lifecycle callsites retain their exact guards, unknowns and source certificates");
            if(pair.Parent==617)
                Equal(true,lifecycleSites.Any(site=>site!["projectileTypes"]!.AsArray().Any(id=>id!.GetValue<int>()==620)),
                    "native Kill candidate620 is independent of AI child618");
            foreach(var call in sourceCalls)
            {
                var method=typeof(Projectile).GetMethods(BindingFlags.Instance|BindingFlags.Static|BindingFlags.Public|BindingFlags.NonPublic)
                    .Single(candidate=>typeof(Projectile).FullName+"."+candidate.Name==call!["method"]!.GetValue<string>());
                AssertParentSourceCertificate(JsonSerializer.SerializeToElement(call),method,"child callsite provenance");
                var il=method.GetMethodBody()!.GetILAsByteArray()!;int at=call!["at"]!.GetValue<int>();
                Equal(true,at>=0&&at+4<il.Length&&il[at] is 0x28 or 0x6f,"child source offset is an actual native call instruction");
                var target=method.Module.ResolveMethod(BitConverter.ToInt32(il,at+1))!;
                Equal(typeof(Projectile),target.DeclaringType!,"child source call targets native Projectile");
                Equal("NewProjectile",target.Name,"child source offset targets the actual spawn overload");
                Equal(true,call["requiredPredicates"]!.AsArray().Count>0,"native spawn guards remain source links, not evaluated truth");
            }
            Equal(string.Join(",",sourceCalls.SelectMany(call=>call!["projectileTypes"]!.AsArray()).Select(id=>id!.GetValue<int>()).Distinct().Order()),
                string.Join(",",refs.Select(reference=>reference!["type"]!.GetValue<int>()).Order()),
                "exactly one profile per literal identity across AI and lifecycle source roots");
            foreach(var reference in refs)
            {
                int id=reference!["type"]!.GetValue<int>();
                Equal(string.Join(",",sourceCalls.Select((call,index)=>(call,index))
                        .Where(site=>site.call!["projectileTypes"]!.AsArray().Any(candidate=>candidate!.GetValue<int>()==id)).Select(site=>site.index)),
                    string.Join(",",reference["sourceCallIndices"]!.AsArray().Select(index=>index!.GetValue<int>())),
                    "child profile links to every and only its original callsites");
                var child=reference["profile"]!.AsObject();
                Equal(id,child["type"]!.GetValue<int>(),"profile identity matches the referenced native candidate");
                Equal("conditional_native_spawn_candidate",child["source"]!.GetValue<string>(),"child defaults retain conditional-source provenance");
                Equal(false,child.ContainsKey("referencedProjectiles"),"nested expansion disabled even when child sources have further calls");
                Equal(0,child["sourceItemType"]!.GetValue<int>(),"child defaults not attributed to parent item");
                Equal(0,child["sourceItemDamage"]!.GetValue<int>(),"child snapshot does not invent actual spawn damage");
                Equal(0f,child["itemShootSpeed"]!.GetValue<float>(),"child defaults do not invent actual spawn velocity");
            }
            string original=related.ToJsonString();
            sourceCalls[0]!["projectileTypes"]![0]=1;
            refs[0]!["profile"]!["sourceItemDamage"]=999;
            Equal(original,ChildSnapshot(pair.Parent)["referencedProjectiles"]!.ToJsonString(),"mutating source calls or child profiles cannot poison cached source refs");
            Equal(false,ChildSnapshot(pair.Parent,false).ContainsKey("referencedProjectiles"),"base capture cache not poisoned by expanded snapshot");
        }
        // A synthetic self/two-cycle link still uses the actual canonical child
        // snapshot; the explicit false flag, not identity guessing, bounds it.
        var bounded=new JsonArray();
        foreach(int id in new[]{617,643,618,644,1,2,3,4,5,-1})
            bounded.Add(new JsonObject{["projectileTypes"]=new JsonArray(id),["at"]=0,["requiredPredicates"]=new JsonArray()});
        var limited=ExpandChildReferenceFixture(bounded)!;
        Equal(10,limited["sourceCalls"]!.AsArray().Count,"source work bound does not drop callsites");
        var limitedRefs=limited["references"]!.AsArray();
        Equal(8,limitedRefs.Count(r=>r!["profile"] is JsonObject),"whole-profile work bound");
        Equal(1,limitedRefs.Count(r=>r!["unresolved"]?.GetValue<string>()=="single_hop_profile_count_bound"),"overflow explicit rather than partial profile");
        Equal(1,limitedRefs.Count(r=>r!["unresolved"]?.GetValue<string>()=="spawn_projectile_identity_not_registered"),"invalid identity refused before native defaults");
        Equal(true,limitedRefs.Where(r=>r!["profile"] is JsonObject).All(r=>!r!["profile"]!.AsObject().ContainsKey("referencedProjectiles")),"self and two-cycle expansion cannot recurse");
    }
}

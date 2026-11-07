using System;
using System.Linq;
using System.Reflection;
using System.Reflection.Emit;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Services;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    private static int EffectSliceExecuted;
    private static bool EffectSliceCondition(Projectile projectile) => projectile.active;
    private static void EffectSliceOpaqueMutation(Projectile projectile) { EffectSliceExecuted++; projectile.ai[0]=900; }
    private static void EffectSliceArrayMutation(float[] state) { EffectSliceExecuted++; state[0]=901; }
    private static void EffectSliceGlobalMutation(int index) { EffectSliceExecuted++; Terraria.Main.projectile[index].ai[0]=902; }
    private static void EffectSliceFixture(Projectile projectile)
    {
        EffectSliceExecuted++;
        Dust.NewDust(projectile.position,4,4,1);
        projectile.ai[0]++;
        _ = Math.Sqrt(projectile.ai[0]);
        if(!EffectSliceCondition(projectile)){projectile.ai[0]=0;projectile.ai[1]=-1;return;}
        if(projectile.ai[0]%12!=0)return;
        for(int i=0;i<2;i++)
            for(int j=0;j<3;j++)
                Projectile.NewProjectile(null,projectile.position,projectile.velocity,1,10,0);
        projectile.ai[0]=-3;
        EffectSliceOpaqueMutation(projectile);
        EffectSliceArrayMutation(projectile.localAI);
        EffectSliceGlobalMutation(projectile.whoAmI);
        if(projectile.localAI[0]>60)projectile.Kill();
        if(projectile.localAI[0]==30) {
            int width=projectile.width; projectile.width=60; projectile.height=60;
            projectile.damage=20; projectile.Damage(); projectile.width=width;
        }
    }
    private static MethodInfo EffectExitFixture(bool sharedEpilogue)
    {
        var assembly=AssemblyBuilder.DefineDynamicAssembly(new AssemblyName("EffectExit"+Guid.NewGuid().ToString("N")),AssemblyBuilderAccess.Run);
        var type=assembly.DefineDynamicModule("fixture").DefineType("Exit",TypeAttributes.Public);
        var method=type.DefineMethod("Source",MethodAttributes.Public|MethodAttributes.Static,typeof(void),new[]{typeof(Projectile)});
        var il=method.GetILGenerator();var effect=il.DefineLabel();var end=il.DefineLabel();
        il.Emit(OpCodes.Ldarg_0);il.Emit(OpCodes.Ldfld,typeof(Projectile).GetField("active")!);il.Emit(OpCodes.Brtrue,effect);
        if(sharedEpilogue)il.Emit(OpCodes.Br,end);else il.Emit(OpCodes.Ret);
        il.MarkLabel(effect);il.Emit(OpCodes.Ldarg_0);il.Emit(OpCodes.Ldc_I4_1);il.Emit(OpCodes.Stfld,typeof(Projectile).GetField("damage")!);
        if(sharedEpilogue)il.Emit(OpCodes.Br,end);else il.Emit(OpCodes.Ret);
        il.MarkLabel(end);if(sharedEpilogue)il.Emit(OpCodes.Ret);
        return type.CreateType()!.GetMethod("Source")!;
    }

    private static void ParentEffectSliceKeepsConditionsClocksAndLoops()
    {
        Equal(1,ReadParentWindows(ParentWindowFixture(1024,100),123,meaningfulBudget:true).Windows.Count,"narrow effect observation admits nop padding within semantic work budget");
        Equal(1,ReadParentWindows(ParentWindowFixture(2048,0),123,meaningfulBudget:true).Windows.Count,"bounded straight-line inline effects do not require helper extraction");
        var overflow=ReadParentWindows(ParentWindowFixture(4096,0),123,meaningfulBudget:true);
        Equal(0,overflow.Windows.Count,"combined instruction and branch work overflow remains refused");
        Equal(true,overflow.Gaps.Contains("identity_window_control_flow_work_bound"),"control flow work refusal explicit");
        Equal(0,ReadParentWindows(ParentWindowFixture(4,4093),123,meaningfulBudget:true).Windows.Count,"raw nop-flood cap retained");
        EffectSliceExecuted=0;
        var facts=GeneratorClient.InspectProjectileAttackSource(typeof(EngineRuntimeChecks).GetMethod(nameof(EffectSliceFixture),BindingFlags.NonPublic|BindingFlags.Static)!,"dispatch");
        Equal(0,EffectSliceExecuted,"capture does not execute source or opaque callbacks");
        var rows=facts["observations"]!.AsArray();
        foreach(string field in new[]{"Entity.width","Entity.height","Projectile.damage"})
            Equal(true,rows.Any(r=>r!["kind"]?.GetValue<string>()=="state_write" && r["expression"]?.GetValue<string>().Contains(field,StringComparison.Ordinal)==true),"effect hitbox and damage writes retained: "+field);
        Equal(true,rows.Any(r=>r!["kind"]?.GetValue<string>()=="return"),"invocation exit source retained");
        foreach(bool shared in new[]{false,true})
        {
            var exits=GeneratorClient.InspectProjectileAttackSource(EffectExitFixture(shared),"dispatch");
            var exitRows=exits["observations"]!.AsArray();
            Equal(shared?1:2,exitRows.Count(r=>r!["kind"]?.GetValue<string>()=="return"),"actual direct versus shared invocation exits");
            var effects=exitRows.Where(r=>r!["kind"]?.GetValue<string>()=="state_write").ToArray();
            Equal(1,effects.Length,"actual controlled damage write remains observed");
            Equal(true,effects.All(r=>r!["requiredPredicates"]!.AsArray().Count>0),"effect remains conditional in both exit forms");
            Equal(!shared,exitRows.Any(r=>r!["kind"]?.GetValue<string>()=="return" && r["requiredPredicates"]!.AsArray().Count>0),"shared epilogue return itself is unconditional, unlike direct early return");
        }
        Equal(false,rows.Any(r=>r!["call"]?.GetValue<string>()=="Dust.NewDust"),"unrelated decorative call not a mechanical root");
        Equal(true,rows.Any(r=>r!["call"]?.GetValue<string>()=="Projectile.Damage"),"direct damage root retained");
        Equal(true,rows.Any(r=>r!["call"]?.GetValue<string>()=="Projectile.Kill"),"lifetime root retained");
        Equal(true,rows.Count(r=>r!["kind"]?.GetValue<string>()=="clock_or_ai_write")>=4,"increment reset invalidation and cooldown writes retained");
        var spawn=rows.Single(r=>r!["call"]?.GetValue<string>()=="Projectile.NewProjectile");
        var predicates=facts["predicates"]!.AsArray();
        foreach(var id in spawn!["requiredPredicates"]!.AsArray())
            Equal(true,predicates.Any(p=>p!["id"]!.GetValue<string>()==id!.GetValue<string>()),"spawn dominating condition present");
        // Debug stores clt in a bool local; Release branches on its two inputs.
        // Follow the captured predicate dependency rather than pinning that IL shape.
        var spawnPredicateIds=spawn!["requiredPredicates"]!.AsArray().Select(v=>v!.GetValue<string>()).ToArray();
        var spawnInputs=predicates.Where(p=>spawnPredicateIds.Contains(p!["id"]!.GetValue<string>()))
            .SelectMany(p=>p!["inputs"]!.AsArray()).Select(v=>v!.GetValue<string>()).ToArray();
        foreach(string bound in new[]{"2","3"})
            Equal(true,spawnInputs.Any(input=>input==bound
                || facts["dependencies"]?[input]?["expression"]?.GetValue<string>() is string expression
                    && expression.StartsWith("clt(",StringComparison.Ordinal) && expression.EndsWith(","+bound+")",StringComparison.Ordinal)),
                "spawn's connected loop comparison retains bound "+bound);
        Equal(true,facts["symbols"]!.AsObject().Any(p=>p.Key.Contains(nameof(EffectSliceCondition),StringComparison.Ordinal)),"opaque condition return remains symbolic dependency");
        foreach(string method in new[]{nameof(EffectSliceOpaqueMutation),nameof(EffectSliceArrayMutation)})
            Equal(true,facts["unresolved"]!.AsArray().Any(p=>p!.GetValue<string>().StartsWith("opaque_actor_call_side_effects:",StringComparison.Ordinal) && p.GetValue<string>().Contains(method,StringComparison.Ordinal)),"opaque actor/AI array mutation explicitly unresolved");
        Equal(true,facts["unresolved"]!.AsArray().Any(p=>p!.GetValue<string>()=="nonselected_call_global_side_effects_unresolved"),"value-only static helper can mutate actor through globals; not certified pure");
        Equal(false,facts["unresolved"]!.AsArray().Any(p=>p!.GetValue<string>().Contains("System.Math.Sqrt",StringComparison.Ordinal)),"value argument cannot mutate clock through alias");
        foreach(var identity in new[]{(Type:617,Style:118,Child:"618"),(Type:643,Style:123,Child:"644")})
        {
            var native=GeneratorClient.CaptureProjectileAttackReference(new Projectile{type=identity.Type,aiStyle=identity.Style});
            var dispatch=native["motionDispatch"]!.AsObject();
            Equal(false,native.ContainsKey("motion"),"terminal effects do not pretend to be movement helpers");
            Equal(true,native["positionIntegration"]?["identitySelected"] is JsonObject,"inline velocity still receives existing native position integration source");
            var selected=dispatch["identitySelected"]!.AsObject();
            Equal(true,selected["identitySelection"]!["selectedEdges"]!.AsArray().Count>0,"native captured identity selects actual control edges");
            var spawned=selected["observations"]!.AsArray().Where(r=>r!["call"]?.GetValue<string>()=="Projectile.NewProjectile").ToArray();
            Equal(true,spawned.Length>0 && spawned.All(r=>r!["arguments"]?["Type"]?.GetValue<string>()==identity.Child),"selected native actor excludes sibling projectile spawn while preserving own child");
            Equal(true,spawned.All(r=>r!["requiredPredicates"]!.AsArray().Count>0),"child spawn retains temporal target and owner control dependencies");
            Equal(true,selected["observations"]!.AsArray().Any(r=>r!["kind"]?.GetValue<string>()=="clock_or_ai_write"),"identity selection does not erase clock writes");
            Equal(true,dispatch["observations"]!.AsArray().Any(r=>r!["call"]?.GetValue<string>()=="Projectile.NewProjectile" && r["arguments"]?["Type"]?.GetValue<string>()==identity.Child),"native child source restored under matching parent identity");
            Equal(true,dispatch["observations"]!.AsArray().Any(r=>r!["kind"]?.GetValue<string>()=="clock_or_ai_write"),"native temporal state stores retained");
            Equal(false,dispatch["observations"]!.AsArray().Any(r=>r!["call"]?.GetValue<string>()=="Dust.NewDust"),"native decorative calls not root noise");
        }
    }
}

using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Reflection.Emit;
using System.Runtime.CompilerServices;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Services;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    private static MethodInfo ParentWindowFixture(int meaningful, int nops, bool backward = false, bool unsupported = false)
    {
        var assembly = AssemblyBuilder.DefineDynamicAssembly(new AssemblyName("ParentWindow" + Guid.NewGuid().ToString("N")), AssemblyBuilderAccess.Run);
        var type = assembly.DefineDynamicModule("fixture").DefineType("Window", TypeAttributes.Public);
        var method = type.DefineMethod("Source", MethodAttributes.Public | MethodAttributes.Static, typeof(void), new[]{typeof(Projectile)});
        var il = method.GetILGenerator(); var start = il.DefineLabel(); var end = il.DefineLabel();
        il.MarkLabel(start); il.Emit(OpCodes.Ldarg_0); il.Emit(OpCodes.Ldfld, typeof(Projectile).GetField("aiStyle")!); il.Emit(OpCodes.Ldc_I4, 123);
        il.Emit(unsupported ? OpCodes.Bgt : OpCodes.Bne_Un, backward ? start : end);
        for(int n=0;n<nops;n++)il.Emit(OpCodes.Nop);
        for(int n=4;n<meaningful;n+=2){il.Emit(OpCodes.Ldc_I4_0);il.Emit(OpCodes.Pop);}
        il.MarkLabel(end);il.Emit(OpCodes.Ret);
        return type.CreateType()!.GetMethod("Source")!;
    }

    private static (List<ITuple> Windows, List<string> Gaps) ReadParentWindows(MethodInfo method, int style)
    {
        const BindingFlags flags=BindingFlags.NonPublic|BindingFlags.Static;
        object code=typeof(GeneratorClient).GetMethod("AttackCode",flags)!.Invoke(null,new object[]{method})!;
        var gaps=new List<string>(); Action<string> report=gaps.Add;
        var windows=(IEnumerable)typeof(GeneratorClient).GetMethod("ProjectileIdentityWindows",flags)!.Invoke(null,new object[]{code,643,style,report})!;
        return (windows.Cast<ITuple>().ToList(),gaps);
    }

    private static void ParentIdentityWindowRefusalDiagnostics()
    {
        var exact=ReadParentWindows(ParentWindowFixture(4,1020),123);
        Equal(1,exact.Windows.Count,"original raw1024 admission unchanged");
        Equal(1024,((Array)exact.Windows[0][3]!).Length,"source window retains every raw instruction");
        var overflow=ReadParentWindows(ParentWindowFixture(4,1021),123);
        Equal(0,overflow.Windows.Count,"original raw1025 refusal unchanged even for nop padding");
        Equal(true,overflow.Gaps.Contains("identity_window_raw_instruction_bound"),"budget refusal not mislabelled unsupported syntax");
        var mismatch=ReadParentWindows(ParentWindowFixture(4,1021),122);
        Equal(0,mismatch.Windows.Count,"wrong identity does not acquire another actor's window");
        Equal(0,mismatch.Gaps.Count,"nonmatching window does not acquire budget diagnosis");
        var backward=ReadParentWindows(ParentWindowFixture(8,0,backward:true),123);
        Equal(0,backward.Windows.Count,"nonforward window still refused");
        Equal(true,backward.Gaps.Contains("identity_window_nonforward_branch_unsupported"),"nonforward unsupported distinct from budget");
        var unknown=ReadParentWindows(ParentWindowFixture(8,0,unsupported:true),123);
        Equal(0,unknown.Windows.Count,"unrecognized comparison still refused");
        Equal(0,unknown.Gaps.Count,"unrecognized comparison not a budget refusal");
        foreach(var identity in new[]{(Type:617,Style:118),(Type:643,Style:123)})
        {
            var facts=GeneratorClient.CaptureProjectileAttackReference(new Projectile{type=identity.Type,aiStyle=identity.Style});
            Equal(false,facts.ContainsKey("motionDispatch"),"existing overbudget native source remains unadmitted");
            var gaps=facts["coverage"]!["unresolved"]!.AsArray();
            Equal(true,gaps.Any(g=>g!.GetValue<string>()=="VanillaAI_identity_window_raw_instruction_bound"),"actual installed native source reports raw budget");
            Equal(false,gaps.Any(g=>g!.GetValue<string>()=="VanillaAI_identity_dispatch_outside_supported_source_shape"),"no false unsupported identity syntax diagnosis");
        }
    }
}

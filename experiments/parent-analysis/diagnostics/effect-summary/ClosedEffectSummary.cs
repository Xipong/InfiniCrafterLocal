#nullable enable
using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using InfiniCrafterLocal.Common.Services;
using Terraria;

// Experiment only: a deliberately incomplete, input-independent proof. It proves
// preservation for *every* possible alias, rather than guessing which reference
// parameter or heap object is the captured Projectile. No callee is executed.
internal sealed class ClosedEffectSummary
{
    internal sealed record Result(bool Proven, string Reason, string[] Methods, int Instructions);
    const BindingFlags All = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static;
    readonly int maxBytes, maxDepth, maxMethods, maxInstructions;
    readonly HashSet<MethodBase> active = new(), done = new();
    readonly List<string> certificates = new();
    readonly HashSet<Type> initializing = new(), initialized = new();
    int work;
    internal ClosedEffectSummary(int maxBytes = 4096, int maxDepth = 8, int maxMethods = 64, int maxInstructions = 10000)
    { this.maxBytes=maxBytes; this.maxDepth=maxDepth; this.maxMethods=maxMethods; this.maxInstructions=maxInstructions; }
    static object? Member(object value, string name) => value.GetType().GetField(name, All)?.GetValue(value) ?? value.GetType().GetProperty(name, All)?.GetValue(value);
    static bool RefFree(Type type, HashSet<Type>? path = null)
    {
        if (type.IsByRef || type.IsPointer || type.IsByRefLike || !type.IsValueType) return false;
        if (type.IsPrimitive || type.IsEnum) return true;
        path ??=new(); if (!path.Add(type) || path.Count > 16) return false;
        return type.GetFields(All).Where(f=>!f.IsStatic).All(f=>RefFree(f.FieldType,new(path)));
    }
    internal Result AnalyzeInvocation(MethodBase method, string opcode)
    {
        if(opcode == "callvirt" && method.IsVirtual && !method.IsFinal && method.DeclaringType?.IsSealed != true)
            return new(false,"open_virtual_dispatch",Array.Empty<string>(),0);
        return Analyze(method);
    }
    internal Result Analyze(MethodBase method)
    {
        try { Visit(method,0); return new(true,"closed_source_preserves_identity_and_no_reference_escape",certificates.ToArray(),work); }
        catch (NotSupportedException e) { return new(false,e.Message,certificates.ToArray(),work); }
        catch (Exception e) { return new(false,"inspection_error:"+e.GetType().Name,certificates.ToArray(),work); }
    }
    void Refuse(string reason, MethodBase method) => throw new NotSupportedException(reason+":"+method.DeclaringType?.FullName+"."+method.Name);
    void EnsureType(Type? type, int depth)
    {
        if(type is null || initialized.Contains(type) || initializing.Contains(type) || type.TypeInitializer is null) return;
        initializing.Add(type); Visit(type.TypeInitializer,depth+1); initializing.Remove(type); initialized.Add(type);
    }
    void Visit(MethodBase method, int depth)
    {
        if (done.Contains(method)) return;
        if (active.Contains(method)) Refuse("recursive_call_cycle",method);
        if (depth > maxDepth) Refuse("depth_bound",method);
        if (done.Count+active.Count >= maxMethods) Refuse("method_bound",method);
        if (method.ContainsGenericParameters || method.IsAbstract || method.GetParameters().Any(p=>p.ParameterType.IsByRef || p.ParameterType.IsPointer || p.ParameterType.IsByRefLike)) Refuse("open_generic_abstract_or_byref",method);
        if (method is MethodInfo mi && mi.ReturnType != typeof(void) && !RefFree(mi.ReturnType)) Refuse("reference_or_byref_result",method);
        MethodBody? body=method.GetMethodBody(); if(body is null) Refuse("no_managed_body",method);
        if(body!.ExceptionHandlingClauses.Count != 0) Refuse("exception_regions",method);
        if((body.GetILAsByteArray()?.Length ?? int.MaxValue)>maxBytes) Refuse("il_byte_bound",method);
        // Address-exposed ref-free values are permitted only as primitive field
        // reads/writes; indirect operations and ref/out call signatures refuse.
        var code=(IEnumerable)typeof(GeneratorClient).GetMethod("AttackCode",All)!.Invoke(null,new object[]{method})!;
        active.Add(method);
        EnsureType(method.DeclaringType,depth);
        foreach(var instruction in code)
        {
            if(++work>maxInstructions) Refuse("instruction_work_bound",method);
            string op=(string)Member(instruction,"Op")!; object? operand=Member(instruction,"Arg");
            if(operand is FieldInfo field)
            {
                if((op=="stfld" || op=="ldflda" || op=="stsfld" || op=="ldsflda") && field.DeclaringType==typeof(Projectile) && field.Name is "type" or "aiStyle") Refuse("identity_write_or_address",method);
                if(op is "stfld" or "stsfld" && !RefFree(field.FieldType)) Refuse("reference_field_escape",method);
                if(op is "ldflda" or "ldsflda" && !RefFree(field.FieldType)) Refuse("reference_field_address",method);
                if(field.IsStatic) EnsureType(field.DeclaringType,depth);
                if(op is "ldfld" or "ldflda" or "stfld" or "ldsfld" or "ldsflda" or "stsfld") continue;
            }
            if(operand is MethodBase call && op is "call" or "callvirt" or "newobj")
            {
                if(op=="callvirt" && call.IsVirtual && !call.IsFinal && call.DeclaringType?.IsSealed!=true) Refuse("open_virtual_dispatch",method);
                if(call.IsStatic || op=="newobj") EnsureType(call.DeclaringType,depth);
                Visit(call,depth+1); continue;
            }
            if(op is "nop" or "const" or "ldc.r4" or "ldc.r8" or "ldc.i8" or "ldnull" or "ldstr" or "ldarg" or "ldloc" or "stloc" or "dup" or "pop" or "ret" or "castclass" or "isinst"
                or "add" or "sub" or "mul" or "div" or "div.un" or "rem" or "rem.un" or "and" or "or" or "xor" or "shl" or "shr" or "shr.un" or "neg" or "not"
                or "ceq" or "clt" or "clt.un" or "cgt" or "cgt.un" or "switch" or "br" or "br.s" or "brtrue" or "brtrue.s" or "brfalse" or "brfalse.s"
                or "beq" or "beq.s" or "bne.un" or "bne.un.s" or "bgt" or "bgt.s" or "bgt.un" or "bgt.un.s" or "bge" or "bge.s" or "bge.un" or "bge.un.s"
                or "blt" or "blt.s" or "blt.un" or "blt.un.s" or "ble" or "ble.s" or "ble.un" or "ble.un.s"
                or "conv.i1" or "conv.u1" or "conv.i2" or "conv.u2" or "conv.i4" or "conv.u4" or "conv.i8" or "conv.u8" or "conv.r4" or "conv.r8" or "conv.r.un") continue;
            Refuse("unsupported_opcode_"+op,method);
        }
        active.Remove(method); done.Add(method);
        certificates.Add(method.Module.ModuleVersionId+":"+method.MetadataToken+":"+method);
    }
}

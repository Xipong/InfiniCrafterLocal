#nullable enable
using System;
using System.Globalization;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using Mono.Cecil;
using Mono.Cecil.Cil;

namespace InfiniCrafterLocal.Common.Services;

// Shared by the metadata-only certificate generator and runtime inspection.
// Tokens/MVID are provenance, not semantics. All operands, typed locals and EH
// boundaries remain significant; unsupported operands fail closed.
internal static class NativeSourceFingerprint
{
    private static string TypeIdentity(TypeReference type)
    {
        string scope = type.GetElementType().Scope switch
        {
            AssemblyNameReference a => a.Name + ":" + Convert.ToHexString(a.PublicKeyToken ?? Array.Empty<byte>()),
            ModuleDefinition m => m.Assembly.Name.Name + ":" + Convert.ToHexString(m.Assembly.Name.PublicKeyToken ?? Array.Empty<byte>()),
            ModuleReference m => m.Name,
            _ => throw new InvalidOperationException("Unresolved native type scope")
        };
        return type.FullName + "@" + scope + (type is GenericInstanceType generic
            ? "[" + string.Join(",", generic.GenericArguments.Select(TypeIdentity)) + "]" : "")
            + (type is TypeSpecification spec ? "|element=" + TypeIdentity(spec.ElementType) : "")
            + (type is IModifierType modifier ? "|modifier=" + TypeIdentity(modifier.ModifierType) : "");
    }
    private static string MethodIdentity(MethodReference method) => method.FullName + "@" + TypeIdentity(method.DeclaringType)
        + "|" + TypeIdentity(method.ReturnType) + "|" + string.Join(",", method.Parameters.Select(p => TypeIdentity(p.ParameterType)))
        + "|" + method.HasThis + "|" + method.ExplicitThis + "|" + method.CallingConvention
        + (method is GenericInstanceMethod generic ? "|" + string.Join(",", generic.GenericArguments.Select(TypeIdentity)) : "");

    internal static string Compute(MethodDefinition method) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(Describe(method)))).ToLowerInvariant();
    internal static string Describe(MethodDefinition method)
    {
        if (!method.HasBody) throw new InvalidOperationException("Native method has no IL body");
        var code = method.Body.Instructions;
        var indices = code.Select((i, n) => (i, n)).ToDictionary(p => p.i, p => p.n);
        int At(Instruction? i) => i is null ? -1 : indices[i];
        var text = new StringBuilder();
        text.Append(TypeIdentity(method.ReturnType)).Append('|').Append(method.HasThis).Append('|')
            .Append(method.ExplicitThis).Append('|').Append(method.CallingConvention).Append('|')
            .Append(method.GenericParameters.Count).Append('|')
            .AppendJoin(',', method.Parameters.Select(p => TypeIdentity(p.ParameterType))).Append('\n');
        text.AppendJoin(',', method.Body.Variables.Select(v => TypeIdentity(v.VariableType))).Append('\n')
            .Append(method.Body.InitLocals).Append('\n');
        foreach (var instruction in code)
        {
            string operand = instruction.Operand switch
            {
                null => "", Instruction i => At(i).ToString(CultureInfo.InvariantCulture),
                Instruction[] targets => string.Join(",", targets.Select(At)),
                VariableDefinition v => v.Index.ToString(CultureInfo.InvariantCulture),
                ParameterDefinition p => p.Index.ToString(CultureInfo.InvariantCulture),
                MethodReference m => MethodIdentity(m), FieldReference f => f.FullName + "@" + TypeIdentity(f.DeclaringType) + "|" + TypeIdentity(f.FieldType),
                TypeReference t => TypeIdentity(t), CallSite c => c.FullName + "|" + c.CallingConvention + "|" + c.HasThis + "|" + c.ExplicitThis + "|" + TypeIdentity(c.ReturnType) + "|" + string.Join(",", c.Parameters.Select(p => TypeIdentity(p.ParameterType))),
                string s => Convert.ToBase64String(Encoding.UTF8.GetBytes(s)),
                float f => Convert.ToHexString(BitConverter.GetBytes(f)),
                double d => Convert.ToHexString(BitConverter.GetBytes(d)),
                sbyte or byte or short or ushort or int or uint or long or ulong => Convert.ToString(instruction.Operand, CultureInfo.InvariantCulture)!,
                _ => throw new InvalidOperationException("Unsupported native IL operand")
            };
            text.Append(instruction.OpCode.Name).Append('|').Append(operand).Append('\n');
        }
        foreach (var h in method.Body.ExceptionHandlers)
            text.Append(h.HandlerType).Append('|').Append(At(h.TryStart)).Append('|').Append(At(h.TryEnd))
                .Append('|').Append(At(h.HandlerStart)).Append('|').Append(At(h.HandlerEnd))
                .Append('|').Append(At(h.FilterStart)).Append('|').Append(h.CatchType is null ? "" : TypeIdentity(h.CatchType)).Append('\n');
        return text.ToString();
    }
}

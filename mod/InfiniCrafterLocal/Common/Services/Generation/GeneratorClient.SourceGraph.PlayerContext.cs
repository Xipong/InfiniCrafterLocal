#nullable enable
using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using Terraria;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Services;

public sealed partial class GeneratorClient
{
    private sealed partial class ParentSourceGraph
    {
        private void PlayerContextHooks(Type owner)
        {
            foreach (MethodInfo method in Overrides(owner, typeof(ModPlayer)).Where(m => PlayerEvents.Contains(m.Name)))
            {
                bool dependent = ReadsParentContext(method, owner, new HashSet<(MethodBase, Type?)>(), 0, method.Module.Assembly);
                if (!dependent && method.ReturnType == typeof(void)
                    && !method.GetParameters().Any(parameter => parameter.ParameterType.IsByRef))
                {
                    // The field-consumer fixed point may still admit this hook
                    // later, when a parent writes the state that activates it.
                    continue;
                }
                Hooks(owner, typeof(ModPlayer), new HashSet<string>(StringComparer.Ordinal) { method.Name },
                    "registered_ModPlayer_candidate", "event_signature");
            }
        }

        private bool ReadsParentContext(MethodBase method, Type? receiver, HashSet<(MethodBase, Type?)> seen, int depth, Assembly assembly)
        {
            if (!seen.Add((method, receiver))) return false;
            if (depth > DepthLimit || seen.Count > DiscoveryNodeLimit || Read(method) is not { } body)
            {
                Gap("player_context_dependency_unresolved");
                return true; // A bound or unreadable helper is not proof of irrelevance.
            }
            static bool ParentType(Type? type)
            {
                if (type?.IsByRef == true || type?.IsArray == true) type = type.GetElementType();
                return type is not null && (typeof(Item).IsAssignableFrom(type) || typeof(Projectile).IsAssignableFrom(type));
            }
            bool ParentArgument(string input)
            {
                var pending = new Stack<string>(); pending.Push(input);
                var origins = new HashSet<string>();
                while (pending.Count > 0 && origins.Count < 256)
                {
                    string id = pending.Pop();
                    if (!origins.Add(id)) continue;
                    foreach (var origin in body.Definitions(id))
                    {
                        if (origin.Op == "ldarg" && origin.Operand is int argument
                            && argument - (method.IsStatic ? 0 : 1) is int index && index >= 0
                            && index < method.GetParameters().Length && ParentType(method.GetParameters()[index].ParameterType)) return true;
                        if (origin.Op is "castclass" or "isinst" && origin.Inputs.Count == 1) pending.Push(origin.Inputs[0]);
                        if (origin.Op == "unresolved_definition_traversal_bound")
                        { Gap("player_context_dependency_unresolved"); return true; }
                    }
                }
                if (pending.Count == 0) return false;
                Gap("player_context_dependency_unresolved");
                return true;
            }
            foreach (var value in body.Values.Values)
            {
                if (value.Operand is Type testedType && (ParentType(testedType) || typeof(ModItem).IsAssignableFrom(testedType))) return true;
                if (value.Operand is FieldInfo field)
                {
                    // Ownership/instance IDs identify the actor, not the parent
                    // mechanics. A generic owner check must not import every
                    // equipped-player effect into every material's dossier.
                    if (ParentType(field.DeclaringType) && !(field.DeclaringType == typeof(Projectile)
                        && field.Name is "owner" or "whoAmI" or "identity")) return true;
                    if (ParentType(field.FieldType)) return true;
                    if (field.DeclaringType == typeof(Entity) && field.Name is not ("whoAmI" or "identity")
                        && value.Inputs.Count > 0 && ParentArgument(value.Inputs[0])) return true;
                }
                if (value.Operand is not MethodBase helper) continue;
                if ((helper.DeclaringType == typeof(object) || helper.DeclaringType == typeof(Entity))
                    && !helper.IsStatic && value.Inputs.Count > 0
                    && ParentArgument(value.Inputs[0])) return true;
                if (ParentType(helper.DeclaringType) || helper is MethodInfo result && ParentType(result.ReturnType)) return true;
                if (helper.DeclaringType is { } delegateType && typeof(Delegate).IsAssignableFrom(delegateType)
                    && helper.Name is "Invoke" or "DynamicInvoke")
                {
                    Gap("player_context_dependency_unresolved");
                    return true; // A runtime delegate may capture parent state; its target is not known here.
                }
                var parameters = helper.GetParameters();
                int firstArgument = helper.IsStatic || value.Op == "newobj" ? 0 : 1;
                for (int index = 0; index < parameters.Length && index + firstArgument < value.Inputs.Count; index++)
                {
                    Type parameterType = parameters[index].ParameterType;
                    bool byRef = parameterType.IsByRef;
                    if (byRef) parameterType = parameterType.GetElementType()!;
                    bool erased = parameterType == typeof(object) || parameterType == typeof(Entity);
                    if (erased && (byRef || ParentArgument(value.Inputs[index + firstArgument]))
                        || byRef && ParentType(parameterType))
                    {
                        // This relevance scan has no caller/alias binding for
                        // erased or indirect parent arguments. Keep conditional
                        // source instead of proving their absence from a type.
                        Gap("player_context_dependency_unresolved");
                        return true;
                    }
                }
                if (helper.Module.Assembly == assembly && helper.Module.Assembly != typeof(NPC).Assembly)
                {
                    Type? boundReceiver = !helper.IsStatic && receiver is not null
                        && helper.DeclaringType?.IsAssignableFrom(receiver) == true && CallsCapturedThis(body, value) ? receiver : null;
                    if (value.Op == "callvirt" && helper is MethodInfo { IsVirtual: true, IsFinal: false }
                        && boundReceiver is null && helper.DeclaringType?.IsSealed != true)
                    {
                        Gap("player_context_dependency_unresolved");
                        return true; // The runtime override can read parent state.
                    }
                    MethodBase target = value.Op == "callvirt" && helper is MethodInfo { IsVirtual: true } virtualMethod && boundReceiver is not null
                        ? CapturedVirtualTarget(virtualMethod, boundReceiver) ?? helper : helper;
                    if (ReadsParentContext(target, boundReceiver, seen, depth + 1, assembly)) return true;
                }
                else if (helper.GetParameters().Any(p => ParentType(p.ParameterType))) return true;
                else if (helper.Module.Assembly != typeof(NPC).Assembly && helper.DeclaringType is { } declaring && typeof(ModPlayer).IsAssignableFrom(declaring))
                {
                    Gap("player_context_dependency_unresolved");
                    return true;
                }
                else if (helper.Module.Assembly != typeof(NPC).Assembly && helper.Module.Assembly != typeof(object).Assembly
                    && helper.GetParameters().Any(p => p.ParameterType == typeof(Player)))
                {
                    Gap("player_context_dependency_unresolved");
                    return true; // Foreign code may read HeldItem; do not guess.
                }
            }
            return false;
        }
    }
}

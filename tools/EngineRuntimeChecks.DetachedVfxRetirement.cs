using System;
using System.Collections;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using InfiniCrafterLocal.Common.VFX;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Mono.Cecil.Cil;
using MonoMod.Cil;

internal static partial class EngineRuntimeChecks
{
    // Real OnWorldUnload/Clear and native Main action-queue consumption. Only
    // GraphicsResource.Dispose is intercepted: shells never enter a GPU API.
    // Baseline-compilable; no dependency on a new candidate helper/signature.
    private static void DetachedVfxWorkerRetiresCpuBeforeGraphicsDisposal()
        => DetachedVfxRetirementProbe(failOwnerDisposal: false);

    private static void DetachedVfxQueuedDisposalCannotRetireNextWorld()
        => DetachedVfxRetirementProbe(failOwnerDisposal: true);

    private static void DetachedVfxRetirementProbe(bool failOwnerDisposal)
    {
        const BindingFlags flags = BindingFlags.Static | BindingFlags.NonPublic;
        Type type = typeof(InfiniDetachedVfxSystem);
        var system = new InfiniDetachedVfxSystem();
        FieldInfo effectField = type.GetField("MaterialPathEffect", flags)!;
        FieldInfo actionsField = typeof(Terraria.Main).GetField("_mainThreadActions", flags)!;
        FieldInfo tickField = type.GetField("LastMaterialsTick", flags)!;
        object? previousEffect = effectField.GetValue(null), previousActions = actionsField.GetValue(null);
        object? previousTick = tickField.GetValue(null);
        bool previousServer = Terraria.Main.dedServ;
        var lists = new List<(IList List, object[] Values)>();
        var dictionaries = new List<(IDictionary Map, List<DictionaryEntry> Values)>();
        foreach (string name in new[] { "MaterialPaths", "PeriodicElements", "MaterialEmissions", "Emissions" })
        {
            var list = (IList)type.GetField(name, flags)!.GetValue(null)!;
            var values = new object[list.Count]; list.CopyTo(values, 0);
            lists.Add((list, values)); list.Clear();
        }
        foreach (string name in new[] { "DrawCallsBySource", "ParticleBudgetsBySource" })
        {
            var map = (IDictionary)type.GetField(name, flags)!.GetValue(null)!;
            var values = new List<DictionaryEntry>();
            foreach (DictionaryEntry entry in map) values.Add(entry);
            dictionaries.Add((map, values)); map.Clear();
        }
        BasicEffect Shell()
        {
            var effect = (BasicEffect)RuntimeHelpers.GetUninitializedObject(typeof(BasicEffect));
            GC.SuppressFinalize(effect);
            return effect;
        }
        BasicEffect retired = Shell(), nextWorld = Shell();
        int ownerThread = Environment.CurrentManagedThreadId;
        var disposed = new List<GraphicsResource>();
        var queue = new ConcurrentQueue<Action>();
        // Replace exactly the native graphics boundary, not Clear or its queue.
        using var hook = new MonoMod.RuntimeDetour.ILHook(
            typeof(GraphicsResource).GetMethod("Dispose", Type.EmptyTypes)!, il => {
                il.Body.Instructions.Clear(); il.Body.ExceptionHandlers.Clear();
                var cursor = new ILCursor(il);
                cursor.Emit(OpCodes.Ldarg_0);
                cursor.EmitDelegate<Action<GraphicsResource>>(resource => {
                    if (Environment.CurrentManagedThreadId != ownerThread)
                        throw new ThreadStateException("controlled FNA main-thread-only disposal boundary");
                    disposed.Add(resource);
                    if (failOwnerDisposal)
                        throw new InvalidOperationException("controlled owner disposal failure");
                });
                cursor.Emit(OpCodes.Ret);
            });
        try
        {
            Terraria.Main.dedServ = false;
            actionsField.SetValue(null, queue);
            effectField.SetValue(null, retired);
            // Seed every CPU owner skipped by the observed baseline exception,
            // including the update-clock sentinel, not merely one visible queue.
            foreach (var row in lists)
            {
                Type element = row.List.GetType().GetGenericArguments()[0];
                row.List.Add(RuntimeHelpers.GetUninitializedObject(element));
            }
            tickField.SetValue(null, 123UL);
            Equal(true, InfiniDetachedVfxSystem.TrySpendDetachedParticle("retirement_probe", 2, 2), "seed real particle budget");
            Equal(true, InfiniDetachedVfxSystem.TrySpendSourceDraw("retirement_probe", 2, 1), "seed real draw budget");
            Exception? workerError = null;
            Task.Run(() => {
                try { system.OnWorldUnload(); }
                catch (Exception error) { workerError = error; }
            }).GetAwaiter().GetResult();
            Equal<Exception?>(null, workerError, "SaveAndQuit worker completes CPU retirement without a graphics call");
            foreach (var row in lists) Equal(0, row.List.Count, "world clear retires every CPU list before owner drain");
            foreach (var row in dictionaries) Equal(0, row.Map.Count, "world clear retires every CPU budget before owner drain");
            Equal(ulong.MaxValue, (ulong)tickField.GetValue(null)!, "world update sentinel is reset despite deferred graphics cleanup");
            Equal<object?>(null, effectField.GetValue(null), "old effect is detached before world reentry");
            Equal(0, disposed.Count, "worker never touches GraphicsResource.Dispose");
            Equal(1, queue.Count, "exact retired effect is queued once");
            Task.Run(system.OnWorldUnload).GetAwaiter().GetResult();
            Equal(1, queue.Count, "repeated empty clear cannot enqueue the same effect twice");

            // Reenter before the callback drains: its captured old generation
            // must not read/null/dispose the new world's effect or clear its CPU work.
            effectField.SetValue(null, nextWorld);
            InfiniDetachedVfxSystem.Enqueue("next_world", "not_loaded.png", "BeforeProjectiles",
                Vector2.One, 0f, 1f, 1f, Color.White, 3, 1);
            Exception? ownerError = null;
            try { typeof(Terraria.Main).GetMethod("ConsumeAllMainThreadActions", flags)!.Invoke(null, null); }
            catch (TargetInvocationException error) { ownerError = error.InnerException; }
            Equal(failOwnerDisposal, ownerError is InvalidOperationException, "injected owner failure is distinct from worker retirement");
            if (ownerError is not null) Equal("controlled owner disposal failure", ownerError.Message, "only the controlled disposal failed");
            Equal(1, disposed.Count, "one owner disposal boundary invocation");
            Equal(true, ReferenceEquals(retired, disposed[0]), "callback disposes captured old generation only");
            Equal(true, ReferenceEquals(nextWorld, effectField.GetValue(null)), "late callback preserves replacement world effect");
            Equal(1, lists[3].List.Count, "late callback preserves next-world CPU emission even when disposal fails");
            Equal(0, queue.Count, "owner consumes its one queued callback");
        }
        finally
        {
            // Discard only this probe's queue; do not drain someone else's work.
            effectField.SetValue(null, previousEffect);
            actionsField.SetValue(null, previousActions);
            tickField.SetValue(null, previousTick);
            Terraria.Main.dedServ = previousServer;
            foreach (var row in lists) { row.List.Clear(); foreach (object value in row.Values) row.List.Add(value); }
            foreach (var row in dictionaries) { row.Map.Clear(); foreach (DictionaryEntry entry in row.Values) row.Map.Add(entry.Key, entry.Value); }
        }
    }
}

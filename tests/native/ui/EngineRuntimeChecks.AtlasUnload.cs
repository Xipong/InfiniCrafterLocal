using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Threading;
using InfiniCrafterLocal.Common.UI;
using Microsoft.Xna.Framework.Graphics;
using ReLogic.Content;

internal static partial class EngineRuntimeChecks
{
    private static void AtlasUnloadRetiresOwnedGraphicsOnMainThread()
        => AtlasUnloadRetirementProbe(failDisposal: false);

    private static void AtlasUnloadIsolatesDisposalFailures()
        => AtlasUnloadRetirementProbe(failDisposal: true);

    private static void AtlasUnloadRetirementProbe(bool failDisposal)
    {
        const BindingFlags flags = BindingFlags.Static | BindingFlags.NonPublic;
        var type = typeof(RecipeJournalUISystem);
        var cache = (Dictionary<Asset<Texture2D>, (Texture2D Source, Texture2D Prepared)>)
            type.GetField("BookSkinTextures", flags)!.GetValue(null)!;
        var assetFields = type.GetFields(flags).Where(field => field.FieldType == typeof(Asset<Texture2D>)).ToArray();
        var clipField = type.GetField("LineageClip", flags)!;
        var fields = assetFields.Append(clipField).ToArray();
        var savedFields = fields.Select(field => field.GetValue(null)).ToArray();
        var savedCache = cache.ToArray();
        var actionsField = typeof(Terraria.Main).GetField("_mainThreadActions", flags)!;
        object? savedActions = actionsField.GetValue(null);
        var actions = new ConcurrentQueue<Action>();
        int mainThread = Environment.CurrentManagedThreadId;
        var disposed = new List<GraphicsResource>();
        var failures = new HashSet<GraphicsResource>();
        var warnings = new List<(string Message, Exception Error)>();
        Action<log4net.Core.LogImpl, object, Exception> warn = (_, message, error)
            => warnings.Add((message.ToString()!, error));
        using var logHook = new MonoMod.RuntimeDetour.Hook(
            typeof(log4net.Core.LogImpl).GetMethod("Warn", new[] { typeof(object), typeof(Exception) })!, warn);
        Action<GraphicsResource> dispose = resource => {
            // Replace only the final GPU boundary, not Unload or tML scheduling.
            if (Environment.CurrentManagedThreadId != mainThread)
                throw new ThreadStateException("FNA3D graphics disposal must be called on the main thread");
            disposed.Add(resource);
            if (failures.Contains(resource)) throw new InvalidOperationException("controlled journal GPU disposal failure");
        };
        using var hook = new MonoMod.RuntimeDetour.Hook(
            typeof(GraphicsResource).GetMethod(nameof(GraphicsResource.Dispose), Type.EmptyTypes)!, dispose);
        void UnloadOnWorker()
        {
            Exception? failure = null;
            var worker = new Thread(() => {
                try { new RecipeJournalUISystem().Unload(); }
                catch (Exception ex) { failure = ex; }
            }) { IsBackground = true };
            worker.Start();
            Equal(true, worker.Join(TimeSpan.FromSeconds(5)), "unload never blocks on the main-thread queue");
            if (failure is not null) throw new InvalidOperationException("Actual journal Unload failed on worker", failure);
        }
        void Drain() => typeof(Terraria.Main).GetMethod("ConsumeAllMainThreadActions", flags)!.Invoke(null, null);
        void Install(Texture2D source, Texture2D prepared, RasterizerState clip)
        {
            var asset = CpuTextureAsset(source);
            cache.Add(asset, (source, prepared));
            foreach (var field in assetFields) field.SetValue(null, asset);
            clipField.SetValue(null, clip);
        }
        try
        {
            actionsField.SetValue(null, actions);
            cache.Clear();
            foreach (var field in fields) field.SetValue(null, null);
            UnloadOnWorker();
            Equal(0, actions.Count, "partial/failed load with no owned graphics needs no callback");

            var firstSource = CpuTexture(8, 8); var firstPrepared = CpuTexture(8, 8);
            var secondSource = CpuTexture(8, 8); var secondPrepared = CpuTexture(8, 8);
            var firstClip = new RasterizerState();
            if (failDisposal) { failures.Add(firstPrepared); failures.Add(firstClip); }
            Install(firstSource, firstPrepared, firstClip);
            cache.Add(CpuTextureAsset(secondSource), (secondSource, secondPrepared));
            UnloadOnWorker();
            Equal(0, disposed.Count, "worker never touches FNA graphics disposal");
            Equal(0, cache.Count, "unload detaches retired prepared texture lookup immediately");
            Equal(true, fields.All(field => field.GetValue(null) is null), "unload clears all asset and rasterizer references");
            Equal(true, actions.Count > 0, "owned GPU resources are scheduled on the actual tML queue");
            int pending = actions.Count;
            UnloadOnWorker();
            Equal(pending, actions.Count, "repeated unload does not retire the same resources twice");

            // Model the next load before the previous generation's callbacks run.
            var nextSource = CpuTexture(8, 8); var nextPrepared = CpuTexture(8, 8);
            var nextClip = new RasterizerState();
            Install(nextSource, nextPrepared, nextClip);
            Drain();
            Equal(3, disposed.Count, "both old prepared textures and old rasterizer are released");
            foreach (var resource in new GraphicsResource[] { firstPrepared, secondPrepared, firstClip })
                Equal(1, disposed.Count(value => ReferenceEquals(value, resource)), "each retired resource is disposed exactly once");
            Equal(false, disposed.Any(value => ReferenceEquals(value, firstSource) || ReferenceEquals(value, secondSource)
                || ReferenceEquals(value, nextSource)), "shared ModContent source textures are never disposed by the journal");
            Equal(false, disposed.Contains(nextPrepared) || disposed.Contains(nextClip), "old callbacks never dispose a new generation");
            Equal(1, cache.Count, "old callbacks never clear new cache entries");
            Equal(true, ReferenceEquals(nextClip, clipField.GetValue(null)), "old callbacks never clear new rasterizer state");

            UnloadOnWorker(); Drain(); UnloadOnWorker(); Drain();
            Equal(5, disposed.Count, "next generation and repeated empty unload are independent");
            Equal(1, disposed.Count(value => ReferenceEquals(value, nextPrepared)), "next prepared texture released once");
            Equal(1, disposed.Count(value => ReferenceEquals(value, nextClip)), "next rasterizer released once");
            Equal(0, actions.Count, "no retirement callbacks remain after drain");
            var logged = warnings.ToArray();
            Equal(failDisposal ? 2 : 0, logged.Length, "each GPU cleanup failure is visibly logged without aborting queue drain");
            foreach (var warning in logged)
            {
                Equal(true, warning.Message.Contains("InfiniCrafterLocal") && warning.Message.Contains("journal"), "cleanup warning identifies its owner");
                Equal("controlled journal GPU disposal failure", warning.Error.Message, "warning retains the original disposal failure");
            }
        }
        finally
        {
            cache.Clear();
            foreach (var pair in savedCache) cache.Add(pair.Key, pair.Value);
            for (int i = 0; i < fields.Length; i++) fields[i].SetValue(null, savedFields[i]);
            actionsField.SetValue(null, savedActions);
        }
        Console.WriteLine("DETAIL: actual journal Unload on worker -> installed tML queue -> main-thread GPU boundary; partial load, repeated unload, borrowed textures, delayed previous-generation callback; disposal failure isolation=" + failDisposal);
    }
}

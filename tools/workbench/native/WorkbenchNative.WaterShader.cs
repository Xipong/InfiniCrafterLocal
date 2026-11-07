using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Text.Json.Nodes;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using ReLogic.Content;
using ReLogic.Content.Readers;
using ReLogic.Content.Sources;
using Terraria;
using Terraria.Graphics.Effects;
using Terraria.GameContent.Shaders;

// Genuine native lifecycle dependency for projectile AI, not an AI replacement.
// The stand does not run the complete water/world postprocessing pipeline.
internal sealed class WNativeWaterShader : IDisposable
{
    const BindingFlags All = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static;
    const string Key = "WaterDistortion";
    readonly string stagedRoot;
    readonly IDictionary effects;
    readonly bool hadPrevious;
    readonly object? previous;
    readonly List<(EventInfo Event, Delegate Handler)> subscriptions = new();
    AssetRepository? assets;
    WaterShaderData? shader;
    Filter? filter;
    bool disposed;
    public JsonObject Report { get; }

    public WNativeWaterShader(WorkbenchGraphicsContext graphics, string vanillaAssetRoot)
    {
        // Validate the exact supplied resource before the native constructor can
        // subscribe to global events. No pixel/texture stand-ins are admitted.
        byte[] bytes = WNativeVanillaProjectileAssets.ReadResource(vanillaAssetRoot, "Misc/Ripples.png", out var receipt);
        FieldInfo? dictionary = null;
        for (Type? type = Filters.Scene.GetType(); type is not null && dictionary is null; type = type.BaseType)
            dictionary = type.GetField("_effects", All | BindingFlags.DeclaredOnly);
        effects = dictionary?.GetValue(Filters.Scene) as IDictionary
            ?? throw new NotSupportedException("Native filter registry unavailable for scoped restoration");
        hadPrevious = effects.Contains(Key); previous = hadPrevious ? effects[Key] : null;
        Report = new JsonObject {
            ["shaderType"] = typeof(WaterShaderData).FullName, ["constructor"] = "WaterShaderData(FilterWaterDistortion)",
            ["resource"] = receipt, ["aiImplementationReplaced"] = false,
            ["nativeQueueRipple"] = true, ["worldWaterPostprocessing"] = "notRun",
            ["scope"] = "Original WaterShaderData constructor and QueueRipple used by native projectile AI. Full water render targets, wave stepping, noise-image shader binding and world postprocessing are not executed by this stand.",
            ["cleanup"] = "pending"
        };
        stagedRoot = Path.Combine(Path.GetTempPath(), "ifc-water-resource-" + Guid.NewGuid().ToString("N"));
        var previousAssets = Main.Assets;
        try
        {
            Directory.CreateDirectory(Path.Combine(stagedRoot, "Images", "Misc"));
            File.WriteAllBytes(Path.Combine(stagedRoot, "Images", "Misc", "Ripples.png"), bytes);
            var readers = new AssetReaderCollection(); readers.RegisterReader(new PngReader(graphics.Device), ".png");
            assets = new AssetRepository(readers, new[] { new FileSystemContentSource(stagedRoot) });
            var texture = assets.Request<Texture2D>("Images/Misc/Ripples", AssetRequestMode.ImmediateLoad);
            if (texture.State != AssetState.Loaded) throw new InvalidDataException("Exact native Ripples resource did not load");
            Report["texture"] = new JsonObject { ["state"] = texture.State.ToString(), ["width"] = texture.Value.Width, ["height"] = texture.Value.Height };
            // Resolve cleanup bindings before constructing/subscribing anything.
            var handlers = new[] {
                ("OnRenderTargetsInitialized", "InitRenderTargets", new[] { typeof(int), typeof(int) }),
                ("OnRenderTargetsReleased", "ReleaseRenderTargets", Type.EmptyTypes),
                ("OnPreDraw", "PreDraw", new[] { typeof(GameTime) })
            };
            var methods = new List<(EventInfo Event, MethodInfo Method)>();
            foreach (var (eventName, methodName, parameters) in handlers)
                methods.Add((typeof(Main).GetEvent(eventName, All) ?? throw new MissingMemberException(typeof(Main).FullName, eventName),
                    typeof(WaterShaderData).GetMethod(methodName, All, null, parameters, null) ?? throw new MissingMethodException(typeof(WaterShaderData).FullName, methodName)));
            Main.Assets = assets;
            shader = new WaterShaderData("FilterWaterDistortion");
            foreach (var entry in methods)
                subscriptions.Add((entry.Event, Delegate.CreateDelegate(entry.Event.EventHandlerType!, shader, entry.Method)));
            shader.UseIntensity(1f);
            filter = new Filter(shader, EffectPriority.VeryHigh);
            Filters.Scene[Key] = filter;
            if (Filters.Scene[Key].GetShader() is not WaterShaderData) throw new InvalidOperationException("Native water shader binding did not retain its genuine type");
            Report["cleanupBindings"] = subscriptions.Count;
        }
        catch { Dispose(); throw; }
        finally { Main.Assets = previousAssets; }
    }

    public void Dispose()
    {
        if (disposed) return; disposed = true;
        var failures = new JsonArray(); int detached = 0;
        if (shader is not null)
        {
            Report["queuedRipplesAtRelease"] = (int?)typeof(WaterShaderData).GetField("_rippleQueueCount", All)?.GetValue(shader);
            foreach (var (nativeEvent, handler) in subscriptions)
                try { nativeEvent.GetRemoveMethod(true)!.Invoke(null, new object[] { handler }); detached++; }
                catch (Exception error) { failures.Add("detach:" + nativeEvent.Name + ":" + error.GetType().Name); }
            try { typeof(WaterShaderData).GetMethod("ReleaseRenderTargets", All, null, Type.EmptyTypes, null)!.Invoke(shader, null); }
            catch (Exception error) { failures.Add("release_targets:" + error.GetType().Name); }
        }
        try
        {
            // Restore only the filter this scope still owns; never overwrite a
            // third-party replacement that occurred during actual native hooks.
            if (filter is not null && ReferenceEquals(effects[Key], filter))
            { if (hadPrevious) effects[Key] = previous; else effects.Remove(Key); }
        }
        finally
        {
            try { assets?.Dispose(); }
            finally { if (Directory.Exists(stagedRoot)) Directory.Delete(stagedRoot, recursive: true); }
        }
        Report["eventHandlersDetached"] = detached;
        Report["cleanupFailures"] = failures;
        Report["cleanup"] = failures.Count == 0 ? "complete" : "failed";
        if (failures.Count > 0) throw new InvalidOperationException("Native water shader cleanup failed: " + failures.ToJsonString());
    }
}

#nullable enable
using System;
using System.Reflection;

internal static partial class EngineRuntimeChecks
{
    // Cleanup seam shared by the retained placed-body ledger checks.
    private static Type PlacedNativeAdapterType() => typeof(global::InfiniCrafterLocal.InfiniCrafterLocalMod).Assembly
        .GetType("InfiniCrafterLocal.Common.Systems.GeneratedPlacedBodyNativeAdapter", false)
        ?? throw new InvalidOperationException("native placed-body final-submission adapter missing");
    private static object? PlacedNativeCall(string name, params object?[] args)
    {
        try { return PlacedNativeAdapterType().GetMethod(name, BindingFlags.Static | BindingFlags.NonPublic)!.Invoke(null, args); }
        catch (TargetInvocationException e) when (e.InnerException is not null) { throw e.InnerException; }
    }
}

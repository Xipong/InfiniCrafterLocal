#nullable enable
using System;
using System.Linq;
using System.Reflection;
using InfiniCrafterLocal.Common.Systems;

internal static partial class EngineRuntimeChecks
{
    // Cleanup seam shared by the retained placed-body ledger checks.
    private static Type PlacedNativeAdapterType() => typeof(global::InfiniCrafterLocal.InfiniCrafterLocalMod).Assembly
        .GetType("InfiniCrafterLocal.Common.Systems.GeneratedPlacedBodyNativeAdapter", false)
        ?? throw new InvalidOperationException("native placed-body final-submission adapter missing");
    private static void PlacedNativeProfileKeepsExactHashShapeAndLifecycle()
    {
        var adapter = PlacedNativeAdapterType();
        var available = adapter.GetProperty("FeatureAvailable", PersistenceStatic)!;
        var lifecycle = new InfiniCrafterLocal.Common.Systems.GeneratedPlacementLedgerSystem();
        PlacedNativeCall("Unload");
        try
        {
            lifecycle.PostSetupContent();
            Equal(true, (bool)available.GetValue(null)!, "native profile installs: "
                + adapter.GetProperty("UnsupportedBoundary", PersistenceStatic)!.GetValue(null));
            Equal(19, (int)PlacedNativeCall("GetOwnedHookCount")!, "complete native hook roster retained");
            Equal(true, GeneratedPlacedBodyNativeAdapter.TryAdmitNative(
                Terraria.ID.TileID.Stone, null, false, out _), "supported ordinary native tile admitted");
            Equal(false, GeneratedPlacedBodyNativeAdapter.TryAdmitNative(
                Terraria.ID.TileID.Count, null, false, out string foreign), "uncertified ModTile refused");
            Equal(true, foreign.Contains("ModTile"), "foreign tile has exact refusal reason");
            Equal(false, GeneratedPlacedBodyNativeAdapter.TryAdmitNative(
                Terraria.ID.TileID.Stone, null, true, out _), "uncertified actor refused");
            var roster = (System.Collections.IList)typeof(Terraria.ModLoader.SystemLoader)
                .GetField("Systems", PersistenceStatic)!.GetValue(null)!;
            var unowned = new UnownedPlacedVisualSystem(); roster.Add(unowned);
            try
            {
                Equal(false, GeneratedPlacedBodyNativeAdapter.TryAdmitNative(
                    Terraria.ID.TileID.Stone, null, false, out string callback), "unowned visual callback refused");
                Equal(true, callback.Contains("unowned visual callback"), "callback has exact refusal reason");
            }
            finally { roster.Remove(unowned); }
            lifecycle.Unload();
            Equal(false, (bool)available.GetValue(null)!, "unload disables admission");
            Equal(0, (int)PlacedNativeCall("GetOwnedHookCount")!, "unload retires all owned hooks");

            // The file-open boundary supplies different bytes, not a forged loaded
            // assembly or a bypass of the production hash gate.
            string unknownProfile = System.IO.Path.Combine(Terraria.Program.SavePath, "unknown-native-profile.dll");
            System.IO.File.WriteAllBytes(unknownProfile, new byte[] { 1, 2, 3 });
            int opened = 0;
            using (var hashProbe = new MonoMod.RuntimeDetour.ILHook(adapter.GetMethod("ValidateNativeProfile", PersistenceStatic)!, il => {
                var sites = il.Body.Instructions.Where(ins => ins.Operand is Mono.Cecil.MethodReference method
                    && method.DeclaringType.FullName == "System.IO.File" && method.Name == "OpenRead").ToArray();
                Equal(1, sites.Length, "one actual native-profile file-open boundary");
                var cursor = new MonoMod.Cil.ILCursor(il); cursor.Goto(sites[0]);
                cursor.EmitDelegate((Func<string,string>)(_ => { opened++; return unknownProfile; }));
            }))
            {
                object?[] install = { (Func<int,int,bool>)((_,_) => false), null, null };
                Equal(false, (bool)PlacedNativeCall("TryInstall", install)!, "unknown native bytes cannot install");
                Equal(true, ((string)install[2]!).Contains("unsupported native assembly SHA256"), "hash refusal precedes hooks");
                Equal(1, opened, "unknown-byte probe reached actual hash owner");
                Equal(0, (int)PlacedNativeCall("GetOwnedHookCount")!, "hash refusal retains no hooks");
            }
            var methods = (MethodInfo[])PlacedNativeCall("GetFixtureMethods")!;
            var lateMethod = methods.Single(method => method.Name == "DrawMultiTileVinesInWind");
            using (var shapeProbe = new MonoMod.RuntimeDetour.ILHook(lateMethod, il => {
                var cursor = new MonoMod.Cil.ILCursor(il); cursor.Emit(Mono.Cecil.Cil.OpCodes.Nop);
            }))
            {
                object?[] install = { (Func<int,int,bool>)((_,_) => false), null, null };
                Equal(false, (bool)PlacedNativeCall("TryInstall", install)!, "altered current hook-chain shape cannot install");
                Equal(true, ((string)install[2]!).Contains("typed/positional IL shape mismatch"), "shape refusal is not a hash refusal");
                Equal(false, (bool)available.GetValue(null)!, "partial installation remains disabled");
                Equal(0, (int)PlacedNativeCall("GetOwnedHookCount")!, "late-chain refusal cleans every earlier hook");
            }
            lifecycle.PostSetupContent();
            Equal(true, (bool)available.GetValue(null)!, "unmodified exact profile reinstalls after refusal");
        }
        finally { lifecycle.Unload(); }
    }

    private sealed class UnownedPlacedVisualSystem : Terraria.ModLoader.ModSystem
    {
        public override void PostDrawTiles() { }
    }

    private static object? PlacedNativeCall(string name, params object?[] args)
    {
        try { return PlacedNativeAdapterType().GetMethod(name, BindingFlags.Static | BindingFlags.NonPublic)!.Invoke(null, args); }
        catch (TargetInvocationException e) when (e.InnerException is not null) { throw e.InnerException; }
    }
}

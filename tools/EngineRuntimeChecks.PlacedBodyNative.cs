#nullable enable
using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Mono.Cecil;
using Mono.Cecil.Cil;
using MonoMod.Cil;
using MonoMod.RuntimeDetour;
using MonoMod.Utils;
using Terraria;
using Terraria.GameContent.Tile_Entities;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    // Register these four exact methods in EngineRuntimeChecks.cs and this file
    // in its explicit Compile items. Baseline compilable: only reflection names
    // refer to the missing adapter. Compiler/native RED->GREEN belongs to parent.
    private static Type PlacedNativeAdapterType() => typeof(global::InfiniCrafterLocal.InfiniCrafterLocalMod).Assembly
        .GetType("InfiniCrafterLocal.Common.Systems.GeneratedPlacedBodyNativeAdapter", false)
        ?? throw new InvalidOperationException("native placed-body final-submission adapter missing");
    private static object? PlacedNativeCall(string name, params object?[] args)
    {
        try { return PlacedNativeAdapterType().GetMethod(name, BindingFlags.Static | BindingFlags.NonPublic)!.Invoke(null, args); }
        catch (TargetInvocationException e) when (e.InnerException is not null) { throw e.InnerException; }
    }
    private static void PlacedNativeRequire(bool value, string label)
    { if (!value) throw new InvalidOperationException(label); }

    public static void NativePlacedBodyGuardsAndPositions()
    {
        var methods = (MethodInfo[])PlacedNativeCall("GetFixtureMethods")!;
        PlacedNativeRequire(methods.Length == 19, "complete 19 native method adapter roster");
        int submissions = 0;
        foreach (var native in methods)
        {
            using var module = ModuleDefinition.ReadModule(native.Module.FullyQualifiedName);
            var fixture = (MethodDefinition)module.LookupToken(native.MetadataToken);
            int count = (int)PlacedNativeCall("ValidateFixture", fixture)!;
            PlacedNativeRequire(count > 0, "native typed callsites missing: " + native.Name);
            submissions += count;
            // Exercise exactly the production rewrite on the real method body.
            using var il = new ILContext(fixture);
            int originalCount = fixture.Body.Instructions.Count;
            var original = fixture.Body.Instructions.ToArray();
            var originalOp = original.Select(i => i.OpCode).ToArray();
            var originalOperand = original.Select(i => i.Operand).ToArray();
            var handlers = fixture.Body.ExceptionHandlers.ToArray();
            int rewritten = (int)PlacedNativeCall("RewriteFixture", il, (Func<int,int,bool>)((_,_) => false))!;
            PlacedNativeRequire(rewritten == count && fixture.Body.Instructions.Count > originalCount, "all final calls rewritten: " + native.Name);
            // All original opcodes/operands remain. No producer, Update, light,
            // RNG, liquid, neighbor, cache, or native final call is replaced.
            for (int j = 0; j < original.Length; j++)
                PlacedNativeRequire((original[j].OpCode == originalOp[j] || (originalOp[j].OperandType == OperandType.ShortInlineBrTarget && original[j].OpCode.Name+".s" == originalOp[j].Name)) && ReferenceEquals(original[j].Operand, originalOperand[j]), "original instruction modified: " + native.Name + " #" + j);
            PlacedNativeRequire(handlers.SequenceEqual(fixture.Body.ExceptionHandlers), "native exception handlers changed");
            PlacedNativeCall("VerifyRewrittenFixture", il);
        }
        PlacedNativeRequire(submissions == 156, "151 sprites + lens + item frame + 3 actor submissions");
        // Slot and typed-signature mutations must fail before any insertion.
        foreach (string mutation in new[]{"signature", "slot", "position", "missing"})
        {
            MethodInfo native = methods.Single(m => m.Name == "DrawMultiTileVinesInWind");
            using var module = ModuleDefinition.ReadModule(native.Module.FullyQualifiedName);
            var fixture = (MethodDefinition)module.LookupToken(native.MetadataToken);
            var draw = fixture.Body.Instructions.First(i => i.Operand is MethodReference mr && mr.DeclaringType.FullName == typeof(SpriteBatch).FullName && mr.Name == "Draw");
            if (mutation == "signature") ((MethodReference)draw.Operand).Parameters[6].ParameterType = module.ImportReference(typeof(Vector2));
            if (mutation == "slot") fixture.Body.Variables[20].VariableType = module.TypeSystem.Single;
            if (mutation == "position") fixture.Body.Instructions.First(i => i.OpCode == OpCodes.Ldloc_S && i.Operand == fixture.Body.Variables[20]).Operand = fixture.Body.Variables[21];
            if (mutation == "missing") { draw.OpCode = OpCodes.Nop; draw.Operand = null; }
            int before = fixture.Body.Instructions.Count;
            bool rejected = false;
            try { PlacedNativeCall("ValidateFixture", fixture); }
            catch (InvalidOperationException) { rejected = true; }
            PlacedNativeRequire(rejected && before == fixture.Body.Instructions.Count, "shape mutant not refused without mutation: " + mutation);
        }
    }

    private static int _placedNativeArgumentEffects, _placedNativeTailEffects;
    [MethodImpl(MethodImplOptions.NoInlining)] private static Color PlacedNativeArgumentEffect()
    { _placedNativeArgumentEffects++; return Color.White; }
    [MethodImpl(MethodImplOptions.NoInlining)] private static void PlacedNativeTailEffect() => _placedNativeTailEffects++;
    [MethodImpl(MethodImplOptions.NoInlining)] private static void PlacedNativeSubmissionProbe(SpriteBatch batch, Texture2D texture, int x, int y)
    {
        batch.Draw(texture, new Vector2(3,7), null, PlacedNativeArgumentEffect(), 0f, Vector2.Zero, 1f, SpriteEffects.None, 0f);
        PlacedNativeTailEffect();
    }
    public static void NativePlacedBodyFinalCallPreservesArgumentEffects()
    {
        // This synthetic caller uses the unchanged real FNA Draw overload.
        // Only the shared final-call insertion helper is applied. No world/GPU.
        var probe = typeof(EngineRuntimeChecks).GetMethod(nameof(PlacedNativeSubmissionProbe), BindingFlags.Static | BindingFlags.NonPublic)!;
        const BindingFlags hidden = BindingFlags.Instance | BindingFlags.NonPublic;
        var batch = (SpriteBatch)RuntimeHelpers.GetUninitializedObject(typeof(SpriteBatch));
        var texture = (Texture2D)RuntimeHelpers.GetUninitializedObject(typeof(Texture2D));
        GC.SuppressFinalize(batch); GC.SuppressFinalize(texture);
        foreach (string name in new[]{"vertexInfo","textureInfo","spriteInfos","sortedSpriteInfos"})
        {
            FieldInfo field = typeof(SpriteBatch).GetField(name, hidden)!;
            field.SetValue(batch, Array.CreateInstance(field.FieldType.GetElementType()!,16));
        }
        typeof(Texture2D).GetProperty("Width")!.SetValue(texture, 16);
        typeof(Texture2D).GetProperty("Height")!.SetValue(texture, 16);
        FieldInfo count = typeof(SpriteBatch).GetField("numSprites", hidden)!;
        using var flush = new Hook(typeof(SpriteBatch).GetMethod("FlushBatch",hidden)!, (Action<SpriteBatch>)(self => count.SetValue(self,0)));
        int predicateVisits=0;
        using var dmd = new DynamicMethodDefinition(probe);
        using var il = new ILContext(dmd.Definition);
        PlacedNativeCall("RewriteProbeFixture", il, (Func<int,int,bool>)((x,y) => { predicateVisits++; return x==41 && y==17; }));
        var run = (Action<SpriteBatch,Texture2D,int,int>)dmd.Generate().CreateDelegate(typeof(Action<SpriteBatch,Texture2D,int,int>));
        int oldArgs=_placedNativeArgumentEffects, oldTail=_placedNativeTailEffects;
        try
        {
            batch.Begin();
            run(batch,texture,41,17);
            PlacedNativeRequire((int)count.GetValue(batch)! == 0 && predicateVisits==1, "owned source skips only final FNA Draw");
            run(batch,texture,42,17);
            PlacedNativeRequire((int)count.GetValue(batch)! == 1 && predicateVisits==2, "unowned neighbor executes unchanged FNA Draw");
            PlacedNativeRequire(_placedNativeArgumentEffects==oldArgs+2 && _placedNativeTailEffects==oldTail+2, "argument evaluation and native tail preserved for both outcomes");
        }
        finally
        {
            batch.End();
            _placedNativeArgumentEffects=oldArgs; _placedNativeTailEffects=oldTail;
            // Never Dispose constructor-bypassed graphics shells.
        }
    }

    public static void NativePlacedBodyAtomicInstallationAndCleanup()
    {
        var type=PlacedNativeAdapterType();
        PropertyInfo available=type.GetProperty("FeatureAvailable",BindingFlags.Static|BindingFlags.NonPublic)!;
        MethodInfo method=((MethodInfo[])PlacedNativeCall("GetFixtureMethods")!).Single(m=>m.Name=="DrawMultiTileVinesInWind");
        PlacedNativeCall("Unload");
        // Late-method corrupting hook must decline admission and remove every
        // earlier owned hook. This is actual MonoMod installation, no drawing.
        using (var mutant = new ILHook(method, il => {
            var call=il.Body.Instructions.First(i=>i.Operand is MethodReference mr && mr.DeclaringType.FullName==typeof(SpriteBatch).FullName && mr.Name=="Draw");
            var c=new ILCursor(il); c.Goto(call); c.Emit(OpCodes.Nop);
        }))
        {
            object?[] args={(Func<int,int,bool>)((_,_)=>false), null, null};
            bool installed=(bool)PlacedNativeCall("TryInstall",args)!;
            PlacedNativeRequire(!installed && !(bool)available.GetValue(null)! && args[2] is string reason && reason.Contains("shape",StringComparison.OrdinalIgnoreCase), "native shape failure must disable complete capability");
            PlacedNativeRequire((int)PlacedNativeCall("GetOwnedHookCount")! == 0, "failed installation owned hooks cleaned");
        }
        try
        {
            object?[] args={(Func<int,int,bool>)((_,_)=>false),null,null};
            PlacedNativeRequire((bool)PlacedNativeCall("TryInstall",args)! && (bool)available.GetValue(null)!, "all 19 native hooks installed atomically");
            PlacedNativeRequire((int)PlacedNativeCall("GetOwnedHookCount")! == 19, "full required hook roster retained");
        }
        finally { PlacedNativeCall("Unload"); }
        PlacedNativeRequire(!(bool)available.GetValue(null)! && (int)PlacedNativeCall("GetOwnedHookCount")! == 0, "unload closes feature before hook disposal");
        var lifecycle = new InfiniCrafterLocal.Common.Systems.GeneratedPlacementLedgerSystem();
        try
        {
            lifecycle.PostSetupContent();
            PlacedNativeRequire((bool)available.GetValue(null)! && (int)PlacedNativeCall("GetOwnedHookCount")! == 19,"production content lifecycle installs complete native adapter");
        }
        finally { lifecycle.Unload(); }
        PlacedNativeRequire(!(bool)available.GetValue(null)! && (int)PlacedNativeCall("GetOwnedHookCount")! == 0,"production unload owns complete adapter retirement");
    }

    private sealed class UnownedPlacedNativeGlobal : GlobalTile
    {
        public override bool PreDraw(int i,int j,int type,SpriteBatch batch) => true;
    }
    private sealed class UnownedPlacedNativeSystem : ModSystem
    {
        public override void PostDrawTiles() { }
    }
    public static void NativePlacedBodyUnsupportedAdmissionIsExplicit()
    {
        PlacedNativeCall("Unload");
        try
        {
            object?[] install={(Func<int,int,bool>)((_,_)=>false),null,null};
            PlacedNativeRequire((bool)PlacedNativeCall("TryInstall",install)!, "native complete set required for admission controls");
            object?[] foreign={Terraria.ID.TileID.Count,null,false,null};
            PlacedNativeRequire(!(bool)PlacedNativeCall("TryAdmitNative",foreign)! && ((string)foreign[3]!).Contains("ModTile"), "foreign ModTile refused explicitly");
            object?[] unproved={1,null,true,null};
            PlacedNativeRequire(!(bool)PlacedNativeCall("TryAdmitNative",unproved)! && ((string)unproved[3]!).Contains("actor"), "uncertified independent actor refused explicitly");
            var rack=(TEHatRack)RuntimeHelpers.GetUninitializedObject(typeof(TEHatRack));
            object?[] indirect={1,rack,false,null};
            PlacedNativeRequire(!(bool)PlacedNativeCall("TryAdmitNative",indirect)! && ((string)indirect[3]!).Contains("parent-owned"), "indirect native actor cannot borrow coordinate-only proof");
            foreach ((Type loader,string field,object witness) in new[]{
                (typeof(TileLoader),"globalTiles",(object)new UnownedPlacedNativeGlobal()),
                (typeof(SystemLoader),"Systems",(object)new UnownedPlacedNativeSystem()) })
            {
                var roster=(IList)loader.GetField(field,BindingFlags.Static|BindingFlags.NonPublic)!.GetValue(null)!;
                roster.Add(witness);
                try
                {
                    object?[] admission={1,null,false,null};
                    PlacedNativeRequire(!(bool)PlacedNativeCall("TryAdmitNative",admission)! && ((string)admission[3]!).Contains("unowned visual callback"), "foreign visual callback refusal: "+field+" -> "+admission[3]);
                }
                finally { roster.Remove(witness); }
            }
        }
        finally { PlacedNativeCall("Unload"); }
    }
}

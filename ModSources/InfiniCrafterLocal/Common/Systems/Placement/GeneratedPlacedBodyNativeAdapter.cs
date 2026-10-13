#nullable enable
using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Mono.Cecil;
using Mono.Cecil.Cil;
using MonoMod.Cil;
using MonoMod.RuntimeDetour;
using MonoMod.Utils;
using Terraria;
using Terraria.DataStructures;
using Terraria.GameContent.Drawing;
using Terraria.GameContent.Tile_Entities;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Systems;

// Private source-adapter proposal. No ModSystem autoload, ledger, renderer,
// texture owner, recipe migration or admission mutation is introduced here.
// Parent lifecycle must call TryInstall(GeneratedPlacementLedgerSystem.
// ShouldSuppressPlacedBody, actorCertificateOrNull, out reason) and Unload.
internal static partial class GeneratedPlacedBodyNativeAdapter
{
    private enum SourceKind { Argument, Local, PointX, PointY }
    private enum SubmissionKind { Sprite, Lens, Icon, Actor }
    private readonly record struct Source(SourceKind Kind, int Slot);
    private sealed record Contract(string Owner, string Name, string[] Parameters, string[] Locals,
        string Shape, Source X, Source Y, SubmissionKind[] Submissions, int ExceptionHandlers);
    private sealed record Site(Instruction Call, Instruction After, SubmissionKind Kind, int PopCount);
    private sealed record Plan(Contract Contract, Site[] Sites);
    private static readonly object Sync = new();
    private static readonly List<ILHook> Hooks = new();
    private static Func<int,int,bool>? CellPredicate;
    // This separate parent-owned proof is REQUIRED for actor admission. It must
    // certify exact live TE generation/footprint/binding and native contents and
    // visual callback ownership; a coordinate or same-type actor is not proof.
    private static Func<TileEntity,int,int,bool>? ActorPredicate;
    private static int Available;
    private static string Boundary = "native placed-body source adapter not installed";
    internal static bool FeatureAvailable => Volatile.Read(ref Available) != 0;
    internal static string UnsupportedBoundary => Volatile.Read(ref Boundary);
    private static InvalidOperationException Guard(string reason) => new("native placed-body shape: " + reason);
    private static void Disable(string reason)
    { Volatile.Write(ref Available,0); Volatile.Write(ref Boundary,reason); }

    internal static bool TryInstall(Func<int,int,bool> shouldSuppressPlacedBody,
        Func<TileEntity,int,int,bool>? certifyActorBody, out string reason)
    {
        ArgumentNullException.ThrowIfNull(shouldSuppressPlacedBody);
        lock (Sync)
        {
            if (Hooks.Count != 0) { reason = "native placed-body hooks already retained; unload before reinstall"; return false; }
            Disable("native placed-body complete adapter set is being validated");
            try
            {
                ValidateNativeProfile();
                MethodInfo[] methods = GetFixtureMethods();
                // Preflight every method before applying even the first hook.
                for (int i=0; i<methods.Length; i++)
                {
                    using var dmd = new DynamicMethodDefinition(methods[i]);
                    using var il = new ILContext(dmd.Definition);
                    BuildPlan(il.Method,Required[i]);
                }
                CellPredicate = shouldSuppressPlacedBody;
                ActorPredicate = certifyActorBody;
                for (int i=0; i<methods.Length; i++)
                {
                    Contract contract=Required[i];
                    var hook = new ILHook(methods[i], il => {
                        try
                        {
                            // Guard the CURRENT MonoMod chain, not just the DLL.
                            Plan plan = BuildPlan(il.Method,contract);
                            Rewrite(il,plan,ShouldSuppress,ShouldSuppressActor,ShouldSuppressLegacy);
                        }
                        catch (Exception e) { Disable(e.Message); throw; }
                    }, applyByDefault:false);
                    Hooks.Add(hook); // retain before Apply, including failed Apply
                    hook.Apply();
                }
                // During partial installation every gate is inert. Publish only
                // after all 19 hooks exist, validated and successfully applied.
                Volatile.Write(ref Boundary,string.Empty);
                Volatile.Write(ref Available,1);
                reason = string.Empty; return true;
            }
            catch (Exception e)
            {
                Disable(e.Message);
                string cleanup = Cleanup();
                CellPredicate = null; ActorPredicate = null;
                reason = e.ToString() + cleanup;
                Volatile.Write(ref Boundary,reason);
                return false;
            }
        }
    }
    internal static void Unload()
    {
        lock (Sync)
        {
            Disable("native placed-body source adapter unloaded");
            string failure=Cleanup(); CellPredicate=null; ActorPredicate=null;
            if (failure.Length != 0) throw Guard("disabled but hook cleanup failed"+failure);
        }
    }
    private static string Cleanup()
    {
        var failures=new List<string>();
        // Attempt ALL disposals. Retain only handles that actually failed so a
        // subsequent Unload can retry; they remain inert because Available=0.
        for (int i=Hooks.Count-1; i>=0; i--)
        {
            try { Hooks[i].Dispose(); Hooks.RemoveAt(i); }
            catch (Exception e) { failures.Add(e.GetType().Name+": "+e.Message); }
        }
        return failures.Count==0 ? string.Empty : "; cleanup: "+string.Join(" | ",failures);
    }
    private static void ValidateNativeProfile()
    {
        string path=typeof(TileDrawing).Assembly.Location;
        if (string.IsNullOrEmpty(path)) throw Guard("native assembly has no literal byte identity");
        using var file=File.OpenRead(path);
        string hash=Convert.ToHexString(SHA256.HashData(file)).ToLowerInvariant();
        if (hash != "fcc6a9624b12191be4a15d714a3675440911feb8c1d374642ab1fd686f0da0a5"
            && hash != "0585f4ebb022708a5d2a52ba92c6b4a4f812154d0333b384ef64d2dbd4f5b124")
            throw Guard("unsupported native assembly SHA256 "+hash);
    }

    // Explicit bounded admission. Parent calls this BEFORE placement mutation
    // and must supply its mechanically witnessed actor classification, including
    // native NPC/other visual actors that are NOT owned by these consumers.
    // No item/tile-name router and no arbitrary cross-mod-output guarantee.
    internal static bool TryAdmitNative(int tileType, TileEntity? actor,
        bool hasUncertifiedVisualActor, out string reason)
    {
        reason = UnsupportedBoundary;
        if (!FeatureAvailable) return false;
        if (tileType < 0 || tileType >= Terraria.ID.TileID.Count || TileLoader.GetTile(tileType) is not null)
        { reason="unsupported placed-body boundary: third-party ModTile visual ownership is not certified"; return false; }
        if (hasUncertifiedVisualActor)
        { reason="unsupported placed-body boundary: independent native/third-party actor visual ownership is not certified"; return false; }
        if (actor is not null && (ActorPredicate is null || actor.GetType().Assembly != typeof(TileEntity).Assembly))
        { reason="unsupported placed-body boundary: native indirect actor requires exact parent-owned generation/content/callback proof"; return false; }
        // Native dispatchers expose real rosters. Decline foreign visual hooks;
        // do not suppress their callbacks or claim that an overlay replaces them.
        try
        {
            if (!CheckForeignVisualRoster(typeof(TileLoader),"globalTiles",typeof(GlobalTile),
                new[]{"PreDraw","DrawEffects","PostDraw","SpecialDraw","EmitParticles"},out reason)) return false;
            if (!CheckForeignVisualRoster(typeof(SystemLoader),"Systems",typeof(ModSystem),
                new[]{"PreDrawTiles","PostDrawTiles"},out reason)) return false;
        }
        catch (Exception e) { reason="unsupported placed-body boundary: visual callback roster proof unavailable: "+e.Message; return false; }
        reason=string.Empty; return true;
    }
    private static bool CheckForeignVisualRoster(Type loader,string field,Type nativeBase,string[] hooks,out string reason)
    {
        FieldInfo? roster=loader.GetField(field,BindingFlags.Static|BindingFlags.NonPublic);
        if (roster is null || !typeof(IEnumerable).IsAssignableFrom(roster.FieldType)
            || roster.GetValue(null) is not IEnumerable entries) throw Guard("literal native visual roster missing: "+field);
        foreach (object instance in entries)
        {
            Type actual=instance.GetType();
            if (!nativeBase.IsAssignableFrom(actual)) throw Guard("visual roster element mismatch: "+field);
            foreach (string name in hooks)
                foreach (MethodInfo method in actual.GetMethods(BindingFlags.Instance|BindingFlags.Public|BindingFlags.NonPublic).Where(m=>m.Name==name))
                    if (method.IsVirtual
                        && nativeBase.GetMethod(name, BindingFlags.Instance|BindingFlags.Public|BindingFlags.NonPublic,
                            null, method.GetParameters().Select(p => p.ParameterType).ToArray(), null) is MethodInfo nativeHook
                        && method.DeclaringType != nativeHook.DeclaringType
                        && method.GetBaseDefinition() == nativeHook.GetBaseDefinition())
                    {
                        // Exactly the parent-owned root PNG consumer, not every
                        // callback sharing this assembly or Mod identity.
                        Type? renderer=typeof(GeneratedPlacedBodyNativeAdapter).Assembly.GetType("InfiniCrafterLocal.Common.Systems.GeneratedPlacedBodyDrawSystem",false);
                        if (method.DeclaringType==renderer && nativeBase==typeof(ModSystem) && name=="PostDrawTiles") continue;
                        reason="unsupported placed-body boundary: unowned visual callback "+actual.FullName+"."+name; return false;
                    }
        }
        reason=string.Empty; return true;
    }
    private static bool ShouldSuppress(int x,int y) => FeatureAvailable && CellPredicate!(x,y);
    private static bool ShouldSuppressActor(TileEntity actor,int x,int y)
        => ShouldSuppress(x,y) && ActorPredicate is not null
        && actor.Position.X==x && actor.Position.Y==y
        && TileEntity.ByPosition.TryGetValue(new Point16(x,y),out TileEntity? current)
        && ReferenceEquals(actor,current) && ActorPredicate(actor,x,y);
    private static bool ShouldSuppressLegacy(int x,int y)
    {
        if (!ShouldSuppress(x,y)) return false;
        return !TileEntity.ByPosition.TryGetValue(new Point16(x,y),out TileEntity? actor)
            || (ActorPredicate is not null && ActorPredicate(actor,x,y));
    }

    private static string ReflectionType(Type type)
    {
        if (type.IsByRef) return ReflectionType(type.GetElementType()!)+"&";
        if (type.IsArray) return ReflectionType(type.GetElementType()!)+"[]";
        if (type.IsGenericType) return type.GetGenericTypeDefinition().FullName!.Replace('+','/')
            +"<"+string.Join(",",type.GetGenericArguments().Select(ReflectionType))+">";
        return type.FullName!.Replace('+','/');
    }
    internal static MethodInfo[] GetFixtureMethods()
    {
        var methods=new List<MethodInfo>();
        foreach (Contract c in Required)
        {
            Type owner=typeof(TileDrawing).Assembly.GetType(c.Owner.Replace('/','+'),true)!;
            var matches=owner.GetMethods(BindingFlags.Instance|BindingFlags.Public|BindingFlags.NonPublic|BindingFlags.DeclaredOnly)
                .Where(m=>m.Name==c.Name && m.ReturnType==typeof(void) && !m.IsStatic
                    && m.GetParameters().Select(p=>ReflectionType(p.ParameterType)).SequenceEqual(c.Parameters)).ToArray();
            if (matches.Length!=1) throw Guard("literal source signature missing/ambiguous: "+c.Owner+"::"+c.Name);
            methods.Add(matches[0]);
        }
        return methods.ToArray();
    }
    private static Contract ContractFor(MethodDefinition method)
    {
        var matches=Required.Where(c=>c.Owner==method.DeclaringType.FullName && c.Name==method.Name).ToArray();
        if (matches.Length!=1) throw Guard("source owner/method not in complete manifest: "+method.FullName);
        Contract c=matches[0];
        if (!method.HasThis || method.ReturnType.FullName!="System.Void"
            || !method.Parameters.Select(p=>p.ParameterType.FullName).SequenceEqual(c.Parameters)) throw Guard("source signature mismatch: "+method.FullName);
        return c;
    }
    private static Plan BuildPlan(MethodDefinition method) => BuildPlan(method,ContractFor(method));
    private static Plan BuildPlan(MethodDefinition method,Contract c)
    {
        // MonoMod copies native instance methods to a STATIC DMD method and
        // makes the original receiver explicit parameter slot 0. Preserve the
        // literal IL argument slots, do not shift them a second time.
        string[] expected=method.HasThis ? c.Parameters : new[]{c.Owner}.Concat(c.Parameters).ToArray();
        if (method.ReturnType.FullName!="System.Void"
            || !method.Parameters.Select(p=>p.ParameterType.FullName).SequenceEqual(expected)
            || (!method.HasThis && !method.DeclaringType.Name.StartsWith("DMD<",StringComparison.Ordinal)))
            throw Guard("native/explicit-this copied source signature mismatch: "+c.Name);
        if (!method.HasBody || !method.Body.Variables.Select(v=>v.VariableType.FullName).SequenceEqual(c.Locals))
            throw Guard("literal local slot/type mismatch: "+method.Name);
        var body=method.Body;
        if (body.ExceptionHandlers.Count!=c.ExceptionHandlers) throw Guard("exception shape mismatch: "+method.Name);
        if (c.ExceptionHandlers==1)
        {
            var eh=body.ExceptionHandlers[0];
            bool tree = c.Name == "DrawTrees";
            ExceptionHandlerType kind = tree ? ExceptionHandlerType.Catch : ExceptionHandlerType.Finally;
            int end = tree ? 1042 : 73, handlerEnd = tree ? 1044 : 77;
            string? catchType = tree ? "System.Object" : null;
            if (eh.HandlerType != kind || body.Instructions.IndexOf(eh.TryStart) != 62
                || body.Instructions.IndexOf(eh.TryEnd) != end || body.Instructions.IndexOf(eh.HandlerStart) != end
                || body.Instructions.IndexOf(eh.HandlerEnd) != handlerEnd || eh.FilterStart is not null || eh.CatchType?.FullName != catchType)
                throw Guard("literal exception region mismatch: " + c.Name);
        }
        ValidateSource(method,c.X); ValidateSource(method,c.Y);
        string actualShape = Fingerprint(method);
        if (actualShape != c.Shape) throw Guard("literal typed/positional IL shape mismatch: "+method.Name+" expected "+c.Shape+" actual "+actualShape);
        var sites=new List<Site>();
        foreach (Instruction instruction in body.Instructions)
        {
            if (instruction.Operand is not MethodReference call) continue;
            SubmissionKind? kind=Submission(call);
            if (kind is null) continue;
            ValidateSubmission(instruction,call,kind.Value);
            Instruction after=instruction.Next ?? throw Guard("final-call native tail missing");
            if (kind==SubmissionKind.Icon)
            {
                // DrawItemIcon returns a scale that this literal caller discards.
                // Skip its existing pop on the suppressed path; fabricate no
                // return value. False follows the original call AND original pop.
                if (after.OpCode!=OpCodes.Pop || after.Next is null) throw Guard("item frame unused return/pop shape mismatch");
                after=after.Next;
            }
            sites.Add(new(instruction,after,kind.Value,call.Parameters.Count+(call.HasThis?1:0)));
        }
        if (!sites.Select(s=>s.Kind).SequenceEqual(c.Submissions)) throw Guard("complete typed submission roster mismatch: "+method.Name);
        // Source-specific positional fences: fingerprints preserve all earlier
        // native updates/RNG/lighting and exact per-segment cell slot writes.
        return new(c,sites.ToArray());
    }
    private static SubmissionKind? Submission(MethodReference call) => (call.DeclaringType.FullName,call.Name) switch
    {
        ("Microsoft.Xna.Framework.Graphics.SpriteBatch","Draw") => SubmissionKind.Sprite,
        ("Terraria.GameContent.VoidLensHelper","DrawToDrawData") => SubmissionKind.Lens,
        ("Terraria.UI.ItemSlot","DrawItemIcon") => SubmissionKind.Icon,
        ("Terraria.Graphics.Renderers.IPlayerRenderer","DrawPlayer") => SubmissionKind.Actor,
        _ => null,
    };
    private static void ValidateSubmission(Instruction instruction,MethodReference call,SubmissionKind kind)
    {
        string[] parameters; string result="System.Void"; bool instance=true; OpCode opcode=OpCodes.Callvirt;
        switch (kind)
        {
            case SubmissionKind.Sprite:
                parameters=new[]{"Microsoft.Xna.Framework.Graphics.Texture2D","Microsoft.Xna.Framework.Vector2","System.Nullable`1<Microsoft.Xna.Framework.Rectangle>","Microsoft.Xna.Framework.Color","System.Single","Microsoft.Xna.Framework.Vector2","System.Single","Microsoft.Xna.Framework.Graphics.SpriteEffects","System.Single"}; break;
            case SubmissionKind.Lens:
                parameters=new[]{"System.Collections.Generic.List`1<Terraria.DataStructures.DrawData>","System.Int32"}; opcode=OpCodes.Call; break;
            case SubmissionKind.Icon:
                parameters=new[]{"Terraria.Item","System.Int32","Microsoft.Xna.Framework.Graphics.SpriteBatch","Microsoft.Xna.Framework.Vector2","System.Single","System.Single","Microsoft.Xna.Framework.Color"};
                instance=false; result="System.Single"; opcode=OpCodes.Call; break;
            case SubmissionKind.Actor:
                parameters=new[]{"Terraria.Graphics.Camera","Terraria.Player","Microsoft.Xna.Framework.Vector2","System.Single","Microsoft.Xna.Framework.Vector2","System.Single","System.Single"}; break;
            default: throw Guard("unknown final submission kind");
        }
        if (instruction.OpCode!=opcode || call.HasThis!=instance || call.ReturnType.FullName!=result
            || call.GenericParameters.Count!=0 || !call.Parameters.Select(p=>p.ParameterType.FullName).SequenceEqual(parameters))
            throw Guard("literal final-call opcode/instance/return/parameter signature mismatch: "+call.FullName);
    }
    private static void ValidateSource(MethodDefinition method,Source source)
    {
        string expected=source.Kind is SourceKind.PointX or SourceKind.PointY ? "Microsoft.Xna.Framework.Point" : "System.Int32";
        string actual;
        if (source.Kind==SourceKind.Argument)
        {
            int index=source.Slot-(method.HasThis?1:0);
            if (index<0 || index>=method.Parameters.Count) throw Guard("source argument slot missing");
            actual=method.Parameters[index].ParameterType.FullName;
        }
        else
        {
            if (source.Slot<0 || source.Slot>=method.Body.Variables.Count) throw Guard("source local slot missing");
            actual=method.Body.Variables[source.Slot].VariableType.FullName;
        }
        if (actual!=expected) throw Guard("source coordinate slot type mismatch");
    }
    private static string Fingerprint(MethodDefinition method)
    {
        var instructions=method.Body.Instructions;
        var indices=instructions.Select((i,n)=>(i,n)).ToDictionary(p=>p.i,p=>p.n);
        int Target(object value) => indices[(value is ILLabel label ? label.Target : (Instruction)value)
            ?? throw Guard("branch target missing")];
        var text=new StringBuilder();
        foreach (Instruction i in instructions)
        {
            object? value=i.Operand; string operand=string.Empty;
            if (value is ILLabel || value is Instruction) operand=Target(value).ToString(CultureInfo.InvariantCulture);
            else if (value is ILLabel[] labels) operand=string.Join(",",labels.Select(l=>Target(l)));
            else if (value is Instruction[] targets) operand=string.Join(",",targets.Select(t=>Target(t)));
            else if (value is VariableDefinition local) operand=local.Index.ToString(CultureInfo.InvariantCulture);
            else if (value is ParameterDefinition parameter) operand=(parameter.Index+(method.HasThis?1:0)).ToString(CultureInfo.InvariantCulture);
            else if (value is MethodReference call) operand=call.DeclaringType.GetElementType().FullName+"::"+call.Name;
            else if (value is FieldReference field) operand=field.DeclaringType.GetElementType().FullName+"::"+field.Name;
            else if (value is TypeReference type) operand=type.GetElementType().FullName;
            else if (value is float f) operand=Convert.ToHexString(BitConverter.GetBytes(f)).ToLowerInvariant();
            else if (value is double d) operand=Convert.ToHexString(BitConverter.GetBytes(d)).ToLowerInvariant();
            else if (value is not null) operand=Convert.ToString(value,CultureInfo.InvariantCulture)!;
            text.Append(i.OpCode.Name).Append('|').Append(operand).Append('\n');
        }
        return Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(text.ToString()))).ToLowerInvariant();
    }

    private static void EmitSource(ILCursor cursor,Source source)
    {
        switch (source.Kind)
        {
            case SourceKind.Argument:
                cursor.Emit(OpCodes.Ldarg,cursor.Method.Parameters[source.Slot-(cursor.Method.HasThis?1:0)]); break;
            case SourceKind.Local: cursor.Emit(OpCodes.Ldloc,cursor.Body.Variables[source.Slot]); break;
            case SourceKind.PointX:
            case SourceKind.PointY:
                cursor.Emit(OpCodes.Ldloc,cursor.Body.Variables[source.Slot]);
                cursor.Emit(OpCodes.Ldfld,typeof(Point).GetField(source.Kind==SourceKind.PointX ? "X" : "Y")!); break;
            default: throw Guard("coordinate load kind missing");
        }
    }
    private static readonly Dictionary<string,OpCode> Opcodes=typeof(OpCodes).GetFields(BindingFlags.Public|BindingFlags.Static)
        .Where(f=>f.FieldType==typeof(OpCode)).Select(f=>(OpCode)f.GetValue(null)!).ToDictionary(o=>o.Name);
    private static void WidenBranches(Mono.Cecil.Cil.MethodBody body)
    {
        // Inserted gates can exceed original short-branch ranges. Only widen
        // branches; no local, argument, call or side-effect instruction changes.
        foreach (Instruction i in body.Instructions)
            if (i.OpCode.OperandType==OperandType.ShortInlineBrTarget)
                i.OpCode=Opcodes[i.OpCode.Name[..^2]];
    }
    private static void InsertGate(ILContext il,Site site,Source x,Source y,
        Func<int,int,bool> predicate,Func<TileEntity,int,int,bool>? actorPredicate=null)
    {
        var cursor=new ILCursor(il);
        cursor.Goto(site.Call,MoveType.AfterLabel); // retarget ALL incoming labels
        cursor.Emit(OpCodes.Nop); // fixture-visible start of source-only loads
        if (site.Kind==SubmissionKind.Actor) cursor.Emit(OpCodes.Ldarg_0);
        EmitSource(cursor,x); EmitSource(cursor,y);
        cursor.Emit(OpCodes.Nop); // separates source loads from delegate trampoline
        if (site.Kind==SubmissionKind.Actor) cursor.EmitDelegate(actorPredicate ?? throw Guard("actor gate predicate missing"));
        else cursor.EmitDelegate(predicate);
        cursor.Emit(OpCodes.Brfalse,site.Call);
        // Native arguments ALREADY evaluated: pop exactly their values and the
        // instance (including a lens managed-byref receiver). No resubmission,
        // texture substitution, global detour, early return or RNG/light skip.
        for (int i=0; i<site.PopCount; i++) cursor.Emit(OpCodes.Pop);
        cursor.Emit(OpCodes.Br,site.After);
        // The false edge executes the identical original native call.
    }
    private static int Rewrite(ILContext il,Plan plan,Func<int,int,bool> predicate,
        Func<TileEntity,int,int,bool> actorPredicate,Func<int,int,bool> legacyPredicate)
    {
        WidenBranches(il.Body);
        foreach (Site site in plan.Sites)
            InsertGate(il,site,plan.Contract.X,plan.Contract.Y,
                plan.Contract.Name=="DrawSpecialTilesLegacy" ? legacyPredicate : predicate,actorPredicate);
        return plan.Sites.Length;
    }

    // Narrow internal fixture seams exercise the REAL guards and insertion, not
    // a reimplementation. No fixture enables live feature/admission flags.
    internal static int ValidateFixture(MethodDefinition method) => BuildPlan(method).Sites.Length;
    internal static int RewriteFixture(ILContext il,Func<int,int,bool> predicate)
    {
        Plan plan=BuildPlan(il.Method);
        return Rewrite(il,plan,predicate,(_,x,y)=>predicate(x,y),predicate);
    }
    internal static int GetOwnedHookCount() { lock(Sync) return Hooks.Count; }
    internal static void RewriteProbeFixture(ILContext il,Func<int,int,bool> predicate)
    {
        var calls=il.Body.Instructions.Where(i=>i.Operand is MethodReference m && Submission(m)==SubmissionKind.Sprite).ToArray();
        if (calls.Length!=1 || il.Method.HasThis || il.Method.Parameters.Count!=4) throw Guard("native FNA probe signature mismatch");
        var call=(MethodReference)calls[0].Operand;
        ValidateSubmission(calls[0],call,SubmissionKind.Sprite);
        var x=new Source(SourceKind.Argument,2); var y=new Source(SourceKind.Argument,3);
        ValidateSource(il.Method,x); ValidateSource(il.Method,y);
        WidenBranches(il.Body);
        InsertGate(il,new(calls[0],calls[0].Next,SubmissionKind.Sprite,call.Parameters.Count+1),x,y,predicate);
    }
    internal static void VerifyRewrittenFixture(ILContext il)
    {
        Contract c=ContractFor(il.Method); int found=0;
        foreach (Instruction i in il.Body.Instructions)
        {
            if (i.Operand is not MethodReference call || Submission(call) is not SubmissionKind kind) continue;
            ValidateSubmission(i,call,kind); found++;
            int pops=call.Parameters.Count+(call.HasThis?1:0);
            Instruction node=i.Previous;
            if (node.OpCode!=OpCodes.Br) throw Guard("suppression tail branch missing");
            Instruction after=kind==SubmissionKind.Icon ? i.Next.Next : i.Next;
            if ((node.Operand is ILLabel l ? l.Target : (Instruction)node.Operand)!=after) throw Guard("suppression tail positional target mismatch");
            for (int j=0;j<pops;j++) { node=node.Previous; if(node.OpCode!=OpCodes.Pop) throw Guard("exact argument/instance pops missing"); }
            node=node.Previous;
            if(node.OpCode!=OpCodes.Brfalse || (node.Operand is ILLabel label ? label.Target : (Instruction)node.Operand)!=i) throw Guard("unchanged native call false edge mismatch");
            // The exact source loads must precede the real delegate trampoline.
            // Verify positional cell slots, never infer ownership from vertices.
            Instruction end=node.Previous;
            int limit=64;
            while(end.OpCode!=OpCodes.Nop && --limit>0) end=end.Previous;
            if(limit==0) throw Guard("source/delegate boundary missing");
            Instruction start=end.Previous;
            limit=16;
            while(start.OpCode!=OpCodes.Nop && --limit>0) start=start.Previous;
            if(limit==0) throw Guard("source load start missing");
            Instruction load=start.Next;
            if(kind==SubmissionKind.Actor)
            { if(load.OpCode!=OpCodes.Ldarg_0) throw Guard("exact actor receiver missing"); load=load.Next; }
            VerifySourceLoad(il.Method,ref load,c.X); VerifySourceLoad(il.Method,ref load,c.Y);
            if(load!=end) throw Guard("unexpected gate source instructions");
        }
        if(found!=c.Submissions.Length) throw Guard("partial rewritten submission roster");
    }
    private static void VerifySourceLoad(MethodDefinition method,ref Instruction load,Source source)
    {
        if(source.Kind==SourceKind.Argument)
        {
            if(load.OpCode!=OpCodes.Ldarg || load.Operand!=method.Parameters[source.Slot-(method.HasThis?1:0)])
                throw Guard("gate coordinate argument positional mismatch");
            load=load.Next; return;
        }
        if(load.OpCode!=OpCodes.Ldloc || load.Operand!=method.Body.Variables[source.Slot])
            throw Guard("gate coordinate local positional mismatch");
        load=load.Next;
        if(source.Kind==SourceKind.Local) return;
        if(load.OpCode!=OpCodes.Ldfld || load.Operand is not FieldReference field
            || field.DeclaringType.FullName!="Microsoft.Xna.Framework.Point" || field.FieldType.FullName!="System.Int32"
            || field.Name!=(source.Kind==SourceKind.PointX ? "X" : "Y")) throw Guard("gate coordinate Point field mismatch");
        load=load.Next;
    }
}

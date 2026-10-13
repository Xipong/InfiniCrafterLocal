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


    private static int _placedNativeArgumentEffects, _placedNativeTailEffects;
    [MethodImpl(MethodImplOptions.NoInlining)] private static Color PlacedNativeArgumentEffect()
    { _placedNativeArgumentEffects++; return Color.White; }
    [MethodImpl(MethodImplOptions.NoInlining)] private static void PlacedNativeTailEffect() => _placedNativeTailEffects++;
    [MethodImpl(MethodImplOptions.NoInlining)] private static void PlacedNativeSubmissionProbe(SpriteBatch batch, Texture2D texture, int x, int y)
    {
        batch.Draw(texture, new Vector2(3,7), null, PlacedNativeArgumentEffect(), 0f, Vector2.Zero, 1f, SpriteEffects.None, 0f);
        PlacedNativeTailEffect();
    }




}

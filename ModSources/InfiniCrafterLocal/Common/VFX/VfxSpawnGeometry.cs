#nullable enable
using System;
using InfiniCrafterLocal.Common.Models;
using Microsoft.Xna.Framework;
using Terraria;
namespace InfiniCrafterLocal.Common.VFX;

internal static class VfxSpawnGeometry
{
    // Position sampling is an independent stream: adding a region never changes
    // any existing authored velocity sequence or the number of admitted particles.
    internal static Random? CreateRandom(VfxSpawnSpec? spawn,int seed,ulong emissionTick)
        =>spawn is null||spawn.Shape=="point"?null:new Random(seed^unchecked((int)emissionTick)^0x53A9B74D);
    internal static Vector2 SampleWorld(VfxSpawnSpec? spawn,Vector2 forward,Random? random)
        =>spawn is null||spawn.Shape=="point"?Vector2.Zero:FromUnitSquare(spawn,forward,(float)random!.NextDouble(),(float)random.NextDouble());
    internal static double MaxDistance(VfxSpawnSpec? spawn)=>spawn is null?0:spawn.Shape switch {
        "point"=>0,"line"=>spawn.LengthPx!.Value*.5,
        "rectangle"=>Math.Sqrt(spawn.WidthPx!.Value*spawn.WidthPx.Value+spawn.HeightPx!.Value*spawn.HeightPx.Value)*.5,
        "annulus"=>spawn.OuterRadiusPx!.Value,
        _=>throw new InvalidOperationException("unadmitted spawn geometry")
    };
    // Uniform line/area projection, no physics, runtime state or RNG side effects.
    internal static Vector2 FromUnitSquare(VfxSpawnSpec spawn,Vector2 forward,float u,float v)
    {
        if(spawn.Shape=="point")return Vector2.Zero;
        if(spawn.Shape=="annulus") {
            float inner=spawn.InnerRadiusPx!.Value,outer=spawn.OuterRadiusPx!.Value;
            float radius=MathF.Sqrt(inner*inner+v*(outer*outer-inner*inner));
            return (MathF.Tau*u).ToRotationVector2()*radius;
        }
        Vector2 local=spawn.Shape=="line"?new((u-.5f)*spawn.LengthPx!.Value,0)
            :new((u-.5f)*spawn.WidthPx!.Value,(v-.5f)*spawn.HeightPx!.Value);
        float rotation=spawn.RotationRadians!.Value+(spawn.Frame=="source"?forward.ToRotation():0);
        return local.RotatedBy(rotation);
    }
}

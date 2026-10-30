#nullable enable
using System;
using InfiniCrafterLocal.Common.Models;
using Microsoft.Xna.Framework;
using Terraria;

namespace InfiniCrafterLocal.Common.VFX;

public sealed partial class InfiniDetachedVfxSystem
{
    // Placement sources have zero velocity. Include the full authored lifetime,
    // offset, maximum profile size and travel, not just the footprint center.
    // Drag is bounded to [0,1], so ignoring it is a conservative upper bound.
    private static double PlacedVfxReachRadius(VfxSlotSpec slot)
    {
        double duration=slot.Duration!.Value;
        if(slot.Element is {} element) {
            double width=element.WidthPx*Math.Max(element.WidthProfile.Start,Math.Max(element.WidthProfile.Middle,element.WidthProfile.End));
            double height=element.HeightPx*Math.Max(element.HeightProfile.Start,Math.Max(element.HeightProfile.Middle,element.HeightProfile.End));
            return PlacedParticleReach(duration,element.SpeedMaxPxPerTick,
                element.AccelerationXPxPerTickSquared,element.AccelerationYPxPerTickSquared,
                element.OffsetForwardPx,element.OffsetSidePx,width,height);
        }
        var particle=slot.Particle!;
        double scale=Math.Max(1,particle.EndScaleMultiplier);
        return PlacedParticleReach(duration,particle.SpeedMaxPxPerTick,
            particle.AccelerationXPxPerTickSquared,particle.AccelerationYPxPerTickSquared,
            0,0,particle.WidthPx*scale,particle.HeightPx*scale);
    }

    private static double PlacedParticleReach(double duration,double speed,double ax,double ay,
        double offsetX,double offsetY,double width,double height)
        => Math.Sqrt(offsetX*offsetX+offsetY*offsetY)
            + speed*duration + Math.Sqrt(ax*ax+ay*ay)*duration*(duration+1)*.5
            + Math.Sqrt(width*width+height*height)*.5;

    // Broad phase for an inactive placement, before querying any native tiles.
    // Already-active bindings still check every tile/frame offscreen, so an
    // off/on cycle cannot revive a retired VFX generation. Keep light uncullable.
    internal static bool MayNeedPlacedVfxFrame(Common.Systems.GeneratedPlacedBodyView view)
    {
        if (view.Vfx is null) return false;
        Vector2 center = new(view.Footprint.X + view.Footprint.Width * .5f,
            view.Footprint.Y + view.Footprint.Height * .5f);
        foreach (VfxSlotSpec slot in view.Data.VfxManifest.Slots)
        {
            if (slot.PlacementBindingId != view.BindingId || slot.EntityId != view.EntityId
                || slot.Event != RuntimeEventKind.Periodic) continue;
            if (slot.RendererKind is "lightCue" or "nativeLight") return true;
            if ((slot.Element is not null || slot.Particle is not null)
                && PlacedVfxInView(center,PlacedVfxReachRadius(slot))) return true;
        }
        return false;
    }

    private static bool PlacedVfxInView(Vector2 position,double radius)
    {
        if(!InfiniVfxClientOptions.EnableScreenCulling)return true;
        return PlacedVfxIntersectsViewport(position,radius,Main.screenPosition,
            Main.screenWidth,Main.screenHeight,Main.GameViewMatrix?.Zoom ?? Vector2.One);
    }

    internal static bool PlacedVfxIntersectsViewport(Vector2 position,double radius,Vector2 camera,
        int width,int height,Vector2 zoom)
    {
        // Unknown/headless viewport cannot prove an effect is invisible. This is
        // admission culling only, not a change to placement identity or gameplay.
        if(width<=0||height<=0||!float.IsFinite(camera.X)||!float.IsFinite(camera.Y)
            ||!float.IsFinite(zoom.X)||!float.IsFinite(zoom.Y)||zoom.X<=0||zoom.Y<=0
            ||!double.IsFinite(radius)||radius<0)return true;
        // Do not shrink the unzoomed viewport for zoom-in. Zoom-out expands about
        // the same center. Margin covers nearby entry and the update/draw delay.
        double halfWidth=width/(2d*Math.Min(1d,zoom.X));
        double halfHeight=height/(2d*Math.Min(1d,zoom.Y));
        double margin=radius+256d;
        return Math.Abs(position.X-(camera.X+width*.5d))<=halfWidth+margin
            && Math.Abs(position.Y-(camera.Y+height*.5d))<=halfHeight+margin;
    }
}

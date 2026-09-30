#nullable enable
using System;
using System.Linq;
using InfiniCrafterLocal.Common.VFX;
using InfiniCrafterLocal.Common.Models;
using Microsoft.Xna.Framework;
using Terraria;
namespace InfiniCrafterLocal.Content.Projectiles;
public sealed partial class GeneratedProjectile
{
    private object _presentationGeneration=new();
    private bool _presentationRetired;
    internal object PresentationGeneration=>_presentationGeneration;
    internal int PresentationWorldAge=>_vfxState.Tick;
    internal bool PresentationSourceLive=>_configured&&!_presentationRetired&&_activationDelayTicks<=0&&_data is not null&&_entity is not null;
    internal bool TryCapturePresentationFrame(string anchor,out VfxSourceFrame frame)
    {
        frame=default;if(!PresentationSourceLive)return false;
        var snapshot=InfiniVfxProjectileSnapshot.Capture(Projectile,_data!,_entity!.Id);
        if(!snapshot.IsValid||!snapshot.TryMaterialAnchor(anchor,Projectile.Center,out var point))return false;
        frame=new(point,anchor=="velocity"?Projectile.velocity.SafeNormalize(snapshot.Forward):snapshot.Forward,snapshot.MaterialVelocity);return frame.Valid;
    }
    internal bool TryCapturePresentationGeometry(string kind,out Vector2[] points)
    {
        points=Array.Empty<Vector2>();if(!PresentationSourceLive)return false;
        if(kind=="beam"&&_entity!.Controller.Code==RuntimeControllerCode.ChannelBeam) {
            if(Projectile.owner<0||Projectile.owner>=Main.player.Length||Main.player[Projectile.owner] is not {active:true})return false;
            GetChannelBeamGeometry(out var a,out var b,out _);points=new[]{a,b};
        } else if(kind=="whip"&&_entity!.Controller.Code!=RuntimeControllerCode.ChannelBeam&&_entity.Movement.Code==18&&_whipPoints.Count>1) points=_whipPoints.ToArray();
        else return false;
        return points.Length<=65&&points.All(p=>float.IsFinite(p.X)&&float.IsFinite(p.Y));
    }
}

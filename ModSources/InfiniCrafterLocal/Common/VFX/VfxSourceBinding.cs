#nullable enable
using System;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Items;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using Terraria;
namespace InfiniCrafterLocal.Common.VFX;

// Only references needed to fence exact local generations are retained. World
// emissions do not retain this object. Definition/budget IDs are never identities.
internal abstract class VfxSourceBinding
{
    internal abstract bool IsLive { get; }
    internal abstract object Generation { get; }
    internal virtual int WorldAge=>0;
    internal abstract bool TryFrame(string anchor,out VfxSourceFrame frame);
    internal virtual bool TryGeometry(string kind,out Vector2[] points) {points=Array.Empty<Vector2>();return false;}
    internal static VfxSourceBinding? Capture(Projectile projectile)
        => projectile.ModProjectile is GeneratedProjectile generated ? new ProjectileBinding(projectile,generated):null;
    internal static VfxSourceBinding? Capture(Player player,Item? item,GeneratedItemData data)
    {
        item ??= player.HeldItem?.ModItem is GeneratedItem held&&held.Data.Id==data.Id?player.HeldItem:null;
        if(item?.ModItem is not GeneratedItem generated||generated.Data.Id!=data.Id)return null;
        int index=ReferenceEquals(player.HeldItem,item)?-1:Array.FindIndex(player.armor??Array.Empty<Item>(),i=>ReferenceEquals(i,item));
        if(index<0&&!ReferenceEquals(player.HeldItem,item))return null;
        return new ItemBinding(player,item,generated,index);
    }
    internal static VfxSourceFrame ItemFrame(Player player,string anchor,Vector2? eventPosition=null)
    {
        Vector2 forward=player.itemRotation.ToRotationVector2()*(player.direction<0?-1:1);
        if(anchor=="velocity")forward=player.velocity.SafeNormalize(forward);
        Vector2 pos=anchor=="hitPoint"?eventPosition??new Vector2(float.NaN):anchor is "tip" or "tipHistory"?player.itemLocation:player.Center;
        return new(pos,forward,player.velocity){SourceCenter=player.Center};
    }
    private sealed class ProjectileBinding : VfxSourceBinding
    {
        private readonly Projectile host;
        private readonly GeneratedProjectile generated;
        private readonly object generation;
        private readonly int slot,owner,identity,type;
        internal ProjectileBinding(Projectile p,GeneratedProjectile g) {host=p;generated=g;generation=g.PresentationGeneration;slot=p.whoAmI;owner=p.owner;identity=p.identity;type=p.type;}
        internal override object Generation=>generation;
        internal override int WorldAge=>generated.PresentationWorldAge;
        internal override bool IsLive=>host.active&&slot>=0&&slot<Main.projectile.Length&&ReferenceEquals(Main.projectile[slot],host)
            &&ReferenceEquals(host.ModProjectile,generated)&&ReferenceEquals(generated.PresentationGeneration,generation)&&generated.PresentationSourceLive
            &&host.whoAmI==slot&&host.owner==owner&&host.identity==identity&&host.type==type;
        internal override bool TryFrame(string anchor,out VfxSourceFrame frame) {frame=default;return IsLive&&generated.TryCapturePresentationFrame(anchor,out frame);}
        internal override bool TryGeometry(string kind,out Vector2[] points) {points=Array.Empty<Vector2>();return IsLive&&generated.TryCapturePresentationGeometry(kind,out points);}
    }
    private sealed class ItemBinding : VfxSourceBinding
    {
        private readonly Player owner;
        private readonly Item item;
        private readonly GeneratedItem generation;
        private readonly int ownerSlot,itemSlot,type;
        private readonly object fence;
        internal ItemBinding(Player p,Item i,GeneratedItem g,int index){owner=p;item=i;generation=g;fence=g.PresentationGeneration;ownerSlot=p.whoAmI;itemSlot=index;type=i.type;}
        internal override object Generation=>fence;
        internal override bool IsLive=>owner.active&&ownerSlot>=0&&ownerSlot<Main.player.Length&&ReferenceEquals(Main.player[ownerSlot],owner)
            &&!item.IsAir&&item.type==type&&ReferenceEquals(item.ModItem,generation)&&ReferenceEquals(generation.PresentationGeneration,fence)
            &&(itemSlot<0?ReferenceEquals(owner.HeldItem,item):itemSlot<owner.armor.Length&&ReferenceEquals(owner.armor[itemSlot],item));
        internal override bool TryFrame(string anchor,out VfxSourceFrame frame) {
            frame=default;if(!IsLive||anchor=="hitPoint"||itemSlot>=0&&anchor is "tip" or "tipHistory")return false;
            frame=ItemFrame(owner,anchor);return frame.Valid;
        }
    }
}

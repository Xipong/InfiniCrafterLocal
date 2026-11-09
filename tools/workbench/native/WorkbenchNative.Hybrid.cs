using System.Linq;
using System;
using System.Collections.Generic;
using Terraria.DataStructures;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Runtime;
using InfiniCrafterLocal.Content.Projectiles;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using MonoMod.RuntimeDetour;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    private static void WValidateHybridEvents(GeneratedItemData data,bool renderedVfx=false)
    {
        foreach(var entity in data.RuntimeProgram.Entities)
            foreach(var action in entity.Events)
            {
                bool body=entity.Kind==RuntimeEntityKind.ItemBody;
                if(body && renderedVfx && WEquipmentBodyEventsSupported(data) && action.Event is RuntimeEventKind.OnHurt or RuntimeEventKind.OnEnemyKill)continue;
                bool hitNpcCallback=action.Event==RuntimeEventKind.OnHit
                    && action.ActionCode is RuntimeEventActionCode.ApplyStatus or RuntimeEventActionCode.Pull;
                bool supported=body
                    ? action.Event is RuntimeEventKind.OnUse or RuntimeEventKind.OnHit or RuntimeEventKind.OnCrit
                        && (action.ActionCode==RuntimeEventActionCode.SpawnEntity
                            || (action.Event is RuntimeEventKind.OnHit or RuntimeEventKind.OnCrit && action.ActionCode is RuntimeEventActionCode.HealOwner or RuntimeEventActionCode.ApplyNpcEffect))
                        || hitNpcCallback
                    : action.ActionCode is RuntimeEventActionCode.SpawnEntity or RuntimeEventActionCode.SelectTargetsAndEmit or RuntimeEventActionCode.DamageNearby
                        || action.Event is RuntimeEventKind.OnHit or RuntimeEventKind.OnCrit && action.ActionCode==RuntimeEventActionCode.ApplyNpcEffect
                        || hitNpcCallback
                        || renderedVfx && action.ActionCode==RuntimeEventActionCode.HealOwner;
                if(!supported) throw new NotSupportedException("Client hybrid admits item-body on_use/on_hit/on_crit spawn and on_hit/on_crit healing or NPC effects, on_hit native status/pull; projectile callbacks admit spawn/select-target emission/native nearby damage, on_hit/on_crit NPC effects, on_hit native status/pull and rendered healing");
            }
    }
    private delegate void WItemEventOriginal(GeneratedItem self,Player player,RuntimeEntitySpec entity,string eventName,NPC? target,int damageDone,string? useInput);
    private delegate void WItemEventObserver(WItemEventOriginal orig,GeneratedItem self,Player player,RuntimeEntitySpec entity,string eventName,NPC? target,int damageDone,string? useInput);
    private static Hook WObserveItemEvents(Action<JsonObject> observe)
        => new(typeof(GeneratedItem).GetMethod("RunItemEvent",TestInstance)!, (WItemEventObserver)((orig,self,player,entity,eventName,target,damageDone,useInput)=>{
            var budget=(RuntimeSpawnBudget)typeof(GeneratedItem).GetField("_itemEventBudget",TestInstance)!.GetValue(self)!;
            var entry=new JsonObject{["kind"]="item_event_dispatch",["itemProjection"]=WItemProjection(self.Item),["event"]=eventName,["useInput"]=useInput,["entityId"]=entity.Id,["npcId"]=target?.whoAmI,["damageDone"]=damageDone,["budgetBefore"]=budget.Remaining,["dedServ"]=Terraria.Main.dedServ,["netMode"]=Terraria.Main.netMode,["observationStage"]="canonical_RunItemEvent_entry",["completed"]=false};
            observe(entry);
            orig(self,player,entity,eventName,target,damageDone,useInput);
            entry["budgetAfter"]=budget.Remaining;
            entry["completed"]=true;
        }));
    private static readonly Dictionary<IEntitySource,int> WSourceParentIds=new(ReferenceEqualityComparer.Instance);
    private static Hook WObserveParentSources(string method)
        => new(typeof(Entity).GetMethod(method)!, (Func<Func<Entity,string?,IEntitySource>,Entity,string?,IEntitySource>)((orig,entity,context)=>{
            var source=orig(entity,context);
            if(entity is Projectile p && WProjectileId(p)>=0) WSourceParentIds[source]=WProjectileId(p);
            return source;
        }));
    private delegate void WConfigureOriginal(GeneratedProjectile self,GeneratedItemData data,RuntimeEntitySpec entity,int depth,int remaining,Vector2 direction,bool preserve,RuntimeSpawnBudget? budget,bool reservation,Vector2? nativeVelocity,int? originalDamage);
    private delegate void WConfigureObserver(WConfigureOriginal orig,GeneratedProjectile self,GeneratedItemData data,RuntimeEntitySpec entity,int depth,int remaining,Vector2 direction,bool preserve,RuntimeSpawnBudget? budget,bool reservation,Vector2? nativeVelocity,int? originalDamage);
    private static Hook WObserveConfiguration(Action<JsonObject> observe)
        => new(typeof(GeneratedProjectile).GetMethod("Configure",TestInstance)!,
            (WConfigureObserver)((orig,self,data,entity,depth,remaining,direction,preserve,budget,reservation,nativeVelocity,originalDamage)=> {
                orig(self,data,entity,depth,remaining,direction,preserve,budget,reservation,nativeVelocity,originalDamage);
                Projectile p=self.Projectile;
                observe(new JsonObject { ["kind"]="entity_configured",["activeEntityCount"]=Terraria.Main.projectile.Count(other=>other.active && other.owner==p.owner && WProjectileEntity(other)==entity.Id),["projectileId"]=WProjectileId(p),["nativeIdentity"]=p.identity,["entityId"]=WProjectileEntity(p),["itemId"]=data.Id,["childDepth"]=WProjectileDepth(p),["damage"]=p.damage,["originalDamage"]=p.originalDamage,["knockback"]=p.knockBack,["vx"]=WFinite(p.velocity.X),["vy"]=WFinite(p.velocity.Y),["dedServ"]=Terraria.Main.dedServ,["netMode"]=Terraria.Main.netMode,["observationStage"]="after_canonical_configure" });
            }));
    private static string WProjectileEntity(Projectile p) => p.ModProjectile is GeneratedProjectile gp?WState<string>(gp,"_entityId"):"vanilla:"+p.type;
    private static int? WProjectileDepth(Projectile p) => p.ModProjectile is GeneratedProjectile gp?WState<int>(gp,"_childDepth"):null;
}

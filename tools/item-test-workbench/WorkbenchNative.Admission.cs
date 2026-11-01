using System;
using System.Linq;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    private static void WValidateHistoryTrail(VfxSlotSpec slot,bool drawPlayer,GeneratedItemData? data=null)
    {
        if(drawPlayer&&data is not null&&slot.EntityId==data.RuntimeProgram.ItemEntityId&&slot.Event=="on_use") {
            if(slot.Layer is not ("BeforePlayer" or "AfterPlayer")||slot.Trail is not {} held
                ||held.Source is not ("center" or "tip")||!(held.Draw=="stroke"||held.Draw=="sprites"&&held.Texture?.Source=="item"))
                throw new NotSupportedException("Held history proof covers stroke or exact item texture with final native body pose only");
            return;
        }
        // Sprite history is evidenced only for the exact published entity texture
        // and its recorded pose; alternate materials/anchors remain unadmitted.
        if(!drawPlayer || slot.Trail is not {} trail || trail.Source!="center"
            || !(trail.Draw=="stroke" || trail.Draw=="sprites" && trail.Texture?.Source=="entity" && trail.Pose=="sampled"))
            throw new NotSupportedException("historyTrail requires full native draw and stroke/center or sampled entity sprites/center");
    }
    private sealed class WWorldIdentity : IDisposable
    {
        private readonly int previous=Terraria.Main.worldID;
        public WWorldIdentity(int id) { Terraria.Main.worldID=id; }
        public void Dispose() { Terraria.Main.worldID=previous; }
    }
    // Binding-local policy only. Whole-definition/passive guards remain in RunWorkbench.
    private static string? WBindingRefusal(GeneratedItemData data,string input,bool full,bool client,bool hybrid,bool render=false)
    {
        var binding=data.RuntimeProgram.BindingForInput(input);
        if(binding is null) return "No binding for input "+input;
        if(!client && binding.UsePolicy.ContactDamage) return "Item-body contact requires native client geometry for input "+input+"; use client_hybrid for admitted no-VFX projectile combinations or client_vfx for supported VFX";
        string kind=binding.UsePolicy.Action.Kind;
        if(client && kind!=RuntimeBindingAction.UseItemBody && !(hybrid && kind==RuntimeBindingAction.SpawnEntity) && !(render && kind==RuntimeBindingAction.ApplyItemEffects) && kind!=RuntimeBindingAction.PlaceItem && !(render && kind==RuntimeBindingAction.EquipPassive)) return "Client input requires use_item_body or hybrid spawn_entity: "+input;
        bool effects=full && kind==RuntimeBindingAction.ApplyItemEffects;
        bool placement=full && kind==RuntimeBindingAction.PlaceItem && binding.UsePolicy.StackCost==1;
        bool equipment=full && input==RuntimeInputKind.Equipped && (data.Accessory.Enabled || data.Armor.Enabled) && kind==RuntimeBindingAction.EquipPassive;
        if(kind!=RuntimeBindingAction.SpawnEntity && !effects && !equipment && !placement && !(client && kind==RuntimeBindingAction.UseItemBody)) return "Input action is not admitted: "+input+" / "+kind;
        if(render && effects && data.EffectsForBinding(binding).ExtraBuffs.Any(b=>b.BuffCode is not (Terraria.ID.BuffID.Gravitation or Terraria.ID.BuffID.Sonar)))
            return "Client VFX ExtraBuffs admit only proven native Gravitation/Sonar flags; other buff actors/art are not admitted";
        if(effects && data.EffectsForBinding(binding).MobilityMode is not ("" or "blink_to_cursor" or "recall_home")) return "Only blink_to_cursor and explicit-scene recall_home item mobility are admitted";
        return null;
    }
    private static void WRequireBinding(GeneratedItemData data,string input,bool full,bool client,bool hybrid,bool render=false)
    {
        if(WBindingRefusal(data,input,full,client,hybrid,render) is string reason) throw new NotSupportedException(reason);
    }
    private static JsonObject WItemProjection(Item item)=>new(){["type"]=item.type,["stack"]=item.stack,["createTile"]=item.createTile,["createWall"]=item.createWall,["placeStyle"]=item.placeStyle,["consumable"]=item.consumable,["shoot"]=item.shoot,["buffType"]=item.buffType,["buffTime"]=item.buffTime,["mana"]=item.mana,["damage"]=item.damage,["noMelee"]=item.noMelee,["useAmmo"]=item.useAmmo,["useTime"]=item.useTime,["useAnimation"]=item.useAnimation,["autoReuse"]=item.autoReuse,["channel"]=item.channel,["damageClass"]=item.DamageType.Name};
    private static JsonArray WExhaustion(Player owner)=>new(owner.GetModPlayer<InfiniCraftPlayer>().CaptureGeneratedItemExhaustion().Select(e=>(JsonNode?)new JsonObject{["itemId"]=e.ItemId,["definitionIdentity"]=e.DefinitionIdentity,["remainingTicks"]=e.RemainingTicks}).ToArray());
}

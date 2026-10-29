using System;
using System.Linq;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using Terraria;

internal static partial class EngineRuntimeChecks
{
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
        if(render && effects && data.EffectsForBinding(binding).ExtraBuffs.Length>0) return "Client VFX item effects currently require no native ExtraBuffs; spawned vanilla buff actors/art are not admitted";
        if(effects && data.EffectsForBinding(binding).MobilityMode is not ("" or "blink_to_cursor")) return "Only blink_to_cursor item mobility is admitted";
        return null;
    }
    private static void WRequireBinding(GeneratedItemData data,string input,bool full,bool client,bool hybrid,bool render=false)
    {
        if(WBindingRefusal(data,input,full,client,hybrid,render) is string reason) throw new NotSupportedException(reason);
    }
    private static JsonObject WItemProjection(Item item)=>new(){["type"]=item.type,["stack"]=item.stack,["createTile"]=item.createTile,["createWall"]=item.createWall,["placeStyle"]=item.placeStyle,["consumable"]=item.consumable,["shoot"]=item.shoot,["buffType"]=item.buffType,["buffTime"]=item.buffTime,["mana"]=item.mana,["damage"]=item.damage,["noMelee"]=item.noMelee,["useAmmo"]=item.useAmmo,["useTime"]=item.useTime,["useAnimation"]=item.useAnimation,["autoReuse"]=item.autoReuse,["channel"]=item.channel,["damageClass"]=item.DamageType.Name};
    private static JsonArray WExhaustion(Player owner)=>new(owner.GetModPlayer<InfiniCraftPlayer>().CaptureGeneratedItemExhaustion().Select(e=>(JsonNode?)new JsonObject{["itemId"]=e.ItemId,["definitionIdentity"]=e.DefinitionIdentity,["remainingTicks"]=e.RemainingTicks}).ToArray());
}

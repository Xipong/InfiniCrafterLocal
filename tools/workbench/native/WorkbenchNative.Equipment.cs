using System;
using System.Globalization;
using System.Collections.Generic;
using InfiniCrafterLocal.Common.Models;
using System.Linq;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Content.Items;
using Terraria;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    // Scene inventory commands move one existing physical instance. Native
    // Player.Update alone applies and resets equipment effects; no stat patching.
    private static void WPlaceEquipment(Player owner, Item item, string placement)
    {
        if (item.IsAir) throw new NotSupportedException("Equipment commands require a live item");
        int functionalSlot;
        if (item.ModItem is GeneratedItem generated && (generated.Data.Accessory.Enabled || generated.Data.Armor.Enabled))
            functionalSlot=generated.Data.Armor.Enabled ? WArmorSlot(generated.Data.Armor.Slot) : 3;
        else if (item.ModItem is null && item.accessory) functionalSlot=3;
        else throw new NotSupportedException("Equipment commands require generated equipment or a native passive accessory");
        int owned=owner.inventory.Count(i=>ReferenceEquals(i,item))+owner.armor.Count(i=>ReferenceEquals(i,item));
        if(owned!=1) throw new InvalidOperationException("Equipment instance must have exactly one inventory/equipment owner");
        int slot=placement=="equip"?functionalSlot:placement=="vanity"?functionalSlot+10:0;
        Item[] destination=placement=="unequip"?owner.inventory:owner.armor;
        if(!destination[slot].IsAir && !ReferenceEquals(destination[slot],item)) throw new InvalidOperationException("Equipment destination occupied");
        if(placement=="equip" && item.accessory && !ItemLoader.CanEquipAccessory(owner,item,slot,false)) throw new InvalidOperationException("Native accessory equip veto");
        for(int i=0;i<owner.inventory.Length;i++) if(ReferenceEquals(owner.inventory[i],item)) owner.inventory[i]=new Item();
        for(int i=0;i<owner.armor.Length;i++) if(ReferenceEquals(owner.armor[i],item)) owner.armor[i]=new Item();
        destination[slot]=item;
    }

    private static int WArmorSlot(string slot) => slot switch { "head"=>0, "body"=>1, "legs"=>2, _=>throw new NotSupportedException("Unknown armor slot: "+slot) };
    private static GeneratedItem WCreateItemHost(GeneratedItemData data) => !data.Armor.Enabled ? new GeneratedItem() : data.Armor.Slot switch {
        "head"=>new GeneratedHeadArmor(), "body"=>new GeneratedBodyArmor(), "legs"=>new GeneratedLegsArmor(), _=>throw new NotSupportedException("Unknown armor slot") };
    private static void WRegisterItemSingleton(GeneratedItem host)
    {
        typeof(ContentInstance<>).MakeGenericType(host.GetType()).GetProperty("Instance")!.SetValue(null,host);
        // Existing generic resolver callers still identify this same physical item.
        typeof(ContentInstance<GeneratedItem>).GetProperty("Instance")!.SetValue(null,host);
    }
    // CPU-only registration carrier, matching the native equipment checks. Native
    // ItemLoader.AutoDefaults sets the equip slot; Player.Update remains the only
    // owner of defense, effects, functional/vanity selection and their reset.
    private sealed class WEquipmentRegistration : IDisposable
    {
        private readonly Dictionary<int,Dictionary<EquipType,int>> slots=(Dictionary<int,Dictionary<EquipType,int>>)typeof(EquipLoader).GetField("idToSlot",PersistenceStatic)!.GetValue(null)!;
        private readonly int type;
        private readonly Dictionary<EquipType,int>? previous;
        private readonly bool enabled;
        private readonly Dictionary<EquipType,Dictionary<int,EquipTexture>> textures=(Dictionary<EquipType,Dictionary<int,EquipTexture>>)typeof(EquipLoader).GetField("equipTextures",PersistenceStatic)!.GetValue(null)!;
        private readonly EquipType equipType;
        private readonly EquipTexture? previousTexture;
        private readonly Item? previousAir=Terraria.ID.ContentSamples.ItemsByType.GetValueOrDefault(0);
        public WEquipmentRegistration(GeneratedItem? host)
        {
            enabled=host?.Data.Armor.Enabled==true;
            if(!enabled)return;
            Terraria.ID.ContentSamples.ItemsByType[0]=new Item();
            type=host!.Item.type;slots.TryGetValue(type,out previous);
            equipType=(EquipType)WArmorSlot(host.Data.Armor.Slot);
            slots[type]=new Dictionary<EquipType,int>{[equipType]=1};
            typeof(EquipLoader).GetMethod("SetSlot",PersistenceStatic)!.Invoke(null,new object[]{host.Item}); // Native template AutoDefaults routing, also needed by EquipFrameEffects.
            textures[equipType].TryGetValue(1,out previousTexture);
            var texture=new EquipTexture();typeof(EquipTexture).GetProperty("Item")!.SetValue(texture,host);typeof(EquipTexture).GetProperty("Type")!.SetValue(texture,equipType);typeof(EquipTexture).GetProperty("Slot")!.SetValue(texture,1);
            textures[equipType][1]=texture;
        }
        public void Dispose(){if(!enabled)return;if(previous is null)slots.Remove(type);else slots[type]=previous;if(previousTexture is null)textures[equipType].Remove(1);else textures[equipType][1]=previousTexture;if(previousAir is null)Terraria.ID.ContentSamples.ItemsByType.Remove(0);else Terraria.ID.ContentSamples.ItemsByType[0]=previousAir;}
    }
    private static bool WEquipmentBodyEventsSupported(GeneratedItemData data)
    {
        var binding=data.RuntimeProgram.BindingForInput(RuntimeInputKind.Equipped);
        return binding?.UsePolicy.Action.Kind==RuntimeBindingAction.EquipPassive
            && (data.Accessory.Enabled || data.Armor.Enabled)
            && data.RuntimeProgram.TryGetEntity(data.RuntimeProgram.ItemEntityId)!.Events.All(e=>
                e.Event is RuntimeEventKind.OnHurt or RuntimeEventKind.OnEnemyKill
                && e.ActionCode==RuntimeEventActionCode.ApplyGeneratedBuff);
    }

    private static JsonArray WInventory(Item[] items, bool armor)
    {
        var result=new JsonArray();
        for(int slot=0;slot<items.Length;slot++) if(!items[slot].IsAir) {
            var item=items[slot];
            result.Add(new JsonObject { ["slot"]=slot,["nativeType"]=item.type,["stack"]=item.stack,["ammoCategory"]=item.ammo,
                ["itemId"]=item.ModItem is GeneratedItem generated?generated.Data.Id:null,
                ["placement"]=armor?(slot<10?"functional":"vanity"):"inventory" });
        }
        return result;
    }

    private static bool WStatAt(JsonArray frames, JsonNode assertion)
    {
        string stat=assertion["stat"]!.GetValue<string>();
        int tick=WInt(assertion,"tick",-1);
        var frame=frames.LastOrDefault(f=>f!["phase"]==null && f["tick"]!.GetValue<int>()==tick);
        return frame is not null && Math.Abs(WReportNumber(frame["player"]![stat]!)-WFloat(assertion,"value",0))<0.00001f;
    }
    private static float WReportNumber(JsonNode value) => float.Parse(value.ToJsonString(),CultureInfo.InvariantCulture);
}

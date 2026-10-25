using System;
using System.Globalization;
using System.Linq;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Content.Items;
using Terraria;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    // Scene inventory commands move one existing physical instance. Native
    // Player.Update alone applies and resets equipment effects; no stat patching.
    private static void WPlaceAccessory(Player owner, Item item, string placement)
    {
        if (!item.accessory || item.IsAir) throw new NotSupportedException("Equipment commands require a live accessory");
        int owned=owner.inventory.Count(i=>ReferenceEquals(i,item))+owner.armor.Count(i=>ReferenceEquals(i,item));
        if(owned!=1) throw new InvalidOperationException("Accessory instance must have exactly one inventory/equipment owner");
        int slot=placement=="equip"?3:placement=="vanity"?13:0;
        Item[] destination=placement=="unequip"?owner.inventory:owner.armor;
        if(!destination[slot].IsAir && !ReferenceEquals(destination[slot],item)) throw new InvalidOperationException("Equipment destination occupied");
        if(placement=="equip" && !ItemLoader.CanEquipAccessory(owner,item,slot,false)) throw new InvalidOperationException("Native accessory equip veto");
        for(int i=0;i<owner.inventory.Length;i++) if(ReferenceEquals(owner.inventory[i],item)) owner.inventory[i]=new Item();
        for(int i=0;i<owner.armor.Length;i++) if(ReferenceEquals(owner.armor[i],item)) owner.armor[i]=new Item();
        destination[slot]=item;
    }

    private static JsonArray WInventory(Item[] items, bool armor)
    {
        var result=new JsonArray();
        for(int slot=0;slot<items.Length;slot++) if(!items[slot].IsAir) {
            var item=items[slot];
            result.Add(new JsonObject { ["slot"]=slot,["nativeType"]=item.type,["stack"]=item.stack,
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

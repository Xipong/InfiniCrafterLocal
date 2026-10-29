using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using MonoMod.RuntimeDetour;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    // Only scene provisioning and observation: native PickAmmo/ItemCheck owns selection and payment.
    private static void WValidateAmmoInventory(JsonObject scenario)
    {
        var seen=new HashSet<int>();
        foreach(var row in scenario["inventory"]?.AsArray() ?? new JsonArray()) {
            WKeys(row,"inventory entry","slot","itemId","stack");
            int slot=WInt(row,"slot",-1), id=WInt(row,"itemId",0), count=WInt(row,"stack",0);
            if(!(slot is >=1 and <=49 or >=54 and <=57) || !seen.Add(slot)) throw new ArgumentException("Inventory slot must be unique, ordinary1..49 or ammo54..57");
            if(id<=0 || id>=ItemID.Count || count<1 || count>9999) throw new ArgumentException("Inventory requires vanilla itemId and stack1..9999");
        }
    }
    private static void WProvisionAmmoInventory(Player owner,JsonObject scenario)
    {
        foreach(var row in scenario["inventory"]?.AsArray() ?? new JsonArray()) {
            var ammo=new Item(WInt(row,"itemId",0));
            if(ammo.ammo!=AmmoID.Arrow && ammo.ammo!=AmmoID.Bullet && ammo.ammo!=AmmoID.Flare && ammo.ammo!=AmmoID.FallenStar) throw new NotSupportedException("Only vanilla arrow/bullet/flare/fallen-star inventory entries are admitted");
            int count=WInt(row,"stack",0);
            if(count>ammo.maxStack) throw new ArgumentException("Inventory stack exceeds native item maxStack");
            ammo.stack=count; owner.inventory[WInt(row,"slot",-1)]=ammo;
        }
    }
    private static Hook WObserveAmmoConsumption(Player owner,Action<JsonObject> record)
    {
        return new Hook(typeof(CombinedHooks).GetMethod(nameof(CombinedHooks.OnConsumeAmmo))!,
            (Action<Action<Player,Item,Item>,Player,Item,Item>)((orig,p,weapon,ammo)=> {
                if(ReferenceEquals(p,owner)) record(new JsonObject { ["kind"]="native_ammo_consumption",["ammoItemId"]=ammo.type,["weaponItemId"]=weapon.type,["stackAtNativeCallback"]=ammo.stack,["slot"]=Array.IndexOf(p.inventory,ammo) });
                orig(p,weapon,ammo);
            }));
    }
    private static bool WAmmoAssertion(string kind,JsonNode assertion,Player owner,JsonArray frames)
    {
        int id=WInt(assertion,"itemId",0), slot=WInt(assertion,"slot",0), value=WInt(assertion,"value",0);
        if(kind=="inventory_stack") return owner.inventory[slot].stack==value && (value==0 ? owner.inventory[slot].IsAir : owner.inventory[slot].type==id);
        var events=frames.SelectMany(f=>f!["events"]!.AsArray()).Where(e=>e is not null);
        if(kind=="ammo_consumed_count") return events.Count(e=>e!["kind"]!.GetValue<string>()=="native_ammo_consumption" && e["ammoItemId"]!.GetValue<int>()==id)==value;
        if(kind=="ammo_source_spawn_count") return events.Count(e=>e!["kind"]!.GetValue<string>()=="spawn" && e["ammoItemIdUsed"]?.GetValue<int>()==id)==value;
        throw new ArgumentException("Unknown ammo assertion");
    }
}

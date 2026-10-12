using System;
using System.Reflection;
using System.Text.Json;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Content.Items;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private static void ParentCritFactsReachCraftSnapshot()
    {
        var client = new GeneratorClient();
        var owner = new Player { name = "parent_crit_probe" };
        var stone = new Item(); stone.SetDefaults(ItemID.StoneBlock);
        var ordinary = new Item(); ordinary.SetDefaults(ItemID.WoodenSword);
        Item? highCrit = null;
        // Discover loaded native defaults, rather than encode remembered weapon stats.
        for (int type = 1; type < ItemID.Count; type++)
        {
            var candidate = new Item(); candidate.SetDefaults(type);
            if (candidate.damage > 0 && candidate.crit > ordinary.crit)
            {
                highCrit = candidate;
                break;
            }
        }
        Equal(true, highCrit is not null, "loaded native item with higher innate crit exists");
        foreach (Item parent in new[] { stone, ordinary, highCrit! })
        {
            int baseCrit = parent.crit;
            // Distinguish base defaults from consumed per-instance modifiers. This
            // deliberately changes only the source instance; request must not undo it.
            parent.crit += 37;
            parent.prefix = PrefixID.Keen;
            parent.stack = 2;
            using var request = JsonDocument.Parse(client.Prepare(parent, stone, owner).PayloadJson);
            var snapshot = request.RootElement.GetProperty("itemA");
            Equal(baseCrit, snapshot.GetProperty("crit").GetInt32(), "wire uses native unprefixed crit");
            Equal(baseCrit, snapshot.GetProperty("fingerprint").GetProperty("crit").GetInt32(), "fingerprint base crit");
            Equal(baseCrit, snapshot.GetProperty("runtimeFacts").GetProperty("crit").GetInt32(), "runtime facts base crit");
            Equal(baseCrit + 37, parent.crit, "consumed parent's modified crit stays untouched");
            Equal((int)PrefixID.Keen, (int)parent.prefix, "consumed parent's prefix stays untouched");
            Equal(2, parent.stack, "source stack stays untouched");
        }

        var data = GeneratedItemData.Placeholder();
        data.Id = "generated_parent_crit_probe";
        data.Name = "Generated crit source";
        data.SourceMode = "test_fixture";
        data.Accessory.Enabled = true;
        data.Accessory.GenericCrit = 17f;
        // Metadata-only fixture; Prepare does not open a texture or initialize graphics.
        data.Visual.EquipOverlayPath = "parent_crit_probe_overlay.png";
        data.Visual.EquipOverlayStatus = "generated";
        data.RuntimeProgram.Bindings = new[] { new RuntimeBindingSpec {
            Id = "equip_crit_source", Input = RuntimeInputKind.Equipped, Role = RuntimeEntityRole.Primary,
            UsePolicy = new RuntimeBindingUsePolicySpec {
                Action = new RuntimeBindingActionSpec {
                    Kind = RuntimeBindingAction.EquipPassive, TargetId = data.RuntimeProgram.ItemEntityId,
                },
            },
        } };
        var generatedParent = new Item(); generatedParent.SetDefaults(ItemID.WoodenSword);
        int nativeBaseCrit = generatedParent.crit;
        var generated = new GeneratedItem();
        AttachItem(generated, generatedParent, data);
        data.ApplyToItem(generatedParent);
        generatedParent.crit = nativeBaseCrit + 43;
        generatedParent.prefix = PrefixID.Keen;
        using var generatedRequest = JsonDocument.Parse(client.Prepare(generatedParent, stone, owner).PayloadJson);
        var generatedSnapshot = generatedRequest.RootElement.GetProperty("itemA");
        Equal(nativeBaseCrit, generatedSnapshot.GetProperty("crit").GetInt32(), "generated clone removes prefix crit too");
        Equal(nativeBaseCrit, generatedSnapshot.GetProperty("fingerprint").GetProperty("crit").GetInt32(), "generated fingerprint base crit");
        Equal(nativeBaseCrit, generatedSnapshot.GetProperty("runtimeFacts").GetProperty("crit").GetInt32(), "generated runtime facts base crit");
        Equal(true, generatedSnapshot.GetProperty("generatedData").GetProperty("accessory").GetProperty("enabled").GetBoolean(),
            "generated source is an enabled accessory");
        Equal(17f, generatedSnapshot.GetProperty("generatedData").GetProperty("accessory").GetProperty("genericCrit").GetSingle(),
            "accepted equipment crit remains separate from raw item crit");
        Equal(nativeBaseCrit + 43, generatedParent.crit, "generated source crit is not mutated");
        Equal(17f, data.Accessory.GenericCrit, "accepted equipment bonus is not changed");
    }
}

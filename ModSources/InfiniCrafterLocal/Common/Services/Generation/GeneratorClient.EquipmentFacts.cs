#nullable enable
using System;
using System.Linq;
using System.Text.Json.Nodes;
using Terraria;
using Terraria.Localization;

namespace InfiniCrafterLocal.Common.Services;

public sealed partial class GeneratorClient
{
    private static readonly Lazy<string?> EquipmentFactCertificate = new(() => NativeAttackCertificate(typeof(Player), "GrantArmorBenefits"));
    private static readonly Lazy<string?> ArmorSetFactCertificate = new(() => NativeAttackCertificate(typeof(Player), "UpdateArmorSets"));
    private static readonly Lazy<JsonArray?> EquipmentFactRows = new(() => ReadEquipmentCatalog("Player.GrantArmorBenefits", EquipmentFactCertificate.Value));
    private static readonly Lazy<JsonArray?> ArmorSetFactRows = new(() => ReadEquipmentCatalog("Player.UpdateArmorSets", ArmorSetFactCertificate.Value));

    private static JsonArray? ReadEquipmentCatalog(string method, string? certificate)
        => certificate is not null && NativeEquipmentFactsCatalog.Sources.TryGetValue(method + ":" + certificate, out var json)
            ? JsonNode.Parse(json) as JsonArray : null;

    internal static JsonObject? CaptureNativeEquipmentReference(Item item)
    {
        // Never call UpdateEquip/UpdateArmorSet, inspect the current player's
        // equipment, or attribute generated/modded proxy behavior to native IDs.
        if (item.IsAir || item.ModItem is not null || !NativeSourceModuleVerified.Value) return null;
        var result = VerifiedNativeEquipmentReference(item.type, true, item.headSlot, item.bodySlot, item.legSlot,
            EquipmentFactRows.Value, EquipmentFactCertificate.Value, ArmorSetFactRows.Value, ArmorSetFactCertificate.Value);
        if (result?["conditionalArmorSets"] is JsonArray sets)
            foreach (JsonObject set in sets.OfType<JsonObject>())
            {
                string key = set["setBonusLocalizationKey"]!.GetValue<string>();
                // Literal source localization is context, not parsed numeric proof.
                try
                {
                    string text = Language.GetTextValue(key);
                    if (text.Length <= 4096)
                    {
                        set["literalSetBonusText"] = text;
                        set["literalTextLanguage"] = Language.ActiveCulture.Name;
                        set["literalTextStatus"] = "observed_literal";
                    }
                    else set["literalTextStatus"] = "refused_character_bound";
                }
                catch { set["literalTextStatus"] = "unavailable"; }
            }
        return result;
    }

    private static JsonObject? VerifiedNativeEquipmentReference(int itemType, bool vanilla, int headSlot, int bodySlot, int legSlot,
        JsonArray? equipmentRows, string? equipmentCertificate, JsonArray? setRows, string? setCertificate)
    {
        if (!vanilla) return null;
        JsonObject? equipped = equipmentCertificate is not null
            ? equipmentRows?.OfType<JsonObject>().FirstOrDefault(row => row["itemId"]?.GetValue<int>() == itemType) : null;
        var sets = new JsonArray();
        if (setCertificate is not null && setRows is not null)
            foreach (JsonObject row in setRows.OfType<JsonObject>())
            {
                var slots = row["condition"]?["functionalEquipSlots"] as JsonObject;
                bool Matches(string name, int value) => value >= 0 && slots?[name] is JsonArray values
                    && values.Any(node => node?.GetValue<int>() == value);
                if (Matches("head", headSlot) || Matches("body", bodySlot) || Matches("legs", legSlot))
                    sets.Add(row.DeepClone());
            }
        if (equipped is null && sets.Count == 0) return null;
        var result = new JsonObject {
            ["source"] = "verified_native_equipment_source_branches",
            ["scope"] = "Partial source references for the unprefixed item in functional equipment. Per-item contributions are separate from conditional FULL armor sets; set slots are native equip-slot IDs, not item IDs. No current player state or arbitrary mod hooks are executed. Other branches, runtime gates, final player stats and mod changes are not inferred. Additions are native stat contributions, not final animation/run speed or final damage multipliers. Boolean native flags are not quantified mechanics. Literal localized set text is not numeric proof. Author chooses generated behavior explicitly.",
        };
        if (equipped is not null)
        {
            result["equippedContributions"] = equipped.DeepClone();
            result["equipmentSourceCertificate"] = equipmentCertificate;
        }
        if (sets.Count != 0)
        {
            result["conditionalArmorSets"] = sets;
            result["setSourceCertificate"] = setCertificate;
        }
        return result;
    }
}

#nullable enable
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using Microsoft.Xna.Framework;
using System;
using System.Collections.Generic;
using System.IO;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;
using Terraria.ModLoader.IO;

namespace InfiniCrafterLocal.Content.Items;

/// <summary>
/// Dedicated extractinator-capable proxy for generated materials.
///
/// GeneratedItem is one shared ModItem type with per-instance JSON. Enabling
/// ItemID.Sets.ExtractinatorMode on that shared type would make every generated
/// item extractinatable. This proxy is a separate item type; only generated data
/// that explicitly authored extractinator_output is spawned here.
/// </summary>
public sealed class GeneratedExtractinatorMaterial : ModItem
{
    private const int NetPayloadVersion = 1;
    public override string Texture => "InfiniCrafterLocal/Assets/GeneratedItem";
    protected override bool CloneNewInstances => true;
    public GeneratedItemData Data { get; private set; } = GeneratedItemData.Placeholder();
    private static int _lowNoiseWarningCount;
    private int _lastRuntimeHydrationTouchTick = -90;

    private static void LogLowNoiseWarning(string context, Exception ex)
    {
        if (_lowNoiseWarningCount >= 8)
            return;
        _lowNoiseWarningCount++;
        try
        {
            global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance?.Logger?.Warn($"[GeneratedExtractinatorMaterial] {context}: {ex.GetType().Name}: {ex.Message}");
        }
        catch { }
    }

    public static bool CanRepresent(GeneratedItemData? data)
    {
        var gp = data?.Gameplay;
        return gp is not null && gp.ExtractinatorOutputItemType > ItemID.None && gp.ExtractinatorOutputStack > 0;
    }

    private bool HasValidOutput => CanRepresent(Data);

    public override void SetStaticDefaults()
    {
        ItemID.Sets.ExtractinatorMode[Type] = Type;
    }

    public override ModItem Clone(Item newEntity)
    {
        var clone = (GeneratedExtractinatorMaterial)base.Clone(newEntity);
        try { clone.Data = GeneratedItemData.FromJson((Data ?? GeneratedItemData.Placeholder()).ToNetworkJson()) ?? GeneratedItemData.Placeholder(); }
        catch { clone.Data = GeneratedItemData.Placeholder(); }
        return clone;
    }

    public void SetData(GeneratedItemData data, bool ensureAssets = true, bool registerLocal = true)
    {
        Data = data ?? GeneratedItemData.Placeholder();
        try { Data.ApplyToItem(Item); }
        catch (Exception ex)
        {
            LogLowNoiseWarning($"ApplyToItem failed for generated extractinator item '{Data?.Id ?? "unknown"}', falling back to placeholder", ex);
            Data = GeneratedItemData.Placeholder();
            try { Data.ApplyToItem(Item); }
            catch (Exception placeholderEx) { LogLowNoiseWarning("Placeholder ApplyToItem also failed", placeholderEx); }
        }
        Item.accessory = false;
        Item.damage = 0;
        Item.noMelee = true;
        Item.noUseGraphic = true;
        Item.useStyle = ItemUseStyleID.None;
        Item.consumable = true;
        Item.maxStack = Math.Max(1, Math.Min(9999, Data.Gameplay?.MaxStack ?? 999));
        if (registerLocal)
        {
            try { global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems?.RegisterLocal(Data, ensureAssets: ensureAssets); }
            catch (Exception ex) { LogLowNoiseWarning($"RegisterLocal failed for generated extractinator item '{Data?.Id ?? "unknown"}'", ex); }
        }
        if (registerLocal && Main.netMode != NetmodeID.SinglePlayer)
        {
            try { Item.NetStateChanged(); } catch { }
        }
    }

    public override void SaveData(TagCompound tag)
    {
        try { tag["infiniJson"] = (Data ?? GeneratedItemData.Placeholder()).ToPlayerSaveJson(); }
        catch { tag["infiniJson"] = GeneratedItemData.Placeholder().ToPlayerSaveJson(); }
    }

    public override void LoadData(TagCompound tag)
    {
        try { SetData(GeneratedItemData.FromPlayerSaveJson(tag.GetString("infiniJson")) ?? GeneratedItemData.Placeholder(), ensureAssets: false, registerLocal: false); }
        catch { try { SetData(GeneratedItemData.Placeholder(), ensureAssets: false, registerLocal: false); } catch { } }
    }

    private void EnsureRuntimeHydration()
    {
        string id = (Data?.Id ?? "").Trim();
        if (string.IsNullOrWhiteSpace(id) || string.Equals(id, "placeholder", StringComparison.OrdinalIgnoreCase))
            return;
        int now = (int)Main.GameUpdateCount;
        if (now - _lastRuntimeHydrationTouchTick < 90)
            return;
        _lastRuntimeHydrationTouchTick = now;
        try
        {
            var registry = global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems;
            if (registry is null)
                return;
            if (registry.TryGet(id, out var cachedData))
            {
                if (GeneratedItemData.IsPlayerSaveReferenceOnly(Data))
                    SetData(cachedData, ensureAssets: false, registerLocal: false);
                global::InfiniCrafterLocal.InfiniCrafterLocalMod.AssetSync?.EnsureAssetsForData(cachedData, forceRetry: false);
                return;
            }
            if (!GeneratedItemData.IsPlayerSaveReferenceOnly(Data))
                global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems?.RegisterLocal(Data, persist: false, ensureAssets: true);
            if (Main.netMode == NetmodeID.MultiplayerClient)
                global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems?.RequestOneFromServer(id, forceAssetRetry: false);
        }
        catch (Exception ex)
        {
            LogLowNoiseWarning($"Runtime hydration touch failed for generated extractinator item '{id}'", ex);
        }
    }

    public override void NetSend(BinaryWriter writer)
    {
        writer.Write(NetPayloadVersion);
        try { writer.Write((Data ?? GeneratedItemData.Placeholder()).ToNetworkJson()); }
        catch { writer.Write(GeneratedItemData.Placeholder().ToNetworkJson()); }
    }

    public override void NetReceive(BinaryReader reader)
    {
        try
        {
            int version = reader.ReadInt32();
            if (version != NetPayloadVersion)
                throw new InvalidDataException($"Unsupported GeneratedExtractinatorMaterial net payload version {version}");
            SetData(GeneratedItemData.FromJson(reader.ReadString()) ?? GeneratedItemData.Placeholder(), ensureAssets: true, registerLocal: true);
        }
        catch { try { SetData(GeneratedItemData.Placeholder(), ensureAssets: true, registerLocal: true); } catch { } }
    }

    public override bool CanStack(Item source)
    {
        if (source.ModItem is not GeneratedExtractinatorMaterial other)
            return false;
        var a = Data?.Gameplay;
        var b = other.Data?.Gameplay;
        return a is not null && b is not null
            && string.Equals(Data?.Id, other.Data?.Id, StringComparison.Ordinal)
            && string.Equals(Data?.RecipeKey, other.Data?.RecipeKey, StringComparison.Ordinal)
            && a.ExtractinatorOutputItemType == b.ExtractinatorOutputItemType
            && a.ExtractinatorOutputStack == b.ExtractinatorOutputStack;
    }

    public override void ExtractinatorUse(int extractinatorBlockType, ref int resultType, ref int resultStack)
    {
        EnsureRuntimeHydration();
        var gp = Data?.Gameplay;
        if (gp is null || gp.ExtractinatorOutputItemType <= ItemID.None || gp.ExtractinatorOutputStack <= 0)
        {
            resultType = ItemID.None;
            resultStack = 0;
            return;
        }
        resultType = gp.ExtractinatorOutputItemType;
        resultStack = Math.Clamp(gp.ExtractinatorOutputStack, 1, 999);
    }

    public override void ModifyTooltips(List<TooltipLine> tooltips)
    {
        EnsureRuntimeHydration();
        tooltips.Add(new TooltipLine(Mod, "InfiniParents", $"Recipe: {Data.ParentA} + {Data.ParentB}") { OverrideColor = Color.LightSkyBlue });
        tooltips.Add(new TooltipLine(Mod, "InfiniExtractinator", "Generated extractinator material") { OverrideColor = Color.LightGoldenrodYellow });
        if (HasValidOutput)
            tooltips.Add(new TooltipLine(Mod, "InfiniExtractinatorOutput", $"Extractinator output: item #{Data.Gameplay.ExtractinatorOutputItemType} x{Math.Clamp(Data.Gameplay.ExtractinatorOutputStack, 1, 999)}") { OverrideColor = Color.LightGreen });
        else
            tooltips.Add(new TooltipLine(Mod, "InfiniExtractinatorInvalid", "No valid extractinator output profile") { OverrideColor = Color.OrangeRed });
        if (!string.IsNullOrWhiteSpace(Data.Tooltip))
            tooltips.Add(new TooltipLine(Mod, "InfiniFlavor", Data.Tooltip));
    }
}

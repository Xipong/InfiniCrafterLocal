#nullable enable
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.VFX;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using System;
using System.Collections.Generic;
using Terraria;
using Terraria.DataStructures;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Players;

/// <summary>
/// Per-instance equipment identity overlay for generated armor/accessories.
/// Static AutoloadEquip proxies still provide valid Terraria equip slots; this layer
/// adds the generated equip_overlay PNG without pretending that one runtime image is
/// a full vanilla multi-frame armor sheet.
/// </summary>
public abstract class GeneratedEquipOverlayDrawLayerBase : PlayerDrawLayer
{
    private readonly record struct OverlayEntry(GeneratedItemData Data, string Slot, int AccessoryIndex);
    private const int EquipCatchupRetryTicks = 90;
    private static readonly object EquipCatchupLock = new();
    private static readonly Dictionary<string, int> EquipCatchupTicks = new(StringComparer.Ordinal);

    protected abstract string SlotKind { get; }

    public static void ClearNetCaches()
    {
        lock (EquipCatchupLock)
            EquipCatchupTicks.Clear();
    }

    internal static void EmitVisibleEquipmentVfx(Player player)
    {
        if (player is null || !player.active || player.dead)
            return;
        foreach (OverlayEntry entry in CollectVisibleOverlays(player))
            InfiniItemVfxRuntime.OnVisibleEquipment(player, entry.Data);
    }

    public override bool GetDefaultVisibility(PlayerDrawSet drawInfo)
    {
        Player player = drawInfo.drawPlayer;
        return player is not null && player.active && !player.dead && !player.invis;
    }

    protected override void Draw(ref PlayerDrawSet drawInfo)
    {
        Player player = drawInfo.drawPlayer;
        if (player is null || !player.active || player.dead || player.invis || drawInfo.shadow > 0f)
            return;
        List<OverlayEntry> entries = CollectVisibleOverlays(player);
        entries.RemoveAll(entry => !string.Equals(entry.Slot, SlotKind, StringComparison.Ordinal));
        if (entries.Count == 0)
            return;

        Vector2 bodyCenter = new(
            (int)(drawInfo.Position.X + player.width * 0.5f),
            (int)(drawInfo.Position.Y + player.height * 0.5f));
        bodyCenter -= Main.screenPosition;
        float grav = player.gravDir < 0f ? -1f : 1f;
        SpriteEffects effects = drawInfo.playerEffect;
        Color lightColor = Lighting.GetColor((int)(player.Center.X / 16f), (int)(player.Center.Y / 16f));

        int accessoryCount = 0;
        foreach (OverlayEntry entry in entries)
            if (entry.Slot == "accessory")
                accessoryCount++;
        int accessoryOrdinal = 0;
        foreach (OverlayEntry entry in entries)
        {
            string path = entry.Data.Visual?.EquipOverlayPath ?? "";
            if (string.IsNullOrWhiteSpace(path))
            {
                RequestEquipCatchup(entry.Data.Id, null);
                continue;
            }
            Texture2D? texture = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Sprites.TryGet(path);
            if (texture is null || texture.Width <= 0 || texture.Height <= 0)
            {
                global::InfiniCrafterLocal.InfiniCrafterLocalMod.AssetSync?.EnsureAssetsForData(entry.Data);
                RequestEquipCatchup(entry.Data.Id, path);
                continue;
            }

            Vector2 offset;
            float targetPixels;
            int shader;
            switch (entry.Slot)
            {
                case "head":
                    offset = new Vector2(0f, -19f * grav);
                    targetPixels = 25f;
                    shader = drawInfo.cHead;
                    break;
                case "legs":
                    offset = new Vector2(0f, 14f * grav);
                    targetPixels = 27f;
                    shader = drawInfo.cLegs;
                    break;
                case "accessory":
                    float angle = MathHelper.PiOver2 + accessoryOrdinal * MathHelper.TwoPi / Math.Max(1, accessoryCount);
                    offset = new Vector2(16f, 0f).RotatedBy(angle);
                    offset.Y *= grav;
                    targetPixels = 18f;
                    int dyeIndex = entry.AccessoryIndex + 3;
                    shader = player.dye is not null && dyeIndex >= 0 && dyeIndex < player.dye.Length
                        ? player.dye[dyeIndex].dye
                        : drawInfo.cBody;
                    accessoryOrdinal++;
                    break;
                default:
                    offset = new Vector2(0f, -2f * grav);
                    targetPixels = 31f;
                    shader = drawInfo.cBody;
                    break;
            }

            float scale = Math.Clamp(targetPixels / Math.Max(texture.Width, texture.Height), 0.18f, 1.25f);
            Vector2 position = bodyCenter + offset.RotatedBy(player.fullRotation);
            Vector2 origin = new(texture.Width * 0.5f, texture.Height * 0.5f);
            DrawData draw = new(texture, position, null, lightColor, player.fullRotation, origin, scale, effects, 0)
            {
                shader = shader,
            };
            drawInfo.DrawDataCache.Add(draw);
        }
    }

    private static List<OverlayEntry> CollectVisibleOverlays(Player player)
    {
        var entries = new List<OverlayEntry>(6);
        if (player?.armor is null)
            return entries;

        for (int armorPart = 0; armorPart < 3; armorPart++)
        {
            int vanityIndex = armorPart + 10;
            int sourceIndex = vanityIndex < player.armor.Length && !player.armor[vanityIndex].IsAir
                ? vanityIndex
                : armorPart;
            TryAdd(player.armor, sourceIndex, entries, armorPart switch
            {
                0 => "head",
                1 => "body",
                _ => "legs",
            }, -1);
        }

        for (int accessoryIndex = 0; accessoryIndex < 7; accessoryIndex++)
        {
            if (player.hideVisibleAccessory is { Length: > 0 }
                && accessoryIndex < player.hideVisibleAccessory.Length
                && player.hideVisibleAccessory[accessoryIndex])
                continue;
            int normalIndex = accessoryIndex + 3;
            int vanityIndex = accessoryIndex + 13;
            int sourceIndex = vanityIndex < player.armor.Length && !player.armor[vanityIndex].IsAir
                ? vanityIndex
                : normalIndex;
            TryAdd(player.armor, sourceIndex, entries, "accessory", accessoryIndex);
        }
        return entries;
    }

    private static void TryAdd(Item[] armor, int index, List<OverlayEntry> entries, string slot, int accessoryIndex)
    {
        if (index < 0 || index >= armor.Length)
            return;
        Item item = armor[index];
        if (item is null || item.IsAir || item.ModItem is not GeneratedItem generated || generated.Data is null)
            return;
        GeneratedItemData data = ResolveEquipPresentationData(generated.Data);
        bool roleMatches = slot == "accessory"
            ? data.Accessory?.Enabled == true || string.Equals(data.Gameplay?.Kind, "accessory", StringComparison.Ordinal)
            : data.Armor?.Enabled == true && string.Equals(data.Armor.Slot, slot, StringComparison.Ordinal);
        if (roleMatches)
            entries.Add(new OverlayEntry(data, slot, accessoryIndex));
    }

    private static GeneratedItemData ResolveEquipPresentationData(GeneratedItemData compact)
    {
        string id = (compact.Id ?? "").Trim();
        if (!GeneratedItemData.IsPlayerSaveReferenceOnly(compact))
            return compact;
        var registry = global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems;
        if (!string.IsNullOrWhiteSpace(id) && registry is not null && registry.TryGet(id, out GeneratedItemData canonical))
            return canonical;
        RequestEquipCatchup(id, null);
        return compact;
    }

    private static void RequestEquipCatchup(string? itemId, string? path)
    {
        string id = (itemId ?? "").Trim();
        if (string.IsNullOrWhiteSpace(id) || Main.netMode != Terraria.ID.NetmodeID.MultiplayerClient)
            return;
        string key = id + "|" + (path ?? "").Trim();
        int now = unchecked((int)Main.GameUpdateCount);
        lock (EquipCatchupLock)
        {
            if (EquipCatchupTicks.TryGetValue(key, out int last) && now - last < EquipCatchupRetryTicks)
                return;
            EquipCatchupTicks[key] = now;
        }
        global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems?.RequestOneFromServer(id, forceAssetRetry: true);
    }
}

public sealed class GeneratedEquipOverlayHeadDrawLayer : GeneratedEquipOverlayDrawLayerBase
{
    protected override string SlotKind => "head";
    public override Position GetDefaultPosition() => new AfterParent(PlayerDrawLayers.Head);
}

public sealed class GeneratedEquipOverlayBodyDrawLayer : GeneratedEquipOverlayDrawLayerBase
{
    protected override string SlotKind => "body";
    public override Position GetDefaultPosition() => new AfterParent(PlayerDrawLayers.Torso);
}

public sealed class GeneratedEquipOverlayLegsDrawLayer : GeneratedEquipOverlayDrawLayerBase
{
    protected override string SlotKind => "legs";
    public override Position GetDefaultPosition() => new AfterParent(PlayerDrawLayers.Leggings);
}

public sealed class GeneratedEquipOverlayAccessoryDrawLayer : GeneratedEquipOverlayDrawLayerBase
{
    protected override string SlotKind => "accessory";
    public override Position GetDefaultPosition() => new AfterParent(PlayerDrawLayers.Wings);
}

public sealed class GeneratedEquipmentPresentationPlayer : ModPlayer
{
    public override void PostUpdateEquips()
        => GeneratedEquipOverlayDrawLayerBase.EmitVisibleEquipmentVfx(Player);
}

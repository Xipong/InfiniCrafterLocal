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
    private readonly record struct OverlayEntry(GeneratedItemData Data, string Slot, int AccessoryIndex, Item SourceItem);
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
            InfiniItemVfxRuntime.OnVisibleEquipment(player, entry.Data,entry.SourceItem);
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

        float grav = player.gravDir < 0f ? -1f : 1f;
        SpriteEffects effects = drawInfo.playerEffect;

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
            Color lightColor;
            Vector2 partPosition;
            Vector2 pivot;
            Rectangle frame;
            float rotation;
            switch (entry.Slot)
            {
                case "head":
                    offset = new Vector2(0f, -19f * grav);
                    targetPixels = 25f;
                    shader = drawInfo.cHead;
                    lightColor = drawInfo.colorArmorHead;
                    partPosition = player.headPosition + drawInfo.helmetOffset;
                    pivot = drawInfo.headVect;
                    frame = player.bodyFrame;
                    rotation = player.headRotation;
                    break;
                case "legs":
                    offset = new Vector2(0f, 14f * grav);
                    targetPixels = 27f;
                    shader = drawInfo.cLegs;
                    lightColor = drawInfo.colorArmorLegs;
                    partPosition = player.legPosition + drawInfo.legsOffset;
                    pivot = drawInfo.legVect;
                    frame = player.legFrame;
                    rotation = player.legRotation;
                    break;
                case "accessory":
                    float angle = MathHelper.PiOver2 + accessoryOrdinal * MathHelper.TwoPi / Math.Max(1, accessoryCount);
                    offset = new Vector2(16f, 0f).RotatedBy(angle);
                    offset.Y *= grav;
                    // One explicit token selects one body-local badge offset. No name,
                    // category or image analysis chooses an anchor. Missing/orbit keeps
                    // the historical ring placement and visibility/dye behavior.
                    offset = entry.Data.Visual?.AccessoryMount switch
                    {
                        "chest" => new Vector2(0f, -2f * grav),
                        "back" => new Vector2(-10f * player.direction, -4f * grav),
                        "waist" => new Vector2(0f, 10f * grav),
                        "shoulder" => new Vector2(8f * player.direction, -12f * grav),
                        _ => offset,
                    };
                    targetPixels = 18f;
                    int dyeIndex = entry.AccessoryIndex + 3;
                    shader = player.dye is not null && dyeIndex >= 0 && dyeIndex < player.dye.Length
                        ? player.dye[dyeIndex].dye
                        : 0;
                    lightColor = drawInfo.colorArmorBody;
                    partPosition = player.bodyPosition;
                    pivot = drawInfo.bodyVect;
                    frame = player.bodyFrame;
                    rotation = player.bodyRotation;
                    accessoryOrdinal++;
                    break;
                default:
                    offset = new Vector2(0f, -2f * grav);
                    targetPixels = 31f;
                    shader = drawInfo.cBody;
                    lightColor = drawInfo.colorArmorBody;
                    partPosition = player.bodyPosition;
                    pivot = drawInfo.bodyVect;
                    frame = player.bodyFrame;
                    rotation = player.bodyRotation;
                    break;
            }

            // Keep the existing single-PNG badge offsets/orbit and size policy, not
            // an armor atlas. Attach that badge to the same local pivot as vanilla
            // head/torso/legs. PlayerDrawLayers.TransformDrawData owns full rotation.
            // tML v2026.06.3.6 (29bf9785): PlayerDrawLayers + PlayerDrawSet.
            Vector2 frameTop = new(
                (int)(drawInfo.Position.X - Main.screenPosition.X - frame.Width / 2 + player.width / 2),
                (int)(drawInfo.Position.Y - Main.screenPosition.Y + player.height - frame.Height + 4f));
            Vector2 badgeCenter = new Vector2(frame.Width * 0.5f, frame.Height - 4f - player.height * 0.5f) + offset;
            Vector2 position = frameTop + partPosition + pivot + (badgeCenter - pivot).RotatedBy(rotation);
            // A minimum scale defeats the target-pixel bound for high-res PNGs.
            float scale = Math.Min(targetPixels / Math.Max(texture.Width, texture.Height), 1.25f);
            Vector2 origin = new(texture.Width * 0.5f, texture.Height * 0.5f);
            DrawData draw = new(texture, position, null, lightColor, rotation, origin, scale, effects, 0)
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
            Item? vanity = vanityIndex < player.armor.Length ? player.armor[vanityIndex] : null;
            // Player.PlayerFrame replaces armor only for a matching equip slot,
            // not merely because the social inventory cell contains an item.
            bool replacesArmor = vanity is not null && (armorPart switch
            {
                0 => vanity.headSlot >= 0,
                1 => vanity.bodySlot >= 0,
                _ => vanity.legSlot >= 0,
            });
            int sourceIndex = replacesArmor ? vanityIndex : armorPart;
            TryAdd(player.armor, sourceIndex, entries, armorPart switch
            {
                0 => "head",
                1 => "body",
                _ => "legs",
            }, -1);
        }

        for (int accessoryIndex = 0; accessoryIndex < 7; accessoryIndex++)
        {
            int normalIndex = accessoryIndex + 3;
            if (!player.IsItemSlotUnlockedAndUsable(normalIndex))
                continue;
            int vanityIndex = accessoryIndex + 13;
            bool hasVanity = vanityIndex < player.armor.Length && player.armor[vanityIndex] is { IsAir: false };
            // Vanilla applies hideVisibleAccessory only to functional slots;
            // social accessories are evaluated separately and remain visible.
            if (!hasVanity && player.hideVisibleAccessory is { Length: > 0 }
                && normalIndex < player.hideVisibleAccessory.Length
                && player.hideVisibleAccessory[normalIndex])
                continue;
            int sourceIndex = hasVanity ? vanityIndex : normalIndex;
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
            ? data.Accessory?.Enabled == true
            : data.Armor?.Enabled == true && string.Equals(data.Armor.Slot, slot, StringComparison.Ordinal);
        if (roleMatches)
            entries.Add(new OverlayEntry(data, slot, accessoryIndex,item));
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

#nullable enable
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.Runtime;
using InfiniCrafterLocal.Common.Services;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using System;
using System.IO;
using Terraria;
using Terraria.DataStructures;
using Terraria.ID;
using Terraria.ModLoader;
using Terraria.ModLoader.IO;

namespace InfiniCrafterLocal.Content.Items;

/// <summary>
/// One proxy ModItem for many generated instances. Runtime behaviour is selected
/// exclusively by the accepted RuntimeProgramSpec binding/entity/component/event
/// graph. Display name, category and parent prose never route gameplay.
/// </summary>
public partial class GeneratedItem : ModItem
{
    private const int GeneratedItemNetPayloadVersion = 7;
    public override string Texture => "InfiniCrafterLocal/Assets/GeneratedItem";
    protected override bool CloneNewInstances => true;
    public GeneratedItemData Data { get; private set; } = GeneratedItemData.Placeholder();
    private static int _warningCount;
    private int _lastHydrationTick = -9999;
    private bool _nativeToolPowersSuppressed;
    private RuntimeSpawnBudget _itemEventBudget = new(0);
    // Only pure apply_item_effects mobility needs an outcome-gated stack debit.
    // Native direct use calls UseItem before ConsumeItem in the same world tick.
    private (Player? Player, Item? Item, GeneratedItemData? Data,
        RuntimeBindingSpec? Binding, uint Tick, bool Succeeded) _pureMobilityUseOutcome;
    private (Player? Player, Item? Item, GeneratedItemData? Data,
        RuntimeBindingSpec? Binding, uint Tick, bool Completed) _stackChanceUseOutcome;
    private (Player? Player, Item? Item, GeneratedItemData? Data,
        RuntimeItemEffectGroupSpec? Group, uint Tick, uint SnapshotTick) _heldEffectRefresh;
    private (Player? Player, Item? Item, GeneratedItemData? Data, uint Tick) _periodicItemEvents;


    private static void Warn(string context, Exception ex)
    {
        if (_warningCount++ >= 8) return;
        try { global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance?.Logger?.Warn($"[GeneratedItem] {context}: {ex.GetType().Name}: {ex.Message}"); }
        catch { }
    }

    public override ModItem Clone(Item newEntity)
    {
        var clone = (GeneratedItem)base.Clone(newEntity);
        try { clone.Data = (Data ?? GeneratedItemData.Placeholder()).CloneForItemInstance(); }
        catch { clone.Data = GeneratedItemData.Placeholder(); }
        clone._itemPresentationToken=0;clone._itemPresentationGeneration=new object();
        clone._itemEventBudget = new RuntimeSpawnBudget(0);
        clone._periodicItemEvents = default;
        clone.ResetPureMobilityUseOutcome();
        CopyNativePrefixLifecycleTo(clone);
        return clone;
    }

    public void SetData(GeneratedItemData data) => SetData(data, ensureAssets: true, registerLocal: true);

    private void SetData(GeneratedItemData data, bool ensureAssets, bool registerLocal, bool notifyNetState = true)
    {
        ResetPureMobilityUseOutcome();
        _itemEventBudget = new RuntimeSpawnBudget(0);
        _periodicItemEvents = default;
        if(Data?.Id!=data?.Id){_itemPresentationToken=0;_itemPresentationGeneration=new object();_hasMaterialTransportIdentity=false;}
        Data = data ?? GeneratedItemData.Placeholder();
        _nativeToolPowersSuppressed = false;
        try { ApplyDataWithNativePrefix(); }
        catch (Exception ex)
        {
            Warn($"ApplyToItem failed for '{Data.Id}'", ex);
            Data = GeneratedItemData.Placeholder();
            try { ApplyDataWithNativePrefix(); } catch { }
        }
        if (registerLocal)
        {
            try { global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems?.RegisterLocal(Data, ensureAssets: ensureAssets); }
            catch (Exception ex) { Warn($"RegisterLocal failed for '{Data.Id}'", ex); }
        }
        if (notifyNetState && registerLocal && Main.netMode != NetmodeID.SinglePlayer)
            try { Item.NetStateChanged(); } catch { }
    }

    public override void SetStaticDefaults()
    {
        // Every generated instance declares literal direct-use stackCost 0/1.
        // Native ItemCheck's ranged/throwing saving runs before ConsumeItem;
        // force entry into that final per-instance gate, never force its result.
        // This type-wide invariant is registered once, not changed per definition.
        // PickAmmo owns an independent IsAmmoFreeThisShot path and ignores this set.
        ItemID.Sets.ForceConsumption[Type] = true;
    }

    public override void SetDefaults()
    {
        ResetPureMobilityUseOutcome();
        _nativeToolPowersSuppressed = false;
        ResetNativePrefixLifecycle();
        Data ??= GeneratedItemData.Placeholder();
        try { ApplyDataWithNativePrefix(); }
        catch
        {
            Data = GeneratedItemData.Placeholder();
            try { ApplyDataWithNativePrefix(); } catch { }
        }
    }

    public override void SaveData(TagCompound tag)
    {
        try { tag["infiniJson"] = (Data ?? GeneratedItemData.Placeholder()).ToPlayerSaveJson(); }
        catch { tag["infiniJson"] = GeneratedItemData.Placeholder().ToPlayerSaveJson(); }
        SaveNativePrefixLifecycle(tag);
    }

    public override void LoadData(TagCompound tag)
    {
        try
        {
            string json = tag is not null && tag.ContainsKey("infiniJson") ? tag.GetString("infiniJson") ?? "" : "";
            GeneratedItemData reference = GeneratedItemData.FromPlayerSaveJson(json) ?? GeneratedItemData.Placeholder();
            try { if (tag is not null) LoadNativePrefixLifecycle(tag); }
            catch (InvalidDataException ex)
            {
                // Bad/unavailable instance metadata cannot replace a valid recipe reference.
                Warn("Native prefix metadata refused", ex);
                RetainNativePrefixForHydration(0);
            }
            SetData(reference, ensureAssets: false, registerLocal: false, notifyNetState: false);
        }
        catch { SetData(GeneratedItemData.Placeholder(), ensureAssets: false, registerLocal: false, notifyNetState: false); }
    }

    public override void NetSend(BinaryWriter writer)
    {
        bool materialTransport=HasMaterialTransportIdentity
            || global::InfiniCrafterLocal.Common.Runtime.GeneratedQuickUtilityActivation.IsEligible(Data);
        writer.Write(materialTransport?8:GeneratedItemNetPayloadVersion);
        try { writer.Write((Data ?? GeneratedItemData.Placeholder()).ToPlayerSaveJson()); }
        catch { writer.Write(GeneratedItemData.Placeholder().ToPlayerSaveJson()); }
        if(materialTransport)writer.Write(PresentationToken);
        writer.Write(ValidateNativePrefixToken(InstanceNativePrefix));
    }

    public override void NetReceive(BinaryReader reader)
    {
        try
        {
            int version = reader.ReadInt32();
            if (version != GeneratedItemNetPayloadVersion && version != 8)
                throw new InvalidDataException($"Unsupported generated item payload {version}");
            GeneratedItemData reference = GeneratedItemData.FromPlayerSaveJson(reader.ReadString()) ?? GeneratedItemData.Placeholder();
            bool materialTransport = version == 8;
            long token = materialTransport ? reader.ReadInt64() : 0;
            if (materialTransport && token == 0) throw new InvalidDataException("missing generated item presentation generation");
            // ItemIO already attempted Prefix on the native defaults before this hook.
            RetainNativePrefixForHydration(reader.ReadInt32());
            GeneratedItemData resolved = reference;
            var registry = global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems;
            if (GeneratedItemRegistryService.IsCurrentWorldData(reference) && !string.IsNullOrWhiteSpace(reference.Id) && registry is not null && registry.TryGet(reference.Id, out var canonical) && GeneratedItemRegistryService.IsCurrentWorldData(canonical))
                resolved = canonical;
            SetData(resolved, ensureAssets: false, registerLocal: false, notifyNetState: false);
            ApplyPresentationToken(token);
            EnsureRuntimeHydration();
        }
        catch { SetData(GeneratedItemData.Placeholder(), ensureAssets: false, registerLocal: false, notifyNetState: false); }
    }

    private void EnsureRuntimeHydration(Player? player = null)
    {
        if (!GeneratedItemRegistryService.IsCurrentWorldData(Data)) return;
        string id = (Data?.Id ?? "").Trim();
        if (id.Length == 0 || id == "placeholder") return;
        int now = (int)Main.GameUpdateCount;
        if (now - _lastHydrationTick < 90) return;
        _lastHydrationTick = now;
        try
        {
            var registry = global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems;
            if (registry is null) return;
            if (registry.TryGet(id, out var canonical) && GeneratedItemRegistryService.IsCurrentWorldData(canonical)
                && !GeneratedItemData.IsPlayerSaveReferenceOnly(canonical))
            {
                if (GeneratedItemData.IsPlayerSaveReferenceOnly(Data))
                    SetData(canonical, ensureAssets: false, registerLocal: false, notifyNetState: false);
                global::InfiniCrafterLocal.InfiniCrafterLocalMod.AssetSync?.EnsureAssetsForData(canonical, forceRetry: false);
            }
            else if (Main.netMode == NetmodeID.MultiplayerClient)
                registry.RequestOneFromServer(id, forceAssetRetry: false);
            else if (!GeneratedItemData.IsPlayerSaveReferenceOnly(Data))
                registry.RegisterLocal(Data, persist: false, ensureAssets: true);
        }
        catch (Exception ex) { Warn($"Runtime hydration failed for '{id}'", ex); }
    }

    private GeneratedItemData PresentationData()
    {
        if (!GeneratedItemData.IsPlayerSaveReferenceOnly(Data) || !GeneratedItemRegistryService.IsCurrentWorldData(Data)) return Data;
        var registry = global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems;
        return registry is not null && registry.TryGet(Data.Id, out var canonical) && GeneratedItemRegistryService.IsCurrentWorldData(canonical)
            ? canonical : Data;
    }

    internal static bool SameGeneratedStack(GeneratedItem destination, Item source)
    {
        if (source.ModItem is not GeneratedItem other
            || destination.Data is null || other.Data is null
            || string.IsNullOrWhiteSpace(destination.Data.Id) || destination.Data.Id == "placeholder"
            || !string.Equals(destination.Data.Id, other.Data.Id, StringComparison.Ordinal)
            || !string.Equals(destination.Data.RecipeKey, other.Data.RecipeKey, StringComparison.Ordinal)
            || GeneratedItemData.IsPlayerSaveReferenceOnly(destination.Data)
            || GeneratedItemData.IsPlayerSaveReferenceOnly(other.Data))
            return false;
        // A reused ID must not turn different executable definitions into one
        // physical stack. This expensive check runs only after the cheap IDs match.
        try {
            return string.Equals(GeneratedItemRegistryService.DefinitionIdentity(destination.Data),
                GeneratedItemRegistryService.DefinitionIdentity(other.Data), StringComparison.Ordinal);
        }
        catch { return false; }
    }

    public override bool CanStack(Item source) => SameGeneratedStack(this, source);

    public override bool CanStackInWorld(Item source) => SameGeneratedStack(this, source);

    // Technical native-proxy suppression only. Leave Item.noUseGraphic and the
    // authored visibility/hint untouched; the AfterParent child owns the PNG.
    public override bool ModifyItemDraw(ref PlayerDrawSet drawInfo, ref DrawData drawData,
        ref DrawData? coloredDrawData, ref DrawData? glowMaskDrawData)
    {
        // Native drawInfo.heldItem is lastVisualizedSelectedItem (a clone), not
        // necessarily the live inventory Item used by the custom child.
        if (!ReferenceEquals(drawInfo.heldItem, Item))
            return true;

        var assets = Terraria.GameContent.TextureAssets.Item;
        int type = Item.type;
        if (type <= ItemID.None || type >= assets.Length)
            return true;
        var nativeAsset = assets[type];
        if (nativeAsset?.IsLoaded != true
            || !ReferenceEquals(drawData.texture, nativeAsset.Value))
            return true;
        // Missing generated art never lends the type-wide cross. Explicit inert
        // diagnostics retain their historical native path when no custom PNG draws.
        if (AllowsDiagnosticProxy(PresentationData()) && !GeneratedHeldItemDrawLayer.HasReadyHeldSprite(drawInfo))
            return true;

        // The native veto covers its base/color/glow bundle. Keep optional draws
        // using OTHER textures rather than clearing unrelated cache entries.
        Texture2D nativeTexture = nativeAsset.Value;
        if (coloredDrawData is DrawData colored && !ReferenceEquals(colored.texture, nativeTexture))
            drawInfo.DrawDataCache.Add(colored);
        if (glowMaskDrawData is DrawData glow && !ReferenceEquals(glow.texture, nativeTexture))
            drawInfo.DrawDataCache.Add(glow);
        return false;
    }

    // Cursor source correction requires the same exact inventory asset as this hook.
    // Readiness is technical presentation only; never change authored hideUseGraphic.
    // Cursor routing and readiness are distinct: a missing generated image must
    // still use this instance's inventory veto, never ContentSamples' cross.
    internal bool SuppressesNativeImageProxy => !AllowsDiagnosticProxy(PresentationData());

    internal bool OwnsCursorItemPresentation()
        => SuppressesNativeImageProxy || HasReadyInventorySprite();

    internal bool HasReadyInventorySprite()
    {
        GeneratedItemData data = PresentationData();
        return !string.IsNullOrWhiteSpace(data.Visual.SpritePath)
            && global::InfiniCrafterLocal.InfiniCrafterLocalMod.Sprites.TryGet(data.Visual.SpritePath) is not null;
    }

    // The static cross is an explicit unavailable/developer diagnostic only,
    // never a substitute for a delivered or still-hydrating generated PNG.
    private static bool AllowsDiagnosticProxy(GeneratedItemData data)
        => data.SourceMode is "corrupt_reference" or "test_fixture" or "developer_fixture";

    public override bool PreDrawInInventory(SpriteBatch spriteBatch, Vector2 position, Rectangle frame, Color drawColor, Color itemColor, Vector2 origin, float scale)
    {
        EnsureRuntimeHydration();
        GeneratedItemData data = PresentationData();
        Texture2D? texture = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Sprites.TryGet(data.Visual.SpritePath);
        if (texture is null) return AllowsDiagnosticProxy(data);
        Rectangle source = texture.Bounds;
        Vector2 drawOrigin = source.Size() / 2f;
        float fit = Math.Min(1f, Math.Max(frame.Width, frame.Height) / Math.Max(1f, Math.Max(texture.Width, texture.Height)));
        Vector2 drawPosition = position + new Vector2(data.Visual.DrawOffsetX, data.Visual.DrawOffsetY);
        float finalScale = scale * fit * data.Visual.InventoryScale;
        spriteBatch.Draw(texture, drawPosition, source, drawColor, 0f, drawOrigin, finalScale, SpriteEffects.None, 0f);
        // Returning false suppresses both vanilla passes. Preserve ItemSlot's optional
        // Item.color overlay using the already-resolved caller color (not GetAlpha again).
        if (Item.color != Color.Transparent)
            spriteBatch.Draw(texture, drawPosition, source, itemColor, 0f, drawOrigin, finalScale, SpriteEffects.None, 0f);
        return false;
    }

    public override bool PreDrawInWorld(SpriteBatch spriteBatch, Color lightColor, Color alphaColor, ref float rotation, ref float scale, int whoAmI)
    {
        EnsureRuntimeHydration();
        GeneratedItemData data = PresentationData();
        Texture2D? texture = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Sprites.TryGet(data.Visual.SpritePath);
        if (texture is null) return AllowsDiagnosticProxy(data);
        Rectangle source = texture.Bounds;
        Vector2 origin = source.Size() / 2f;
        if (!data.Visual.RenderSizePx.HasValue || !data.Visual.ForwardAngleDegrees.HasValue) return AllowsDiagnosticProxy(data);
        float finalScale = scale * data.Visual.WorldScale * SpritePresentation.FrameScale(data.Visual.RenderSizePx, source.Width, source.Height);
        Vector2 drawPosition = Item.Bottom - Main.screenPosition - new Vector2(0f, origin.Y * finalScale) + new Vector2(data.Visual.DrawOffsetX, data.Visual.DrawOffsetY);
        spriteBatch.Draw(texture, drawPosition, source, alphaColor, rotation, origin, finalScale, SpriteEffects.None, 0f);
        // Match Main.DrawItem's separate Item.color pass; alphaColor already includes
        // the caller's alpha/shimmer treatment and must not be multiplied again.
        if (Item.color != Color.Transparent)
            spriteBatch.Draw(texture, drawPosition, source, Item.GetColor(lightColor), rotation, origin, finalScale, SpriteEffects.None, 0f);
        return false;
    }
}

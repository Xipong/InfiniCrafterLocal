#nullable enable
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.Runtime;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Common.Systems;
using InfiniCrafterLocal.Common.VFX;
using InfiniCrafterLocal.Content.Projectiles;
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
    private int _lastBlockedNoticeTick = -9999;
    private RuntimeSpawnBudget _itemEventBudget = new(0);
    // Only pure apply_item_effects mobility needs an outcome-gated stack debit.
    // Native direct use calls UseItem before ConsumeItem in the same world tick.
    private (Player? Player, Item? Item, GeneratedItemData? Data,
        RuntimeBindingSpec? Binding, uint Tick, bool Succeeded) _pureMobilityUseOutcome;


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
        clone.ResetPureMobilityUseOutcome();
        CopyNativePrefixLifecycleTo(clone);
        return clone;
    }

    public void SetData(GeneratedItemData data) => SetData(data, ensureAssets: true, registerLocal: true);

    private void SetData(GeneratedItemData data, bool ensureAssets, bool registerLocal, bool notifyNetState = true)
    {
        ResetPureMobilityUseOutcome();
        _itemEventBudget = new RuntimeSpawnBudget(0);
        if(Data?.Id!=data?.Id){_itemPresentationToken=0;_itemPresentationGeneration=new object();_hasMaterialTransportIdentity=false;}
        Data = data ?? GeneratedItemData.Placeholder();
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
            if (version != 5 && version != 6 && version != GeneratedItemNetPayloadVersion && version != 8)
                throw new InvalidDataException($"Unsupported generated item payload {version}");
            GeneratedItemData reference = GeneratedItemData.FromPlayerSaveJson(reader.ReadString()) ?? GeneratedItemData.Placeholder();
            bool materialTransport = version == 6 || version == 8;
            long token = materialTransport ? reader.ReadInt64() : 0;
            if (materialTransport && token == 0) throw new InvalidDataException("missing generated item presentation generation");
            // ItemIO already attempted Prefix on the native defaults before this hook.
            // New payloads carry the token separately; legacy hydrated hosts still
            // contribute their actual native Item.prefix (lost old tokens cannot be invented).
            RetainNativePrefixForHydration(version >= 7 ? reader.ReadInt32() : Item.prefix);
            GeneratedItemData resolved = reference;
            var registry = global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems;
            if (!string.IsNullOrWhiteSpace(reference.Id) && registry is not null && registry.TryGet(reference.Id, out var canonical) && GeneratedItemRegistryService.IsCurrentWorldData(canonical))
                resolved = canonical;
            SetData(resolved, ensureAssets: false, registerLocal: false, notifyNetState: false);
            ApplyPresentationToken(token);
            EnsureRuntimeHydration();
        }
        catch { SetData(GeneratedItemData.Placeholder(), ensureAssets: false, registerLocal: false, notifyNetState: false); }
    }

    private void EnsureRuntimeHydration(Player? player = null)
    {
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
        if (!GeneratedItemData.IsPlayerSaveReferenceOnly(Data)) return Data;
        var registry = global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems;
        return registry is not null && registry.TryGet(Data.Id, out var canonical) && GeneratedItemRegistryService.IsCurrentWorldData(canonical)
            ? canonical : Data;
    }

    public override bool CanStack(Item source)
        => source.ModItem is GeneratedItem other
            && string.Equals(Data.Id, other.Data.Id, StringComparison.Ordinal)
            && string.Equals(Data.RecipeKey, other.Data.RecipeKey, StringComparison.Ordinal);

    private RuntimeBindingSpec? ActiveUseBinding(Player player)
        => Data.RuntimeProgram.BindingForInput(GeneratedQuickUseSystem.IsNativeQuickUse(player)
            ? RuntimeInputKind.PrimaryUse
            : player.altFunctionUse == 2 ? RuntimeInputKind.AlternateUse : RuntimeInputKind.PrimaryUse);

    private bool BindingUsesItemBodyContact(RuntimeBindingSpec? binding)
        => binding?.UsePolicy.ContactDamage == true;

    private bool BaseNoMeleeFor(RuntimeBindingSpec binding)
        => Data.RuntimeProgram.ItemUse.DisableMeleeHitbox
            || !BindingUsesItemBodyContact(binding)
            || Data.Gameplay.AmmoCategory.Length > 0;

    private void ApplyActiveUseProjection(RuntimeBindingSpec binding)
    {
        int nativePrefix = BeginNativePrefixProjection();
        RuntimeBindingActionSpec action = binding.UsePolicy.Action;
        bool placing = action.Kind == RuntimeBindingAction.PlaceItem;
        RuntimePlacementSpec? placement = action.Placement;
        Item.createTile = placing ? placement!.TileId : -1;
        Item.createWall = placing ? placement!.WallId : -1;
        Item.placeStyle = placing ? placement!.PlaceStyle : 0;
        Item.useTurn = placing || Data.Gameplay.UseTurn;
        Item.noMelee = placing || BaseNoMeleeFor(binding);
        // Item.consumable is shared by two vanilla systems: direct-use consumption
        // (gated by our ConsumeItem override) and PickAmmo ammo consumption (gated by
        // CanConsumeAmmo). An ammo item must stay consumable so a weapon can spend it;
        // direct use is still governed by the binding stackCost via ConsumeItem.
        Item.consumable = binding.UsePolicy.StackCost == 1
            || Data.Gameplay.AmmoCategory.Length > 0;
        Item.damage = Math.Max(0, Data.Gameplay.Damage); // zero placement damage only after native prefix application
        // manaCost is the authored item-use cost for every active use binding.
        Item.mana = Math.Max(0, Data.Gameplay.ManaCost);
        bool applyingItemEffects = action.Kind == RuntimeBindingAction.ApplyItemEffects;
        Data.ApplyUseEffectFields(Item, applyingItemEffects);
        bool spawning = action.Kind == RuntimeBindingAction.SpawnEntity;
        Data.ApplyWeaponAmmoField(Item, spawning);
        Item.sentry = spawning && Data.RuntimeProgram.TryGetEntity(action.TargetId)?.NativeSentry == true;
        Item.shoot = spawning ? ModContent.ProjectileType<GeneratedProjectile>() : ProjectileID.None;
        Item.shootSpeed = spawning
            ? Data.RuntimeProgram.TryGetEntity(action.TargetId)?.Spawn.SpeedPxPerTick ?? 0f
            : 0f;
        // The same Item is used as direct-use input and as a vanilla ammo stack.
        // Direct-use projection must not erase the independent authored ammo fields.
        if (Item.ammo != AmmoID.None)
        {
            Item.shoot = Data.Gameplay.AmmoProjectileId;
            Item.shootSpeed = Data.Gameplay.AmmoShootSpeedPxPerTick;
        }
        FinishNativePrefixProjection(nativePrefix, placing);
    }

    /// <summary>
    /// Consumes the one-shot receipt written by the exact-identity placement ledger.
    /// Only a changed native cell covered by a before-mutation authorization can
    /// create that receipt; multiplayer first waits for the server intent fence.
    /// </summary>
    private static bool ConsumeAcceptedPlacementReceipt(Player player)
        => global::InfiniCrafterLocal.Common.Systems.GeneratedPlacementLedgerSystem.TryConsumePlacementReceipt(player);

    public override bool AltFunctionUse(Player player)
        => Data?.RuntimeProgram?.BindingForInput(RuntimeInputKind.AlternateUse) is not null;

    internal static string UseBlockedReason(Player player, GameplaySpec? gameplay)
    {
        if (player is null || gameplay is null) return "";
        return gameplay.UseConditionMode switch
        {
            "grounded" when !HasNativeGroundSupport(player) => "Requires solid ground",
            "not_wet" when player.wet => "Cannot be used while wet",
            "life_above" when player.statLife < gameplay.UseConditionMinLife => $"Requires {gameplay.UseConditionMinLife} life",
            "mana_above" when player.statMana < gameplay.UseConditionMinMana => $"Requires {gameplay.UseConditionMinMana} mana",
            _ => "",
        };
    }

    private static bool HasNativeGroundSupport(Player player)
    {
        if (player.velocity.Y != 0f || player.width <= 0 || player.height <= 0
            || !float.IsFinite(player.position.X) || !float.IsFinite(player.position.Y))
            return false;
        int gravityDirection = player.gravDir < 0f ? -1 : 1;
        Vector2 probe = new(0f, gravityDirection);
        // Native collision helpers publish scratch flags for the movement caller.
        // This is a read-only contact query, so neither those flags nor Player state
        // may change merely because CanUseItem examined an authored condition.
        bool up = Collision.up, down = Collision.down, stair = Collision.stair,
            stairFall = Collision.stairFall, sloping = Collision.sloping;
        try
        {
            Vector2 movement = Collision.TileCollision(player.position, probe,
                player.width, player.height, gravDir: gravityDirection);
            if (movement.Y == 0f)
                return true;
            // TileCollision deliberately leaves slope resolution to SlopeCollision.
            // Probe from one pixel into the gravity-facing surface; native slope
            // resolution must return to the current contact, not just a nearby tile.
            Vector4 slope = Collision.SlopeCollision(player.position + probe, probe,
                player.width, player.height, fall: gravityDirection < 0);
            return (slope.Y - player.position.Y) * gravityDirection <= 0f
                && slope.W * gravityDirection < 1f;
        }
        finally
        {
            Collision.up = up; Collision.down = down; Collision.stair = stair;
            Collision.stairFall = stairFall; Collision.sloping = sloping;
        }
    }

    public override bool CanUseItem(Player player)
    {
        ResetPureMobilityUseOutcome();
        EnsureRuntimeHydration(player);
        RuntimeBindingSpec? binding = ActiveUseBinding(player);
        if (binding is null || !GeneratedQuickUseSystem.AcceptsBinding(player, binding, Data.Gameplay)) return false;
        ApplyActiveUseProjection(binding);
        string blocked = UseBlockedReason(player, Data.Gameplay);
        if (!string.IsNullOrWhiteSpace(blocked))
        {
            if (player.whoAmI == Main.myPlayer && (int)Main.GameUpdateCount - _lastBlockedNoticeTick > 30)
            {
                _lastBlockedNoticeTick = (int)Main.GameUpdateCount;
                Main.NewText(blocked, Color.OrangeRed);
            }
            return false;
        }
        if (binding.UsePolicy.Action.Kind == RuntimeBindingAction.SpawnEntity)
        {
            RuntimeEntitySpec? entity = Data.RuntimeProgram.TryGetEntity(binding.UsePolicy.Action.TargetId);
            if (entity?.Spawn.MaxActive is not null && !GeneratedProjectile.CanAdmitEntityBatch(Data, entity, player.whoAmI,
                Math.Min(RootBindingSpawnCapacity(entity), InfiniRuntimeLimits.MaxRuntimeActiveProjectilesPerOwner
                    - GeneratedProjectile.CountActiveGeneratedProjectiles(player.whoAmI))))
                return false;
            if (entity?.IsOwnerAttached == true)
            {
                foreach (Projectile projectile in Main.ActiveProjectiles)
                    if (projectile.owner == player.whoAmI && projectile.ModProjectile is GeneratedProjectile generated && generated.Matches(Data.Id, entity.Id))
                        return false;
            }
        }
        if (binding.UsePolicy.Action.Kind == RuntimeBindingAction.PlaceItem)
        {
            RuntimePlacementSpec? placement = binding.UsePolicy.Action.Placement;
            if (placement is null || !GeneratedPlacementLedgerSystem.PreparePlacement(player, Data, placement))
                return false;
        }
        _itemEventBudget = new RuntimeSpawnBudget(Data.RuntimeProgram.Limits.MaxEventSpawnsPerActivation);
        return true;
    }

    public override void PickAmmo(Item weapon, Player player, ref int type, ref float speed, ref StatModifier damage, ref float knockback)
    {
        // Installed Player.PickAmmo adds ammo.shoot to weapon.shoot for these two
        // categories before calling the ammo ModItem hook. Restore the exact
        // authored projectile here; keep vanilla speed/damage/knockback intact.
        if (Item.ammo == weapon.useAmmo &&
            (weapon.useAmmo == AmmoID.Rocket || weapon.useAmmo == AmmoID.Solution))
            type = Data.Gameplay.AmmoProjectileId;
    }

    public override bool ConsumeItem(Player player)
    {
        RuntimeBindingSpec? binding = ActiveUseBinding(player);
        if (binding is null)
        {
            ResetPureMobilityUseOutcome();
            return false;
        }
        bool pureMobility = IsPureMobilityUse(binding);
        bool mobilitySucceeded = ConsumePureMobilityUseOutcome(player, binding);
        if (pureMobility)
            return binding.UsePolicy.StackCost == 1 && mobilitySucceeded;
        // This hook owns direct-use stack consumption only. Item.consumable can also be
        // true because the item is ammunition (vanilla PickAmmo requires that), so the
        // binding stackCost stays the single owner of whether a direct use spends a stack.
        // A placement binding additionally requires proof that Terraria actually placed
        // the authored tile/wall: vanilla reaches consumption even when placement produced
        // nothing, so charging on intent alone would silently destroy the item.
        if (binding.UsePolicy.Action.Kind == RuntimeBindingAction.PlaceItem)
        {
            GeneratedPlacementLedgerSystem.TryCommitAuthorizedPlacement(player);
            return binding.UsePolicy.StackCost == 1 && ConsumeAcceptedPlacementReceipt(player);
        }
        return binding.UsePolicy.StackCost == 1;
    }

    public override bool? UseItem(Player player)
    {
        ResetPureMobilityUseOutcome();
        EnsureRuntimeHydration(player);
        RuntimeBindingSpec? binding = ActiveUseBinding(player);
        if (binding is null) return false;
        RuntimeEntitySpec itemEntity = Data.RuntimeProgram.TryGetEntity(Data.RuntimeProgram.ItemEntityId)!;
        if (binding.UsePolicy.Action.Kind == RuntimeBindingAction.ApplyItemEffects)
        {
            bool mobilitySucceeded = ApplyItemEffects(player);
            if (IsPureMobilityUse(binding))
            {
                _pureMobilityUseOutcome = (player, Item, Data, binding, Main.GameUpdateCount, mobilitySucceeded);
            }
        }
        if (binding.UsePolicy.Action.Kind == RuntimeBindingAction.PlaceItem)
            GeneratedPlacementLedgerSystem.TryCommitAuthorizedPlacement(player);
        // Placement is not an authored use effect. on_use events and their VFX belong to
        // the attack/consume policy, so a tile placement must not fire them.
        if (binding.UsePolicy.Action.Kind != RuntimeBindingAction.PlaceItem)
        {
            RunItemEvent(player, itemEntity, RuntimeEventKind.OnUse, null, 0);
            InfiniItemVfxRuntime.EmitAndSyncEvent(player, Data, itemEntity.Id, RuntimeEventKind.OnUse);
        }
        // true means the use attempt is complete, not that mobility succeeded.
        // Keeping native itemTime avoids retrying mixed buffs/events when mobility
        // refuses; pure mobility's stack debit is separately gated by its outcome.
        return true;
    }

    private bool IsPureMobilityUse(RuntimeBindingSpec binding)
    {
        if (binding.UsePolicy.Action.Kind != RuntimeBindingAction.ApplyItemEffects
            || string.IsNullOrWhiteSpace(Data.Gameplay.MobilityMode)
            || binding.UsePolicy.ContactDamage || Item.shoot > ProjectileID.None
            || Item.healLife > 0 || Item.healMana > 0 || Item.buffType > 0
            || Data.Gameplay.GeneratedBuff?.HasAnyEffect == true)
            return false;
        foreach (BuffEntrySpec buff in Data.Gameplay.ExtraBuffs ?? Array.Empty<BuffEntrySpec>())
            if (buff.BuffCode > 0 && buff.BuffTime > 0)
                return false;
        RuntimeEntitySpec? body = Data.RuntimeProgram.TryGetEntity(Data.RuntimeProgram.ItemEntityId);
        // Do not reinterpret or waive the cost of authored gameplay event actions.
        return body is not null && body.Events.Length == 0;
    }

    private void ResetPureMobilityUseOutcome() => _pureMobilityUseOutcome = default;

    private bool ConsumePureMobilityUseOutcome(Player player, RuntimeBindingSpec binding)
    {
        var outcome = _pureMobilityUseOutcome;
        bool succeeded = outcome.Succeeded
            && ReferenceEquals(outcome.Player, player) && ReferenceEquals(outcome.Item, Item)
            && ReferenceEquals(outcome.Data, Data) && ReferenceEquals(outcome.Binding, binding)
            && outcome.Tick == Main.GameUpdateCount;
        ResetPureMobilityUseOutcome();
        return succeeded;
    }

    private bool ApplyItemEffects(Player player)
    {
        GameplaySpec gp = Data.Gameplay;
        foreach (BuffEntrySpec buff in gp.ExtraBuffs ?? Array.Empty<BuffEntrySpec>())
            if (buff.BuffCode > 0 && buff.BuffTime > 0)
                player.AddBuff(buff.BuffCode, buff.BuffTime);
        if (gp.GeneratedBuff?.HasAnyEffect == true)
            player.GetModPlayer<InfiniCraftPlayer>().ApplyGeneratedUtilityBuff(gp.GeneratedBuff, syncNetwork: Main.netMode != NetmodeID.SinglePlayer);
        return !string.IsNullOrWhiteSpace(gp.MobilityMode)
            && player.GetModPlayer<InfiniCraftPlayer>().TryRunGeneratedMobility(gp);
    }

    // Root binding shots are not event actions: their immediate capacity is the
    // authored spawn count, while SpawnRuntimeEntity gives them a separate event ledger.
    internal static int RootBindingSpawnCapacity(RuntimeEntitySpec entity)
        => Math.Clamp(entity.Spawn.Count, 1, InfiniRuntimeLimits.MaxRuntimeSpawnCount);

    public override void HoldItem(Player player)
    {
        EnsureRuntimeHydration(player);
        GameplaySpec gp = Data.Gameplay;
        if (gp.HoldLightStrength > 0f && Main.netMode != NetmodeID.Server)
        {
            Color color = RuntimeColorPolicy.Resolve(gp.HoldLightColorName, Color.White);
            float strength = Math.Clamp(gp.HoldLightStrength, 0f, 1.5f);
            Lighting.AddLight(player.Center, color.R / 255f * strength, color.G / 255f * strength, color.B / 255f * strength);
        }
        if ((gp.PickPower > 0 || gp.AxePower > 0 || gp.HammerPower > 0) && Math.Abs(gp.MiningSpeedScale - 1f) > 0.001f)
            player.pickSpeed /= Math.Clamp(gp.MiningSpeedScale, 0.1f, 4f);

        RuntimeBindingSpec? hold = Data.RuntimeProgram.BindingForInput(RuntimeInputKind.Hold);
        if (hold?.UsePolicy.Action.Kind == RuntimeBindingAction.SpawnEntity && InfiniRuntimeAuthority.ShouldRunLocalPlayerAction(player))
        {
            RuntimeEntitySpec? entity = Data.RuntimeProgram.TryGetEntity(hold.UsePolicy.Action.TargetId);
            bool exists = false;
            if (entity is not null)
            {
                foreach (Projectile projectile in Main.ActiveProjectiles)
                {
                    if (projectile.owner == player.whoAmI && projectile.ModProjectile is GeneratedProjectile generated && generated.Matches(Data.Id, entity.Id))
                    {
                        exists = true;
                        break;
                    }
                }
            }
            if (!exists && entity is not null && CanSpawnRoot(player, entity))
            {
                var combat = CalculateHoldRootCombat(player, entity);
                GeneratedProjectile.SpawnRuntimeEntity(Data, entity.Id, player, player.GetSource_ItemUse(Item), player.Center, new Vector2(player.direction, 0f), 0, RootBindingSpawnCapacity(entity),
                    rootDamageOverride: combat.Damage, rootKnockbackOverride: combat.Knockback);
            }
        }
        RuntimeEntitySpec itemEntity = Data.RuntimeProgram.TryGetEntity(Data.RuntimeProgram.ItemEntityId)!;
        RunPeriodicItemEvents(player, itemEntity);
        InfiniItemVfxRuntime.OnPeriodic(player, Data, itemEntity.Id);
    }


    private void RunPeriodicItemEvents(Player player, RuntimeEntitySpec entity)
    {
        var budget = new RuntimeSpawnBudget(Data.RuntimeProgram.Limits.MaxEventSpawnsPerActivation);
        foreach (RuntimeEventActionSpec action in entity.ActionsFor(RuntimeEventKind.Periodic))
        {
            int period = Math.Max(6, action.PeriodTicks);
            if ((Main.GameUpdateCount + (ulong)action.Id.GetHashCode()) % (ulong)period != 0) continue;
            QueueOrExecuteItemAction(
                player,
                entity,
                action,
                null,
                player.Center,
                new Vector2(player.direction, 0f),
                Data.Gameplay.Damage,
                budget,
                player.GetSource_Misc("InfiniRuntimePeriodic"));
        }
    }

    private void RunItemEvent(Player player, RuntimeEntitySpec entity, string eventName, NPC? target, int damageDone)
    {
        Vector2 position = target?.Center ?? player.Center;
        Vector2 direction = new(player.direction, 0f);
        foreach (RuntimeEventActionSpec action in entity.ActionsFor(eventName))
            QueueOrExecuteItemAction(
                player,
                entity,
                action,
                target,
                position,
                direction,
                damageDone,
                _itemEventBudget,
                player.GetSource_ItemUse(Item));
    }

    private void QueueOrExecuteItemAction(
        Player player,
        RuntimeEntitySpec entity,
        RuntimeEventActionSpec action,
        NPC? target,
        Vector2 position,
        Vector2 direction,
        int damageDone,
        RuntimeSpawnBudget budget,
        IEntitySource source)
    {
        if (action.DelayTicks > 0)
        {
            RuntimeDelayedActionScheduler.TrySchedule(
                Data,
                entity,
                action,
                player,
                source,
                position,
                direction,
                target,
                damageDone,
                0,
                budget);
            return;
        }
        RuntimeProgramExecutor.ExecuteAction(
            Data,
            entity,
            action,
            player,
            source,
            position,
            direction,
            target,
            damageDone,
            0,
            budget);
    }


    public override bool Shoot(Player player, EntitySource_ItemUse_WithAmmo source, Vector2 position, Vector2 velocity, int type, int damage, float knockback)
    {
        RestoreRootCombatSource(player);
        RuntimeBindingSpec? binding = ActiveUseBinding(player);
        if (binding?.UsePolicy.Action.Kind != RuntimeBindingAction.SpawnEntity) return false;
        if (!InfiniRuntimeAuthority.ShouldRunLocalPlayerAction(player)) return false;
        RuntimeEntitySpec? entity = Data.RuntimeProgram.TryGetEntity(binding.UsePolicy.Action.TargetId);
        if (entity is null) return false;
        GeneratedProjectile.SpawnRuntimeEntity(Data, entity.Id, player, source, position, velocity.SafeNormalize(new Vector2(player.direction, 0f)), 0, RootBindingSpawnCapacity(entity), activationBudget: _itemEventBudget,
            rootDamageOverride: damage, rootKnockbackOverride: knockback,
            rootSpeedOverride: Data.RuntimeProgram.WeaponAmmo?.SpeedBasis == "native_shot" ? velocity.Length() : null);
        return false;
    }

    public override Vector2? HoldoutOffset()
        => new(Data.RuntimeProgram.ItemUse.HoldoutOffsetX, Data.RuntimeProgram.ItemUse.HoldoutOffsetY);

    public override void ModifyItemScale(Player player, ref float scale)
        => scale *= Math.Clamp(Data.Gameplay.ItemScale, 0.25f, 4f);

    public override void UseItemHitbox(Player player, ref Rectangle hitbox, ref bool noHitbox)
    {
        RuntimeItemContactSpec contact = Data.RuntimeProgram.ItemContact;
        RuntimeBindingSpec? binding = ActiveUseBinding(player);
        if (!BindingUsesItemBodyContact(binding))
        {
            noHitbox = true;
            return;
        }
        float scale = contact.HitboxScale;
        int width = Math.Max(1, (int)MathF.Round(hitbox.Width * scale) + contact.ContactForgivenessPx * 2);
        int height = Math.Max(1, (int)MathF.Round(hitbox.Height * scale) + contact.ContactForgivenessPx * 2);
        hitbox = new Rectangle(hitbox.Center.X - width / 2, hitbox.Center.Y - height / 2, width, height);
    }

    public override void OnHitNPC(Player player, NPC target, NPC.HitInfo hit, int damageDone)
    {
        RuntimeBindingSpec? binding = ActiveUseBinding(player);
        if (!BindingUsesItemBodyContact(binding)) return;
        RuntimeEntitySpec itemEntity = Data.RuntimeProgram.TryGetEntity(Data.RuntimeProgram.ItemEntityId)!;
        Vector2 eventPosition = target.Center;
        RuntimeHitPullBridge.SendItemHit(player, this, target, hit.Crit);
        RunItemEvent(player, itemEntity, RuntimeEventKind.OnHit, target, damageDone);
        if (hit.Crit) RunItemEvent(player, itemEntity, RuntimeEventKind.OnCrit, target, damageDone);
        InfiniItemVfxRuntime.EmitAndSyncEvent(player, Data, itemEntity.Id, RuntimeEventKind.OnHit, eventPosition);
        if (hit.Crit) InfiniItemVfxRuntime.EmitAndSyncEvent(player, Data, itemEntity.Id, RuntimeEventKind.OnCrit, eventPosition);
    }

    public override void UpdateAccessory(Player player, bool hideVisual)
    {
        EnsureRuntimeHydration(player);
        RuntimeBindingSpec? binding = Data.RuntimeProgram.BindingForInput(RuntimeInputKind.Equipped);
        if (binding?.UsePolicy.Action.Kind != RuntimeBindingAction.EquipPassive || !Data.Accessory.Enabled) return;
        ApplyEquipmentEffects(player, Data.Accessory);
        InfiniItemVfxRuntime.OnPeriodic(player, Data, Data.RuntimeProgram.ItemEntityId,Item);
    }

    public override void UpdateEquip(Player player)
    {
        EnsureRuntimeHydration(player);
        RuntimeBindingSpec? binding = Data.RuntimeProgram.BindingForInput(RuntimeInputKind.Equipped);
        if (binding?.UsePolicy.Action.Kind != RuntimeBindingAction.EquipPassive || !Data.Armor.Enabled) return;
        ApplyEquipmentEffects(player, Data.Armor);
        InfiniItemVfxRuntime.OnPeriodic(player, Data, Data.RuntimeProgram.ItemEntityId,Item);
    }

    private static void ApplyEquipmentEffects(Player player, AccessorySpec a)
    {
        // Terraria already applies Item.defense in Player.GrantArmorBenefits.
        player.statLifeMax2 += a.MaxLife; player.statManaMax2 += a.MaxMana;
        player.lifeRegen += a.LifeRegen; player.manaRegenBonus += a.ManaRegen;
        player.moveSpeed += a.MovementSpeed; player.GetModPlayer<InfiniCraftPlayer>().AddGeneratedMaxRunSpeedBonus(a.MaxRunSpeed); player.jumpSpeedBoost += a.JumpSpeed;
        player.GetDamage(DamageClass.Generic) += a.GenericDamage; player.GetDamage(DamageClass.Melee) += a.MeleeDamage;
        player.GetDamage(DamageClass.Ranged) += a.RangedDamage; player.GetDamage(DamageClass.Magic) += a.MagicDamage; player.GetDamage(DamageClass.Summon) += a.SummonDamage;
        player.GetCritChance(DamageClass.Generic) += a.GenericCrit; player.GetAttackSpeed(DamageClass.Generic) += a.AttackSpeed; player.GetKnockback(DamageClass.Generic) += a.Knockback;
        player.maxMinions += a.MinionSlots; player.maxTurrets += a.SentrySlots;
        if (a.ManaCostReduction > 0f) player.manaCost = Math.Max(0.1f, player.manaCost - a.ManaCostReduction);
        player.GetModPlayer<InfiniCraftPlayer>().AddGeneratedAmmoSaveChance(a.AmmoSaveChance);
        player.GetModPlayer<InfiniCraftPlayer>().AddGeneratedSummonTagDamage(a.SummonTagDamage);
        player.aggro += a.Aggro; player.endurance += a.Endurance; player.GetArmorPenetration(DamageClass.Generic) += a.ArmorPenetration;
        player.whipRangeMultiplier += a.WhipRange;
        if (a.FallDamageImmune) player.noFallDmg = true; if (a.LavaImmune) player.lavaImmune = true; if (a.WaterWalk) player.waterWalk = true;
        AddEquipmentLight(player, a.LightStrength, a.LightColorName);
    }

    private static void ApplyEquipmentEffects(Player player, ArmorSpec a)
    {
        player.statLifeMax2 += a.MaxLife; player.statManaMax2 += a.MaxMana;
        player.lifeRegen += a.LifeRegen; player.manaRegenBonus += a.ManaRegen;
        player.moveSpeed += a.MovementSpeed; player.GetModPlayer<InfiniCraftPlayer>().AddGeneratedMaxRunSpeedBonus(a.MaxRunSpeed); player.jumpSpeedBoost += a.JumpSpeed;
        player.GetDamage(DamageClass.Generic) += a.GenericDamage; player.GetDamage(DamageClass.Melee) += a.MeleeDamage;
        player.GetDamage(DamageClass.Ranged) += a.RangedDamage; player.GetDamage(DamageClass.Magic) += a.MagicDamage; player.GetDamage(DamageClass.Summon) += a.SummonDamage;
        player.GetCritChance(DamageClass.Generic) += a.GenericCrit; player.GetAttackSpeed(DamageClass.Generic) += a.AttackSpeed; player.GetKnockback(DamageClass.Generic) += a.Knockback;
        player.maxMinions += a.MinionSlots; player.maxTurrets += a.SentrySlots;
        if (a.ManaCostReduction > 0f) player.manaCost = Math.Max(0.1f, player.manaCost - a.ManaCostReduction);
        player.GetModPlayer<InfiniCraftPlayer>().AddGeneratedAmmoSaveChance(a.AmmoSaveChance);
        player.GetModPlayer<InfiniCraftPlayer>().AddGeneratedSummonTagDamage(a.SummonTagDamage);
        player.aggro += a.Aggro; player.endurance += a.Endurance; player.GetArmorPenetration(DamageClass.Generic) += a.ArmorPenetration;
        player.whipRangeMultiplier += a.WhipRange;
        if (a.FallDamageImmune) player.noFallDmg = true; if (a.LavaImmune) player.lavaImmune = true; if (a.WaterWalk) player.waterWalk = true;
        AddEquipmentLight(player, a.LightStrength, a.LightColorName);
    }

    private static void AddEquipmentLight(Player player, float strength, string colorName)
    {
        if (strength <= 0f || Main.netMode == NetmodeID.Server) return;
        Color color = RuntimeColorPolicy.Resolve(colorName, Color.White);
        strength = Math.Clamp(strength, 0f, 1.5f);
        Lighting.AddLight(player.Center, color.R / 255f * strength, color.G / 255f * strength, color.B / 255f * strength);
    }

    public override bool IsArmorSet(Item head, Item body, Item legs)
    {
        ArmorSpec armor = Data.Armor;
        if (!armor.Enabled || !string.Equals(armor.Slot, "head", StringComparison.OrdinalIgnoreCase) || string.IsNullOrWhiteSpace(armor.SetKey)) return false;
        return IsSetPiece(head, "head", armor.SetKey) && IsSetPiece(body, "body", armor.SetKey) && IsSetPiece(legs, "legs", armor.SetKey);
    }

    private static bool IsSetPiece(Item item, string slot, string setKey)
        => item?.ModItem is GeneratedItem generated && generated.Data.Armor.Enabled
            && string.Equals(generated.Data.Armor.Slot, slot, StringComparison.OrdinalIgnoreCase)
            && string.Equals(generated.Data.Armor.SetKey, setKey, StringComparison.Ordinal);

    public override void UpdateArmorSet(Player player)
    {
        ArmorSpec a = Data.Armor;
        if (!a.Enabled || !string.Equals(a.Slot, "head", StringComparison.OrdinalIgnoreCase)) return;
        player.GetDamage(DamageClass.Generic) += a.SetBonusGenericDamage;
        player.GetDamage(DamageClass.Melee) += a.SetBonusMeleeDamage;
        player.GetDamage(DamageClass.Ranged) += a.SetBonusRangedDamage;
        player.GetDamage(DamageClass.Magic) += a.SetBonusMagicDamage;
        player.GetDamage(DamageClass.Summon) += a.SetBonusSummonDamage;
        player.GetCritChance(DamageClass.Generic) += a.SetBonusGenericCrit;
        player.moveSpeed += a.SetBonusMovementSpeed; player.lifeRegen += a.SetBonusLifeRegen; player.manaRegenBonus += a.SetBonusManaRegen;
        player.maxMinions += a.SetBonusMinionSlots; player.maxTurrets += a.SetBonusSentrySlots;
        if (a.SetBonusManaCostReduction > 0f) player.manaCost = Math.Max(0.1f, player.manaCost - a.SetBonusManaCostReduction);
        player.GetModPlayer<InfiniCraftPlayer>().AddGeneratedAmmoSaveChance(a.SetBonusAmmoSaveChance);
        player.aggro += a.SetBonusAggro; player.endurance += a.SetBonusEndurance; player.GetArmorPenetration(DamageClass.Generic) += a.SetBonusArmorPenetration;
    }

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
            || !ReferenceEquals(drawData.texture, nativeAsset.Value)
            || !GeneratedHeldItemDrawLayer.HasReadyHeldSprite(drawInfo))
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
    internal bool HasReadyInventorySprite()
    {
        GeneratedItemData data = PresentationData();
        return !string.IsNullOrWhiteSpace(data.Visual.SpritePath)
            && global::InfiniCrafterLocal.InfiniCrafterLocalMod.Sprites.TryGet(data.Visual.SpritePath) is not null;
    }

    public override bool PreDrawInInventory(SpriteBatch spriteBatch, Vector2 position, Rectangle frame, Color drawColor, Color itemColor, Vector2 origin, float scale)
    {
        EnsureRuntimeHydration();
        GeneratedItemData data = PresentationData();
        Texture2D? texture = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Sprites.TryGet(data.Visual.SpritePath);
        if (texture is null) return true;
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
        if (texture is null) return true;
        Rectangle source = texture.Bounds;
        Vector2 origin = source.Size() / 2f;
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

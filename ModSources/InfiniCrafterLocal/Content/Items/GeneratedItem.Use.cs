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
using System;
using Terraria;
using Terraria.DataStructures;
using Terraria.ID;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Content.Items;

// Native direct-use and held-item hooks share the same accepted binding projection.
public partial class GeneratedItem
{
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
        // configure_tool owns canonical powers; only native body/tool or explicit
        // projectile+tool actions execute them. Pure effects (including refused
        // recall) and placement must not also enter Player's independent mining
        // path. noMelee/contactDamage do not gate that path. Restore every eligible
        // projection: NativePrefixBase does not snapshot pick/axe/hammer.
        bool nativeToolAction = action.Kind == RuntimeBindingAction.UseItemBody
            || action.Kind == RuntimeBindingAction.SpawnEntity;
        Item.pick = nativeToolAction ? Math.Max(0, Data.Gameplay.PickPower) : 0;
        Item.axe = nativeToolAction ? Math.Max(0, Data.Gameplay.AxePower) : 0;
        Item.hammer = nativeToolAction ? Math.Max(0, Data.Gameplay.HammerPower) : 0;
        _nativeToolPowersSuppressed = !nativeToolAction;
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
        // Prefix eligibility remains tied to the authored item identity, not a
        // temporarily free input. Scope the final prefixed cost below.
        Item.mana = Math.Max(0, Data.Gameplay.ManaCost);
        bool applyingItemEffects = action.Kind == RuntimeBindingAction.ApplyItemEffects;
        Data.ApplyUseEffectFields(Item, applyingItemEffects, binding);
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
        // Native CheckMana owns reductions, admission and the sole payment.
        if (!RuntimeUseInputScope.Matches(Data.Gameplay.ManaCostInput, binding.Input)) Item.mana = 0;
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

    internal static string UseBlockedReason(Player player, GameplaySpec? gameplay, string? input = null)
    {
        if (player is null || gameplay is null) return "";
        RuntimeUseConditionSpec? selected = input is null ? null : Array.Find(gameplay.UseConditions ?? Array.Empty<RuntimeUseConditionSpec>(), c => c.Input == input);
        string common = ConditionBlockedReason(player, gameplay.UseConditionMode, gameplay.UseConditionMinLife, gameplay.UseConditionMinMana);
        return common.Length != 0 || selected is null ? common
            : ConditionBlockedReason(player, selected.UseConditionMode, selected.UseConditionMinLife, selected.UseConditionMinMana);
    }

    private static string ConditionBlockedReason(Player player, string mode, int minLife, int minMana)
        => mode switch
        {
            "grounded" when !HasNativeGroundSupport(player) => InfiniCraftPlayer.GeneratedUseFeedbackText("GroundRequired"),
            "not_wet" when player.wet => InfiniCraftPlayer.GeneratedUseFeedbackText("Wet"),
            "life_above" when player.statLife < minLife => InfiniCraftPlayer.GeneratedUseFeedbackText("LifeRequired", minLife),
            "mana_above" when player.statMana < minMana => InfiniCraftPlayer.GeneratedUseFeedbackText("ManaRequired", minMana),
            _ => "",
        };

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
        if (binding is null || !GeneratedQuickUseSystem.AcceptsBinding(player, binding, Data.EffectsForBinding(binding))) return false;
        ApplyActiveUseProjection(binding);
        string blocked = UseBlockedReason(player, Data.Gameplay, binding.Input);
        if (!string.IsNullOrWhiteSpace(blocked))
        {
            player.GetModPlayer<InfiniCraftPlayer>().NotifyGeneratedUseRefusal(blocked);
            return false;
        }
        if (binding.UsePolicy.Action.Kind == RuntimeBindingAction.SpawnEntity)
        {
            RuntimeEntitySpec? entity = Data.RuntimeProgram.TryGetEntity(binding.UsePolicy.Action.TargetId);
            if (entity is null) return false;
            string spawnRefusal = RootSpawnBlockedReason(player, entity);
            if (spawnRefusal.Length != 0)
            {
                player.GetModPlayer<InfiniCraftPlayer>().NotifyGeneratedUseRefusal(spawnRefusal);
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

    // Read the exact native admission facts; this does not reserve or alter a budget.
    internal string RootSpawnBlockedReason(Player player, RuntimeEntitySpec entity)
    {
        int count = RootBindingSpawnCapacity(entity);
        if (GeneratedProjectile.CountActiveGeneratedProjectiles(player.whoAmI)
            > InfiniRuntimeLimits.MaxRuntimeActiveProjectilesPerOwner - count)
            return InfiniCraftPlayer.GeneratedUseFeedbackText("OwnerProjectileLimit",
                InfiniRuntimeLimits.MaxRuntimeActiveProjectilesPerOwner);
        if (!GeneratedProjectile.CanAdmitEntityBatch(Data, entity, player.whoAmI, count))
            return InfiniCraftPlayer.GeneratedUseFeedbackText("EntityBatchLimit", count, entity.Spawn.MaxActive!);
        if (entity.IsOwnerAttached)
            foreach (Projectile projectile in Main.ActiveProjectiles)
                if (projectile.owner == player.whoAmI && projectile.ModProjectile is GeneratedProjectile generated
                    && generated.Matches(Data.Id, entity.Id))
                    return InfiniCraftPlayer.GeneratedUseFeedbackText("OwnerAttachedActive");
        return "";
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
            return binding.UsePolicy.StackCost == 1 && mobilitySucceeded && ConsumeStackChance(player, binding);
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
        return binding.UsePolicy.StackCost == 1 && ConsumeStackChance(player, binding);
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
            bool mobilitySucceeded = ApplyItemEffects(player, binding);
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
            RunItemEvent(player, itemEntity, RuntimeEventKind.OnUse, null, 0, binding.Input);
            InfiniItemVfxRuntime.EmitAndSyncEvent(player, Data, itemEntity.Id, RuntimeEventKind.OnUse);
            if (binding.UsePolicy.StackConsumeChancePercent is not null)
                _stackChanceUseOutcome = (player, Item, Data, binding, Main.GameUpdateCount, true);
        }
        // true means the use attempt is complete, not that mobility succeeded.
        // Keeping native itemTime avoids retrying mixed buffs/events when mobility
        // refuses; pure mobility's stack debit is separately gated by its outcome.
        return true;
    }

    private bool IsPureMobilityUse(RuntimeBindingSpec binding)
    {
        IItemEffectsSpec effects = Data.EffectsForBinding(binding);
        if (binding.UsePolicy.Action.Kind != RuntimeBindingAction.ApplyItemEffects
            || string.IsNullOrWhiteSpace(effects.MobilityMode)
            || binding.UsePolicy.ContactDamage || Item.shoot > ProjectileID.None
            || Item.healLife > 0 || Item.healMana > 0 || Item.buffType > 0
            || effects.GeneratedBuff?.HasAnyEffect == true)
            return false;
        foreach (BuffEntrySpec buff in effects.ExtraBuffs ?? Array.Empty<BuffEntrySpec>())
            if (buff.BuffCode > 0 && buff.BuffTime > 0)
                return false;
        RuntimeEntitySpec? body = Data.RuntimeProgram.TryGetEntity(Data.RuntimeProgram.ItemEntityId);
        // Do not reinterpret or waive the cost of authored gameplay event actions.
        return body is not null && body.Events.Length == 0;
    }

    private void ResetPureMobilityUseOutcome()
    {
        _pureMobilityUseOutcome = default;
        _stackChanceUseOutcome = default;
    }

    private bool ConsumePureMobilityUseOutcome(Player player, RuntimeBindingSpec binding)
    {
        var outcome = _pureMobilityUseOutcome;
        bool succeeded = outcome.Succeeded
            && ReferenceEquals(outcome.Player, player) && ReferenceEquals(outcome.Item, Item)
            && ReferenceEquals(outcome.Data, Data) && ReferenceEquals(outcome.Binding, binding)
            && outcome.Tick == Main.GameUpdateCount;
        _pureMobilityUseOutcome = default;
        return succeeded;
    }

    private bool ConsumeStackChance(Player player, RuntimeBindingSpec binding)
    {
        // Absent policy preserves the historical literal gate. Explicit probability
        // requires a completed local native activation and spends its receipt once.
        if (binding.UsePolicy.StackConsumeChancePercent is not int chance) return true;
        var outcome = _stackChanceUseOutcome;
        _stackChanceUseOutcome = default;
        if (!outcome.Completed || !ReferenceEquals(outcome.Player, player)
            || !ReferenceEquals(outcome.Item, Item) || !ReferenceEquals(outcome.Data, Data)
            || !ReferenceEquals(outcome.Binding, binding) || outcome.Tick != Main.GameUpdateCount
            || !InfiniRuntimeAuthority.ShouldRunLocalPlayerAction(player)) return false;
        // Endpoints do not advance RNG. Placement never reaches this method.
        return chance == 100 || (chance > 0 && Main.rand.Next(100) < chance);
    }

    private bool ApplyItemEffects(Player player, RuntimeBindingSpec binding)
    {
        IItemEffectsSpec gp = Data.EffectsForBinding(binding);
        foreach (BuffEntrySpec buff in gp.ExtraBuffs ?? Array.Empty<BuffEntrySpec>())
            if (buff.BuffCode > 0 && buff.BuffTime > 0)
                player.AddBuff(buff.BuffCode, buff.BuffTime);
        if (gp.GeneratedBuff?.HasAnyEffect == true)
            player.GetModPlayer<InfiniCraftPlayer>().ApplyGeneratedUtilityBuff(gp.GeneratedBuff, syncNetwork: Main.netMode != NetmodeID.SinglePlayer, source: Data);
        if (string.IsNullOrWhiteSpace(gp.MobilityMode)) return false;
        var owner = player.GetModPlayer<InfiniCraftPlayer>();
        bool succeeded = owner.TryRunGeneratedMobility(gp);
        if (!succeeded) owner.NotifyGeneratedUseRefusal(owner.LastGeneratedMobilityFailureMessage);
        return succeeded;
    }

    // Root binding shots are not event actions: their immediate capacity is the
    // authored spawn count, while SpawnRuntimeEntity gives them a separate event ledger.
    internal static int RootBindingSpawnCapacity(RuntimeEntitySpec entity)
        => Math.Clamp(entity.Spawn.Count, 1, InfiniRuntimeLimits.MaxRuntimeSpawnCount);

    private void RefreshHeldEffectGroup(Player player)
    {
        if (player is not { active: true, dead: false } || !ReferenceEquals(player.HeldItem, Item)
            || !InfiniRuntimeAuthority.ShouldRunPlayerGameplay(player)
            || Data.RuntimeProgram.TryGetEffectGroup(Data.RuntimeProgram.HeldEffectGroupId) is not { GeneratedBuff: { HasAnyEffect: true } buff } group)
            return;
        var previous = _heldEffectRefresh;
        uint tick = Main.GameUpdateCount;
        bool same = ReferenceEquals(previous.Player, player) && ReferenceEquals(previous.Item, Item)
            && ReferenceEquals(previous.Data, Data) && ReferenceEquals(previous.Group, group);
        if (same && previous.Tick == tick) return;
        bool snapshot = !same || tick < previous.SnapshotTick || tick - previous.SnapshotTick >= 30;
        var owner = player.GetModPlayer<InfiniCraftPlayer>();
        owner.ApplyGeneratedUtilityBuff(buff,
            syncNetwork: Main.netMode == NetmodeID.Server && snapshot
                && buff.ExhaustionTicks is not > 0 && !owner.HasGeneratedItemExhaustion(Data), source: Data);
        _heldEffectRefresh = (player, Item, Data, group, tick, snapshot ? tick : previous.SnapshotTick);
    }

    private void RestoreIdleNativeToolPowers()
    {
        if (!_nativeToolPowersSuppressed) return;
        // Only the native power projection is temporary. Reapplying the full
        // definition/prefix here would disturb the selected use and other mods'
        // instance fields; NativePrefixBase itself does not own tool powers.
        Item.pick = Math.Max(0, Data.Gameplay.PickPower);
        Item.axe = Math.Max(0, Data.Gameplay.AxePower);
        Item.hammer = Math.Max(0, Data.Gameplay.HammerPower);
        _nativeToolPowersSuppressed = false;
    }

    public override void UpdateInventory(Player player)
    {
        // UpdateEquips visits inventory before ItemCheck. ItemCheck then decrements
        // itemAnimation BEFORE SmartSelectLookup and HoldItem. At 1 -> 0 there is
        // no remaining mining window, but SmartSelect already needs the real pick.
        // A switched-away item also cannot be the current native mining input.
        if (!ReferenceEquals(player.HeldItem, Item) || player.itemAnimation <= 1)
            RestoreIdleNativeToolPowers();
    }

    public override void HoldItem(Player player)
    {
        EnsureRuntimeHydration(player);
        // This hook is inside ItemCheck, after CanUseItem/StartActualUse but BEFORE
        // OwnerOnlyCode (mining) and the generic UseItem tail. Never restore during
        // a live animation, including a cooldown-refused effect or its final tick.
        if (player.itemAnimation <= 0)
            RestoreIdleNativeToolPowers();
        RefreshHeldEffectGroup(player);
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
}

#nullable enable
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Runtime;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Common.VFX;
using Microsoft.Xna.Framework;
using System;
using System.Collections.Generic;
using Terraria;
using Terraria.DataStructures;
using Terraria.ID;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Content.Projectiles;

/// <summary>
/// Bounded executor for one explicitly authored runtime entity. The entity id,
/// kind, movement/controller opcodes and event links arrive over the typed v5
/// contract. There is no weapon-family, category or prose dispatch here.
/// </summary>
public sealed partial class GeneratedProjectile : ModProjectile
{
    public override string Texture => "InfiniCrafterLocal/Assets/GeneratedProjectile";

    private GeneratedItemData? _data;
    private RuntimeEntitySpec? _entity;
    private string _generatedItemId = "";
    private string _entityId = "";
    private bool _configured;
    private int _childDepth;
    private int _remainingSpawnBudget; // peer-visible snapshot only; not owner authority
    private RuntimeSpawnBudget? _activationSpawnBudget;
    private RuntimeSpawnLease? _spawnBudgetLease;
    private int _age;
    private int _remainingBounces;
    private int _activationDelayTicks;
    private int _pendingHydrationTicks;
    private bool _preserveSyncedStateOnHydrate;
    private bool _spawnEventRan;
    private bool _expireEventRan;
    private bool _returning;
    private bool _released;
    private int _chargeTicks;
    private int _controllerTimer;
    private bool _beamManaClockStarted;
    private uint _beamLastManaTick;
    private readonly float[] _beamScanSamples = new float[3];
    private int _lastTarget = -1;
    private int _lastOwnerVectorSyncAge = -1000;
    private Vector2 _initialDirection = Vector2.UnitX;
    private Vector2 _spawnCenter;
    private readonly List<Vector2> _whipPoints = new(32);
    private InfiniVfxState _vfxState = new();


    private int AuthoredTicksToProjectileUpdates(int ticks)
        => Math.Max(0, ticks) * Math.Max(1, Projectile.extraUpdates + 1);

    public bool IsGeneratedWhipTagSource => _configured && _entity?.Movement.Code == 18;
    internal bool Matches(string? generatedItemId, string? entityId)
        => _configured && string.Equals(_generatedItemId, generatedItemId?.Trim(), StringComparison.Ordinal)
            && string.Equals(_entityId, entityId?.Trim(), StringComparison.Ordinal);
    internal bool TryGetHitSource(out GeneratedItemData data, out RuntimeEntitySpec entity)
    {
        data = _data!; entity = _entity!;
        return _configured && data is not null && entity is not null
            && entity.IsProjectileEntity
            && ReferenceEquals(data.RuntimeProgram.TryGetEntity(_entityId), entity)
            && string.Equals(data.Id, _generatedItemId, StringComparison.Ordinal);
    }

    private bool IsPrimaryRuntimeEntity
        => _configured
            && _data?.RuntimeProgram.PrimaryOwner == RuntimeProgramSpec.ProjectileOwner
            && string.Equals(_data.RuntimeProgram.PrimaryEntityId, _entityId, StringComparison.Ordinal);

    private void ClaimHeldProjectile(Player owner, bool keepAnimation = false, bool matchAnimation = false)
    {
        if (!IsPrimaryRuntimeEntity) return;
        owner.heldProj = Projectile.whoAmI;
        if (keepAnimation)
        {
            owner.itemTime = Math.Max(owner.itemTime, 2);
            owner.itemAnimation = Math.Max(owner.itemAnimation, 2);
        }
        if (matchAnimation)
            owner.MatchItemTimeToItemAnimation();
    }

    public override void SetStaticDefaults()
    {
        ProjectileID.Sets.TrailCacheLength[Type] = 24;
        ProjectileID.Sets.TrailingMode[Type] = 2;
        // The proxy type can be used as a held projectile. This stable tModLoader set
        // prevents player gfxOffY from being applied twice to held-projectile drawing.
        ProjectileID.Sets.HeldProjDoesNotUsePlayerGfxOffY[Type] = true;
    }

    public override void SetDefaults()
    {
        Projectile.width = 12;
        Projectile.height = 12;
        Projectile.friendly = false;
        Projectile.hostile = false;
        Projectile.penetrate = 1;
        Projectile.timeLeft = 300;
        Projectile.tileCollide = false;
        Projectile.ignoreWater = false;
        Projectile.netImportant = false;
        Projectile.sentry = false;
    }

    internal void Configure(
        GeneratedItemData data,
        RuntimeEntitySpec entity,
        int childDepth,
        int remainingSpawnBudget,
        Vector2 initialDirection,
        bool preserveSyncedState = false,
        RuntimeSpawnBudget? activationBudget = null,
        bool ownsSpawnReservation = false)
    {
        int syncedTimeLeft = Projectile.timeLeft;
        int syncedBounces = _remainingBounces;
        int syncedActivationDelay = _activationDelayTicks;
        _data = data;
        _entity = entity;
        _generatedItemId = data.Id;
        _entityId = entity.Id;
        _childDepth = Math.Clamp(childDepth, 0, data.RuntimeProgram.Limits.MaxChildDepth);
        _remainingSpawnBudget = Math.Clamp(remainingSpawnBudget, 0, InfiniRuntimeLimits.MaxRuntimeActiveProjectilesPerOwner);
        // Only the firing peer owns the mutable ledger. ExtraAI is an observation,
        // never a grant of fresh event-spawn capacity on another network peer.
        if (activationBudget is not null)
            _activationSpawnBudget = activationBudget;
        else if (!preserveSyncedState && Projectile.owner >= 0 && Projectile.owner < Main.maxPlayers
            && Main.player[Projectile.owner] is { active: true } owner
            && InfiniRuntimeAuthority.ShouldRunLocalPlayerAction(owner))
            _activationSpawnBudget = new RuntimeSpawnBudget(_remainingSpawnBudget);
        else if (!preserveSyncedState)
            _activationSpawnBudget = null;
        bool localAuthority = Projectile.owner >= 0 && Projectile.owner < Main.maxPlayers
            && Main.player[Projectile.owner] is { active: true } budgetOwner
            && InfiniRuntimeAuthority.ShouldRunLocalPlayerAction(budgetOwner);
        if (!preserveSyncedState)
        {
            _spawnBudgetLease?.Release();
            _spawnBudgetLease = null;
            if (localAuthority && entity.Spawn.DescendantMaxActive is int cap)
            {
                // A free root has no ancestor occupancy. A nested declaration
                // adds a cap and cannot replace the incoming ancestor ledger.
                _activationSpawnBudget = new RuntimeSpawnBudget(cap, concurrent: true,
                    parent: childDepth > 0 ? activationBudget ?? _activationSpawnBudget : null);
            }
        }
        _initialDirection = initialDirection.SafeNormalize(Vector2.UnitX);
        _spawnCenter = Projectile.Center;
        _remainingBounces = entity.Collision.BounceCount;
        _activationDelayTicks = entity.Spawn.OverTarget.DelayTicks;
        if (!preserveSyncedState) {
            _beamManaClockStarted = false;
            _beamLastManaTick = 0;
            _vfxSourceToken=0;
            _presentationGeneration=new object();
            _presentationRetired=false;
            _vfxState = new InfiniVfxState { LocalSeed = data.VfxManifest.Seed,SourceKey=$"net:{Projectile.owner}:{VfxSourceToken()}:{data.Id}:{entity.Id}" };
        }
        else {
            if(_vfxState.LocalSeed==0)_vfxState.LocalSeed=data.VfxManifest.Seed;
            _vfxState.Tick=Math.Max(_vfxState.Tick,_age/Math.Max(1,Projectile.extraUpdates+1));
            if(_vfxState.SourceKey.Length==0)_vfxState.SourceKey=$"net:{Projectile.owner}:{VfxSourceToken()}:{data.Id}:{entity.Id}";
        }
        _configured = true;
        _pendingHydrationTicks = 0;
        ApplyEntityStats();
        if (!preserveSyncedState)
            Projectile.originalDamage = Projectile.damage;
        if (preserveSyncedState)
        {
            Projectile.timeLeft = Math.Max(1, syncedTimeLeft);
            _remainingBounces = Math.Clamp(syncedBounces, 0, entity.Collision.BounceCount);
            _activationDelayTicks = Math.Max(0, syncedActivationDelay);
            Projectile.friendly = _activationDelayTicks <= 0 && entity.Damage.Enabled && Projectile.damage > 0;
            Projectile.alpha = _activationDelayTicks > 0 ? 220 : 0;
        }
        _preserveSyncedStateOnHydrate = false;
        // Only fully configured native results convert a reservation to live
        // occupancy. A configuration exception leaves it available for refund.
        if (!preserveSyncedState && localAuthority && ownsSpawnReservation && activationBudget is not null)
        {
            RuntimeSpawnLease? lease = null;
            lease = activationBudget.TrackLive(Projectile,
                () => ReferenceEquals(_spawnBudgetLease, lease) && ReferenceEquals(Projectile.ModProjectile, this)
                    && Projectile.whoAmI >= 0 && Projectile.whoAmI < Main.projectile.Length
                    && ReferenceEquals(Main.projectile[Projectile.whoAmI], Projectile));
            _spawnBudgetLease = lease;
        }
    }

    private void ApplyEntityStats()
    {
        RuntimeEntitySpec entity = _entity!;
        Vector2 center = Projectile.Center;
        Projectile.width = entity.Hitbox.WidthPx;
        Projectile.height = entity.Hitbox.HeightPx;
        Projectile.Center = center;
        Projectile.scale = entity.Hitbox.DrawScale * entity.Visual.Scale;
        Projectile.hostile = false;
        // NewProjectileDirect owns initial damage/knockback (including event
        // multipliers); live/network state owns subsequent changes such as charge.
        // Hydrating entity metadata must not reset either to authored base stats.
        Projectile.DamageType = TerrariaRuntimeVocabulary.ResolveDamageClass(entity.Damage.DamageClass);
        Projectile.ownerHitCheck = entity.Damage.OwnerHitCheck;
        Projectile.penetrate = entity.Collision.Pierce;
        // Native Damage() uses maxPenetrate to decide whether owner NPC
        // immunity applies. Dynamic admission must update both initial fields.
        Projectile.maxPenetrate = entity.Collision.Pierce;
        Projectile.tileCollide = entity.Collision.TileCollide;
        Projectile.ignoreWater = entity.Collision.IgnoreWater;
        Projectile.extraUpdates = entity.Collision.ExtraUpdates;
        _activationDelayTicks = AuthoredTicksToProjectileUpdates(entity.Spawn.OverTarget.DelayTicks);
        Projectile.friendly = _activationDelayTicks == 0 && entity.Damage.Enabled && Projectile.damage > 0;
        Projectile.usesLocalNPCImmunity = entity.Collision.NpcImmunityMode == "local";
        Projectile.localNPCHitCooldown = Projectile.usesLocalNPCImmunity
            ? entity.Collision.LocalNpcHitCooldownTicks
            : -2;
        Projectile.netImportant = entity.IsOwnerAttached
            || entity.IsStationary
            || entity.NativeSentry == true
            || entity.Controller.Code != RuntimeControllerCode.None;
        Projectile.sentry = entity.NativeSentry == true;
        Projectile.timeLeft = Math.Max(1, AuthoredTicksToProjectileUpdates(entity.LifetimeTicks) + _activationDelayTicks);
        // Charging is a lifecycle phase, not an entity-kind collision policy.
        // Released peers retain their explicitly authored collision on hydration.
        if (entity.Controller.Code == RuntimeControllerCode.ChargeThenRelease && !_released)
            Projectile.tileCollide = false;
    }

    internal static int SpawnRuntimeEntity(
        GeneratedItemData data,
        string entityId,
        Player owner,
        IEntitySource source,
        Vector2 origin,
        Vector2 aimDirection,
        int childDepth,
        int remainingSpawnBudget,
        int? requestedCount = null,
        float? spreadOverride = null,
        float damageMultiplier = 1f,
        RuntimeSpawnBudget? activationBudget = null,
        int? rootDamageOverride = null,
        float? rootKnockbackOverride = null,
        float? rootSpeedOverride = null)
    {
        if (data is null || owner is null || !owner.active || !InfiniRuntimeAuthority.ShouldRunLocalPlayerAction(owner))
            return 0;
        if (rootSpeedOverride is float speed && (!float.IsFinite(speed) || speed < 0f))
            return 0;
        RuntimeEntitySpec? entity = data.RuntimeProgram.TryGetEntity(entityId);
        // Root binding shots are exempt from the EVENT budget but all roots from
        // that activation receive this same ledger for subsequent event actions.
        activationBudget ??= new RuntimeSpawnBudget(data.RuntimeProgram.Limits.MaxEventSpawnsPerActivation);
        if (entity is null || !entity.IsProjectileEntity || !entity.Spawn.Enabled)
            return 0;
        if (childDepth > data.RuntimeProgram.Limits.MaxChildDepth)
            return 0;
        if (remainingSpawnBudget <= 0)
            return 0;

        int spawned = 0;
        try
        {
            Vector2 cursor = Main.MouseWorld;
            Vector2 position = entity.Spawn.Placement switch
            {
                "owner_center" => owner.MountedCenter,
                "cursor" => cursor,
                "ground_at_cursor" => FindGroundAtCursor(cursor),
                "above_cursor" => cursor - Vector2.UnitY * Math.Max(16f, entity.Spawn.OverTarget.HeightTiles * 16f),
                "native_resting_spot" => NativeRestingSpot(owner, entity),
                _ => origin,
            };
            if (entity.Spawn.OverTarget.HeightTiles > 0f && entity.Spawn.Placement != "above_cursor")
                position -= Vector2.UnitY * entity.Spawn.OverTarget.HeightTiles * 16f;

            Vector2 baseDirection = entity.Spawn.Aim switch
            {
                "cursor" => (cursor - position).SafeNormalize(new Vector2(owner.direction, 0f)),
                "facing" => new Vector2(owner.direction, 0f),
                "velocity" => aimDirection.SafeNormalize(new Vector2(owner.direction, 0f)),
                "none" => Vector2.Zero,
                _ => aimDirection.SafeNormalize(new Vector2(owner.direction, 0f)),
            };
            if (baseDirection != Vector2.Zero)
                position += baseDirection * entity.Spawn.OffsetPx;

            int availableOwnerSlots = InfiniRuntimeLimits.MaxRuntimeActiveProjectilesPerOwner
                - CountActiveGeneratedProjectiles(owner.whoAmI);
            if (availableOwnerSlots <= 0)
                return 0;
            int count = Math.Clamp(
                requestedCount ?? entity.Spawn.Count,
                1,
                Math.Min(
                    availableOwnerSlots,
                    Math.Min(InfiniRuntimeLimits.MaxRuntimeSpawnCount, remainingSpawnBudget)));
            // Concurrency is explicit entity admission, independent of movement/type.
            // Refuse the effective whole batch; never clip an authored multi-shot batch.
            if (!CanAdmitEntityBatch(data, entity, owner.whoAmI, count))
                return 0;
            float spread = Math.Clamp(spreadOverride ?? entity.Spawn.SpreadRadians, 0f, MathHelper.TwoPi);
            for (int i = 0; i < count; i++)
            {
                float offset = count <= 1 ? 0f : MathHelper.Lerp(-spread * 0.5f, spread * 0.5f, i / (float)(count - 1));
                Vector2 direction = baseDirection == Vector2.Zero ? Vector2.Zero : baseDirection.RotatedBy(offset);
                Vector2 velocity = entity.IsStationary ? Vector2.Zero : direction * (rootSpeedOverride ?? entity.Spawn.SpeedPxPerTick);
                // A supplied value is final native shooting or explicitly selected
                // live-parent child combat; never repeat player/class modifiers.
                // Null retains the independently authored child lane.
                int damage = entity.Damage.Enabled
                    ? rootDamageOverride ?? Math.Max(0, (int)MathF.Round(entity.Damage.Damage * Math.Clamp(damageMultiplier, 0f, 10f)))
                    : 0;
                Projectile projectile = Projectile.NewProjectileDirect(
                    source,
                    position,
                    velocity,
                    ModContent.ProjectileType<GeneratedProjectile>(),
                    damage,
                    rootKnockbackOverride ?? entity.Damage.Knockback,
                    owner.whoAmI);
                if (!projectile.active || projectile.ModProjectile is not GeneratedProjectile generated)
                    continue;
                try
                {
                    generated.Configure(data, entity, childDepth, activationBudget.Remaining, direction == Vector2.Zero ? new Vector2(owner.direction, 0f) : direction,
                        activationBudget: activationBudget, ownsSpawnReservation: childDepth > 0);
                }
                catch
                {
                    // A failed configuration must not leave a partial actor
                    // outside its admission pool or execute terminal effects.
                    projectile.active = false;
                    throw;
                }
                projectile.netUpdate = true;
                spawned++;
                if (entity.NativeSentry == true) owner.UpdateMaxTurrets();
            }
        }
        catch
        {
            // The caller refunds normal refusals after the returned count. An
            // exception skips that path: return only reservations not attached
            // to successful hosts, then preserve the original failure.
            if (childDepth > 0) activationBudget.Return(remainingSpawnBudget - spawned);
            throw;
        }
        return spawned;
    }

    internal static bool CanAdmitEntityBatch(GeneratedItemData data, RuntimeEntitySpec entity, int ownerId, int count)
    {
        if (entity.Spawn.MaxActive is not int maximum) return true;
        int active = 0;
        foreach (Projectile projectile in Main.ActiveProjectiles)
            if (projectile.owner == ownerId && projectile.ModProjectile is GeneratedProjectile generated
                && generated.Matches(data.Id, entity.Id))
                active++;
        return count > 0 && active <= maximum - count;
    }

    internal static int CountActiveGeneratedProjectiles(int ownerId)
    {
        int count = 0;
        foreach (Projectile projectile in Main.ActiveProjectiles)
        {
            if (projectile.owner == ownerId && projectile.ModProjectile is GeneratedProjectile)
                count++;
        }
        return count;
    }

    private static Vector2 NativeRestingSpot(Player owner, RuntimeEntitySpec entity)
    {
        owner.FindSentryRestingSpot(ModContent.ProjectileType<GeneratedProjectile>(), out int x, out int y, out _);
        return new Vector2(x, y - entity.Hitbox.HeightPx * 0.5f);
    }

    private static Vector2 FindGroundAtCursor(Vector2 cursor)
    {
        Point tile = cursor.ToTileCoordinates();
        int x = Math.Clamp(tile.X, 1, Main.maxTilesX - 2);
        int y = Math.Clamp(tile.Y, 1, Main.maxTilesY - 2);
        for (int i = 0; i < 80 && y + i < Main.maxTilesY - 2; i++)
        {
            Tile t = Framing.GetTileSafely(x, y + i);
            if (t.HasTile && Main.tileSolid[t.TileType])
                return new Vector2(x * 16f + 8f, (y + i) * 16f - 4f);
        }
        return cursor;
    }

    private bool TryHydrate()
    {
        if (_configured) return true;
        _pendingHydrationTicks++;
        if (_generatedItemId.Length > 0 && _entityId.Length > 0)
        {
            var registry = global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems;
            if (registry is not null && registry.TryGet(_generatedItemId, out GeneratedItemData data))
            {
                RuntimeEntitySpec? entity = data.RuntimeProgram.TryGetEntity(_entityId);
                if (entity is not null)
                {
                    Configure(
                        data,
                        entity,
                        _childDepth,
                        _remainingSpawnBudget,
                        _initialDirection,
                        preserveSyncedState: _preserveSyncedStateOnHydrate);
                    return true;
                }
            }
            if (Main.netMode == NetmodeID.MultiplayerClient && _pendingHydrationTicks % 60 == 1)
                registry?.RequestOneFromServer(_generatedItemId, forceAssetRetry: false);
        }
        Projectile.friendly = false;
        Projectile.velocity = Vector2.Zero;
        Projectile.timeLeft = Math.Max(Projectile.timeLeft, 30);
        if (_pendingHydrationTicks > 600) Projectile.Kill();
        return false;
    }
}

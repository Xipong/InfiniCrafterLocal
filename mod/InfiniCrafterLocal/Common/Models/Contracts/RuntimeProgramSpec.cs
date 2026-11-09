#nullable enable
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.VFX;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json.Serialization;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Models;

/// <summary>
/// Finite, typed wire contract for the low-level Gameplay Author program.
/// Every gameplay decision below is explicit in the authored runtimeProgram.
/// C# validates/clamps engine limits and dispatches exact opcodes; it never
/// classifies an item from its name, category, tooltip, or a weapon family.
/// </summary>
public sealed class RuntimeProgramSpec
{
    public const string CurrentApiVersion = "infini.runtime-program.v5";
    public const string CurrentWireSchema = "infini.runtime-program.wire.v3";
    public const string ItemBodyOwner = "item_body";
    public const string ProjectileOwner = "projectile";

    public string ApiVersion { get; set; } = CurrentApiVersion;
    public string Schema { get; set; } = CurrentWireSchema;
    public string ItemEntityId { get; set; } = "";
    public string PrimaryEntityId { get; set; } = "";
    public string PrimaryOwner { get; set; } = "";
    public RuntimeLimitsSpec Limits { get; set; } = new();
    public RuntimeEntitySpec[] Entities { get; set; } = Array.Empty<RuntimeEntitySpec>();
    public RuntimeBindingSpec[] Bindings { get; set; } = Array.Empty<RuntimeBindingSpec>();
    public RuntimeItemUseSpec ItemUse { get; set; } = new();
    public RuntimeItemContactSpec ItemContact { get; set; } = new();
    private RuntimeItemEffectGroupSpec[]? _effectGroups;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public RuntimeItemEffectGroupSpec[]? EffectGroups
    {
        get => _effectGroups;
        set => _effectGroups = value is { Length: > 0 and <= 48 } ? value
            : throw new InvalidDataException("present effectGroups requires 1..48 named groups");
    }
    private string? _heldEffectGroupId;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? HeldEffectGroupId
    {
        get => _heldEffectGroupId;
        set => _heldEffectGroupId = RuntimeItemEffectGroupSpec.RequireId(value);
    }
    private RuntimeWeaponAmmoSpec? _weaponAmmo;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public RuntimeWeaponAmmoSpec? WeaponAmmo
    {
        get => _weaponAmmo;
        set => _weaponAmmo = value ?? throw new InvalidDataException("present weaponAmmo cannot be null");
    }

    public bool HasExecutableBinding => Bindings.Any(x => x is not null && RuntimeBindingSpec.IsActiveInput(x.Input));

    public void NormalizeAndValidate()
    {
        ApiVersion = (ApiVersion ?? "").Trim();
        Schema = (Schema ?? "").Trim();
        ItemEntityId = RuntimeText.Id(ItemEntityId);
        PrimaryEntityId = RuntimeText.Id(PrimaryEntityId);
        PrimaryOwner = (PrimaryOwner ?? "").Trim().ToLowerInvariant();
        if (!string.Equals(ApiVersion, CurrentApiVersion, StringComparison.Ordinal)
            || !string.Equals(Schema, CurrentWireSchema, StringComparison.Ordinal))
            throw new InvalidDataException($"Unsupported runtime program contract: {ApiVersion}/{Schema}");

        Limits ??= new RuntimeLimitsSpec();
        Limits.Normalize();
        Entities ??= Array.Empty<RuntimeEntitySpec>();
        Bindings ??= Array.Empty<RuntimeBindingSpec>();
        ItemUse ??= new RuntimeItemUseSpec();
        ItemContact ??= new RuntimeItemContactSpec();
        WeaponAmmo?.NormalizeAndValidate();
        if (WeaponAmmo is not null && !Bindings.Any(binding => binding is not null
                && RuntimeBindingSpec.IsActiveInput(binding.Input)
                && binding.UsePolicy?.Action?.Kind == RuntimeBindingAction.SpawnEntity))
            throw new InvalidDataException("weaponAmmo requires an active spawn_entity binding; passive hold is not a native ammo shot");
        if (Entities.Length < 1 || Entities.Length > Limits.MaxEntityCount)
            throw new InvalidDataException($"runtimeProgram.entities must contain 1..{Limits.MaxEntityCount} rows");
        if (Bindings.Length > InfiniRuntimeLimits.MaxRuntimeBindings)
            throw new InvalidDataException($"runtimeProgram.bindings exceeds {InfiniRuntimeLimits.MaxRuntimeBindings}");

        // Both reference adapters inspect original typed source fields before
        // retained v5 normalization can lowercase, clamp or default them.
        foreach (RuntimeEntitySpec? source in Entities)
        foreach (RuntimeEventActionSpec? action in source?.Events ?? Array.Empty<RuntimeEventActionSpec>())
        {
            if (action is null) continue;
            RuntimeEntitySpec? child = Entities.FirstOrDefault(row => row?.Id == action.EntityId);
            if (action.ActionCode == RuntimeEventActionCode.SpawnEntity && child?.Spawn is { } spawn
                && !spawn.AcceptsEmissionSpread(action.SpreadRadians))
                throw new InvalidDataException("radial/disk event emission requires exact neutral spread before normalization");
            if (action.ActionCode == RuntimeEventActionCode.SelectTargetsAndEmit
                && !RuntimeEventActionSpec.SupportsTargetEmission(child))
                throw new InvalidDataException("target emission requires the exact referenced spawn before normalization");
            if (action.HitTargetSpawn is not null
                && (source is null || !source.IsProjectileEntity || !RuntimeEventActionSpec.SupportsTargetEmission(child)))
                throw new InvalidDataException("target-relative emission requires exact source and referenced spawn before normalization");
        }

        var entityIds = new HashSet<string>(StringComparer.Ordinal);
        int itemBodies = 0;
        foreach (RuntimeEntitySpec? entity in Entities)
        {
            if (entity is null)
                throw new InvalidDataException("runtimeProgram.entities contains null");
            entity.NormalizeAndValidate(Limits);
            if (!entityIds.Add(entity.Id))
                throw new InvalidDataException($"duplicate runtime entity id '{entity.Id}'");
            if (entity.Kind == RuntimeEntityKind.ItemBody)
                itemBodies++;
        }
        RuntimeMotionAdmission.ValidateProgram(this);
        if (itemBodies != 1)
            throw new InvalidDataException("runtimeProgram must contain exactly one item_body");
        RuntimeEntitySpec? item = TryGetEntity(ItemEntityId);
        if (item is null || item.Kind != RuntimeEntityKind.ItemBody)
            throw new InvalidDataException("runtimeProgram.itemEntityId must reference item_body");
        RuntimeEntitySpec? primary = TryGetEntity(PrimaryEntityId);
        if (primary is null)
            throw new InvalidDataException("runtimeProgram.primaryEntityId must reference an entity");
        string expectedOwner = primary.Kind == RuntimeEntityKind.ItemBody ? ItemBodyOwner : ProjectileOwner;
        if (PrimaryOwner != expectedOwner)
            throw new InvalidDataException($"runtimeProgram.primaryOwner must be '{expectedOwner}' for primary entity '{PrimaryEntityId}'");

        var groupIds = new HashSet<string>(StringComparer.Ordinal);
        foreach (RuntimeItemEffectGroupSpec? group in EffectGroups ?? Array.Empty<RuntimeItemEffectGroupSpec>())
        {
            if (group is null) throw new InvalidDataException("effectGroups contains null");
            group.NormalizeAndValidate();
            if (!groupIds.Add(group.Id)) throw new InvalidDataException($"duplicate effect group '{group.Id}'");
        }
        var usedGroups = new HashSet<string>(StringComparer.Ordinal);
        var bindingIds = new HashSet<string>(StringComparer.Ordinal);
        var exclusiveInputs = new HashSet<string>(StringComparer.Ordinal);
        foreach (RuntimeBindingSpec? binding in Bindings)
        {
            if (binding is null)
                throw new InvalidDataException("runtimeProgram.bindings contains null");
            binding.NormalizeAndValidate();
            if (!bindingIds.Add(binding.Id))
                throw new InvalidDataException($"duplicate runtime binding id '{binding.Id}'");
            string bindingTarget = binding.UsePolicy.Action.TargetId;
            string bindingAction = binding.UsePolicy.Action.Kind;
            if (binding.UsePolicy.Action.EffectGroupId is string groupId)
            {
                if (!groupIds.Contains(groupId)) throw new InvalidDataException($"binding '{binding.Id}' selects missing effect group '{groupId}'");
                usedGroups.Add(groupId);
            }
            if (!entityIds.Contains(bindingTarget))
                throw new InvalidDataException($"binding '{binding.Id}' targets unknown entity '{bindingTarget}'");
            if (RuntimeBindingSpec.IsExclusiveInput(binding.Input) && !exclusiveInputs.Add(binding.Input))
                throw new InvalidDataException($"input '{binding.Input}' has multiple exclusive owners");
            RuntimeEntitySpec target = TryGetEntity(bindingTarget)!;
            if (!RuntimeBindingAction.IsAllowed(binding.Input, bindingAction))
                throw new InvalidDataException($"binding '{binding.Id}' cannot run action '{bindingAction}' from input '{binding.Input}'");
            if (bindingAction == RuntimeBindingAction.SpawnEntity)
            {
                if (!target.IsProjectileEntity)
                    throw new InvalidDataException($"binding '{binding.Id}' spawn_entity target must be a projectile entity");
                if (!RuntimeEntityKind.IsBindingSpawnable(target.Kind))
                    throw new InvalidDataException($"binding '{binding.Id}' cannot directly spawn entity kind '{target.Kind}'");
            }
            else if (target.Kind != RuntimeEntityKind.ItemBody)
            {
                throw new InvalidDataException($"binding '{binding.Id}' action '{bindingAction}' requires item_body target");
            }
            string expectedRole = bindingTarget == PrimaryEntityId ? RuntimeEntityRole.Primary : RuntimeEntityRole.Secondary;
            if (binding.Role != expectedRole)
                throw new InvalidDataException($"binding '{binding.Id}' role must be '{expectedRole}' for target '{bindingTarget}'");
        }

        if (HeldEffectGroupId is string heldId)
        {
            if (TryGetEffectGroup(heldId)?.IsGeneratedBuffOnly != true)
                throw new InvalidDataException("heldEffectGroupId must select a generated-buff-only group");
            usedGroups.Add(heldId);
        }
        foreach (RuntimeEntitySpec source in Entities)
        foreach (RuntimeEventActionSpec action in source.Events)
        {
            if (action.ActionCode != RuntimeEventActionCode.ApplyGeneratedBuff) continue;
            if (source.Kind != RuntimeEntityKind.ItemBody || action.EffectGroupId is not string groupId
                || TryGetEffectGroup(groupId)?.IsGeneratedBuffOnly != true)
                throw new InvalidDataException("generated-buff reaction requires an item-body source and exact generated-buff-only group");
            usedGroups.Add(groupId);
        }
        if (!groupIds.SetEquals(usedGroups))
            throw new InvalidDataException("every named effect group requires an exact active binding, held or equipment-reaction consumer");

        bool hasPlaceUse = Bindings.Any(x =>
            x is not null
            && x.Input is RuntimeInputKind.PrimaryUse or RuntimeInputKind.AlternateUse
            && x.UsePolicy.Action.Kind == RuntimeBindingAction.PlaceItem);
        bool hasNonPlaceActiveUse = Bindings.Any(x =>
            x is not null
            && x.Input is RuntimeInputKind.PrimaryUse or RuntimeInputKind.AlternateUse
            && x.UsePolicy.Action.Kind != RuntimeBindingAction.PlaceItem);
        if (hasPlaceUse && hasNonPlaceActiveUse)
        {
            bool everyPlaceIsAlternate = Bindings.All(x =>
                x is null
                || x.UsePolicy.Action.Kind != RuntimeBindingAction.PlaceItem
                || x.Input == RuntimeInputKind.AlternateUse);
            bool hasPrimaryNonPlace = Bindings.Any(x =>
                x is not null
                && x.Input == RuntimeInputKind.PrimaryUse
                && x.UsePolicy.Action.Kind != RuntimeBindingAction.PlaceItem);
            if (!everyPlaceIsAlternate || !hasPrimaryNonPlace)
                throw new InvalidDataException("hybrid placeable requires primary non-placement use and alternate placement");
        }
        else if (hasPlaceUse && Bindings.Any(x =>
            x is not null
            && x.UsePolicy.Action.Kind == RuntimeBindingAction.PlaceItem
            && x.Input != RuntimeInputKind.PrimaryUse))
        {
            throw new InvalidDataException("pure placeable requires primary placement");
        }

        ItemUse.Normalize();
        ItemContact.Normalize();
        bool hasActiveItemUse = Bindings.Any(x => x is not null && x.Input is RuntimeInputKind.PrimaryUse or RuntimeInputKind.AlternateUse);
        bool hasEmittingItemUse = Bindings.Any(x => x is not null
            && (x.Input == RuntimeInputKind.PrimaryUse || x.Input == RuntimeInputKind.AlternateUse)
            && x.UsePolicy.Action.Kind != RuntimeBindingAction.PlaceItem);
        bool hasItemContactBinding = Bindings.Any(x => x?.UsePolicy.ContactDamage == true);
        if (hasActiveItemUse && !ItemUse.Configured)
            throw new InvalidDataException("active primary/alternate binding requires explicit configure_item_use");

        var graph = new Dictionary<string, HashSet<string>>(StringComparer.Ordinal);
        int eventSpawnBudget = 0, primaryUseSpawnBudget = 0, alternateUseSpawnBudget = 0;
        foreach (RuntimeEntitySpec entity in Entities)
        {
            graph[entity.Id] = new HashSet<string>(StringComparer.Ordinal);
            foreach (RuntimeEventActionSpec action in entity.Events)
            {
                RuntimeEventKind.ValidateProducer(entity, action.Event, hasItemContactBinding, hasEmittingItemUse,
                    Bindings.Any(b => b.Input == RuntimeInputKind.Equipped && b.UsePolicy.Action.Kind == RuntimeBindingAction.EquipPassive));
                if (action.UseInput is not null
                    && (entity.Kind != RuntimeEntityKind.ItemBody || action.Event != RuntimeEventKind.OnUse))
                    throw new InvalidDataException("useInput is supported only on item_body on_use events");
                if (action.UseInput is not null && !Bindings.Any(b => RuntimeUseInputScope.Matches(action.UseInput, b.Input)
                    && b.UsePolicy.Action.Kind != RuntimeBindingAction.PlaceItem))
                    throw new InvalidDataException("useInput requires a matching non-placement active binding");
                if (action.ActionCode is RuntimeEventActionCode.SpawnEntity or RuntimeEventActionCode.SelectTargetsAndEmit)
                {
                    if (!entity.IsProjectileEntity
                        && (action.DamageBasis == RuntimeChildCombatBasis.LiveParent
                            || action.KnockbackBasis == RuntimeChildCombatBasis.LiveParent))
                        throw new InvalidDataException($"event '{action.Id}' live_parent combat requires a projectile source");
                    RuntimeEntitySpec? child = TryGetEntity(action.EntityId);
                    if (child is null || child.Kind == RuntimeEntityKind.ItemBody)
                        throw new InvalidDataException($"event '{action.Id}' references invalid entity '{action.EntityId}'");
                    if (action.HitTargetSpawn is not null
                        && (!entity.IsProjectileEntity || !RuntimeEventActionSpec.SupportsTargetEmission(child)))
                        throw new InvalidDataException($"event '{action.Id}' target-relative spawn requires a moving child with event-origin placement, velocity aim, zero offset and no over-target transform");
                    if (action.ActionCode == RuntimeEventActionCode.SelectTargetsAndEmit
                        && !RuntimeEventActionSpec.SupportsTargetEmission(child))
                        throw new InvalidDataException($"event '{action.Id}' requires an independent projectile with explicit origin/velocity spawn, zero offset and no over-target adapter");
                    graph[entity.Id].Add(child.Id);
                    int count = action.ActionCode == RuntimeEventActionCode.SelectTargetsAndEmit
                        ? action.StepCount!.Value : action.Count;
                    // Distinct accepted input uses start distinct ledgers. Only their
                    // immediate item on_use branches are mutually exclusive here;
                    // descendants, other events and both/legacy scopes remain shared.
                    if (entity.Kind == RuntimeEntityKind.ItemBody && action.Event == RuntimeEventKind.OnUse
                        && action.UseInput == RuntimeInputKind.PrimaryUse) primaryUseSpawnBudget += count;
                    else if (entity.Kind == RuntimeEntityKind.ItemBody && action.Event == RuntimeEventKind.OnUse
                        && action.UseInput == RuntimeInputKind.AlternateUse) alternateUseSpawnBudget += count;
                    else eventSpawnBudget += count;
                }
            }
            if (!string.IsNullOrWhiteSpace(entity.Targeting.ShotEntityId))
            {
                RuntimeEntitySpec? shot = TryGetEntity(entity.Targeting.ShotEntityId);
                if (shot is null || !shot.IsProjectileEntity)
                    throw new InvalidDataException($"entity '{entity.Id}' targets invalid shot entity '{entity.Targeting.ShotEntityId}'");
                graph[entity.Id].Add(shot.Id);
            }
            if (entity.Controller.Code == RuntimeControllerCode.TargetAndFire
                && string.IsNullOrWhiteSpace(entity.Targeting.ShotEntityId))
                throw new InvalidDataException($"entity '{entity.Id}' target_and_fire has no explicit shotEntityId");
            if (entity.Controller.Code == RuntimeControllerCode.TargetAndFire && entity.Targeting.IntervalTicks <= 0)
                throw new InvalidDataException($"entity '{entity.Id}' target_and_fire requires positive typed intervalTicks");
            if (entity.Controller.Code == RuntimeControllerCode.TargetAndFire
                && (entity.Targeting.DamageBasis is null || entity.Targeting.KnockbackBasis is null
                    || entity.Targeting.DamageMultiplier is null))
                throw new InvalidDataException($"entity '{entity.Id}' target_and_fire requires explicit damageBasis, knockbackBasis and damageMultiplier");
            if (entity.Controller.Code != RuntimeControllerCode.TargetAndFire
                && (entity.Targeting.DamageBasis is not null || entity.Targeting.KnockbackBasis is not null
                    || entity.Targeting.DamageMultiplier is not null))
                throw new InvalidDataException($"entity '{entity.Id}' child combat targeting fields require target_and_fire");
        }
        if (eventSpawnBudget + Math.Max(primaryUseSpawnBudget, alternateUseSpawnBudget) > Limits.MaxEventSpawnsPerActivation)
            throw new InvalidDataException("runtime event spawn budget exceeded");
        ValidateAcyclicBoundedGraph(graph, Limits.MaxChildDepth);
    }

    private static void ValidateAcyclicBoundedGraph(Dictionary<string, HashSet<string>> graph, int maxDepth)
    {
        var visiting = new HashSet<string>(StringComparer.Ordinal);
        var visited = new HashSet<string>(StringComparer.Ordinal);
        var depthByNode = new Dictionary<string, int>(StringComparer.Ordinal);
        int Visit(string node)
        {
            if (depthByNode.TryGetValue(node, out int cachedDepth))
                return cachedDepth;
            if (!visiting.Add(node))
                throw new InvalidDataException($"runtime entity event cycle at '{node}'");
            int depth = 0;
            foreach (string child in graph[node])
                depth = Math.Max(depth, 1 + Visit(child));
            visiting.Remove(node);
            visited.Add(node);
            if (depth > maxDepth)
                throw new InvalidDataException($"runtime entity graph depth {depth} exceeds {maxDepth}");
            depthByNode[node] = depth;
            return depth;
        }
        foreach (string node in graph.Keys)
            if (!visited.Contains(node))
                Visit(node);
    }

    public RuntimeEntitySpec? TryGetEntity(string? id)
    {
        if (string.IsNullOrWhiteSpace(id)) return null;
        string key = id.Trim();
        return Entities.FirstOrDefault(x => x is not null && string.Equals(x.Id, key, StringComparison.Ordinal));
    }

    public RuntimeBindingSpec? BindingForInput(string input)
        => Bindings.FirstOrDefault(x => x is not null && string.Equals(x.Input, input, StringComparison.Ordinal));

    public RuntimeItemEffectGroupSpec? TryGetEffectGroup(string? id)
        => id is null ? null : EffectGroups?.FirstOrDefault(x => x is not null && x.Id == id);
}

public sealed class RuntimeLimitsSpec
{
    public int MaxEntityCount { get; set; } = InfiniRuntimeLimits.MaxRuntimeEntities;
    public int MaxChildDepth { get; set; } = InfiniRuntimeLimits.MaxRuntimeChildDepth;
    public int MaxEventSpawnsPerActivation { get; set; } = InfiniRuntimeLimits.MaxRuntimeEventSpawns;

    public void Normalize()
    {
        MaxEntityCount = Math.Clamp(MaxEntityCount, 1, InfiniRuntimeLimits.MaxRuntimeEntities);
        MaxChildDepth = Math.Clamp(MaxChildDepth, 0, InfiniRuntimeLimits.MaxRuntimeChildDepth);
        MaxEventSpawnsPerActivation = Math.Clamp(MaxEventSpawnsPerActivation, 0, InfiniRuntimeLimits.MaxRuntimeEventSpawns);
    }
}

public static class RuntimeEntityKind
{
    public const string ItemBody = "item_body";
    public const string OwnerAttachedProjectile = "owner_attached_projectile";
    public const string FreeProjectile = "free_projectile";
    public const string StationaryProjectile = "stationary_projectile";
    public const string TemporaryHelper = "temporary_helper";
    public const string Field = "field";
    public const string ChildProjectile = "child_projectile";
    private static readonly HashSet<string> Known = new(StringComparer.Ordinal)
    {
        ItemBody, OwnerAttachedProjectile, FreeProjectile, StationaryProjectile,
        TemporaryHelper, Field, ChildProjectile,
    };
    public static bool IsKnown(string? value) => value is not null && Known.Contains(value);
    public static bool IsProjectile(string? value) => value is not null && value != ItemBody && Known.Contains(value);
    public static bool IsBindingSpawnable(string? value)
        => value is OwnerAttachedProjectile or FreeProjectile or StationaryProjectile or TemporaryHelper or Field;
    public static string VisualRoleFor(string? value)
        => value switch
        {
            ItemBody => "inventory_item",
            OwnerAttachedProjectile => "held_body",
            FreeProjectile => "projectile",
            StationaryProjectile => "deployed_entity",
            TemporaryHelper => "helper",
            Field => "field",
            ChildProjectile => "child_projectile",
            _ => "",
        };
}

public static class RuntimeInputKind
{
    public const string PrimaryUse = "primary_use";
    public const string AlternateUse = "alternate_use";
    public const string Hold = "hold";
    public const string Equipped = "equipped";
}

// Optional scopes retain absence in saved/network definitions; omitted means both.
public static class RuntimeUseInputScope
{
    public const string Both = "both";
    public static string Require(string? value)
        => value is RuntimeInputKind.PrimaryUse or RuntimeInputKind.AlternateUse or Both
            ? value : throw new InvalidDataException("use input scope must be primary_use, alternate_use or both");
    public static bool Matches(string? scope, string? input)
        => input is RuntimeInputKind.PrimaryUse or RuntimeInputKind.AlternateUse
            && (scope is null or Both || scope == input);
}

public static class RuntimeBindingAction
{
    public const string SpawnEntity = "spawn_entity";
    public const string UseItemBody = "use_item_body";
    public const string ApplyItemEffects = "apply_item_effects";
    public const string PlaceItem = "place_item";
    public const string EquipPassive = "equip_passive";
    public const string NativeFishing = "native_fishing";
    private static readonly HashSet<string> Known = new(StringComparer.Ordinal)
    {
        SpawnEntity, UseItemBody, ApplyItemEffects, PlaceItem, EquipPassive, NativeFishing,
    };
    public static bool IsKnown(string? value) => value is not null && Known.Contains(value);

    public static bool IsAllowed(string? input, string? action)
        => input switch
        {
            RuntimeInputKind.PrimaryUse
                => action is SpawnEntity or UseItemBody or ApplyItemEffects or PlaceItem or NativeFishing,
            RuntimeInputKind.AlternateUse
                => action is SpawnEntity or UseItemBody or ApplyItemEffects or PlaceItem or NativeFishing,
            RuntimeInputKind.Hold => action == SpawnEntity,
            RuntimeInputKind.Equipped => action == EquipPassive,
            _ => false,
        };
}

public static class RuntimeEventKind
{
    public const string OnUse = "on_use";
    public const string OnSpawn = "on_spawn";
    public const string OnHit = "on_hit";
    public const string OnCrit = "on_crit";
    public const string OnTileCollision = "on_tile_collision";
    public const string OnExpire = "on_expire";
    public const string OnKill = "on_kill";
    public const string Periodic = "periodic";
    public const string OnRelease = "on_release";
    public const string ChannelComplete = "channel_complete";
    public const string OnHurt = "on_hurt";
    public const string OnEnemyKill = "on_enemy_kill";
    public const string OnJump = "on_jump";
    private static readonly HashSet<string> Known = new(StringComparer.Ordinal)
    {
        OnUse, OnSpawn, OnHit, OnCrit, OnTileCollision, OnExpire, OnKill,
        Periodic, OnRelease, ChannelComplete, OnHurt, OnEnemyKill, OnJump,
    };
    public static bool IsKnown(string? value) => value is not null && Known.Contains(value);

    public static bool SupportsVfxAnchor(string eventName,string anchor)
        =>eventName!=OnJump||anchor is "self" or "owner" or "hitPoint" or "velocity" or "field";

    public static void ValidateProducer(RuntimeEntitySpec entity, string eventName, bool itemContactEnabled, bool hasActiveItemUse, bool hasEquipment = false, bool hasAirJump = false)
    {
        bool projectile = entity.IsProjectileEntity;
        bool sourceCompatible = eventName switch
        {
            OnUse or OnHurt or OnEnemyKill or OnJump => entity.Kind == RuntimeEntityKind.ItemBody,
            OnSpawn or OnTileCollision or OnExpire or OnKill or OnRelease or ChannelComplete => projectile,
            OnHit or OnCrit or Periodic => true,
            _ => false,
        };
        if (!sourceCompatible)
            throw new InvalidDataException($"entity '{entity.Id}' of kind '{entity.Kind}' cannot emit '{eventName}'");

        bool available = eventName switch
        {
            OnUse => hasActiveItemUse,
            OnHurt or OnEnemyKill => hasEquipment,
            OnJump => hasAirJump,
            OnHit or OnCrit => entity.Kind == RuntimeEntityKind.ItemBody ? itemContactEnabled : entity.Damage.Enabled,
            OnTileCollision => entity.Collision.TileCollide,
            OnRelease or ChannelComplete => entity.Charge is not null,
            OnSpawn or OnExpire or OnKill => projectile,
            Periodic => true,
            _ => false,
        };
        if (!available)
            throw new InvalidDataException($"entity '{entity.Id}' declares event '{eventName}' without an executable producer");
    }
}

public sealed class RuntimeBindingSpec
{
    public string Id { get; set; } = "";
    public string Input { get; set; } = "";
    public string Role { get; set; } = "";
    public RuntimeBindingUsePolicySpec UsePolicy { get; set; } = new();

    public void NormalizeAndValidate()
    {
        Id = RuntimeText.Id(Id);
        Input = (Input ?? "").Trim().ToLowerInvariant();
        Role = (Role ?? "").Trim().ToLowerInvariant();
        if (!IsActiveInput(Input))
            throw new InvalidDataException($"unknown runtime input '{Input}'");
        if (!RuntimeEntityRole.IsKnown(Role))
            throw new InvalidDataException($"unknown runtime binding role '{Role}'");
        UsePolicy ??= new RuntimeBindingUsePolicySpec();
        UsePolicy.NormalizeAndValidate(Input);
    }

    public static bool IsActiveInput(string? input)
        => input is RuntimeInputKind.PrimaryUse or RuntimeInputKind.AlternateUse or RuntimeInputKind.Hold or RuntimeInputKind.Equipped;
    public static bool IsExclusiveInput(string? input)
        => input is RuntimeInputKind.PrimaryUse or RuntimeInputKind.AlternateUse or RuntimeInputKind.Hold;
}

public sealed class RuntimeBindingUsePolicySpec
{
    public RuntimeBindingActionSpec Action { get; set; } = new();
    public int StackCost { get; set; }
    public bool ContactDamage { get; set; }
    private int? _stackConsumeChancePercent;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? StackConsumeChancePercent
    {
        get => _stackConsumeChancePercent;
        set
        {
            if (value is null || value < 0 || value > 100)
                throw new InvalidDataException("stackConsumeChancePercent must be an explicit integer 0..100");
            _stackConsumeChancePercent = value;
        }
    }

    public void NormalizeAndValidate(string input)
    {
        Action ??= new RuntimeBindingActionSpec();
        Action.NormalizeAndValidate();
        if (StackCost is not (0 or 1))
            throw new InvalidDataException("binding usePolicy.stackCost must be exactly 0 or 1");
        if (StackConsumeChancePercent is int chance
            && (chance < 0 || chance > 100 || StackCost != 1
                || input is not (RuntimeInputKind.PrimaryUse or RuntimeInputKind.AlternateUse)
                || Action.Kind == RuntimeBindingAction.PlaceItem))
            throw new InvalidDataException("stackConsumeChancePercent requires 0..100 and an active non-placement stackCost=1 binding");
        if (Action.Kind == RuntimeBindingAction.NativeFishing
            && (input is not (RuntimeInputKind.PrimaryUse or RuntimeInputKind.AlternateUse) || StackCost != 0 || ContactDamage))
            throw new InvalidDataException("native_fishing requires primary_use or alternate_use, stackCost=0 and contactDamage=false; native bait owns consumption");
        if (Action.Kind == RuntimeBindingAction.PlaceItem)
        {
            if (StackCost != 1)
                throw new InvalidDataException("place_item requires stackCost=1");
            if (ContactDamage)
                throw new InvalidDataException("place_item cannot deal contact damage");
        }
        if (input is not (RuntimeInputKind.PrimaryUse or RuntimeInputKind.AlternateUse)
            && (StackCost != 0 || ContactDamage))
            throw new InvalidDataException("non-use binding requires stackCost=0 and contactDamage=false");
    }
}

public sealed class RuntimeBindingActionSpec
{
    public string Kind { get; set; } = "";
    public string TargetId { get; set; } = "";
    public RuntimePlacementSpec? Placement { get; set; }
    public RuntimeFishingSpec? Fishing { get; set; }
    private string? _effectGroupId;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? EffectGroupId
    {
        get => _effectGroupId;
        set => _effectGroupId = RuntimeItemEffectGroupSpec.RequireId(value);
    }

    public void NormalizeAndValidate()
    {
        Kind = (Kind ?? "").Trim().ToLowerInvariant();
        TargetId = RuntimeText.Id(TargetId);
        if (!RuntimeBindingAction.IsKnown(Kind))
            throw new InvalidDataException($"unknown runtime binding action '{Kind}'");
        if (Kind == RuntimeBindingAction.NativeFishing)
        {
            if (Fishing is null) throw new InvalidDataException("native_fishing requires an exact fishing payload");
            Fishing.Validate();
        }
        else if (Fishing is not null)
            throw new InvalidDataException("only native_fishing may carry a fishing payload");
        if (EffectGroupId is not null && Kind != RuntimeBindingAction.ApplyItemEffects)
            throw new InvalidDataException("only apply_item_effects may select an effectGroupId");
        if (Kind == RuntimeBindingAction.PlaceItem)
        {
            if (Placement is null)
                throw new InvalidDataException("place_item requires an exact placement payload");
            Placement.NormalizeAndValidate();
        }
        else if (Placement is not null)
        {
            throw new InvalidDataException("only place_item may carry a placement payload");
        }
    }
}

// Native Terraria fishing owns the wooden bobber, line, bait, bite and catch lifecycle.
// These values configure casting, not a generated projectile or authored catch table.
public sealed class RuntimeFishingSpec
{
    public int Power { get; set; }
    public float CastSpeedPxPerTick { get; set; }

    public void Validate()
    {
        if (Power is < 1 or > 1000)
            throw new InvalidDataException("fishing power must be 1..1000");
        if (!float.IsFinite(CastSpeedPxPerTick) || CastSpeedPxPerTick <= 0f || CastSpeedPxPerTick > 64f)
            throw new InvalidDataException("fishing castSpeedPxPerTick must be finite and >0..64");
    }
}

public sealed class RuntimePlacementSpec
{
    public int TileId { get; set; } = -1;
    public int WallId { get; set; } = -1;
    public int PlaceStyle { get; set; }
    private RuntimeOwnedTileSpec? _ownedTile;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public RuntimeOwnedTileSpec? OwnedTile
    {
        get => _ownedTile;
        set => _ownedTile = value ?? throw new InvalidDataException("present ownedTile cannot be null");
    }
    private RuntimePlacedBodySpec? _placedBody;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public RuntimePlacedBodySpec? PlacedBody
    {
        get => _placedBody;
        set => _placedBody = value ?? throw new InvalidDataException("present placedBody cannot be null");
    }

    [JsonIgnore] internal bool HasPlacedFootprint => OwnedTile is not null || PlacedBody is not null || PlacedLight is not null || PlacedVfx is not null;

    private RuntimePlacedVfxSpec? _placedVfx;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public RuntimePlacedVfxSpec? PlacedVfx
    {
        get => _placedVfx;
        set => _placedVfx = value ?? throw new InvalidDataException("present placedVfx cannot be null");
    }

    private RuntimePlacedLightSpec? _placedLight;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public RuntimePlacedLightSpec? PlacedLight
    {
        get => _placedLight;
        set => _placedLight = value ?? throw new InvalidDataException("present placedLight cannot be null");
    }

    public void NormalizeAndValidate()
    {
        if (TileId < -1 || TileId >= TileLoader.TileCount)
            throw new InvalidDataException($"tile ID {TileId} is not loaded");
        if (WallId < -1 || WallId >= WallLoader.WallCount)
            throw new InvalidDataException($"wall ID {WallId} is not loaded");
        if ((TileId >= 0 ? 1 : 0) + (WallId >= 0 ? 1 : 0) + (OwnedTile is not null ? 1 : 0) != 1)
            throw new InvalidDataException("placement must select exactly one native tile, wall or owned tile");
        if (OwnedTile is not null)
        {
            OwnedTile.Validate();
            if (PlaceStyle != 0) throw new InvalidDataException("owned tile has only style zero");
            if (PlacedBody is null) throw new InvalidDataException("owned tile requires explicit placedBody");
        }
        if (PlaceStyle is < 0 or > 1000)
            throw new InvalidDataException("placement style must be 0..1000");
        if (PlacedVfx is not null)
        {
            if (TileId < 0 && OwnedTile is null || WallId >= 0)
                throw new InvalidDataException("placedVfx requires exact tile-only placement");
            PlacedVfx.Validate();
        }
        if (PlacedLight is not null)
        {
            if (TileId < 0 && OwnedTile is null || WallId >= 0)
                throw new InvalidDataException("placedLight requires exact tile-only placement");
            PlacedLight.Validate();
        }
        if (PlacedBody is not null)
        {
            if (OwnedTile is null || TileId != -1 || WallId != -1)
                throw new InvalidDataException("placedBody requires explicit owned tile placement; native tile art is not replaced");
            PlacedBody.Validate();
        }
    }
}

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed class RuntimeOwnedTileSpec
{
    [JsonRequired] public int Width { get; init; }
    [JsonRequired] public int Height { get; init; }
    [JsonRequired] public string Collision { get; init; } = null!;
    [JsonRequired] public string Support { get; init; } = null!;
    [JsonIgnore] internal string Key => FormattableString.Invariant($"GeneratedOwned_{Width}x{Height}_{Collision}_{Support}");
    public void Validate()
    {
        if (Width is < 1 or > 16 || Height is < 1 or > 16
            || Collision is not ("open" or "solid") || Support is not ("floor" or "wall" or "unanchored"))
            throw new InvalidDataException("owned tile requires explicit bounded width/height, collision and support");
    }
}

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed class RuntimePlacedVfxSpec
{
    [JsonRequired] public int MinFrameY { get; init; }
    [JsonRequired] public int MaxFrameY { get; init; }
    public void Validate()
    {
        if (MinFrameY is < 0 or > 32767 || MaxFrameY is < 0 or > 32767 || MinFrameY > MaxFrameY)
            throw new InvalidDataException("placedVfx requires ordered inclusive native TileFrameY bounds 0..32767");
    }
}

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed class RuntimePlacedLightSpec
{
    public sealed class StrengthJsonConverter : JsonConverter<double>
    {
        private static readonly RawJsonFloatDomain Domain = new("0.01", "1.5", null);
        public override bool HandleNull => true;
        public override double Read(ref System.Text.Json.Utf8JsonReader reader, Type type, System.Text.Json.JsonSerializerOptions options)
            => Domain.ReadDouble(ref reader);
        public override void Write(System.Text.Json.Utf8JsonWriter writer, double value, System.Text.Json.JsonSerializerOptions options)
        {
            if (!double.IsFinite(value) || value is < 0.01 or > 1.5) throw new System.Text.Json.JsonException("placed light strength out of domain");
            writer.WriteNumberValue(value);
        }
    }

    [JsonRequired, JsonConverter(typeof(StrengthJsonConverter))] public double Strength { get; init; }
    [JsonRequired] public string Color { get; init; } = null!;

    public void Validate()
    {
        if (!double.IsFinite(Strength) || Strength is < 0.01 or > 1.5
            || string.IsNullOrEmpty(Color) || RuntimeColorPolicy.NormalizeRequired(Color) != Color)
            throw new InvalidDataException("placedLight requires explicit bounded strength and exact color");
    }
}

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed class RuntimePlacedBodySpec
{
    [JsonRequired] public int RenderSizePx { get; init; }
    [JsonRequired] public double FootprintAnchorX { get; init; }
    [JsonRequired] public double FootprintAnchorY { get; init; }
    private string? _pivotSpace;
    // Omission retains historical full-frame semantics; explicit null is invalid.
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? PivotSpace
    {
        get => _pivotSpace;
        init
        {
            if (value is not ("frame" or "alpha_bounds"))
                throw new InvalidDataException("placedBody pivotSpace must be frame or alpha_bounds");
            _pivotSpace = value;
        }
    }
    [JsonRequired] public double ImagePivotX { get; init; }
    [JsonRequired] public double ImagePivotY { get; init; }
    [JsonRequired] public int OffsetXPx { get; init; }
    [JsonRequired] public int OffsetYPx { get; init; }
    [JsonRequired] public double RotationDegrees { get; init; }
    [JsonRequired] public bool FlipX { get; init; }
    [JsonRequired] public bool FlipY { get; init; }

    public void Validate()
    {
        static bool Unit(double value) => double.IsFinite(value) && value >= 0 && value <= 1;
        if (RenderSizePx is < 1 or > 512 || !Unit(FootprintAnchorX) || !Unit(FootprintAnchorY)
            || !Unit(ImagePivotX) || !Unit(ImagePivotY) || OffsetXPx is < -512 or > 512
            || OffsetYPx is < -512 or > 512 || !double.IsFinite(RotationDegrees)
            || RotationDegrees is < -180 or > 180)
            throw new InvalidDataException("placedBody transform is outside explicit accepted bounds");
    }
}

public static class RuntimeEntityRole
{
    public const string Primary = "primary";
    public const string Secondary = "secondary";

    public static bool IsKnown(string? value) => value is Primary or Secondary;
}

public sealed partial class RuntimeEntitySpec
{
    private bool? _nativeSentry;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public bool? NativeSentry
    {
        get => _nativeSentry;
        set => _nativeSentry = value ?? throw new InvalidDataException("nativeSentry must be an explicit boolean when present");
    }
    public string Id { get; set; } = "";
    public string Kind { get; set; } = "";
    public string VisualRole { get; set; } = "";
    public RuntimeEntityVisualSpec Visual { get; set; } = new();
    public RuntimeSpawnSpec Spawn { get; set; } = new();
    public RuntimeDamageSpec Damage { get; set; } = new();
    public int LifetimeTicks { get; set; } = 1;
    public RuntimeHitboxSpec Hitbox { get; set; } = new();
    private RuntimeHitboxCurveSpec? _hitboxCurve;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public RuntimeHitboxCurveSpec? HitboxCurve
    {
        get => _hitboxCurve;
        set => _hitboxCurve = value ?? throw new InvalidDataException("present hitboxCurve cannot be null");
    }
    private RuntimeTurnModifierSpec? _turnModifier;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public RuntimeTurnModifierSpec? TurnModifier { get => _turnModifier; set => _turnModifier = value ?? throw new InvalidDataException("present turnModifier cannot be null"); }
    private RuntimeHomingModifierSpec? _homingModifier;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public RuntimeHomingModifierSpec? HomingModifier { get => _homingModifier; set => _homingModifier = value ?? throw new InvalidDataException("present homingModifier cannot be null"); }
    private RuntimeNpcAttractionSpec? _npcAttraction;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public RuntimeNpcAttractionSpec? NpcAttraction { get => _npcAttraction; set => _npcAttraction = value ?? throw new InvalidDataException("present npcAttraction cannot be null"); }
    private RuntimeVisualScaleCurveSpec? _visualScaleCurve;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public RuntimeVisualScaleCurveSpec? VisualScaleCurve { get => _visualScaleCurve; set => _visualScaleCurve = value ?? throw new InvalidDataException("present visualScaleCurve cannot be null"); }
    public RuntimeCollisionSpec Collision { get; set; } = new();
    public RuntimeMovementSpec Movement { get; set; } = new();
    public RuntimeControllerSpec Controller { get; set; } = new();
    public RuntimeTargetingSpec Targeting { get; set; } = new();
    public RuntimeLightSpec Light { get; set; } = new();
    public RuntimeEventActionSpec[] Events { get; set; } = Array.Empty<RuntimeEventActionSpec>();

    public bool IsProjectileEntity => RuntimeEntityKind.IsProjectile(Kind);
    public bool IsOwnerAttached => Kind == RuntimeEntityKind.OwnerAttachedProjectile;
    public bool IsStationary => Kind is RuntimeEntityKind.StationaryProjectile or RuntimeEntityKind.Field or RuntimeEntityKind.TemporaryHelper;
    [JsonIgnore]
    public bool UsesInitialVelocity => !IsStationary || HasMotionPositionDriver
        || Controller.Code == RuntimeControllerCode.TargetAndFire && Movement.IsConfigured;

    public void NormalizeAndValidate(RuntimeLimitsSpec limits)
    {
        Id = RuntimeText.Id(Id);
        Kind = (Kind ?? "").Trim().ToLowerInvariant();
        VisualRole = RuntimeText.Safe(VisualRole, 64);
        if (!RuntimeEntityKind.IsKnown(Kind))
            throw new InvalidDataException($"unknown runtime entity kind '{Kind}'");
        Visual ??= new RuntimeEntityVisualSpec();
        Spawn ??= new RuntimeSpawnSpec();
        Damage ??= new RuntimeDamageSpec();
        Hitbox ??= new RuntimeHitboxSpec();
        Collision ??= new RuntimeCollisionSpec();
        Movement ??= new RuntimeMovementSpec();
        Controller ??= new RuntimeControllerSpec();
        Targeting ??= new RuntimeTargetingSpec();
        Light ??= new RuntimeLightSpec();
        Events ??= Array.Empty<RuntimeEventActionSpec>();
        if (Events.Length > InfiniRuntimeLimits.MaxRuntimeEventsPerEntity)
            throw new InvalidDataException($"entity '{Id}' has too many event actions");

        ValidateMotionComponents();
        Visual.Normalize();
        if (Visual.AssetMode == "runtime_geometry" && Visual.Geometry is null)
            throw new InvalidDataException("runtime_geometry presentation requires explicit body geometry");
        if (Visual.Geometry is { } geometry)
        {
            if (Kind == RuntimeEntityKind.ItemBody || Visual.AssetMode != "runtime_geometry")
                throw new InvalidDataException("Body geometry belongs only to non-item runtime_geometry presentation");
            if (geometry.Axis == "aim" && Aim is null)
                throw new InvalidDataException("Body geometry aim axis requires entity aim");
            if (geometry.Source == "collision_path" && BeamGeometry is null && LashGeometry is null)
                throw new InvalidDataException("Collision path presentation requires beam or lash geometry");
        }
        // New metadata has exactly one texture owner. Alias/item-body rows may
        // not create a second authority; absent fields remain saved-v5 compatible.
        if ((Visual.Grip is not null || Visual.RenderSizePx.HasValue || Visual.PreferredCanvasSize.HasValue || Visual.ForwardAngleDegrees.HasValue)
            && (Kind == RuntimeEntityKind.ItemBody || Visual.AssetMode != "baked_sprite"))
            throw new InvalidDataException($"entity '{Id}' presentation size/canvas/axis belongs only to a distinct baked body");
        string expectedVisualRole = RuntimeEntityKind.VisualRoleFor(Kind);
        if (!string.Equals(VisualRole, expectedVisualRole, StringComparison.Ordinal)
            || !string.Equals(Visual.Role, expectedVisualRole, StringComparison.Ordinal))
            throw new InvalidDataException($"entity '{Id}' visual roles must equal '{expectedVisualRole}' for kind '{Kind}'");
        if (Targeting.HasVolleyOptions && (Controller.Code != RuntimeControllerCode.TargetAndFire
            || Kind is not (RuntimeEntityKind.StationaryProjectile or RuntimeEntityKind.TemporaryHelper or RuntimeEntityKind.FreeProjectile or RuntimeEntityKind.ChildProjectile)))
            throw new InvalidDataException("targeting options require the explicit target_and_fire owner");
        Movement.NormalizeAndValidate(Kind);
        Controller.NormalizeAndValidate(Kind);
        if (Kind == RuntimeEntityKind.ItemBody)
        {
            if (Spawn.Enabled || Spawn.MaxActive.HasValue || Spawn.DescendantMaxActive.HasValue || NativeSentry.HasValue
                || Damage.Enabled || Movement.IsConfigured || Controller.IsConfigured || HitboxCurve is not null
                || TurnModifier is not null || HomingModifier is not null || NpcAttraction is not null || VisualScaleCurve is not null)
                throw new InvalidDataException($"item_body '{Id}' cannot carry projectile components");
        }
        else
        {
            Spawn.Normalize();
            Damage.Normalize();
            if (LifetimeTicks > InfiniRuntimeLimits.MaxRuntimeLifetimeTicks)
                throw new InvalidDataException($"entity '{Id}' lifetime exceeds {InfiniRuntimeLimits.MaxRuntimeLifetimeTicks} world ticks");
            LifetimeTicks = Math.Clamp(LifetimeTicks, 1, InfiniRuntimeLimits.MaxRuntimeLifetimeTicks);
            Hitbox.Normalize();
            Collision.Normalize();
            if (Spawn.VelocityDistribution is not null
                && (IsStationary && !HasMotionPositionDriver))
                throw new InvalidDataException($"entity '{Id}' does not execute sampled initial velocity");
            TurnModifier?.Validate(); HomingModifier?.Validate();
            NpcAttraction?.Validate(); VisualScaleCurve?.Validate();
            if ((TurnModifier is not null || HomingModifier is not null)
                && (Kind is not (RuntimeEntityKind.FreeProjectile or RuntimeEntityKind.ChildProjectile) && !HasMotionPositionDriver
                    || Controller.Code is not (RuntimeControllerCode.None or RuntimeControllerCode.TargetAndFire) || !(Movement.IsConfigured || HasMotionPositionDriver)))
                throw new InvalidDataException("velocity modifiers require a free/child projectile with explicit movement ownership");
            if (VisualScaleCurve is not null && (HitboxCurve?.MirrorToSprite == true))
                throw new InvalidDataException("dynamic sprite scale has exactly one authored owner and excludes special beam/whip line geometry");
            if (HitboxCurve is { } curve)
            {
                curve.Validate();
                if (curve.MirrorToSprite && VisualScaleCurve is not null)
                    throw new InvalidDataException("hitboxCurve cannot coexist with beam/whip collision or a second mirrored sprite-scale owner");
            }
            bool requiresPositionDriver = Kind is RuntimeEntityKind.OwnerAttachedProjectile or RuntimeEntityKind.FreeProjectile or RuntimeEntityKind.ChildProjectile;
            if (requiresPositionDriver && !Movement.IsConfigured && !HasMotionPositionDriver)
                throw new InvalidDataException($"projectile entity '{Id}' requires explicit movement or a position-owning controller");
            Targeting.Normalize();
            Light.Normalize();
            if (!Spawn.Enabled)
                throw new InvalidDataException($"projectile entity '{Id}' has no explicit spawn component");
        }
        var eventIds = new HashSet<string>(StringComparer.Ordinal);
        foreach (RuntimeEventActionSpec? action in Events)
        {
            if (action is null)
                throw new InvalidDataException($"entity '{Id}' contains null event action");
            action.NormalizeAndValidate();
            if (!eventIds.Add(action.Id))
                throw new InvalidDataException($"duplicate event action id '{action.Id}' on '{Id}'");
        }
    }

    public RuntimeEventActionSpec[] ActionsFor(string eventName)
        => Events.Where(x => x is not null && string.Equals(x.Event, eventName, StringComparison.Ordinal)).ToArray();
}

public sealed class RuntimeEntityVisualSpec
{
    private RuntimeBodyGeometrySpec? geometry;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public RuntimeBodyGeometrySpec? Geometry {
        get => geometry;
        set => geometry = value ?? throw new InvalidDataException("entity.visual.geometry must be an object when present");
    }
    private ItemGripSpec? _grip;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public ItemGripSpec? Grip {
        get => _grip;
        set => _grip = value ?? throw new InvalidDataException("entity.visual.grip must be an object when present");
    }
    private int? renderSizePx;
    private float? forwardAngleDegrees;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? RenderSizePx
    {
        get => renderSizePx;
        set => renderSizePx = SpritePresentation.RequireRenderSize(value);
    }
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    [JsonConverter(typeof(SpritePresentation.ForwardAngleJsonConverter))]
    public float? ForwardAngleDegrees
    {
        get => forwardAngleDegrees;
        set => forwardAngleDegrees = SpritePresentation.RequireForwardAngle(value);
    }
    private int? preferredCanvasSize;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? PreferredCanvasSize
    {
        get => preferredCanvasSize;
        set => preferredCanvasSize = value is 24 or 32 or 48 or 64 or 96 or 128
            ? value : throw new InvalidDataException("entity.visual.preferredCanvasSize must be 24/32/48/64/96/128 when present");
    }

    public string Role { get; set; } = "";
    public string AssetMode { get; set; } = "";
    public string Prompt { get; set; } = "";
    public string Silhouette { get; set; } = "";
    public string VisualIdentity { get; set; } = "";
    public float Scale { get; set; } = 1f;
    public string SpritePath { get; set; } = "";
    public string SpriteUrl { get; set; } = "";
    public string SpriteStatus { get; set; } = "";
    public float SpriteTechnicalScore { get; set; } = 0f;

    // A retained PNG is not proof that its selected producer completed. Keep
    // root/body/overlay consumers on the same declared completion domain.
    internal static bool HasCompletedPngProducer(string? status)
        => status is "generated" or "generated_warn_invalid";

    public void Normalize()
    {
        Grip?.Validate();
        Geometry?.Validate();
        Role = RuntimeText.Safe(Role, 64);
        AssetMode = RuntimeText.Safe(AssetMode, 32).ToLowerInvariant();
        Prompt = RuntimeText.Prose(Prompt, 1400);
        Silhouette = RuntimeText.Prose(Silhouette, 700);
        VisualIdentity = RuntimeText.Prose(VisualIdentity, 700);
        Scale = Math.Clamp(Scale <= 0f ? 1f : Scale, 0.25f, 4f);
        SpritePath = RuntimeText.Safe(SpritePath, 260);
        SpriteUrl = RuntimeText.Safe(SpriteUrl, 500);
        SpriteStatus = RuntimeText.Safe(SpriteStatus, 48).ToLowerInvariant();
        SpriteTechnicalScore = Math.Clamp(SpriteTechnicalScore, 0f, 1f);
        if (AssetMode == "baked_sprite" && (string.IsNullOrWhiteSpace(SpritePath) || !HasCompletedPngProducer(SpriteStatus)))
            throw new InvalidDataException("required baked runtime sprite is unavailable");
        if (AssetMode is not ("baked_sprite" or "reuse_item_icon" or "runtime_geometry" or "no_asset"))
            throw new InvalidDataException($"unknown entity assetMode '{AssetMode}'");
    }
}

public sealed class RuntimeSpawnSpec
{
    public bool Enabled { get; set; }
    public float SpeedPxPerTick { get; set; }
    public int Count { get; set; } = 1;
    private int? _maxActive;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? MaxActive
    {
        get => _maxActive;
        set
        {
            if (value is null || value < 1 || value > InfiniRuntimeLimits.MaxRuntimeActiveProjectilesPerOwner)
                throw new InvalidDataException("spawn.maxActive must be an explicit integer from 1 to the owner projectile ceiling");
            _maxActive = value;
        }
    }
    private int? _descendantMaxActive;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? DescendantMaxActive
    {
        get => _descendantMaxActive;
        set
        {
            if (value is null || value < 1 || value > InfiniRuntimeLimits.MaxRuntimeActiveProjectilesPerOwner)
                throw new InvalidDataException("spawn.descendantMaxActive must be an explicit integer from 1 to the owner projectile ceiling");
            _descendantMaxActive = value;
        }
    }
    public float SpreadRadians { get; set; }
    private int _offsetPx;
    private string _aim = "cursor", _placement = "item_use_origin";
    private bool _offsetPresent, _aimPresent, _placementPresent;
    public int OffsetPx { get => _offsetPx; set { _offsetPx = value; _offsetPresent = true; } }
    public string Aim { get => _aim; set { _aim = value; _aimPresent = true; } }
    public string Placement { get => _placement; set { _placement = value; _placementPresent = true; } }
    public RuntimeOverTargetSpec OverTarget { get; set; } = new();
    private RuntimeSpawnVelocitySpec? _velocityDistribution;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public RuntimeSpawnVelocitySpec? VelocityDistribution
    {
        get => _velocityDistribution;
        set => _velocityDistribution = value ?? throw new InvalidDataException("present spawn.velocityDistribution cannot be null");
    }

    internal bool HasExactTargetEmissionOrigin()
        => _offsetPresent && _aimPresent && _placementPresent && Enabled
            && Placement == "item_use_origin" && Aim == "velocity" && OffsetPx == 0
            && OverTarget is not null && OverTarget.HeightTiles == 0f && OverTarget.DelayTicks == 0;

    internal bool AcceptsEmissionSpread(float spread)
        => VelocityDistribution?.Kind is not ("radial" or "disk") || spread == 0f;

    public void Normalize()
    {
        if (VelocityDistribution is { } distribution)
        {
            distribution.Validate();
            if (SpeedPxPerTick != 0f)
                throw new InvalidDataException("sampled velocity requires the exact inactive constant-speed wire slot 0");
            if (distribution.Kind is "fan_speed" or "cone" && Aim is not ("cursor" or "facing" or "velocity"))
                throw new InvalidDataException("directional sampled velocity requires an explicit aim axis");
            if (distribution.Kind is "radial" or "disk" && SpreadRadians != 0f)
                throw new InvalidDataException("radial/disk velocity requires exact neutral deterministic spread 0");
        }
        SpeedPxPerTick = Math.Clamp(SpeedPxPerTick, 0f, 80f);
        Count = Math.Clamp(Count, 1, InfiniRuntimeLimits.MaxRuntimeSpawnCount);
        SpreadRadians = Math.Clamp(SpreadRadians, 0f, MathF.Tau);
        OffsetPx = Math.Clamp(OffsetPx, -128, 256);
        Aim = RuntimeText.Safe(Aim, 32).ToLowerInvariant();
        Placement = RuntimeText.Safe(Placement, 48).ToLowerInvariant();
        if (Aim is not ("cursor" or "facing" or "velocity" or "none"))
            throw new InvalidDataException($"unknown spawn aim '{Aim}'");
        if (Placement is not ("item_use_origin" or "owner_center" or "cursor" or "ground_at_cursor" or "above_cursor" or "native_resting_spot"))
            throw new InvalidDataException($"unknown spawn placement '{Placement}'");
        OverTarget ??= new RuntimeOverTargetSpec();
        OverTarget.Normalize();
    }
}

public sealed class RuntimeSpawnVelocitySpec
{
    [JsonRequired] public string Kind { get; set; } = "";
    private float? _minSpeedPxPerUpdate;
    public sealed class MinSpeedPxPerUpdateJsonConverter : RawJsonNullableFloatDomainConverter
    {
        public MinSpeedPxPerUpdateJsonConverter() : base("0", "80", "0") { }
    }
    [JsonConverter(typeof(MinSpeedPxPerUpdateJsonConverter))]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public float? MinSpeedPxPerUpdate
    {
        get => _minSpeedPxPerUpdate;
        set
        {
            if (value is not float speed || !float.IsFinite(speed) || speed < 0f || speed > 80f)
                throw new InvalidDataException("minimum sampled speed must be finite 0..80");
            _minSpeedPxPerUpdate = speed;
        }
    }
    private float? _maxSpeedPxPerUpdate;
    public sealed class MaxSpeedPxPerUpdateJsonConverter : RawJsonNullableFloatDomainConverter
    {
        public MaxSpeedPxPerUpdateJsonConverter() : base("0", "80", "0") { }
    }
    [JsonConverter(typeof(MaxSpeedPxPerUpdateJsonConverter))]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public float? MaxSpeedPxPerUpdate
    {
        get => _maxSpeedPxPerUpdate;
        set
        {
            if (value is not float speed || !float.IsFinite(speed) || speed < 0f || speed > 80f)
                throw new InvalidDataException("maximum sampled speed must be finite 0..80");
            _maxSpeedPxPerUpdate = speed;
        }
    }
    private float? _halfAngleRadians;
    public sealed class HalfAngleRadiansJsonConverter : RawJsonNullableFloatDomainConverter
    {
        public HalfAngleRadiansJsonConverter() : base("0", "3.141592653589793", "0") { }
    }
    [JsonConverter(typeof(HalfAngleRadiansJsonConverter))]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public float? HalfAngleRadians
    {
        get => _halfAngleRadians;
        set
        {
            if (value is not float angle || !float.IsFinite(angle) || angle < 0f || angle > MathF.PI)
                throw new InvalidDataException("cone half-angle must be finite 0..pi");
            _halfAngleRadians = angle;
        }
    }

    internal bool IsValid => MaxSpeedPxPerUpdate is not null && (Kind switch
    {
        "disk" => MinSpeedPxPerUpdate is null && HalfAngleRadians is null,
        "fan_speed" or "radial" => MinSpeedPxPerUpdate is not null
            && MinSpeedPxPerUpdate <= MaxSpeedPxPerUpdate && HalfAngleRadians is null,
        "cone" => MinSpeedPxPerUpdate is not null
            && MinSpeedPxPerUpdate <= MaxSpeedPxPerUpdate && HalfAngleRadians is not null,
        _ => false,
    });

    public void Validate()
    {
        if (!IsValid)
            throw new InvalidDataException("sampled velocity requires one exact variant, all its fields and min <= max");
    }
}

public sealed class RuntimeOverTargetSpec
{
    public float HeightTiles { get; set; }
    public int DelayTicks { get; set; }
    public void Normalize()
    {
        HeightTiles = Math.Clamp(HeightTiles, 0f, 80f);
        DelayTicks = Math.Clamp(DelayTicks, 0, 600);
    }
    public bool Enabled => HeightTiles > 0f || DelayTicks > 0;
}

public sealed class RuntimeDamageSpec
{
    public bool Enabled { get; set; }
    public string DamageClass { get; set; } = "generic";
    public int Damage { get; set; }
    public float Knockback { get; set; }
    public bool OwnerHitCheck { get; set; }
    public void Normalize()
    {
        DamageClass = RuntimeText.Safe(DamageClass, 129);
        _ = TerrariaRuntimeVocabulary.ResolveDamageClass(DamageClass);
        Damage = Math.Clamp(Damage, 0, 2000);
        Knockback = Math.Clamp(Knockback, 0f, 20f);
    }
}

public sealed class RuntimeHitboxCurveSpec
{
    public sealed class StartScaleJsonConverter : RawJsonFloatDomainConverter
    {
        public StartScaleJsonConverter() : base("0.25", "8") { }
    }
    [JsonConverter(typeof(StartScaleJsonConverter))]
    [JsonRequired] public float StartScale { get; set; }
    public sealed class EndScaleJsonConverter : RawJsonFloatDomainConverter
    {
        public EndScaleJsonConverter() : base("0.25", "8") { }
    }
    [JsonConverter(typeof(EndScaleJsonConverter))]
    [JsonRequired] public float EndScale { get; set; }
    [JsonRequired] public int StartDelayTicks { get; set; }
    [JsonRequired] public int DurationTicks { get; set; }
    [JsonRequired] public string Curve { get; set; } = "";
    [JsonRequired] public bool MirrorToSprite { get; set; }

    public void Validate()
    {
        RequireRange(StartScale, 0.25f, 8f);
        RequireRange(EndScale, 0.25f, 8f);
        RequireRange(StartDelayTicks, 0, 21600);
        RequireRange(DurationTicks, 1, 21600);
        if (Curve is not ("linear" or "exponential"))
            throw new InvalidDataException("hitboxCurve.curve must be linear or exponential");
    }

    private static void RequireRange(float value, float low, float high)
    {
        if (!float.IsFinite(value) || value < low || value > high)
            throw new InvalidDataException("hitboxCurve fields require exact finite registry bounds");
    }

    public float ScaleAt(int activeUpdates, int updatesPerWorldTick)
    {
        double activeTicks = Math.Max(0, activeUpdates) / (double)Math.Max(1, updatesPerWorldTick);
        double progress = Math.Clamp((activeTicks - StartDelayTicks) / DurationTicks, 0d, 1d);
        return Curve == "exponential"
            ? (float)(StartScale * Math.Pow(EndScale / (double)StartScale, progress))
            : (float)(StartScale + (EndScale - StartScale) * progress);
    }
}

public static class RuntimeModifierClock
{
    public static bool Active(int activeUpdates, int updatesPerWorldTick, int delayTicks, int durationTicks)
    {
        // AI increments activeUpdates before consumers. Select the interval at
        // the beginning of this step, including all subupdates in the phase.
        double tick = Math.Max(0, activeUpdates - 1) / (double)Math.Max(1, updatesPerWorldTick);
        return tick >= delayTicks && tick < (long)delayTicks + durationTicks;
    }

    public static void RequireRange(float value, float low, float high)
    {
        if (!float.IsFinite(value) || value < low || value > high)
            throw new InvalidDataException("modifier fields require exact finite registry bounds");
    }
}

// A selected motion window can own all timing. Retained scalar pairs still
// intersect that window exactly; absent scalars never invent a finite cutoff.
public abstract class RuntimeTimedModifierSpec : RuntimeWindowedMotionSpec
{
    private int? _startDelayTicks;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? StartDelayTicks
    {
        get => _startDelayTicks;
        set => _startDelayTicks = value ?? throw new InvalidDataException("present modifier delay cannot be null");
    }
    private int? _durationTicks;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? DurationTicks
    {
        get => _durationTicks;
        set => _durationTicks = value ?? throw new InvalidDataException("present modifier duration cannot be null");
    }
    public override void Validate()
    {
        base.Validate();
        if (StartDelayTicks.HasValue != DurationTicks.HasValue)
            throw new InvalidDataException("modifier scalar timing requires both delay and duration");
        if (!StartDelayTicks.HasValue) {
            if (Window is null)
                throw new InvalidDataException("modifier requires an explicit window or scalar timing pair");
            return;
        }
        RuntimeModifierClock.RequireRange(StartDelayTicks.Value, 0, 21600);
        RuntimeModifierClock.RequireRange(DurationTicks!.Value, 1, 21600);
    }
}

public sealed class RuntimeTurnModifierSpec : RuntimeTimedModifierSpec
{
    public sealed class TurnRadiansPerUpdateJsonConverter : RawJsonFloatDomainConverter
    {
        public TurnRadiansPerUpdateJsonConverter() : base("-0.5", "0.5", "0") { }
    }
    [JsonConverter(typeof(TurnRadiansPerUpdateJsonConverter))]
    [JsonRequired] public float TurnRadiansPerUpdate { get; set; }
    public override void Validate()
    {
        base.Validate();
        RuntimeModifierClock.RequireRange(TurnRadiansPerUpdate, -0.5f, 0.5f);
    }
}


public sealed class RuntimeHomingModifierSpec : RuntimeTimedModifierSpec
{
    public sealed class RangeTilesJsonConverter : RawJsonFloatDomainConverter
    {
        public RangeTilesJsonConverter() : base("1", "120") { }
    }
    [JsonConverter(typeof(RangeTilesJsonConverter))]
    [JsonRequired] public float RangeTiles { get; set; }
    public sealed class MaxTurnRadiansPerUpdateJsonConverter : RawJsonFloatDomainConverter
    {
        public MaxTurnRadiansPerUpdateJsonConverter() : base("0.0001", "3.2") { }
    }
    [JsonConverter(typeof(MaxTurnRadiansPerUpdateJsonConverter))]
    [JsonRequired] public float MaxTurnRadiansPerUpdate { get; set; }
    [JsonRequired] public bool RequireLineOfSight { get; set; }
    public override void Validate()
    {
        base.Validate();
        RuntimeModifierClock.RequireRange(RangeTiles, 1f, 120f);
        RuntimeModifierClock.RequireRange(MaxTurnRadiansPerUpdate, 0.0001f, 3.2f);
    }
}

public sealed class RuntimeNpcAttractionSpec : RuntimeTimedModifierSpec
{
    public sealed class RangeTilesJsonConverter : RawJsonFloatDomainConverter
    {
        public RangeTilesJsonConverter() : base("1", "80") { }
    }
    [JsonConverter(typeof(RangeTilesJsonConverter))]
    [JsonRequired] public float RangeTiles { get; set; }
    public sealed class StrengthPerUpdateJsonConverter : RawJsonFloatDomainConverter
    {
        public StrengthPerUpdateJsonConverter() : base("0.001", "4") { }
    }
    [JsonConverter(typeof(StrengthPerUpdateJsonConverter))]
    [JsonRequired] public float StrengthPerUpdate { get; set; }
    [JsonRequired] public string Falloff { get; set; } = "";
    [JsonRequired] public int MaxTargets { get; set; }
    public override void Validate()
    {
        base.Validate();
        RuntimeModifierClock.RequireRange(RangeTiles, 1f, 80f);
        RuntimeModifierClock.RequireRange(StrengthPerUpdate, 0.001f, 4f);
        RuntimeModifierClock.RequireRange(MaxTargets, 1, 16);
        if (Falloff is not ("constant" or "linear")) throw new InvalidDataException("unknown NPC attraction falloff");
    }
}

public sealed class RuntimeVisualScaleCurveSpec : RuntimeWindowedMotionSpec
{
    public sealed class StartScaleJsonConverter : RawJsonFloatDomainConverter
    {
        public StartScaleJsonConverter() : base("0.25", "8") { }
    }
    [JsonConverter(typeof(StartScaleJsonConverter))]
    [JsonRequired] public float StartScale { get; set; }
    public sealed class EndScaleJsonConverter : RawJsonFloatDomainConverter
    {
        public EndScaleJsonConverter() : base("0.25", "8") { }
    }
    [JsonConverter(typeof(EndScaleJsonConverter))]
    [JsonRequired] public float EndScale { get; set; }
    [JsonRequired] public int StartDelayTicks { get; set; }
    [JsonRequired] public int DurationTicks { get; set; }
    [JsonRequired] public string Curve { get; set; } = "";
    public override void Validate()
    {
        base.Validate();
        RuntimeModifierClock.RequireRange(StartScale, 0.25f, 8f);
        RuntimeModifierClock.RequireRange(EndScale, 0.25f, 8f);
        RuntimeModifierClock.RequireRange(StartDelayTicks, 0, 21600);
        RuntimeModifierClock.RequireRange(DurationTicks, 1, 21600);
        if (Curve is not ("linear" or "exponential")) throw new InvalidDataException("unknown visual scale curve");
    }
    public float ScaleAt(int activeUpdates, int updatesPerWorldTick)
    {
        double tick = Math.Max(0, activeUpdates) / (double)Math.Max(1, updatesPerWorldTick);
        double progress = Math.Clamp((tick - StartDelayTicks) / DurationTicks, 0d, 1d);
        return Curve == "exponential" ? (float)(StartScale * Math.Pow(EndScale / (double)StartScale, progress))
                                    : (float)(StartScale + (EndScale - StartScale) * progress);
    }
}

public sealed class RuntimeHitboxSpec
{
    public int WidthPx { get; set; } = 14;
    public int HeightPx { get; set; } = 14;
    public float DrawScale { get; set; } = 1f;
    public float HitboxScale { get; set; } = 1f;
    public void Normalize()
    {
        WidthPx = Math.Clamp(WidthPx, 4, 192);
        HeightPx = Math.Clamp(HeightPx, 4, 192);
        DrawScale = Math.Clamp(DrawScale, 0.25f, 4f);
        HitboxScale = Math.Clamp(HitboxScale, 0.25f, 3f);
    }
}

public sealed class RuntimeCollisionSpec
{
    public bool TileCollide { get; set; } = true;
    public bool IgnoreWater { get; set; }
    public int BounceCount { get; set; }
    private float? _bounceSpeedRetention;
    public sealed class BounceSpeedRetentionJsonConverter : RawJsonNullableFloatDomainConverter {
        public BounceSpeedRetentionJsonConverter() : base("0", "1", "1") { }
    }
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    [JsonConverter(typeof(BounceSpeedRetentionJsonConverter))]
    public float? BounceSpeedRetention {
        get => _bounceSpeedRetention;
        set {
            if (value is not float retention || !float.IsFinite(retention) || retention < 0f || retention > 1f)
                throw new InvalidDataException("bounceSpeedRetention must be finite 0..1");
            _bounceSpeedRetention = retention;
        }
    }
    public int Pierce { get; set; } = 1;
    public int ExtraUpdates { get; set; }
    public string NpcImmunityMode { get; set; } = "owner";
    public int LocalNpcHitCooldownTicks { get; set; } = -1;
    public void Normalize()
    {
        BounceCount = Math.Clamp(BounceCount, 0, 32);
        Pierce = Math.Clamp(Pierce, -1, 100);
        ExtraUpdates = Math.Clamp(ExtraUpdates, 0, 5);
        NpcImmunityMode = RuntimeText.Safe(NpcImmunityMode, 16).ToLowerInvariant();
        if (NpcImmunityMode is not ("owner" or "local"))
            throw new InvalidDataException($"unknown npc immunity mode '{NpcImmunityMode}'");
        LocalNpcHitCooldownTicks = Math.Clamp(LocalNpcHitCooldownTicks, -1, 600);
    }
}

public sealed class RuntimeMovementSpec
{
    public string Name { get; set; } = "";
    public int Code { get; set; }
    public bool IsConfigured => Name == "move_straight";

    public void NormalizeAndValidate(string entityKind)
    {
        if (Code != 0 || Name is not ("" or "move_straight"))
            throw new InvalidDataException("movement requires current opcode 0; slots 1..20 are reserved");
    }
}

public sealed class RuntimeControllerSpec
{
    public string Name { get; set; } = "";
    public int Code { get; set; }
    public bool IsConfigured => Code != RuntimeControllerCode.None || Name != "";

    public void NormalizeAndValidate(string entityKind)
    {
        if (Code is not (RuntimeControllerCode.None or RuntimeControllerCode.TargetAndFire)
            || Name != RuntimeOpcodeNames.ControllerName(Code))
            throw new InvalidDataException("controller requires exact current name/opcode; slots 1..2 are reserved");
        if (Code == RuntimeControllerCode.TargetAndFire && entityKind is not (RuntimeEntityKind.StationaryProjectile or RuntimeEntityKind.TemporaryHelper or RuntimeEntityKind.FreeProjectile or RuntimeEntityKind.ChildProjectile))
            throw new InvalidDataException("target_and_fire requires stationary_projectile, temporary_helper, free_projectile or child_projectile");
    }
}

public static class RuntimeChildCombatBasis
{
    public const string AuthoredChild = "authored_child";
    public const string LiveParent = "live_parent";

    internal static string Require(string? value)
        => value is AuthoredChild or LiveParent ? value
            : throw new InvalidDataException("child combat basis must be exactly authored_child or live_parent");
}

public sealed class RuntimeTargetingSpec
{
    public string ShotEntityId { get; set; } = "";
    public int IntervalTicks { get; set; }
    public float RangeTiles { get; set; }
    public float SameTargetBias { get; set; }
    // Nullable storage also serves inactive targeting placeholders. An active
    // target_and_fire requires all three explicit combat choices at admission.
    private string? _damageBasis;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? DamageBasis { get => _damageBasis; set => _damageBasis = RuntimeChildCombatBasis.Require(value); }
    private string? _knockbackBasis;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? KnockbackBasis { get => _knockbackBasis; set => _knockbackBasis = RuntimeChildCombatBasis.Require(value); }
    public sealed class DamageMultiplierJsonConverter : RawJsonNullableFloatDomainConverter
    {
        public DamageMultiplierJsonConverter() : base("0", "4") { }
    }
    private float? _damageMultiplier;
    [JsonConverter(typeof(DamageMultiplierJsonConverter))]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public float? DamageMultiplier
    {
        get => _damageMultiplier;
        set
        {
            if (value is not float multiplier || !float.IsFinite(multiplier) || multiplier < 0f || multiplier > 4f)
                throw new InvalidDataException("targeting damageMultiplier must be finite and within 0..4");
            _damageMultiplier = multiplier;
        }
    }
    // Declared optional targeting neutrals remain absent from persisted identity:
    // count=1, spread=0, distance_score, LOS=false and hardRange=false.
    // Explicit null is never omission.
    private int? _count;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? Count {
        get => _count;
        set => _count = value ?? throw new InvalidDataException("present targeting count must be an integer");
    }
    private double? _spreadRadians;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public double? SpreadRadians {
        get => _spreadRadians;
        set => _spreadRadians = value ?? throw new InvalidDataException("present targeting spread must be a number");
    }
    private string? _targetPolicy;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? TargetPolicy {
        get => _targetPolicy;
        set => _targetPolicy = value ?? throw new InvalidDataException("present targeting policy must be an exact token");
    }
    private bool? _requireLineOfSight;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public bool? RequireLineOfSight {
        get => _requireLineOfSight;
        set => _requireLineOfSight = value ?? throw new InvalidDataException("present targeting LOS must be boolean");
    }
    private bool? _hardRange;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public bool? HardRange {
        get => _hardRange;
        set => _hardRange = value ?? throw new InvalidDataException("present targeting hard range must be boolean");
    }
    [JsonIgnore] public bool HasVolleyOptions => Count.HasValue || SpreadRadians.HasValue
        || TargetPolicy is not null || RequireLineOfSight.HasValue || HardRange.HasValue;
    public void Normalize()
    {
        ShotEntityId = RuntimeText.IdOptional(ShotEntityId);
        IntervalTicks = Math.Clamp(IntervalTicks, 0, 3600);
        RangeTiles = Math.Clamp(RangeTiles, 0f, InfiniRuntimeLimits.MaxRuntimeRangeTiles);
        SameTargetBias = Math.Clamp(SameTargetBias, 0f, 1f);
        if (Count is < 1 or > 4)
            throw new InvalidDataException("targeting count is outside explicit accepted bounds");
        if (SpreadRadians is < 0d or > 0.75d)
            throw new InvalidDataException("targeting spread is outside explicit accepted bounds");
        if (SpreadRadians.HasValue && (!double.IsFinite(SpreadRadians.Value)
            || SpreadRadians != 0d && (float)SpreadRadians.Value == 0f)
            || TargetPolicy is not null and not ("distance_score" or "player_assigned_first"))
            throw new InvalidDataException("targeting volley/policy is outside explicit accepted bounds");
    }
}

public sealed class RuntimeLightSpec
{
    public float Strength { get; set; }
    public string Color { get; set; } = "white";
    public void Normalize()
    {
        Strength = Math.Clamp(Strength, 0f, 1.5f);
        Color = RuntimeColorPolicy.NormalizeRequired(Color, allowEmpty: Strength <= 0f);
    }
}

public static class RuntimeControllerCode
{
    public const int None = 0;
    // Slots 1 and 2 are retired/reserved.
    public const int TargetAndFire = 3;
}

public static class RuntimeEventActionCode
{
    public const int SpawnEntity = 1;
    public const int ApplyStatus = 2;
    // Slots 3 and 4 are retired/reserved.
    public const int Pull = 5;
    public const int HealOwner = 6;
    public const int MoveOwner = 7;
    public const int SelectTargetsAndEmit = 8;
    public const int ApplyGeneratedBuff = 9;
    public const int DamageNearby = 10;
    public const int ApplyNpcEffect = 11;
    public const int ReduceHealingPotionCooldown = 12;
}

public sealed class RuntimeHitTargetSpawnSpec
{
    private double? _beforeProbability;
    [JsonRequired]
    public double? BeforeProbability
    {
        get => _beforeProbability;
        set
        {
            if (value is not double number || !double.IsFinite(number) || number < 0d || number > 1d)
                throw new InvalidDataException("invalid target-relative spawn BeforeProbability");
            _beforeProbability = number;
        }
    }
    private float? _hitboxMaxSideFactor;
    [JsonRequired]
    public float? HitboxMaxSideFactor
    {
        get => _hitboxMaxSideFactor;
        set
        {
            if (value is not float number || !float.IsFinite(number) || number < 0f || number > 2f)
                throw new InvalidDataException("invalid target-relative spawn HitboxMaxSideFactor");
            _hitboxMaxSideFactor = number;
        }
    }
    private float? _clearancePx;
    [JsonRequired]
    public float? ClearancePx
    {
        get => _clearancePx;
        set
        {
            if (value is not float number || !float.IsFinite(number) || number < 0f || number > 128f)
                throw new InvalidDataException("invalid target-relative spawn ClearancePx");
            _clearancePx = number;
        }
    }
    private float? _beforePositionJitterRadiusPx;
    [JsonRequired]
    public float? BeforePositionJitterRadiusPx
    {
        get => _beforePositionJitterRadiusPx;
        set
        {
            if (value is not float number || !float.IsFinite(number) || number < 0f || number > 128f)
                throw new InvalidDataException("invalid target-relative spawn BeforePositionJitterRadiusPx");
            _beforePositionJitterRadiusPx = number;
        }
    }
    private float? _beforeDirectionJitterRadians;
    [JsonRequired]
    public float? BeforeDirectionJitterRadians
    {
        get => _beforeDirectionJitterRadians;
        set
        {
            if (value is not float number || !float.IsFinite(number) || number < 0f || number > MathF.PI)
                throw new InvalidDataException("invalid target-relative spawn BeforeDirectionJitterRadians");
            _beforeDirectionJitterRadians = number;
        }
    }
    private float? _afterFanSpreadRadians;
    [JsonRequired]
    public float? AfterFanSpreadRadians
    {
        get => _afterFanSpreadRadians;
        set
        {
            if (value is not float number || !float.IsFinite(number) || number < 0f || number > MathF.Tau)
                throw new InvalidDataException("invalid target-relative spawn AfterFanSpreadRadians");
            _afterFanSpreadRadians = number;
        }
    }
    private int? _initialIgnoreCountdownUpdates;
    [JsonRequired]
    public int? InitialIgnoreCountdownUpdates
    {
        get => _initialIgnoreCountdownUpdates;
        set
        {
            if (value is not int number || number < 0 || number > 600)
                throw new InvalidDataException("invalid target-relative spawn InitialIgnoreCountdownUpdates");
            _initialIgnoreCountdownUpdates = number;
        }
    }
    internal bool IsValid => BeforeProbability is not null
        && HitboxMaxSideFactor is not null
        && ClearancePx is not null
        && BeforePositionJitterRadiusPx is not null
        && BeforeDirectionJitterRadians is not null
        && AfterFanSpreadRadians is not null
        && InitialIgnoreCountdownUpdates is not null;
    public void Validate()
    {
        if (!IsValid)
            throw new InvalidDataException("target-relative spawn requires all geometry and exclusion choices");
    }

}

public sealed class RuntimeEventActionSpec
{
    private RuntimeNpcEffectSpec? _npcEffect;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public RuntimeNpcEffectSpec? NpcEffect
    {
        get => _npcEffect;
        set => _npcEffect = value ?? throw new InvalidDataException("present npcEffect cannot be null");
    }
    public string Id { get; set; } = "";
    public string Event { get; set; } = "";
    private string? _useInput;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? UseInput
    {
        get => _useInput;
        set => _useInput = RuntimeUseInputScope.Require(value);
    }
    public string Action { get; set; } = "";
    public int ActionCode { get; set; }
    public string EntityId { get; set; } = "";
    private int _count = 1;
    private float _spreadRadians;
    private float _damageMultiplier = 1f;
    private int _delayTicks;
    private bool _countPresent, _spreadPresent, _damageMultiplierPresent, _delayPresent;
    public int Count { get => _count; set { _countPresent = true; _count = value; } }
    public float SpreadRadians { get => _spreadRadians; set { _spreadPresent = true; _spreadRadians = value; } }
    public float DamageMultiplier { get => _damageMultiplier; set { _damageMultiplierPresent = true; _damageMultiplier = value; } }
    private string? _damageBasis;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? DamageBasis { get => _damageBasis; set => _damageBasis = RuntimeChildCombatBasis.Require(value); }
    private string? _knockbackBasis;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? KnockbackBasis { get => _knockbackBasis; set => _knockbackBasis = RuntimeChildCombatBasis.Require(value); }
    private RuntimeHitTargetSpawnSpec? _hitTargetSpawn;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public RuntimeHitTargetSpawnSpec? HitTargetSpawn
    {
        get => _hitTargetSpawn;
        set => _hitTargetSpawn = value ?? throw new InvalidDataException("present hitTargetSpawn cannot be null");
    }
    public int DelayTicks { get => _delayTicks; set { _delayPresent = true; _delayTicks = value; } }
    public int PeriodTicks { get; set; }
    public int BuffId { get; set; } = -1;
    public int DurationTicks { get; set; }
    public int RadiusPx { get; set; }
    public float RangeTiles { get; set; }
    public string Mode { get; set; } = "";
    public float Strength { get; set; }
    private int? _maxTargets;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? MaxTargets
    {
        get => _maxTargets;
        set
        {
            if (value is not int number || number < 1 || number > 16)
                throw new InvalidDataException("maxTargets must be an integer in 1..16");
            _maxTargets = number;
        }
    }
    private float? _ownerStrength;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public float? OwnerStrength
    {
        get => _ownerStrength;
        set
        {
            if (value is not float number || !float.IsFinite(number) || number < 0.01f || number > 4f)
                throw new InvalidDataException("ownerStrength must be a finite impulse in 0.01..4");
            _ownerStrength = number;
        }
    }
    private float? _targetStrength;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public float? TargetStrength
    {
        get => _targetStrength;
        set
        {
            if (value is not float number || !float.IsFinite(number) || number < 0.01f || number > 4f)
                throw new InvalidDataException("targetStrength must be a finite impulse in 0.01..4");
            _targetStrength = number;
        }
    }

    public float RadiusTiles { get; set; }
    public float DamageFraction { get; set; }
    private int? _cooldownReductionTicks;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? CooldownReductionTicks
    {
        get => _cooldownReductionTicks;
        set { if (value is not int ticks || ticks < 1 || ticks > 3600) throw new InvalidDataException("cooldownReductionTicks must be 1..3600"); _cooldownReductionTicks = ticks; }
    }
    public int MaxHeal { get; set; }
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)]
    public int ReactionCooldownTicks { get; set; }
    private string? _effectGroupId;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? EffectGroupId
    {
        get => _effectGroupId;
        set => _effectGroupId = RuntimeItemEffectGroupSpec.RequireId(value);
    }
    public int CooldownTicks { get; set; }
    public bool SafeTileOnly { get; set; } = true;

    private int? _stepCount;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? StepCount
    {
        get => _stepCount;
        set
        {
            if (value is null || value < 1 || value > 12)
                throw new InvalidDataException("stepCount must be an integer in 1..12");
            _stepCount = value;
        }
    }
    private double? _stepRangeTiles;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public double? StepRangeTiles
    {
        get => _stepRangeTiles;
        set
        {
            if (value is null || !double.IsFinite(value.Value) || value < 1d || value > 60d)
                throw new InvalidDataException("stepRangeTiles must be finite in 1..60");
            _stepRangeTiles = value;
        }
    }
    private string? _selectionAnchor;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? SelectionAnchor
    {
        get => _selectionAnchor;
        set
        {
            if (value is not ("previous_target" or "event_target"))
                throw new InvalidDataException("selectionAnchor must explicitly select previous_target or event_target");
            _selectionAnchor = value;
        }
    }
    private string? _repeatPolicy;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? RepeatPolicy
    {
        get => _repeatPolicy;
        set
        {
            if (value is not ("allow_revisits" or "exclude_visited"))
                throw new InvalidDataException("repeatPolicy must explicitly select allow_revisits or exclude_visited");
            _repeatPolicy = value;
        }
    }
    private bool? _requireLineOfSight;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public bool? RequireLineOfSight
    {
        get => _requireLineOfSight;
        set
        {
            if (value is null) throw new InvalidDataException("requireLineOfSight cannot be null");
            _requireLineOfSight = value;
        }
    }
    private int? _initialIgnoreCountdownUpdates;
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? InitialIgnoreCountdownUpdates
    {
        get => _initialIgnoreCountdownUpdates;
        set
        {
            if (value is null || value < 0 || value > 600)
                throw new InvalidDataException("initialIgnoreCountdownUpdates must be an integer in 0..600");
            _initialIgnoreCountdownUpdates = value;
        }
    }

    internal static bool SupportsTargetEmission(RuntimeEntitySpec? child)
        => child is not null && child.Kind is (RuntimeEntityKind.FreeProjectile or RuntimeEntityKind.ChildProjectile)
            && child.Spawn is not null && child.Spawn.HasExactTargetEmissionOrigin();

    public void NormalizeAndValidate()
    {
        if (ActionCode == RuntimeEventActionCode.ApplyNpcEffect)
        {
            if (Action != "apply_npc_effect_on_event" || Event is not (RuntimeEventKind.OnHit or RuntimeEventKind.OnCrit)
                || NpcEffect is null || DurationTicks is < 1 or > 3600 || DelayTicks is < 0 or > 600
                || EntityId != "" || Count != 1 || SpreadRadians != 0f || DamageMultiplier != 1f || PeriodTicks != 0
                || BuffId != -1 || RadiusPx != 0 || RangeTiles != 0f || Mode != "" || Strength != 0f
                || RadiusTiles != 0f || DamageFraction != 0f || MaxHeal != 0 || CooldownTicks != 0 || !SafeTileOnly)
                throw new InvalidDataException("NPC effect requires exact direct-hit action, effect, duration and neutral foreign fields");
            NpcEffect.Validate();
        }
        else if (NpcEffect is not null)
            throw new InvalidDataException("npcEffect requires apply_npc_effect_on_event");
        if (HitTargetSpawn is not null)
        {
            HitTargetSpawn.Validate();
            if (!_countPresent || !_spreadPresent || !_damageMultiplierPresent || !_delayPresent
                || ActionCode != RuntimeEventActionCode.SpawnEntity || Action != "spawn_entity_on_event" || Event is not (RuntimeEventKind.OnHit or RuntimeEventKind.OnCrit)
                || DamageBasis is null || KnockbackBasis is null || Count < 1 || Count > 12
                || SpreadRadians != 0f || !float.IsFinite(DamageMultiplier) || DamageMultiplier < 0f || DamageMultiplier > 4f
                || DelayTicks < 0 || DelayTicks > 600)
                throw new InvalidDataException("target-relative spawn requires exact direct-hit event, explicit combat bases, count, multiplier and inactive spread");
        }
        if (ActionCode == RuntimeEventActionCode.SelectTargetsAndEmit
            && (Event is not (RuntimeEventKind.OnHit or RuntimeEventKind.OnCrit)
                || Action != RuntimeOpcodeNames.EventActionName(ActionCode)
                || EntityId != RuntimeText.IdOptional(EntityId)))
            throw new InvalidDataException("target emission requires exact event/action/reference strings without normalization");
        Id = RuntimeText.Id(Id);
        Event = RuntimeText.Safe(Event, 32).ToLowerInvariant();
        Action = RuntimeText.Safe(Action, 64);
        EntityId = RuntimeText.IdOptional(EntityId);
        if (!RuntimeEventKind.IsKnown(Event))
            throw new InvalidDataException($"unknown runtime event '{Event}'");
        if (ActionCode < RuntimeEventActionCode.SpawnEntity || ActionCode > RuntimeEventActionCode.ReduceHealingPotionCooldown || ActionCode is 3 or 4)
            throw new InvalidDataException($"unsupported event action opcode {ActionCode}");
        if (!string.Equals(Action, RuntimeOpcodeNames.EventActionName(ActionCode), StringComparison.Ordinal))
            throw new InvalidDataException($"event action name/opcode mismatch '{Action}'/{ActionCode}");
        if (ActionCode == RuntimeEventActionCode.ReduceHealingPotionCooldown)
        {
            if (CooldownReductionTicks is null || Event is not (RuntimeEventKind.OnHit or RuntimeEventKind.OnCrit))
                throw new InvalidDataException("cooldown reduction requires an explicit amount and a direct hit/crit event");
        }
        else if (CooldownReductionTicks is not null) throw new InvalidDataException("cooldown reduction belongs to its exact action");
        if (ActionCode == RuntimeEventActionCode.ApplyGeneratedBuff)
        {
            if (Event is not (RuntimeEventKind.OnHurt or RuntimeEventKind.OnEnemyKill) || EffectGroupId is null)
                throw new InvalidDataException("generated-buff reaction requires an exact group and equipment event");
            if (EntityId != "" || Count != 1 || SpreadRadians != 0f || DamageMultiplier != 1f || PeriodTicks != 0
                || BuffId != -1 || DurationTicks != 0 || RadiusPx != 0 || RangeTiles != 0f || Mode != ""
                || Strength != 0f || RadiusTiles != 0f || DamageFraction != 0f || MaxHeal != 0
                || CooldownTicks != 0 || !SafeTileOnly || DelayTicks is < 0 or > 600)
                throw new InvalidDataException("generated-buff reaction cannot consume non-neutral fields owned by another event opcode");
        }
        else if (EffectGroupId is not null)
            throw new InvalidDataException("event effectGroupId requires the generated-buff reaction opcode");
        if (ActionCode == RuntimeEventActionCode.SelectTargetsAndEmit)
        {
            if (Event is not (RuntimeEventKind.OnHit or RuntimeEventKind.OnCrit)
                || string.IsNullOrWhiteSpace(EntityId) || !_delayPresent || DelayTicks < 0 || DelayTicks > 600
                || StepCount is null || StepRangeTiles is null || SelectionAnchor is null || RepeatPolicy is null
                || RequireLineOfSight is null || InitialIgnoreCountdownUpdates is null)
                throw new InvalidDataException("target emission requires every explicit hit-event parameter without defaults");
            if (Count != 1 || SpreadRadians != 0f || DamageMultiplier != 1f || PeriodTicks != 0
                || BuffId != -1 || DurationTicks != 0 || RadiusPx != 0 || RangeTiles != 0f || Mode != ""
                || Strength != 0f || RadiusTiles != 0f || DamageFraction != 0f || MaxHeal != 0
                || CooldownTicks != 0 || !SafeTileOnly)
                throw new InvalidDataException("target emission cannot consume non-neutral fields owned by another event opcode");
        }
        else if (StepCount is not null || StepRangeTiles is not null || SelectionAnchor is not null || RepeatPolicy is not null
            || RequireLineOfSight is not null || InitialIgnoreCountdownUpdates is not null)
            throw new InvalidDataException("target selection/emission params require the exact SelectTargetsAndEmit opcode");
        if (ActionCode == RuntimeEventActionCode.SpawnEntity
            && (DamageBasis is null || KnockbackBasis is null))
            throw new InvalidDataException($"event '{Id}' spawn_entity_on_event requires explicit damageBasis and knockbackBasis");
        if (ActionCode != RuntimeEventActionCode.SpawnEntity
            && (DamageBasis is not null || KnockbackBasis is not null))
            throw new InvalidDataException($"event '{Id}' child combat fields require spawn_entity_on_event");
        if (ActionCode == RuntimeEventActionCode.Pull && Mode == "both")
        {
            if (OwnerStrength is null || TargetStrength is null || Strength != 0f || RadiusTiles != 0f
                || Event is not (RuntimeEventKind.OnHit or RuntimeEventKind.OnCrit))
                throw new InvalidDataException("both pull requires only two explicit impulses and the same direct target");
            if (EntityId != "" || Count != 1 || SpreadRadians != 0f || DamageMultiplier != 1f
                || PeriodTicks != 0 || BuffId != -1 || DurationTicks != 0 || RadiusPx != 0 || RangeTiles != 0f
                || DamageFraction != 0f || MaxHeal != 0 || CooldownTicks != 0 || !SafeTileOnly
                || DelayTicks is < 0 or > 600)
                throw new InvalidDataException("both pull cannot consume other action fields");
        }
        else if (OwnerStrength is not null || TargetStrength is not null)
            throw new InvalidDataException("two-body impulses require pull mode both");
        if (ActionCode == RuntimeEventActionCode.DamageNearby)
        {
            if (MaxTargets is null || !_damageMultiplierPresent
                || RadiusPx is < 8 or > 960 || !float.IsFinite(DamageMultiplier) || DamageMultiplier is < 0.05f or > 4f
                || DelayTicks is < 0 or > 600
                || Event is not (RuntimeEventKind.OnHit or RuntimeEventKind.OnCrit or RuntimeEventKind.OnTileCollision
                    or RuntimeEventKind.OnExpire or RuntimeEventKind.OnKill or RuntimeEventKind.OnHurt or RuntimeEventKind.OnEnemyKill))
                throw new InvalidDataException("nearby damage requires exact bounded damage, radius, count and event");
            if (EntityId != "" || Count != 1 || SpreadRadians != 0f || PeriodTicks != 0 || BuffId != -1 || DurationTicks != 0
                || RangeTiles != 0f || Mode != "" || Strength != 0f || RadiusTiles != 0f || DamageFraction != 0f
                || MaxHeal != 0 || CooldownTicks != 0 || !SafeTileOnly)
                throw new InvalidDataException("nearby damage cannot consume other action fields");
        }
        else if (MaxTargets is not null)
            throw new InvalidDataException("maxTargets requires nearby damage");
        Count = Math.Clamp(Count, 1, InfiniRuntimeLimits.MaxRuntimeSpawnCount);
        SpreadRadians = Math.Clamp(SpreadRadians, 0f, MathF.Tau);
        DamageMultiplier = Math.Clamp(DamageMultiplier, 0f, 10f);
        DelayTicks = Math.Clamp(DelayTicks, 0, 600);
        PeriodTicks = Math.Clamp(PeriodTicks, 0, 3600);
        if (BuffId < -1 || BuffId >= BuffLoader.BuffCount)
            throw new InvalidDataException($"buff ID {BuffId} is not loaded");
        DurationTicks = Math.Clamp(DurationTicks, 0, 21600);
        RadiusPx = Math.Clamp(RadiusPx, 0, 1024);
        RangeTiles = Math.Clamp(RangeTiles, 0f, InfiniRuntimeLimits.MaxRuntimeRangeTiles);
        Mode = RuntimeText.Safe(Mode, 32).ToLowerInvariant();
        Strength = Math.Clamp(Strength, 0f, 4f);
        RadiusTiles = Math.Clamp(RadiusTiles, 0f, InfiniRuntimeLimits.MaxRuntimeRangeTiles);
        DamageFraction = Math.Clamp(DamageFraction, 0f, 1f);
        MaxHeal = Math.Clamp(MaxHeal, 0, 500);
        CooldownTicks = Math.Clamp(CooldownTicks, 0, 36000);
        bool reactive = Event is RuntimeEventKind.OnHurt or RuntimeEventKind.OnEnemyKill;
        if (reactive && (ReactionCooldownTicks is < 6 or > 3600
            || ActionCode is not (RuntimeEventActionCode.SpawnEntity or RuntimeEventActionCode.DamageNearby or RuntimeEventActionCode.ApplyGeneratedBuff))
            || !reactive && ReactionCooldownTicks != 0)
            throw new InvalidDataException("Reactive equipment requires an explicit 6..3600 tick cooldown and supported action");
        if (Event == RuntimeEventKind.Periodic && PeriodTicks < 6)
            throw new InvalidDataException($"periodic event action '{Id}' requires periodTicks >= 6");
        if (ActionCode is (RuntimeEventActionCode.SpawnEntity or RuntimeEventActionCode.SelectTargetsAndEmit) && string.IsNullOrWhiteSpace(EntityId))
            throw new InvalidDataException($"spawn event action '{Id}' has no entityId");
        if (ActionCode == RuntimeEventActionCode.ApplyStatus && (BuffId <= 0 || DurationTicks <= 0))
            throw new InvalidDataException($"status event action '{Id}' requires buffId and durationTicks");
        if (ActionCode == RuntimeEventActionCode.Pull && Mode is not ("target_to_owner" or "target_to_entity" or "owner_to_target" or "both"))
            throw new InvalidDataException($"pull event action '{Id}' has unsupported mode '{Mode}'");
        if (ActionCode == RuntimeEventActionCode.MoveOwner && Mode is not ("blink_to_entity" or "blink_to_event_position"))
            throw new InvalidDataException($"move-owner event action '{Id}' has unsupported mode '{Mode}'");
    }
}

public sealed class RuntimeItemUseSpec
{
    public bool Configured { get; set; }
    public string UseStyle { get; set; } = "shoot";
    public bool HideUseGraphic { get; set; }
    public bool DisableMeleeHitbox { get; set; }
    public bool Channel { get; set; }
    public string HandPose { get; set; } = "";
    public int HoldoutOffsetX { get; set; }
    public int HoldoutOffsetY { get; set; }
    public void Normalize()
    {
        UseStyle = RuntimeText.Safe(UseStyle, 32).ToLowerInvariant();
        _ = TerrariaRuntimeVocabulary.ResolveItemUseStyle(UseStyle);
        HandPose = RuntimeText.Safe(HandPose, 32).ToLowerInvariant();
        HoldoutOffsetX = Math.Clamp(HoldoutOffsetX, -96, 96);
        HoldoutOffsetY = Math.Clamp(HoldoutOffsetY, -96, 96);
    }
}

public sealed class RuntimeItemContactSpec
{
    public float HitboxScale { get; set; } = 1f;
    public int ContactForgivenessPx { get; set; }
    public void Normalize()
    {
        HitboxScale = Math.Clamp(HitboxScale <= 0f ? 1f : HitboxScale, 0.5f, 2f);
        ContactForgivenessPx = Math.Clamp(ContactForgivenessPx, 0, 64);
    }
}

internal static class RuntimeOpcodeNames
{
    private static readonly string[] EventNames =
    {
        "", "spawn_entity_on_event", "apply_status_on_event", "",
        "", "pull_on_event", "heal_owner_on_event", "move_owner_on_event",
        "select_targets_and_emit_on_event", "apply_generated_buff_on_event", "damage_nearby_on_event", "apply_npc_effect_on_event", "reduce_healing_potion_cooldown_on_event",
    };
    public static string MovementName(int code) => code == 0 ? "move_straight" : "";
    public static string ControllerName(int code) => code == RuntimeControllerCode.TargetAndFire ? "target_and_fire" : "";
    public static string EventActionName(int code) => code >= 0 && code < EventNames.Length ? EventNames[code] : "";
}

internal static class RuntimeText
{
    public static string Safe(string? value, int maxLength)
    {
        string text = (value ?? "").Trim();
        return text.Length <= maxLength ? text : text[..maxLength];
    }
    public static string Prose(string? value, int maxScalars)
    {
        string text = (value ?? "").Trim();
        int scalars = 0, end = 0;
        foreach (var rune in text.EnumerateRunes())
        {
            if (scalars++ == maxScalars) break;
            end += rune.Utf16SequenceLength;
        }
        return end == text.Length ? text : text[..end];
    }
    public static bool ProseFits(string value, int maxScalars)
        => value.EnumerateRunes().Count() <= maxScalars;
    public static string Id(string? value)
    {
        string text = Safe(value, 48);
        if (string.IsNullOrWhiteSpace(text) || !char.IsLower(text[0]) || text.Any(c => !(char.IsLower(c) || char.IsDigit(c) || c == '_')))
            throw new InvalidDataException($"invalid runtime id '{text}'");
        return text;
    }
    public static string IdOptional(string? value)
    {
        string text = Safe(value, 48);
        return string.IsNullOrWhiteSpace(text) ? "" : Id(text);
    }
}

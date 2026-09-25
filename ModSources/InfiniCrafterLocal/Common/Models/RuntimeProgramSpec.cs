#nullable enable
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.VFX;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
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
        if (Entities.Length < 1 || Entities.Length > Limits.MaxEntityCount)
            throw new InvalidDataException($"runtimeProgram.entities must contain 1..{Limits.MaxEntityCount} rows");
        if (Bindings.Length > InfiniRuntimeLimits.MaxRuntimeBindings)
            throw new InvalidDataException($"runtimeProgram.bindings exceeds {InfiniRuntimeLimits.MaxRuntimeBindings}");

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
        int eventSpawnBudget = 0;
        foreach (RuntimeEntitySpec entity in Entities)
        {
            graph[entity.Id] = new HashSet<string>(StringComparer.Ordinal);
            foreach (RuntimeEventActionSpec action in entity.Events)
            {
                RuntimeEventKind.ValidateProducer(entity, action.Event, hasItemContactBinding, hasEmittingItemUse);
                if (action.ActionCode == RuntimeEventActionCode.SpawnEntity)
                {
                    RuntimeEntitySpec? child = TryGetEntity(action.EntityId);
                    if (child is null || child.Kind == RuntimeEntityKind.ItemBody)
                        throw new InvalidDataException($"event '{action.Id}' references invalid entity '{action.EntityId}'");
                    graph[entity.Id].Add(child.Id);
                    eventSpawnBudget += action.Count;
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
        }
        if (eventSpawnBudget > Limits.MaxEventSpawnsPerActivation)
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

public static class RuntimeBindingAction
{
    public const string SpawnEntity = "spawn_entity";
    public const string UseItemBody = "use_item_body";
    public const string ApplyItemEffects = "apply_item_effects";
    public const string PlaceItem = "place_item";
    public const string EquipPassive = "equip_passive";
    private static readonly HashSet<string> Known = new(StringComparer.Ordinal)
    {
        SpawnEntity, UseItemBody, ApplyItemEffects, PlaceItem, EquipPassive,
    };
    public static bool IsKnown(string? value) => value is not null && Known.Contains(value);

    public static bool IsAllowed(string? input, string? action)
        => input switch
        {
            RuntimeInputKind.PrimaryUse or RuntimeInputKind.AlternateUse
                => action is SpawnEntity or UseItemBody or ApplyItemEffects or PlaceItem,
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
    private static readonly HashSet<string> Known = new(StringComparer.Ordinal)
    {
        OnUse, OnSpawn, OnHit, OnCrit, OnTileCollision, OnExpire, OnKill,
        Periodic, OnRelease, ChannelComplete,
    };
    public static bool IsKnown(string? value) => value is not null && Known.Contains(value);

    public static void ValidateProducer(RuntimeEntitySpec entity, string eventName, bool itemContactEnabled, bool hasActiveItemUse)
    {
        bool projectile = entity.IsProjectileEntity;
        bool sourceCompatible = eventName switch
        {
            OnUse => entity.Kind == RuntimeEntityKind.ItemBody,
            OnSpawn or OnTileCollision or OnExpire or OnKill or OnRelease or ChannelComplete => projectile,
            OnHit or OnCrit or Periodic => true,
            _ => false,
        };
        if (!sourceCompatible)
            throw new InvalidDataException($"entity '{entity.Id}' of kind '{entity.Kind}' cannot emit '{eventName}'");

        bool available = eventName switch
        {
            OnUse => hasActiveItemUse,
            OnHit or OnCrit => entity.Kind == RuntimeEntityKind.ItemBody ? itemContactEnabled : entity.Damage.Enabled,
            OnTileCollision => entity.Collision.TileCollide,
            OnRelease or ChannelComplete => entity.Controller.Code == RuntimeControllerCode.ChargeThenRelease,
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

    public void NormalizeAndValidate(string input)
    {
        Action ??= new RuntimeBindingActionSpec();
        Action.NormalizeAndValidate();
        if (StackCost is not (0 or 1))
            throw new InvalidDataException("binding usePolicy.stackCost must be exactly 0 or 1");
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

    public void NormalizeAndValidate()
    {
        Kind = (Kind ?? "").Trim().ToLowerInvariant();
        TargetId = RuntimeText.Id(TargetId);
        if (!RuntimeBindingAction.IsKnown(Kind))
            throw new InvalidDataException($"unknown runtime binding action '{Kind}'");
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

public sealed class RuntimePlacementSpec
{
    public int TileId { get; set; } = -1;
    public int WallId { get; set; } = -1;
    public int PlaceStyle { get; set; }

    public void NormalizeAndValidate()
    {
        if (TileId < -1 || TileId >= TileLoader.TileCount)
            throw new InvalidDataException($"tile ID {TileId} is not loaded");
        if (WallId < -1 || WallId >= WallLoader.WallCount)
            throw new InvalidDataException($"wall ID {WallId} is not loaded");
        if (TileId < 0 && WallId < 0)
            throw new InvalidDataException("placement must enable a tile or wall");
        if (PlaceStyle is < 0 or > 1000)
            throw new InvalidDataException("placement style must be 0..1000");
    }
}

public static class RuntimeEntityRole
{
    public const string Primary = "primary";
    public const string Secondary = "secondary";

    public static bool IsKnown(string? value) => value is Primary or Secondary;
}

public sealed class RuntimeEntitySpec
{
    public string Id { get; set; } = "";
    public string Kind { get; set; } = "";
    public string VisualRole { get; set; } = "";
    public RuntimeEntityVisualSpec Visual { get; set; } = new();
    public RuntimeSpawnSpec Spawn { get; set; } = new();
    public RuntimeDamageSpec Damage { get; set; } = new();
    public int LifetimeTicks { get; set; } = 1;
    public RuntimeHitboxSpec Hitbox { get; set; } = new();
    public RuntimeCollisionSpec Collision { get; set; } = new();
    public RuntimeMovementSpec Movement { get; set; } = new();
    public RuntimeControllerSpec Controller { get; set; } = new();
    public RuntimeTargetingSpec Targeting { get; set; } = new();
    public RuntimeLightSpec Light { get; set; } = new();
    public RuntimeEventActionSpec[] Events { get; set; } = Array.Empty<RuntimeEventActionSpec>();

    public bool IsProjectileEntity => RuntimeEntityKind.IsProjectile(Kind);
    public bool IsOwnerAttached => Kind == RuntimeEntityKind.OwnerAttachedProjectile;
    public bool IsStationary => Kind is RuntimeEntityKind.StationaryProjectile or RuntimeEntityKind.Field or RuntimeEntityKind.TemporaryHelper;

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

        Visual.Normalize();
        string expectedVisualRole = RuntimeEntityKind.VisualRoleFor(Kind);
        if (!string.Equals(VisualRole, expectedVisualRole, StringComparison.Ordinal)
            || !string.Equals(Visual.Role, expectedVisualRole, StringComparison.Ordinal))
            throw new InvalidDataException($"entity '{Id}' visual roles must equal '{expectedVisualRole}' for kind '{Kind}'");
        if (Kind == RuntimeEntityKind.ItemBody)
        {
            if (Spawn.Enabled || Damage.Enabled || Movement.IsConfigured || Controller.IsConfigured)
                throw new InvalidDataException($"item_body '{Id}' cannot carry projectile components");
        }
        else
        {
            Spawn.Normalize();
            Damage.Normalize();
            LifetimeTicks = Math.Clamp(LifetimeTicks, 1, InfiniRuntimeLimits.MaxRuntimeLifetimeTicks);
            Hitbox.Normalize();
            Collision.Normalize();
            Movement.NormalizeAndValidate(Kind);
            Controller.NormalizeAndValidate(Kind);
            bool requiresPositionDriver = Kind is RuntimeEntityKind.OwnerAttachedProjectile or RuntimeEntityKind.FreeProjectile or RuntimeEntityKind.ChildProjectile;
            bool controllerOwnsPosition = Controller.Code is RuntimeControllerCode.ChannelBeam or RuntimeControllerCode.ChargeThenRelease or RuntimeControllerCode.TargetAndFire;
            if (requiresPositionDriver && !Movement.IsConfigured && !controllerOwnsPosition)
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
    public string Role { get; set; } = "";
    public string AssetMode { get; set; } = "";
    public string Prompt { get; set; } = "";
    public string Silhouette { get; set; } = "";
    public string VisualIdentity { get; set; } = "";
    public string ImpactPrompt { get; set; } = "";
    public string ImpactNegativePrompt { get; set; } = "";
    public float Scale { get; set; } = 1f;
    public string SpritePath { get; set; } = "";
    public string SpriteUrl { get; set; } = "";
    public string SpriteStatus { get; set; } = "";
    public float SpriteTechnicalScore { get; set; } = 0f;
    public string ImpactSpritePath { get; set; } = "";
    public string ImpactSpriteUrl { get; set; } = "";
    public string ImpactSpriteStatus { get; set; } = "";
    public float ImpactSpriteTechnicalScore { get; set; } = 0f;

    public void Normalize()
    {
        Role = RuntimeText.Safe(Role, 64);
        AssetMode = RuntimeText.Safe(AssetMode, 32).ToLowerInvariant();
        Prompt = RuntimeText.Safe(Prompt, 1400);
        Silhouette = RuntimeText.Safe(Silhouette, 700);
        VisualIdentity = RuntimeText.Safe(VisualIdentity, 700);
        ImpactPrompt = RuntimeText.Safe(ImpactPrompt, 1400);
        ImpactNegativePrompt = RuntimeText.Safe(ImpactNegativePrompt, 700);
        Scale = Math.Clamp(Scale <= 0f ? 1f : Scale, 0.25f, 4f);
        SpritePath = RuntimeText.Safe(SpritePath, 260);
        SpriteUrl = RuntimeText.Safe(SpriteUrl, 500);
        SpriteStatus = RuntimeText.Safe(SpriteStatus, 48).ToLowerInvariant();
        SpriteTechnicalScore = Math.Clamp(SpriteTechnicalScore, 0f, 1f);
        ImpactSpritePath = RuntimeText.Safe(ImpactSpritePath, 260);
        ImpactSpriteUrl = RuntimeText.Safe(ImpactSpriteUrl, 500);
        ImpactSpriteStatus = RuntimeText.Safe(ImpactSpriteStatus, 48).ToLowerInvariant();
        ImpactSpriteTechnicalScore = Math.Clamp(ImpactSpriteTechnicalScore, 0f, 1f);
        if (AssetMode == "baked_sprite" && (string.IsNullOrWhiteSpace(SpritePath) || SpriteStatus is "failed" or "prompt_only" or "placeholder" or "backend_config_error"))
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
    public float SpreadRadians { get; set; }
    public int OffsetPx { get; set; }
    public string Aim { get; set; } = "cursor";
    public string Placement { get; set; } = "item_use_origin";
    public RuntimeOverTargetSpec OverTarget { get; set; } = new();

    public void Normalize()
    {
        SpeedPxPerTick = Math.Clamp(SpeedPxPerTick, 0f, 80f);
        Count = Math.Clamp(Count, 1, InfiniRuntimeLimits.MaxRuntimeSpawnCount);
        SpreadRadians = Math.Clamp(SpreadRadians, 0f, MathF.Tau);
        OffsetPx = Math.Clamp(OffsetPx, -128, 256);
        Aim = RuntimeText.Safe(Aim, 32).ToLowerInvariant();
        Placement = RuntimeText.Safe(Placement, 48).ToLowerInvariant();
        if (Aim is not ("cursor" or "facing" or "velocity" or "none"))
            throw new InvalidDataException($"unknown spawn aim '{Aim}'");
        if (Placement is not ("item_use_origin" or "owner_center" or "cursor" or "ground_at_cursor" or "above_cursor"))
            throw new InvalidDataException($"unknown spawn placement '{Placement}'");
        OverTarget ??= new RuntimeOverTargetSpec();
        OverTarget.Normalize();
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
    public RuntimeParamsSpec Params { get; set; } = new();
    public bool IsConfigured => !string.IsNullOrWhiteSpace(Name);

    public void NormalizeAndValidate(string entityKind)
    {
        Name = RuntimeText.Safe(Name, 64);
        Params ??= new RuntimeParamsSpec();
        Params.Normalize();
        // Omitted movement is meaningful for stationary/field/helper entities. Code 0
        // is also the explicit move_straight opcode, so Name is the presence bit.
        if (!IsConfigured)
        {
            Code = 0;
            return;
        }
        if (Code < 0 || Code > InfiniRuntimeLimits.MaxSupportedMovementCode)
            throw new InvalidDataException($"unsupported movement opcode {Code}");
        if (Code >= 16 && entityKind != RuntimeEntityKind.OwnerAttachedProjectile)
            throw new InvalidDataException($"movement opcode {Code} requires owner_attached_projectile");
        if (!string.Equals(Name, RuntimeOpcodeNames.MovementName(Code), StringComparison.Ordinal))
            throw new InvalidDataException($"movement name/opcode mismatch '{Name}'/{Code}");
    }
}

public sealed class RuntimeControllerSpec
{
    public string Name { get; set; } = "";
    public int Code { get; set; }
    public RuntimeParamsSpec Params { get; set; } = new();
    public bool IsConfigured => Code != RuntimeControllerCode.None || !string.IsNullOrWhiteSpace(Name);

    public void NormalizeAndValidate(string entityKind)
    {
        Name = RuntimeText.Safe(Name, 64);
        Params ??= new RuntimeParamsSpec();
        Params.Normalize();
        if (Code < 0 || Code > InfiniRuntimeLimits.MaxSupportedControllerCode)
            throw new InvalidDataException($"unsupported controller opcode {Code}");
        if (Code == RuntimeControllerCode.ChannelBeam && entityKind != RuntimeEntityKind.OwnerAttachedProjectile)
            throw new InvalidDataException("channel_beam requires owner_attached_projectile");
        if (Code == RuntimeControllerCode.TargetAndFire && entityKind is not (RuntimeEntityKind.StationaryProjectile or RuntimeEntityKind.TemporaryHelper))
            throw new InvalidDataException("target_and_fire requires stationary_projectile or temporary_helper");
        if (Code == RuntimeControllerCode.ChargeThenRelease && entityKind is not (RuntimeEntityKind.OwnerAttachedProjectile or RuntimeEntityKind.FreeProjectile))
            throw new InvalidDataException("charge_then_release requires owner_attached_projectile or free_projectile");
        if (!string.Equals(Name, RuntimeOpcodeNames.ControllerName(Code), StringComparison.Ordinal))
            throw new InvalidDataException($"controller name/opcode mismatch '{Name}'/{Code}");
    }
}

public sealed class RuntimeParamsSpec
{
    public float RangeTiles { get; set; }
    public float HomingStrength { get; set; }
    public float GravityPerTick { get; set; }
    public float VelocityRetention { get; set; }
    public int ReturnAfterTicks { get; set; }
    public float ReturnSpeed { get; set; }
    public float WaveAmplitude { get; set; }
    public float PhaseStrength { get; set; }
    public float Acceleration { get; set; }
    public float MaxSpeed { get; set; }
    public float TurnRadiansPerTick { get; set; }
    public float PullStrength { get; set; }
    public float ProximityRadiusPx { get; set; }
    public float ScalePerTick { get; set; }
    public float MaxScale { get; set; }
    public int Segments { get; set; }
    public int DurationTicks { get; set; }
    public float WidthPx { get; set; }
    public int WarmupTicks { get; set; }
    public int ChargeTicks { get; set; }
    public float PowerMultiplier { get; set; }
    public string ShotEntity { get; set; } = "";
    public int IntervalTicks { get; set; }
    public float SameTargetBias { get; set; }

    public void Normalize()
    {
        RangeTiles = Math.Clamp(RangeTiles, 0f, InfiniRuntimeLimits.MaxRuntimeRangeTiles);
        HomingStrength = Math.Clamp(HomingStrength, 0f, 1f);
        GravityPerTick = Math.Clamp(GravityPerTick, -2f, 2f);
        VelocityRetention = Math.Clamp(VelocityRetention, 0f, 1.2f);
        ReturnAfterTicks = Math.Clamp(ReturnAfterTicks, 0, 600);
        ReturnSpeed = Math.Clamp(ReturnSpeed, 0f, 250f);
        WaveAmplitude = Math.Clamp(WaveAmplitude, 0f, 96f);
        PhaseStrength = Math.Clamp(PhaseStrength, 0f, 1f);
        Acceleration = Math.Clamp(Acceleration, 0f, 4f);
        MaxSpeed = Math.Clamp(MaxSpeed, 0f, 250f);
        TurnRadiansPerTick = Math.Clamp(TurnRadiansPerTick, -1f, 1f);
        PullStrength = Math.Clamp(PullStrength, 0f, 4f);
        ProximityRadiusPx = Math.Clamp(ProximityRadiusPx, 0f, 512f);
        ScalePerTick = Math.Clamp(ScalePerTick, -0.2f, 0.5f);
        MaxScale = Math.Clamp(MaxScale, 0.1f, 8f);
        Segments = Math.Clamp(Segments, 0, 48);
        DurationTicks = Math.Clamp(DurationTicks, 0, 600);
        WidthPx = Math.Clamp(WidthPx, 0f, 192f);
        WarmupTicks = Math.Clamp(WarmupTicks, 0, 600);
        ChargeTicks = Math.Clamp(ChargeTicks, 0, 600);
        PowerMultiplier = Math.Clamp(PowerMultiplier, 0f, 4f);
        ShotEntity = RuntimeText.IdOptional(ShotEntity);
        IntervalTicks = Math.Clamp(IntervalTicks, 0, 3600);
        SameTargetBias = Math.Clamp(SameTargetBias, 0f, 1f);
    }
}

public sealed class RuntimeTargetingSpec
{
    public string ShotEntityId { get; set; } = "";
    public int IntervalTicks { get; set; }
    public float RangeTiles { get; set; }
    public float SameTargetBias { get; set; }
    public void Normalize()
    {
        ShotEntityId = RuntimeText.IdOptional(ShotEntityId);
        IntervalTicks = Math.Clamp(IntervalTicks, 0, 3600);
        RangeTiles = Math.Clamp(RangeTiles, 0f, InfiniRuntimeLimits.MaxRuntimeRangeTiles);
        SameTargetBias = Math.Clamp(SameTargetBias, 0f, 1f);
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
    public const int ChannelBeam = 1;
    public const int ChargeThenRelease = 2;
    public const int TargetAndFire = 3;
}

public static class RuntimeEventActionCode
{
    public const int SpawnEntity = 1;
    public const int ApplyStatus = 2;
    public const int DamageArea = 3;
    public const int ChainDamage = 4;
    public const int Pull = 5;
    public const int HealOwner = 6;
    public const int MoveOwner = 7;
}

public sealed class RuntimeEventActionSpec
{
    public string Id { get; set; } = "";
    public string Event { get; set; } = "";
    public string Action { get; set; } = "";
    public int ActionCode { get; set; }
    public string EntityId { get; set; } = "";
    public int Count { get; set; } = 1;
    public float SpreadRadians { get; set; }
    public float DamageMultiplier { get; set; } = 1f;
    public int DelayTicks { get; set; }
    public int PeriodTicks { get; set; }
    public int BuffId { get; set; } = -1;
    public int DurationTicks { get; set; }
    public int RadiusPx { get; set; }
    public float RangeTiles { get; set; }
    public string Mode { get; set; } = "";
    public float Strength { get; set; }
    public float RadiusTiles { get; set; }
    public float DamageFraction { get; set; }
    public int MaxHeal { get; set; }
    public int CooldownTicks { get; set; }
    public bool SafeTileOnly { get; set; } = true;

    public void NormalizeAndValidate()
    {
        Id = RuntimeText.Id(Id);
        Event = RuntimeText.Safe(Event, 32).ToLowerInvariant();
        Action = RuntimeText.Safe(Action, 64);
        EntityId = RuntimeText.IdOptional(EntityId);
        if (!RuntimeEventKind.IsKnown(Event))
            throw new InvalidDataException($"unknown runtime event '{Event}'");
        if (ActionCode < RuntimeEventActionCode.SpawnEntity || ActionCode > RuntimeEventActionCode.MoveOwner)
            throw new InvalidDataException($"unsupported event action opcode {ActionCode}");
        if (!string.Equals(Action, RuntimeOpcodeNames.EventActionName(ActionCode), StringComparison.Ordinal))
            throw new InvalidDataException($"event action name/opcode mismatch '{Action}'/{ActionCode}");
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
        if (Event == RuntimeEventKind.Periodic && PeriodTicks < 6)
            throw new InvalidDataException($"periodic event action '{Id}' requires periodTicks >= 6");
        if (ActionCode == RuntimeEventActionCode.SpawnEntity && string.IsNullOrWhiteSpace(EntityId))
            throw new InvalidDataException($"spawn event action '{Id}' has no entityId");
        if (ActionCode == RuntimeEventActionCode.ApplyStatus && (BuffId <= 0 || DurationTicks <= 0))
            throw new InvalidDataException($"status event action '{Id}' requires buffId and durationTicks");
        if (ActionCode == RuntimeEventActionCode.Pull && Mode is not ("target_to_owner" or "target_to_entity" or "owner_to_target"))
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
    public string ReleaseTiming { get; set; } = "";
    public int HoldoutOffsetX { get; set; }
    public int HoldoutOffsetY { get; set; }
    public void Normalize()
    {
        UseStyle = RuntimeText.Safe(UseStyle, 32).ToLowerInvariant();
        _ = TerrariaRuntimeVocabulary.ResolveItemUseStyle(UseStyle);
        HandPose = RuntimeText.Safe(HandPose, 32).ToLowerInvariant();
        ReleaseTiming = RuntimeText.Safe(ReleaseTiming, 32).ToLowerInvariant();
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
    private static readonly string[] MovementNames =
    {
        "move_straight", "move_slow_homing", "move_gravity_arc", "move_drift", "move_orbit",
        "move_boomerang", "move_bounce", "move_sine_homing", "move_phase", "move_accelerate",
        "move_spiral", "move_vortex_orb", "move_blackhole_pull", "move_proximity_missile",
        "move_returning_glaive", "move_expanding_wave", "move_flail_tether", "move_yoyo_hover",
        "move_whip_lash", "move_forward_then_retract",
    };
    private static readonly string[] ControllerNames = { "", "channel_beam", "charge_then_release", "target_and_fire" };
    private static readonly string[] EventNames =
    {
        "", "spawn_entity_on_event", "apply_status_on_event", "damage_area_on_event",
        "chain_damage_on_event", "pull_on_event", "heal_owner_on_event", "move_owner_on_event",
    };
    public static string MovementName(int code) => code >= 0 && code < MovementNames.Length ? MovementNames[code] : "";
    public static string ControllerName(int code) => code >= 0 && code < ControllerNames.Length ? ControllerNames[code] : "";
    public static string EventActionName(int code) => code >= 0 && code < EventNames.Length ? EventNames[code] : "";
}

internal static class RuntimeText
{
    public static string Safe(string? value, int maxLength)
    {
        string text = (value ?? "").Trim();
        return text.Length <= maxLength ? text : text[..maxLength];
    }
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

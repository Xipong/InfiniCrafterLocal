#nullable enable
using System;
using System.Collections.Generic;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Common.VFX;
using Terraria;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Players;

public sealed partial class InfiniCraftPlayer
{
    private const int MaxAirJumpSources = 32;
    private sealed record AirJumpGrant(GeneratedItemData Source, PlayerAirJumpSpec Movement,
        string Definition, long Generation, string Component);
    private readonly List<AirJumpGrant> _airJumpGrants = new();
    // Consumption belongs to an authored component of a definition, separately
    // from physical items or buff tokens. Keep it through the airborne interval.
    private readonly Dictionary<(string Item, string Definition, string Component), int> _airJumpRemaining = new();
    private AirJumpGrant? _activeAirJump;
    private int _activeAirJumpHoldTicks;
    private string _airJumpWorld = "";

    internal void ResetAirJumpGrants()
    {
        _airJumpGrants.Clear();
        if (!Player.active || Player.dead || _airJumpWorld != GeneratedItemRegistryService.CurrentWorldIdString())
            ClearAirJumpState();
        _airJumpWorld = GeneratedItemRegistryService.CurrentWorldIdString();
    }

    internal void RegisterAirJumpGrant(GeneratedItemData source, PlayerAirJumpSpec spec, long generation, string componentKey = "accessory")
    {
        spec.Validate();
        if (!Player.active || Player.dead || generation == 0 || !ValidAirJumpSource(source)
            || string.IsNullOrWhiteSpace(componentKey) || componentKey.Length > 128) return;
        var authored = AuthoredAirJumpComponent(source, componentKey);
        if (authored?.AirJump != spec || !authored.IsActive(Player)) return;
        string definition = GeneratedItemRegistryService.DefinitionIdentity(source);
        foreach (var existing in _airJumpGrants)
            if (existing.Source.Id == source.Id && existing.Definition == definition && existing.Component == componentKey) return;
        if (_airJumpGrants.Count >= MaxAirJumpSources) return;
        _airJumpGrants.Add(new(source, spec, definition, generation, componentKey));
        // Enable is deliberately separate from Available. Only native refresh
        // and OnStarted can grant availability, including when equipped midair.
        Player.GetJumpState<GeneratedAirJump>().Enable();
    }

    private static bool ValidAirJumpSource(GeneratedItemData source)
        => GeneratedItemRegistryService.IsCurrentWorldData(source)
            && !GeneratedItemData.IsPlayerSaveReferenceOnly(source)
            && !string.IsNullOrWhiteSpace(source.Id) && source.Id.Length <= 256;

    private static PlayerEffectSpec? AuthoredAirJumpComponent(GeneratedItemData source, string component)
    {
        bool equipped = source.RuntimeProgram.BindingForInput(RuntimeInputKind.Equipped)?.UsePolicy.Action.Kind
            == RuntimeBindingAction.EquipPassive;
        return component switch {
            "accessory" when equipped && source.Accessory.Enabled => source.Accessory.PlayerEffect,
            "armor" when equipped && source.Armor.Enabled => source.Armor.PlayerEffect,
            "buff" => source.Gameplay.GeneratedBuff?.PlayerEffect,
            _ when component.StartsWith("group:", StringComparison.Ordinal)
                => source.RuntimeProgram.TryGetEffectGroup(component[6..])?.GeneratedBuff?.PlayerEffect,
            _ => null,
        };
    }

    internal bool TryGetLiveAirJumpSource(string itemId, out GeneratedItemData data, out long generation, long? expectedGeneration = null)
    {
        foreach (var grant in _airJumpGrants)
            if (grant.Source.Id == itemId && (!expectedGeneration.HasValue || grant.Generation == expectedGeneration.Value)
                && ValidAirJumpSource(grant.Source))
            {
                data = grant.Source; generation = grant.Generation; return true;
            }
        data = null!; generation = 0; return false;
    }

    internal bool IsLiveAirJumpSource(GeneratedItemData source)
        => TryGetLiveAirJumpSource(source.Id, out var live, out _)
            && GeneratedItemRegistryService.DefinitionIdentity(source) == GeneratedItemRegistryService.DefinitionIdentity(live);

    private bool IsLiveAirJumpGrant(AirJumpGrant grant)
        => _airJumpGrants.Exists(live => live.Source.Id == grant.Source.Id
            && live.Definition == grant.Definition && live.Generation == grant.Generation && live.Component == grant.Component
            && ValidAirJumpSource(live.Source));

    private AirJumpGrant? NextGeneratedAirJump()
    {
        foreach (var grant in _airJumpGrants)
            if (ValidAirJumpSource(grant.Source)
                && _airJumpRemaining.TryGetValue((grant.Source.Id, grant.Definition, grant.Component), out int count) && count > 0)
                return grant;
        return null;
    }

    internal bool CanStartGeneratedAirJump() => Player.active && !Player.dead && NextGeneratedAirJump() is not null;

    internal float GeneratedAirJumpDurationMultiplier()
    {
        var grant = NextGeneratedAirJump();
        if (grant is null || Terraria.Player.jumpHeight <= 0) return 0f;
        // Native casts the product to int. Correct only a division roundoff
        // that would lose an authored tick, using the next representable value.
        // The loader still applies other mods' duration multiplier afterwards.
        int ticks = grant.Movement.HoldDurationTicks;
        float multiplier = (float)ticks / Terraria.Player.jumpHeight;
        if ((int)(Terraria.Player.jumpHeight * multiplier) < ticks) multiplier = MathF.BitIncrement(multiplier);
        return multiplier;
    }

    internal void RefreshGeneratedAirJumps()
    {
        _airJumpRemaining.Clear();
        foreach (var grant in _airJumpGrants)
            if (ValidAirJumpSource(grant.Source))
                _airJumpRemaining[(grant.Source.Id, grant.Definition, grant.Component)] = grant.Movement.Count;
    }

    internal void StartGeneratedAirJump(GeneratedAirJump jump)
    {
        var grant = NextGeneratedAirJump();
        if (grant is null) { Player.GetJumpState(jump).Available = false; return; }
        var key = (grant.Source.Id, grant.Definition, grant.Component);
        _airJumpRemaining[key]--;
        _activeAirJump = grant;
        _activeAirJumpHoldTicks = Math.Max(0, Player.jump);
        Player.velocity.Y = -grant.Movement.LaunchSpeedPxPerTick * Player.gravDir;
        // Reusable ExtraJump state is a native tML contract. Equipment updates
        // never assign this flag and newly equipped definitions have no ledger.
        Player.GetJumpState(jump).Available = NextGeneratedAirJump() is not null;
        InfiniItemVfxRuntime.EmitAndSyncJump(Player, grant.Source, Player.Center, grant.Generation);
    }

    internal void EndGeneratedAirJump()
    {
        _activeAirJump = null;
        _activeAirJumpHoldTicks = 0;
    }

    internal void ApplyGeneratedAirJumpHorizontalSpeeds()
    {
        if (_activeAirJump is not { } active || !IsLiveAirJumpGrant(active)) return;
        Player.runAcceleration *= active.Movement.HorizontalAccelerationMultiplier;
        Player.maxRunSpeed *= active.Movement.HorizontalSpeedMultiplier;
    }

    public override void PreUpdate()
    {
        // Stop before native JumpMovement's final speed assignment; otherwise
        // expiration would insert one vanilla-speed impulse after our last tick.
        if (_activeAirJump is not null && _activeAirJumpHoldTicks <= 0)
            Player.StopExtraJumpInProgress();
    }

    public override void PreUpdateMovement()
    {
        if (_activeAirJump is not { } active) return;
        if (!IsLiveAirJumpGrant(active)) { Player.StopExtraJumpInProgress(); return; }
        if (!Player.controlJump || Player.jump <= 0 || !Player.GetJumpState<GeneratedAirJump>().Active) return;
        // Native rewrites held velocity each tick using the common jump speed.
        // Apply this source's authored value after native movement and before
        // collision; native release, rope, mount and crowd-control stops remain.
        Player.velocity.Y = -active.Movement.LaunchSpeedPxPerTick * Player.gravDir;
        if (_activeAirJumpHoldTicks > 0) _activeAirJumpHoldTicks--;
    }

    internal void ClearAirJumpState()
    {
        _airJumpGrants.Clear();
        _airJumpRemaining.Clear();
        if (ModContent.GetInstance<GeneratedAirJump>() is { } jump && jump.Type < Player.ExtraJumps.Length)
        {
            if (Player.GetJumpState(jump).Active) Player.StopExtraJumpInProgress();
            Player.GetJumpState(jump).Available = false;
        }
        EndGeneratedAirJump();
    }
}

public sealed class GeneratedAirJumpLifecycleSystem : ModSystem
{
    private static void ClearPlayers()
    {
        foreach (var player in Main.player)
            if (player is not null && player.TryGetModPlayer<InfiniCraftPlayer>(out var owner)) owner.ClearAirJumpState();
    }
    public override void OnWorldUnload() => ClearPlayers();
    public override void Unload() => ClearPlayers();
}

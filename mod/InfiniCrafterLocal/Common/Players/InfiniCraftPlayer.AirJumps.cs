#nullable enable
using System;
using System.Collections.Generic;
using System.Linq;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Common.VFX;
using InfiniCrafterLocal.Content.Items;
using Terraria;
using Terraria.ModLoader;
using Terraria.ModLoader.Default;

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
    internal object AirJumpLifetime { get; private set; } = new();

    internal void ResetAirJumpGrants()
    {
        foreach (var expired in _finalTickAirJumpSources) RetireAirJumpPrediction(expired);
        _finalTickAirJumpSources.Clear();
        // A source snapshot/event can arrive before the first equipment pass.
        // Initializing the world marker must not retire that new attachment.
        if (!Player.active || Player.dead || (_airJumpWorld.Length > 0
            && _airJumpWorld != GeneratedItemRegistryService.CurrentWorldIdString()))
            ClearAirJumpState();
        else
            _airJumpGrants.Clear();
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
        => TryResolveAirJumpSource(itemId, out data, out generation, out _, expectedGeneration);

    // Presentation reads the synchronized source, not the last equipment pass.
    // This query never enables ExtraJump, applies a buff or refills its ledger.
    internal bool TryResolveAirJumpSource(string itemId, out GeneratedItemData data, out long generation,
        out object lifetime, long? expectedGeneration = null)
    {
        data = null!; generation = 0; lifetime = null!;
        if (!Player.active || Player.dead
            || Main.netMode == Terraria.ID.NetmodeID.MultiplayerClient && !IsCurrentAirJumpAuthority) return false;
        foreach (var active in _activeGeneratedUtilityBuffs.Concat(_finalTickAirJumpSources))
        {
            if ((active.Ticks <= 0 && active.SourceFinalTick != Main.GameUpdateCount)
                || active.SourceGeneration >= 0 || active.SourceItemId != itemId
                || expectedGeneration.HasValue && active.SourceGeneration != expectedGeneration.Value
                    && !(Main.netMode == Terraria.ID.NetmodeID.MultiplayerClient && Player.whoAmI == Main.myPlayer
                        && active.SourcePredictionGeneration < 0
                        && active.SourcePredictionGeneration == expectedGeneration.Value)
                || active.ResolveSource() is not { } source || !ValidAirJumpSource(source)
                || AuthoredAirJumpComponent(source, active.SourceComponent) is not { AirJump: not null } authored
                || !PlayerEffectSpec.SameEffect(authored, active.PlayerEffect) || !authored.IsActive(Player)) continue;
            data = source; generation = active.SourceGeneration; lifetime = active.SourceLifetime; return true;
        }
        if (expectedGeneration is <= 0) return false;
        foreach (var (item, component) in FunctionalAirJumpEquipment())
        {
            if (item is not { IsAir: false, ModItem: GeneratedItem generated }
                || generated.Data.Id != itemId || !ValidAirJumpSource(generated.Data)
                || generated.ExistingPresentationToken <= 0
                || expectedGeneration.HasValue && generated.ExistingPresentationToken != expectedGeneration.Value
                || AuthoredAirJumpComponent(generated.Data, component) is not { AirJump: not null } authored
                || !authored.IsActive(Player)) continue;
            data = generated.Data; generation = generated.ExistingPresentationToken;
            lifetime = generated.PresentationGeneration; return true;
        }
        return false;
    }

    internal bool TryGetAirJumpNetworkGeneration(string itemId, long localGeneration, out long generation)
    {
        generation = 0;
        if (!TryResolveAirJumpSource(itemId, out _, out long current, out var lifetime, localGeneration)) return false;
        if (current > 0) { generation = current; return true; }
        foreach (var active in _activeGeneratedUtilityBuffs.Concat(_finalTickAirJumpSources))
            if (ReferenceEquals(active.SourceLifetime, lifetime) && active.SourceAuthorityConfirmed)
            { generation = current; return true; }
        return false;
    }

    private void ConfirmAirJumpSourceGeneration(long predicted, long authoritative)
    {
        for (int index = 0; index < _airJumpGrants.Count; index++)
            if (_airJumpGrants[index].Generation == predicted)
                _airJumpGrants[index] = _airJumpGrants[index] with { Generation = authoritative };
        if (_activeAirJump?.Generation == predicted)
            _activeAirJump = _activeAirJump with { Generation = authoritative };
    }

    private IEnumerable<(Item Item, string Component)> FunctionalAirJumpEquipment()
    {
        for (int slot = 0; slot < Math.Min(10, Player.armor.Length); slot++)
            if (slot < 3 || Player.IsItemSlotUnlockedAndUsable(slot))
                yield return (Player.armor[slot], slot < 3 ? "armor" : "accessory");
        foreach (ModAccessorySlot slot in ModContent.GetContent<ModAccessorySlot>())
            if (FunctionalAirJumpAccessory(slot) is { } item)
                yield return (item, "accessory");
    }

    private Item? FunctionalAirJumpAccessory(ModAccessorySlot slot)
    {
        // CurrentPlayerOverride is a ref struct and cannot cross an iterator
        // boundary. Resolve the slot under the scope, return only its Item.
        using var current = new Main.CurrentPlayerOverride(Player);
        return slot.Type >= 0 && slot.Type < Player.GetModPlayer<ModAccessorySlotPlayer>().LoadedSlotCount
            && LoaderManager.Get<AccessorySlotLoader>().ModdedIsSpecificItemSlotUnlockedAndUsable(slot.Type, Player, false)
                ? slot.FunctionalItem : null;
    }

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

    internal void RunGeneratedAirJumpMovement(On_Player.orig_JumpMovement nativeMovement)
    {
        if (_activeAirJump is { } current)
        {
            if (!Player.GetJumpState<GeneratedAirJump>().Active) EndGeneratedAirJump();
            else if (_activeAirJumpHoldTicks <= 0 || !IsLiveAirJumpGrant(current))
                Player.StopExtraJumpInProgress();
        }
        // Scope the held impulse to its native consumer. PreUpdateMovement is
        // too late: replacing velocity there erases gravity, wing/gliding and
        // other movement already applied after JumpMovement. Never leave the
        // shared native jump speed changed for another player or native phase.
        bool customHold = _activeAirJump is not null && Player.controlJump && Player.jump > 0;
        float nativeSpeed = Terraria.Player.jumpSpeed;
        try
        {
            if (customHold) Terraria.Player.jumpSpeed = _activeAirJump!.Movement.LaunchSpeedPxPerTick;
            nativeMovement(Player);
            // Count the launch tick too, but not ticks where native movement
            // is skipped (rope/crowd control). Preserve native duration hooks.
            if (_activeAirJump is not null && Player.GetJumpState<GeneratedAirJump>().Active
                && Player.controlJump && _activeAirJumpHoldTicks > 0)
                _activeAirJumpHoldTicks--;
        }
        finally
        {
            if (customHold) Terraria.Player.jumpSpeed = nativeSpeed;
        }
    }

    internal void ClearAirJumpState()
    {
        // A retained short buff or the same equipped item can return after
        // death/world exit. Its old presentation binding must not revive.
        AirJumpLifetime = new();
        _airJumpPredictionFence = Guid.Empty;
        _airJumpPredictionServerFence = Guid.Empty;
        foreach (var active in _activeGeneratedUtilityBuffs.Concat(_finalTickAirJumpSources))
            RetireAirJumpPrediction(active);
        _finalTickAirJumpSources.Clear();
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
    public override void Load() => On_Player.JumpMovement += JumpMovement;

    internal static void JumpMovement(On_Player.orig_JumpMovement nativeMovement, Player player)
    {
        if (player.TryGetModPlayer<InfiniCraftPlayer>(out var owner)) owner.RunGeneratedAirJumpMovement(nativeMovement);
        else nativeMovement(player);
    }

    public override void PostUpdateEverything()
    {
        if (Main.netMode != Terraria.ID.NetmodeID.Server) return;
        foreach (var player in Main.player)
            if (player is not null && player.TryGetModPlayer<InfiniCraftPlayer>(out var owner))
                owner.CompleteAirJumpPredictionFence();
    }

    private static void ClearPlayers()
    {
        foreach (var player in Main.player)
            if (player is not null && player.TryGetModPlayer<InfiniCraftPlayer>(out var owner)) owner.RetireAirJumpAuthority();
    }
    public override void OnWorldUnload() => ClearPlayers();
    public override void Unload()
    {
        On_Player.JumpMovement -= JumpMovement;
        ClearPlayers();
    }
}

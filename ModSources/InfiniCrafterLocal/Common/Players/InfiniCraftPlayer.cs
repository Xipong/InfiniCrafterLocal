#nullable enable
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.Config;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;
using Terraria.ModLoader.IO;

namespace InfiniCrafterLocal.Common.Players;

public sealed partial class InfiniCraftPlayer : ModPlayer
{
    public const int CraftDurationTicks = 240 * 60;
    public const int CraftRecoveryTimeoutTicks = 20 * 60 * 60;
    public const int CraftRetryBackoffBaseTicks = 5 * 60;
    public const int CraftRetryBackoffMaxTicks = 20 * 60;
    public const int PostCraftAudioGuardTicks = 15 * 60;
    // Multiplayer crafting is server-authoritative via PacketRequestServerCraft;
    // clients never commit authoritative GeneratedItemData.
    public const byte PacketCraftCommitResult = InfiniNetPacketIds.CraftCommitResult;
    public const byte PacketRequestServerCraft = InfiniNetPacketIds.RequestServerCraft;
    public const byte PacketCancelServerCraft = InfiniNetPacketIds.CancelServerCraft;
    public const byte PacketSyncGeneratedUtilityBuff = InfiniNetPacketIds.SyncGeneratedUtilityBuff;
    public const int RemoteServerCraftTimeoutTicks = CraftRecoveryTimeoutTicks;

    private const int MaxServerCraftRequestCacheEntries = 2048;
    private static readonly Dictionary<string, string> ServerCommittedCraftRequests = new(StringComparer.Ordinal);
    private static readonly HashSet<string> ServerCancelledCraftRequests = new(StringComparer.Ordinal);
    private static readonly Queue<string> ServerCommittedCraftRequestOrder = new();
    private static readonly Queue<string> ServerCancelledCraftRequestOrder = new();
    private static readonly object ServerCommittedCraftRequestsLock = new();
    private static bool _inventoryPrefetchConfigWarningLogged;

    private GeneratorClient.PreparedGenerationRequest? _request;
    private Task<GeneratedItemData?>? _task;
    private int _ticksLeft;
    private int _elapsedTicks;
    private int _totalCraftTicks;
    private int _announceTick;
    private bool _lateMessageShown;
    private bool _awaitingServerCommit;
    private int _serverCraftWaitTicks;
    private int _retryWaitTicks;
    private int _generationAttempt;
    private int _lastRetryNoticeTick;
    private int _lastGeneratorOfflineNoticeTick;
    private string _serverRequestId = "";
    private string _label = "";
    private readonly List<Item> _deferredExitRefunds = new();
    private bool _pendingRefundSavedForWorldExit;
    private float _craftSoundVolumeSnapshot = -1f;
    private float _craftMusicVolumeSnapshot = -1f;
    private float _craftAmbientVolumeSnapshot = -1f;
    private float _lastGoodSoundVolume = -1f;
    private float _lastGoodMusicVolume = -1f;
    private float _lastGoodAmbientVolume = -1f;
    private int _craftAudioGuardTicks;
    private int _registrySyncRetryTicks;
    private int _registrySyncRetryStep;
    private int _generatedBuffTicks;
    private readonly List<ActiveGeneratedUtilityBuff> _activeGeneratedUtilityBuffs = new();
    private float _generatedMiningSpeedMultiplier = 1f;
    private float _generatedLightStrength;
    private string _generatedLightColorName = "";
    private int _generatedOreSenseRadiusTiles;
    private float _generatedMovementSpeed;
    private float _generatedJumpBoost;
    private int _generatedManaRegen;
    private int _generatedLifeRegen;
    private int _generatedMobilityCooldownTicks;
    private float _generatedAmmoSaveChance;
    private string _lastGeneratedMobilityFailureMessage = "";
    private int _heldItemPresentationSyncTick;
    private string _heldItemPresentationSyncKey = "";
    private int _inventoryAssetPrefetchTicks;

    public Item InputA = new();
    public Item InputB = new();

    public bool HasPendingCraft => _request is not null || _task is not null || _awaitingServerCommit;
    public bool HasInputA => InputA is not null && !InputA.IsAir;
    public bool HasInputB => InputB is not null && !InputB.IsAir;
    public bool HasAnyInput => HasInputA || HasInputB;
    public bool HasStationState => HasPendingCraft || HasAnyInput;
    public bool CanStartStationCraft => !HasPendingCraft && HasInputA && HasInputB;
    public int TicksLeft => Math.Max(0, _ticksLeft);
    public int ElapsedTicks => Math.Clamp(_elapsedTicks, 0, CraftDurationTicks);
    public float CraftProgress => HasPendingCraft ? Math.Clamp(_elapsedTicks / (float)CraftDurationTicks, 0f, 1f) : 0f;
    public bool IsWaitingForModel => HasPendingCraft && _elapsedTicks >= CraftDurationTicks && (_task is null || !_task.IsCompleted);
    public bool IsWaitingForRetry => _request is not null && _task is null && !_awaitingServerCommit && _retryWaitTicks > 0;
    public int RetrySecondsLeft => Math.Max(0, (int)Math.Ceiling(_retryWaitTicks / 60f));
    public int GenerationAttempt => Math.Max(0, _generationAttempt);
    public int GeneratedMobilityCooldownTicks => Math.Max(0, _generatedMobilityCooldownTicks);
    public int GeneratedMobilityCooldownSeconds => Math.Max(0, (int)Math.Ceiling(GeneratedMobilityCooldownTicks / 60f));
    public string LastGeneratedMobilityFailureMessage => string.IsNullOrWhiteSpace(_lastGeneratedMobilityFailureMessage) ? "Generated mobility failed" : _lastGeneratedMobilityFailureMessage;

    public override void ResetEffects()
    {
        // Equipment hooks run again every tick. Keep the generated chance exact
        // and rebuild it from the currently equipped authored items instead of
        // converting it to one of Terraria's coarse 20%/25% flags.
        _generatedAmmoSaveChance = 0f;
    }

    public void AddGeneratedAmmoSaveChance(float chance)
    {
        chance = Math.Clamp(chance, 0f, 0.9999f);
        if (chance <= 0f)
            return;
        _generatedAmmoSaveChance = 1f - ((1f - _generatedAmmoSaveChance) * (1f - chance));
    }

    public override bool CanConsumeAmmo(Item weapon, Item ammo)
    {
        if (_generatedAmmoSaveChance <= 0f)
            return true;
        return Main.rand.NextFloat() >= _generatedAmmoSaveChance;
    }


    public string CraftLabel => string.IsNullOrWhiteSpace(_label) ? "InfiniCraft" : _label;


    private void TickGeneratedInventoryAssetPrefetch()
    {
        if (Main.dedServ || !Main.playerInventory || Player.whoAmI != Main.myPlayer)
            return;

        InfiniGameplayQolConfig? config = null;
        try { config = ModContent.GetInstance<InfiniGameplayQolConfig>(); }
        catch (Exception ex)
        {
            if (!_inventoryPrefetchConfigWarningLogged)
            {
                _inventoryPrefetchConfigWarningLogged = true;
                try { global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance?.Logger?.Warn($"[InfiniCraftPlayer] InfiniGameplayQolConfig unavailable; inventory asset prefetch will use safe defaults: {ex.GetType().Name}: {ex.Message}"); } catch { }
            }
        }
        if (config is not null && !config.EnableInventoryAssetPrefetch)
            return;

        int interval = Math.Clamp(config?.InventoryAssetPrefetchIntervalTicks ?? 120, 30, 600);
        if (_inventoryAssetPrefetchTicks > 0)
        {
            _inventoryAssetPrefetchTicks--;
            return;
        }
        _inventoryAssetPrefetchTicks = interval;

        int maxItems = Math.Clamp(config?.InventoryAssetPrefetchMaxItems ?? 24, 4, 64);
        int ensured = 0;
        foreach (Item item in GeneratedPrefetchCandidateItems(Player))
        {
            if (ensured >= maxItems)
                break;
            var data = GeneratedDataFromItem(item);
            if (data is null || string.IsNullOrWhiteSpace(data.Id) || string.Equals(data.Id, "placeholder", StringComparison.OrdinalIgnoreCase))
                continue;
            try
            {
                global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems?.RegisterLocal(data, persist: true, ensureAssets: true);
                ensured++;
            }
            catch { }
        }
    }

    private static IEnumerable<Item> GeneratedPrefetchCandidateItems(Player player)
    {
        foreach (Item item in ItemsFromArray(player?.inventory)) yield return item;
        foreach (Item item in ItemsFromArray(player?.armor)) yield return item;
        foreach (Item item in ItemsFromArray(player?.miscEquips)) yield return item;
    }

    private static IEnumerable<Item> ItemsFromArray(Item[]? items)
    {
        if (items is null) yield break;
        foreach (Item item in items)
        {
            if (item is not null && !item.IsAir)
                yield return item;
        }
    }

    private static GeneratedItemData? GeneratedDataFromItem(Item? item)
    {
        if (item is null || item.IsAir) return null;
        if (item.ModItem is GeneratedItem generated) return generated.Data;
        if (item.ModItem is GeneratedExtractinatorMaterial material) return material.Data;
        return null;
    }

    private void TickGeneratedRegistryCatchup()
    {
        if (Main.netMode != NetmodeID.MultiplayerClient || _registrySyncRetryTicks <= 0)
            return;
        _registrySyncRetryTicks--;
        if (_registrySyncRetryTicks > 0)
            return;

        global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems?.RequestFullSyncFromServer();
        _registrySyncRetryStep++;
        _registrySyncRetryTicks = _registrySyncRetryStep switch
        {
            1 => 10 * 60,
            2 => 30 * 60,
            _ => 0,
        };
    }
}

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

// AGENT MAP: local craft lifecycle and recovery state machine.
// Owns in-flight generator task, retry/cache recovery, refunds, and commit cleanup.
// It should call GeneratorClient/registry services; it should not author gameplay
// or accept client-generated authoritative data.
public sealed partial class InfiniCraftPlayer
{
    private static string NormalizeCraftRequestId(string? requestId)
        => (requestId ?? string.Empty).Trim();

    private static bool HasCraftRequestId(string? requestId)
        => NormalizeCraftRequestId(requestId).Length > 0;

    private static bool IsValidIncomingCraftItemType(int type)
        => type > ItemID.None;

    private static bool HasReforgePrefix(int prefix)
        => prefix != InfiniTerrariaSentinels.NoPrefix;

    private static int NormalizeCraftStack(int stack)
        => stack < 1 ? 1 : stack;


    public override void Initialize()
    {
        InputA = NewAirItem();
        InputB = NewAirItem();
    }

    public override void OnEnterWorld()
    {
        if (InputA is null) InputA = NewAirItem();
        if (InputB is null) InputB = NewAirItem();
        // Late-join catch-up: make sure this client has the generated-item registry
        // before it sees someone else use an already-crafted item.
        global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems?.RequestFullSyncFromServer();
        _registrySyncRetryTicks = 5 * 60;
        _registrySyncRetryStep = 0;
        RememberPositiveAudioSettings();
        RestoreDeferredExitRefunds();
    }

    public override void SaveData(TagCompound tag)
    {
        _pendingRefundSavedForWorldExit = false;
        try
        {
            var refunds = PendingRefundTagsForSave();
            if (refunds.Count <= 0)
                return;

            tag["infiniPendingCraftRefunds"] = refunds;
            tag["infiniPendingCraftLabel"] = CraftLabel;
            _pendingRefundSavedForWorldExit = true;
        }
        catch
        {
            // Never let the station refund backup corrupt/brick the player file.
            _pendingRefundSavedForWorldExit = false;
        }
    }

    public override void LoadData(TagCompound tag)
    {
        _deferredExitRefunds.Clear();
        try
        {
            if (!tag.ContainsKey("infiniPendingCraftRefunds"))
                return;

            foreach (var itemTag in tag.GetList<TagCompound>("infiniPendingCraftRefunds"))
            {
                try
                {
                    Item item = ItemIO.Load(itemTag);
                    if (item is not null && !item.IsAir && item.stack > 0)
                        _deferredExitRefunds.Add(item.Clone());
                }
                catch
                {
                    // Ignore corrupted refund entries; normal inventory loading must not break.
                }
            }
        }
        catch
        {
            _deferredExitRefunds.Clear();
        }
    }

    private List<TagCompound> PendingRefundTagsForSave()
    {
        var refunds = new List<TagCompound>();

        if (HasPendingCraft && _request is not null)
        {
            AddRefundTag(refunds, _request.RefundA);
            AddRefundTag(refunds, _request.RefundB);
            return refunds;
        }

        if (HasInputA) AddRefundTag(refunds, InputA);
        if (HasInputB) AddRefundTag(refunds, InputB);
        return refunds;
    }

    private static void AddRefundTag(List<TagCompound> refunds, Item item)
    {
        if (item is null || item.IsAir || item.stack <= 0)
            return;
        Item saved = item.Clone();
        saved.stack = Math.Max(1, saved.stack);
        refunds.Add(ItemIO.Save(saved));
    }

    private void RestoreDeferredExitRefunds()
    {
        if (_deferredExitRefunds.Count <= 0)
            return;

        int count = 0;
        foreach (Item item in _deferredExitRefunds)
        {
            if (item is null || item.IsAir || item.stack <= 0)
                continue;
            RefundOne(item);
            count++;
        }
        _deferredExitRefunds.Clear();
        if (count > 0)
            CombatText.NewText(Player.Hitbox, Color.LightSkyBlue, $"InfiniCraft: возвращены предметы незавершённого крафта x{count}");
    }

    public bool BeginCraft(GeneratorClient.PreparedGenerationRequest request, string label)
    {
        if (HasPendingCraft)
            return false;

        CaptureAudioSettingsSnapshot();

        _request = request;
        _label = label;
        _ticksLeft = CraftDurationTicks;
        _elapsedTicks = 0;
        _totalCraftTicks = 0;
        _announceTick = 0;
        _lateMessageShown = false;
        _awaitingServerCommit = false;
        _serverCraftWaitTicks = 0;

        // Only the HTTP call runs in the background. Item/Projectile introspection has already
        // happened on the main thread while building PreparedGenerationRequest.
        _generationAttempt = 0;
        _retryWaitTicks = 0;
        _lastRetryNoticeTick = 0;
        _lastGeneratorOfflineNoticeTick = 0;
        StartGenerationTask("initial");
        CombatText.NewText(Player.Hitbox, Color.Cyan, "InfiniCraft: крафт до 240с, выдача по готовности");
        return true;
    }

    private void StartGenerationTask(string reason)
    {
        var request = _request;
        if (request is null)
            return;
        _generationAttempt++;
        _retryWaitTicks = 0;
        _task = Task.Run(() => global::InfiniCrafterLocal.InfiniCrafterLocalMod.Generator.GeneratePreparedBlocking(request));
        if (_generationAttempt > 1)
            CombatText.NewText(Player.Hitbox, Color.LightSkyBlue, $"InfiniCraft: повторный запрос #{_generationAttempt}");
    }

    private void ScheduleEarlyRetry(string reason)
    {
        _task = null;
        int backoff = Math.Min(CraftRetryBackoffMaxTicks, CraftRetryBackoffBaseTicks + Math.Max(0, _generationAttempt - 1) * 3 * 60);
        _retryWaitTicks = Math.Max(60, backoff);
        if (_lastRetryNoticeTick <= 0 || _totalCraftTicks - _lastRetryNoticeTick >= 10 * 60)
        {
            _lastRetryNoticeTick = _totalCraftTicks;
            CombatText.NewText(Player.Hitbox, Color.Orange, $"InfiniCraft: ждём готовый рецепт / cache retry через {RetrySecondsLeft}с");
        }
    }

    private void ScheduleGeneratorOfflineRetry(string reason)
    {
        _task = null;
        _retryWaitTicks = Math.Max(30 * 60, _retryWaitTicks);
        // Keep this low-noise: cache recovery can briefly see the endpoint cooling
        // down even when the item is generated successfully a moment later. Do not
        // spam the player with the port number every retry tick.
        if (_totalCraftTicks >= 15 * 60 && (_lastGeneratorOfflineNoticeTick <= 0 || _totalCraftTicks - _lastGeneratorOfflineNoticeTick >= 60 * 60))
        {
            _lastGeneratorOfflineNoticeTick = _totalCraftTicks;
            CombatText.NewText(Player.Hitbox, Color.Orange, $"InfiniCraft: LocalGenerator временно недоступен — тихий retry через {RetrySecondsLeft}с");
        }
    }


    public override void PostUpdate()
    {
        TickCraftAudioGuard();
        TickGeneratedUtilityBuff();
        TickGeneratedRegistryCatchup();
        TickGeneratedInventoryAssetPrefetch();
        GeneratedHeldItemDrawLayer.MaybeBroadcastLocalHeldItem(Player, ref _heldItemPresentationSyncTick, ref _heldItemPresentationSyncKey);

        if (!Main.playerInventory && !HasPendingCraft && HasAnyInput)
            ReturnStationInputs();

        if (_awaitingServerCommit)
        {
            // Multiplayer clients do not run LocalGenerator and do not submit GeneratedItemData.
            // This state only waits for the authoritative host to finish PacketRequestServerCraft.
            _serverCraftWaitTicks++;
            _totalCraftTicks++;
            if (_elapsedTicks < CraftDurationTicks)
                _elapsedTicks++;
            _ticksLeft = Math.Max(0, CraftDurationTicks - _elapsedTicks);
            if (_serverCraftWaitTicks == 2 * 60)
                CombatText.NewText(Player.Hitbox, Color.LightSkyBlue, "InfiniCraft: хост генерирует предмет");
            if (_serverCraftWaitTicks >= RemoteServerCraftTimeoutTicks)
            {
                SendRemoteServerCraftCancel("client_timeout");
                CombatText.NewText(Player.Hitbox, Color.OrangeRed, "InfiniCraft: хост не завершил генерацию — запрос отменён");
                ClearCraft();
            }
            return;
        }

        if (_request is null && _task is null)
            return;

        _totalCraftTicks++;
        if (_elapsedTicks < CraftDurationTicks)
            _elapsedTicks++;
        _ticksLeft = Math.Max(0, CraftDurationTicks - _elapsedTicks);
        _announceTick++;

        if (_task is null)
        {
            if (_retryWaitTicks > 0)
            {
                _retryWaitTicks--;
                if (_retryWaitTicks <= 0)
                    StartGenerationTask("early_retry");
                return;
            }

            if (_request is not null && _totalCraftTicks < CraftRecoveryTimeoutTicks)
            {
                if (global::InfiniCrafterLocal.InfiniCrafterLocalMod.Generator?.IsEndpointCoolingDown == true)
                {
                    ScheduleGeneratorOfflineRetry("endpoint_cooldown");
                    return;
                }
                StartGenerationTask("missing_task_retry");
                return;
            }

            FailCraft("InfiniCraft: генератор не завершил крафт — предметы возвращены", "генератор хоста не завершил крафт");
            return;
        }

        // Give the item as soon as the background craft is ready. The 240s timer is a
        // progress estimate/upper UI bar, not an artificial delay.
        if (!_task.IsCompleted)
        {
            // CombatText is now only a low-noise fallback. The inventory station UI is the primary timer.
            if (_ticksLeft > 0 && _announceTick >= 15 * 60)
            {
                _announceTick = 0;
                CombatText.NewText(Player.Hitbox, Color.LightSkyBlue, $"InfiniCraft: до {Math.Ceiling(_ticksLeft / 60f)}с");
            }
            if (_ticksLeft <= 0 && !_lateMessageShown)
            {
                _lateMessageShown = true;
                CombatText.NewText(Player.Hitbox, Color.Orange, "InfiniCraft: модель ещё думает / возможен retry");
            }
            return;
        }

        GeneratedItemData? data = null;
        try
        {
            data = _task.Result;
        }
        catch
        {
            data = null;
        }

        if (data is null)
        {
            var generator = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Generator;
            if (generator?.LastRecipeFailureIsFatal == true)
            {
                string detail = generator.LastRecipeFailureStatusCode > 0
                    ? $"HTTP {generator.LastRecipeFailureStatusCode}"
                    : "ошибка рецепта";
                if (!string.IsNullOrWhiteSpace(generator.LastRecipeFailureMessage))
                    detail += $": {generator.LastRecipeFailureMessage}";
                string playerMessage = !string.IsNullOrWhiteSpace(generator.LastRecipeFailurePlayerMessage)
                    ? generator.LastRecipeFailurePlayerMessage
                    : "InfiniCraft: рецепт не прошёл проверку — предметы возвращены; попробуй скрафтить заново";
                FailCraft(playerMessage, detail);
                return;
            }

            if (_request is not null && _totalCraftTicks < CraftRecoveryTimeoutTicks)
            {
                if (generator?.IsEndpointCoolingDown == true)
                {
                    ScheduleGeneratorOfflineRetry("endpoint_cooldown_after_null");
                    return;
                }
                ScheduleEarlyRetry("null_result_recovery");
                return;
            }

            FailCraft("InfiniCraft: генератор не отдал готовый рецепт — предметы возвращены", "генератор хоста не отдал готовый предмет");
            return;
        }

        SpawnGeneratedItem(data);
    }


    private void FailCraft(string localMessage, string remoteMessage)
    {
        if (IsServerAuthoritativeCraft)
        {
            RefundIngredients();
            SendServerAuthoritativeResultIfNeeded(false, "", remoteMessage);
            ClearCraft();
            return;
        }

        RefundIngredients();
        CombatText.NewText(Player.Hitbox, Color.OrangeRed, localMessage);
        ClearCraft();
    }


    private void SpawnGeneratedItem(GeneratedItemData data)
    {
        // Multiplayer craft is server-authoritative. A client must never commit
        // GeneratedItemData to the host; if this path is reached on a client, an old
        // local-generation flow leaked back in, so fail closed and refund.
        if (Main.netMode == NetmodeID.MultiplayerClient)
        {
            FailCraft("InfiniCraft: клиентский коммит отключён — предметы возвращены", "client-generated commit path is disabled");
            return;
        }

        if (IsServerAuthoritativeCraft && IsServerCraftCancelled(Player.whoAmI, _serverRequestId))
        {
            RefundIngredients();
            SendServerAuthoritativeResultIfNeeded(false, "", "server craft request was cancelled");
            ClearCraft();
            return;
        }

        if (SpawnGeneratedItemServerSide(Player, data, out string error))
        {
            SendServerAuthoritativeResultIfNeeded(true, data.Name, "ok");
            RunLocalCraftReveal(Player, data);
            ClearCraft();
            return;
        }

        FailCraft("InfiniCraft: серверный коммит сорвался — предметы возвращены", string.IsNullOrWhiteSpace(error) ? "хост не создал предмет" : error);
    }


    public void AbortTransientCraftForWorldExit()
    {
        // World exit/unload must not eat station inputs or in-flight craft ingredients.
        // If SaveData already persisted a refund bundle, do not also put the same items
        // into inventory here; they will be restored by LoadData/OnEnterWorld.
        if (!_pendingRefundSavedForWorldExit)
        {
            if (_awaitingServerCommit)
                SendRemoteServerCraftCancel("client_world_exit");
            else if (HasPendingCraft)
                RefundIngredients();

            if (HasInputA || HasInputB)
                ReturnStationInputs();
        }

        ClearCraft();
    }


    private void CaptureAudioSettingsSnapshot()
    {
        RememberPositiveAudioSettings();
        _craftSoundVolumeSnapshot = PositiveOrFallback(ReadMainFloatSetting("soundVolume"), _lastGoodSoundVolume);
        _craftMusicVolumeSnapshot = PositiveOrFallback(ReadMainFloatSetting("musicVolume"), _lastGoodMusicVolume);
        _craftAmbientVolumeSnapshot = PositiveOrFallback(ReadMainFloatSetting("ambientVolume"), _lastGoodAmbientVolume);
        _craftAudioGuardTicks = Math.Max(_craftAudioGuardTicks, PostCraftAudioGuardTicks);
    }

    private void RestoreSuspiciousAudioMute()
    {
        // Some external/edge craft paths have been observed to leave Terraria's global
        // audio sliders at 0 after a generation finishes. This guard is intentionally
        // narrow: it only restores a setting if it was positive at craft start and is
        // now exactly/suspiciously muted. It does not normalize volumes or touch item
        // sound profiles.
        RestoreMainFloatIfSuspiciouslyMuted("soundVolume", _craftSoundVolumeSnapshot);
        RestoreMainFloatIfSuspiciouslyMuted("musicVolume", _craftMusicVolumeSnapshot);
        RestoreMainFloatIfSuspiciouslyMuted("ambientVolume", _craftAmbientVolumeSnapshot);
        // Keep snapshots alive for a short post-craft window. Some resets happen one
        // or more frames after ClearCraft(), so a single restore at finish was not enough.
    }

    private static float PositiveOrFallback(float current, float fallback)
    {
        if (current > 0.001f)
            return current;
        return fallback > 0.001f ? fallback : current;
    }

    private void RememberPositiveAudioSettings()
    {
        RememberPositiveAudioSetting("soundVolume", ref _lastGoodSoundVolume);
        RememberPositiveAudioSetting("musicVolume", ref _lastGoodMusicVolume);
        RememberPositiveAudioSetting("ambientVolume", ref _lastGoodAmbientVolume);
    }

    private static void RememberPositiveAudioSetting(string name, ref float cache)
    {
        float v = ReadMainFloatSetting(name);
        if (v > 0.001f)
            cache = v;
    }

    private void TickCraftAudioGuard()
    {
        bool active = HasPendingCraft || _craftAudioGuardTicks > 0;
        if (!active)
        {
            RememberPositiveAudioSettings();
            return;
        }

        RestoreSuspiciousAudioMute();
        if (!HasPendingCraft && _craftAudioGuardTicks > 0)
            _craftAudioGuardTicks--;

        if (!HasPendingCraft && _craftAudioGuardTicks <= 0)
        {
            _craftSoundVolumeSnapshot = -1f;
            _craftMusicVolumeSnapshot = -1f;
            _craftAmbientVolumeSnapshot = -1f;
            RememberPositiveAudioSettings();
        }
    }

    private static float ReadMainFloatSetting(string name)
    {
        float main = ReadStaticFloat(typeof(Main), name);
        if (main >= 0f)
            return main;

        // Some tML/audio paths expose the SFX slider through SoundEngine rather
        // than Main.soundVolume.  Reflection keeps this compatible across tML
        // builds and avoids compile-time dependency on a specific property shape.
        if (string.Equals(name, "soundVolume", StringComparison.OrdinalIgnoreCase))
        {
            foreach (string alt in new[] { "SoundVolume", "soundVolume", "Volume" })
            {
                float v = ReadStaticFloat(typeof(Terraria.Audio.SoundEngine), alt);
                if (v >= 0f)
                    return v;
            }
        }
        return -1f;
    }

    private static float ReadStaticFloat(Type type, string name)
    {
        const System.Reflection.BindingFlags flags = System.Reflection.BindingFlags.Static | System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic;
        try
        {
            var field = type.GetField(name, flags);
            if (field is not null && field.GetValue(null) is float fv)
                return fv;

            var prop = type.GetProperty(name, flags);
            if (prop is not null && prop.GetValue(null) is float pv)
                return pv;
        }
        catch { }
        return -1f;
    }

    private static void RestoreMainFloatIfSuspiciouslyMuted(string name, float snapshot)
    {
        if (snapshot <= 0.001f)
            return;

        RestoreStaticFloatIfSuspiciouslyMuted(typeof(Main), name, snapshot);
        if (string.Equals(name, "soundVolume", StringComparison.OrdinalIgnoreCase))
        {
            foreach (string alt in new[] { "SoundVolume", "soundVolume", "Volume" })
                RestoreStaticFloatIfSuspiciouslyMuted(typeof(Terraria.Audio.SoundEngine), alt, snapshot);
        }
    }

    private static void RestoreStaticFloatIfSuspiciouslyMuted(Type type, string name, float snapshot)
    {
        const System.Reflection.BindingFlags flags = System.Reflection.BindingFlags.Static | System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic;
        try
        {
            var field = type.GetField(name, flags);
            if (field is not null && field.GetValue(null) is float current)
            {
                if (current <= 0.001f)
                    field.SetValue(null, Math.Clamp(snapshot, 0f, 1f));
                return;
            }

            var prop = type.GetProperty(name, flags);
            if (prop is not null && prop.CanWrite && prop.GetValue(null) is float currentProp && currentProp <= 0.001f)
                prop.SetValue(null, Math.Clamp(snapshot, 0f, 1f));
        }
        catch { }
    }

    private void ClearCraft()
    {
        RestoreSuspiciousAudioMute();
        _craftAudioGuardTicks = Math.Max(_craftAudioGuardTicks, PostCraftAudioGuardTicks);

        _request = null;
        _task = null;
        _ticksLeft = 0;
        _elapsedTicks = 0;
        _totalCraftTicks = 0;
        _announceTick = 0;
        _lateMessageShown = false;
        _retryWaitTicks = 0;
        _generationAttempt = 0;
        _lastRetryNoticeTick = 0;
        _lastGeneratorOfflineNoticeTick = 0;
        _awaitingServerCommit = false;
        _serverCraftWaitTicks = 0;
        _serverRequestId = "";
        _label = "";
        _pendingRefundSavedForWorldExit = false;
    }

}

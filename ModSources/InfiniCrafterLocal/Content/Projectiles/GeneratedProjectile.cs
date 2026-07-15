#nullable enable
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.Audio;
using InfiniCrafterLocal.Common.VFX;
using InfiniCrafterLocal.Common.Services;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Terraria;
using Terraria.DataStructures;
using Terraria.ID;
using Terraria.Audio;
using Terraria.GameContent;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Content.Projectiles;

public sealed partial class GeneratedProjectile : ModProjectile
{

    // =============================================================================
    // NAV TOC: GeneratedProjectile.cs
    // =============================================================================
    // NAV: PROJECTILE_STATE_AND_CONFIG        generated spec / vfx manifest / local runtime state
    // NAV: PROJECTILE_DEFAULTS_AND_NETWORK   tML defaults, SendExtraAI/ReceiveExtraAI contract
    // NAV: PROJECTILE_AI_MAIN_LOOP           AI(), family runtime behaviours and movement executors
    // NAV: PROJECTILE_COLLISION_AND_HIT      Colliding, hitbox modifiers, OnHit, gameplay effects
    // NAV: PROJECTILE_CHILD_AND_OVERLAY      real children, visual overlays, split/chain/burst helpers
    // NAV: PROJECTILE_DRAWING                PreDraw, generated sprites, fallback visual drawing
    // NAV: PROJECTILE_KILL_AND_DECAY         OnKill and kill/decay VFX handoff
    // =============================================================================
    public override string Texture => "InfiniCrafterLocal/Assets/GeneratedProjectile";


// =============================================================================
// NAV: PROJECTILE_STATE_AND_CONFIG
// =============================================================================
    private AttackSpec _spec = new();
    private VfxManifestSpec _vfxManifest = new();
    private InfiniVfxState _vfxState = new();
    private bool _configured;
    private bool _statsApplied;
    private int _remainingBounces;
    private bool _returningPhase;
    private bool _orbitInitialized;
    private float _orbitStartAngle;
    private float _orbitStartRadius;
    private bool _procced;
    private bool _expireSecondariesSpawned;
    private int _spawnedGameplayChildCount;
    private bool _stuckToTile;
    private bool _impactMobilityUsed;
    private string _generatedItemId = "";
    private string _lastReceivedVfxManifestJson = "";
    private int _spawnIgnoreNpc = -1;
    private int _spawnIgnoreTicks = 0;
    private int _lastImpactSoundLocalTick = -9999;
    private float _beamLengthPx;
    private int _beamBaseDamage;
    private bool _beamBaseDamageInitialized;
    private bool _chargeReleaseFired;
    private int _chargeTicksAccumulated;
    private int _sentryFireTimer;
    private bool _whipInitialized;
    private Vector2 _whipBaseDirection;
    private readonly List<Vector2> _whipControlPoints = new(24);
    private readonly float[] _beamScanSamples = new float[3];
    private static readonly Dictionary<string, int> WarningLogTicks = new(StringComparer.Ordinal);

    internal bool IsActiveBeamFor(string? generatedItemId)
        => Projectile.active
            && _configured
            && IsBeamDelivery()
            && !string.IsNullOrWhiteSpace(generatedItemId)
            && string.Equals(_generatedItemId, generatedItemId.Trim(), StringComparison.Ordinal);

    internal bool IsActiveChargeFor(string? generatedItemId)
        => Projectile.active
            && _configured
            && IsChargeReleaseDelivery()
            && !string.IsNullOrWhiteSpace(generatedItemId)
            && string.Equals(_generatedItemId, generatedItemId.Trim(), StringComparison.Ordinal);

    internal bool IsGeneratedWhipTagSource => _configured && IsWhipDelivery();

    private static void RequestProjectileAssetCatchupIfMissing(string? spritePath, string? generatedItemId = null)
    {
        if (Main.netMode != NetmodeID.MultiplayerClient || !HasPngPath(spritePath))
            return;
        string key = !string.IsNullOrWhiteSpace(generatedItemId)
            ? ("item:" + generatedItemId.Trim())
            : ("asset:" + GeneratedAssetSyncService.FileNameFromPath(spritePath));
        if (string.IsNullOrWhiteSpace(key) || key == "asset:")
            return;
        int now = (int)Main.GameUpdateCount;
        lock (MissingProjectileAssetRequestTicks)
        {
            if (MissingProjectileAssetRequestTicks.TryGetValue(key, out int last) && now - last < MissingProjectileAssetRetryTicks)
                return;
            PruneTickMapLocked(MissingProjectileAssetRequestTicks, now, MaxMissingRequestStateEntries, MissingRequestStateAgeTicks, key);
            MissingProjectileAssetRequestTicks[key] = now;
        }
        if (!string.IsNullOrWhiteSpace(generatedItemId))
            global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems?.RequestOneFromServer(generatedItemId.Trim(), forceAssetRetry: true);
        else
            global::InfiniCrafterLocal.InfiniCrafterLocalMod.GeneratedItems?.RequestFullSyncFromServer(forceAssetRetry: true);
    }


// =============================================================================
// NAV: PROJECTILE_AI_MAIN_LOOP
// =============================================================================











}

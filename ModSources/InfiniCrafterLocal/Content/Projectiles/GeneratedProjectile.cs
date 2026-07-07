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
    private bool _procced;
    private bool _stuckToTile;
    private bool _impactMobilityUsed;
    private string _generatedItemId = "";
    private string _lastReceivedVfxManifestJson = "";
    private int _spawnIgnoreNpc = -1;
    private int _spawnIgnoreTicks = 0;
    private int _lastImpactSoundLocalTick = -9999;
    private static readonly Dictionary<string, int> WarningLogTicks = new(StringComparer.Ordinal);




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

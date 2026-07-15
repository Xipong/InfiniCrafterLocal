from __future__ import annotations

from pathlib import Path

from csharp_partial_reader import read_text_with_partial_bundles
ROOT = Path(__file__).resolve().parents[2]


def _check_csharp_generated_item_data_keeps_runtime_api_and_debug_delivery_guards() -> None:
    source = read_text_with_partial_bundles(ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "Models" / "GeneratedItemData.cs")
    assert "public string RuntimeApiVersion" in source
    limits = (ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "InfiniRuntimeLimits.cs").read_text(encoding="utf-8")
    assert "RuntimeApiCurrent = \"v0.4.51\"" in limits
    assert "RuntimeApiCurrent = InfiniRuntimeLimits.RuntimeApiCurrent" in source
    assert "v0.4.23" not in source and "v0.4.30" not in source
    assert "RuntimeApiCurrent" in source
    assert "RuntimeApiSupported" in source
    assert "SourceMode = \"failed\"" in source
    assert "Unsupported generated runtime API" in source
    assert "Dictionary<string, JsonElement> Debug" in source
    assert "NormalizeTopLevelDebugForJson" in source
    assert "RuntimeAttackContractSupported" in source
    assert "Generated attack runtime is missing the current authored contract; regenerate this item." in source
    assert "Unsupported generated runtime opcode" in source


def _check_csharp_projectile_runtime_is_authored_only_and_logs_network_failures() -> None:
    source = read_text_with_partial_bundles(ROOT / "ModSources" / "InfiniCrafterLocal" / "Content" / "Projectiles" / "GeneratedProjectile.cs")
    assert "Legacy non-runtime-authored generated projectile is no longer supported" in source
    assert "RuntimeCodesSupported" in source
    assert "Legacy lean projectile packets are no longer supported" in source
    assert "Logger?.Warn" in source
    assert "DrawRuntimePlanFallback" in source
    assert "PresentationColor" in source and "_spec.EffectCode switch" in source
    assert "PlayImpactSound" in source and "InfiniSoundLibrary.ForImpact" in source
    # Runtime-authored drawing no longer reaches legacy shape-string heuristics.
    assert "shape.Contains" not in source
    assert "PatternText.Contains" not in source
    assert "DrawRuntimePlanFallback" in source


def _check_csharp_generated_item_no_legacy_toy_string_routing() -> None:
    source = (ROOT / "ModSources" / "InfiniCrafterLocal" / "Content" / "Items" / "GeneratedItem.cs").read_text(encoding="utf-8")
    assert "toy.Contains" not in source
    assert "pattern.Contains" not in source
    assert "visualMode.Contains" not in source
    assert "InfiniToy" not in source
    assert "RuntimePlanAuthored" in source


def _check_csharp_projectile_no_legacy_noop_or_free_text_runtime_tables() -> None:
    source = read_text_with_partial_bundles(ROOT / "ModSources" / "InfiniCrafterLocal" / "Content" / "Projectiles" / "GeneratedProjectile.cs")
    for removed in [
        "ApplyScriptedToyTick",
        "ApplyToyMotion",
        "ApplyToyOnHit",
        "ApplyPatternTick",
        "ApplyPatternOnHit",
        "SpawnVisualImpact",
        "MaterialColorName",
        "ApplyAuthoredDebuff",
        "_legacy",
        "_toyTextCache",
        "_patternTextCache",
    ]:
        assert removed not in source
    assert "shapeText.Contains" not in source
    assert "rotText.Contains" not in source
    assert "DebuffHint" not in source or "writer.Write(ShortNet(_spec.DebuffHint" in source or "writer.Write(Short(_spec.DebuffHint" in source


def _check_csharp_projectile_children_keep_authored_presentation_without_prompt_inheritance() -> None:
    source = read_text_with_partial_bundles(ROOT / "ModSources" / "InfiniCrafterLocal" / "Content" / "Projectiles" / "GeneratedProjectile.cs")
    assert "ApplyAuthoredChildPresentation(child, _spec)" in source
    assert "RestoreAuthoredChildPresentationFromRegistry" in source
    assert "child.ProjectileSpritePath = parent.ChildSpritePath.Trim()" in source
    assert "parent.SecondaryProjectileShape" in source
    assert "parent.SecondaryMaterial" in source
    assert "child.ProjectileSpritePrompt = """ in source
    assert "child.VfxManifestJson = """ in source
    assert "tiny executable shards only" not in source



def _check_csharp_has_spear_thrust_holdout_runtime_without_legacy_routing() -> None:
    item_source = read_text_with_partial_bundles(ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "Models" / "GeneratedItemData.cs")
    projectile_source = read_text_with_partial_bundles(ROOT / "ModSources" / "InfiniCrafterLocal" / "Content" / "Projectiles" / "GeneratedProjectile.cs")
    assert "AttackRuntimeFamily" in item_source
    assert "public string RuntimeFamily" in item_source
    assert "Attack.RuntimeFamily = NormalizeRuntimeFamily(Attack.RuntimeFamily);" in item_source
    assert "AttackRuntimeFamilyCompat" not in item_source
    assert "RuntimeFamily" in item_source
    assert "public int UseStyleCode" in item_source
    assert "item.useStyle = Attack.UseStyleCode" in item_source
    assert "item.noUseGraphic = true" in item_source
    assert "item.noMelee = true" in item_source
    assert "HeldThrustLine" in projectile_source
    assert "ApplyHeldThrustAI" in projectile_source
    assert "Projectile.ownerHitCheck = _spec.OwnerHitCheck" in projectile_source
    assert "Collision.CheckAABBvLineCollision" in projectile_source
    assert "ApplyHeldThrustAI" in projectile_source


def _check_server_source_has_family_movement_codes_for_runtime_validation() -> None:
    source = (ROOT / "LocalGenerator" / "infini_local" / "core" / "runtime_executor_vocabulary.py").read_text(encoding="utf-8")
    assert '"flail_tether": 16' in source
    assert '"yoyo_hover": 17' in source
    assert '"whip_lash": 18' in source
    assert '"legacyFields"' not in (ROOT / "LocalGenerator" / "infini_local" / "core" / "runtime_authoring" / "__init__.py").read_text(encoding="utf-8")


def _check_projectile_network_carries_family_state_not_prose_scripts() -> None:
    source = read_text_with_partial_bundles(ROOT / "ModSources" / "InfiniCrafterLocal" / "Content" / "Projectiles" / "GeneratedProjectile.cs")
    assert "writer.Write(ShortNet(_spec.RuntimeFamily" in source
    assert "ReadStringKeepBase(reader, _spec.RuntimeFamily" in source
    assert "writer.Write(ShortNet(_spec.WeaponFamily" in source
    assert "writer.Write(ShortNet(_spec.ProjectileFamily" in source
    assert "writer.Write(ShortNet(_spec.AmmoKind" in source
    assert "writer.Write(_spec.UseStyleCode)" in source
    assert "writer.Write(_spec.OwnerHitCheck)" in source
    for removed in ["ToyIdentity", "SpecialRule", "BehaviorActions", "BehaviorTimeline", "OnUseScript", "OnTickScript", "OnHitScript", "OnExpireScript", "ProjectileChild"]:
        assert removed not in source
    assert "writer.Write(Short(_spec.ToyIdentity" not in source
    assert "RuntimeFamily()" in source


def _check_csharp_swing_is_melee_core_and_dummy_command_exists() -> None:
    item_source = (ROOT / "ModSources" / "InfiniCrafterLocal" / "Content" / "Items" / "GeneratedItem.cs").read_text(encoding="utf-8")
    dummy_source = (ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "Commands" / "InfiniDummyCommand.cs").read_text(encoding="utf-8")
    assert "GeneratedRuntimeFamilyPolicy.Is(runtimeFamily, GeneratedRuntimeFamilyPolicy.Swing)" in item_source
    assert 'return false;' in item_source
    assert 'OnHitNPC' in item_source
    assert 'SwingSecondarySpec' in item_source
    assert 'SecondaryProjectileShape' in item_source
    assert 'Command => "infinidummy"' in dummy_source
    assert 'ItemID.TargetDummy' in dummy_source


def _check_csharp_craft_inputs_ignore_terraria_prefixes() -> None:
    source = (ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "Services" / "GeneratorClient.cs").read_text(encoding="utf-8")
    player_source = read_text_with_partial_bundles(ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "Players" / "InfiniCraftPlayer.cs")
    assert 'craftInputPolicy = "base_item_stats_ignore_prefixes"' in source
    assert "CraftIdentityItem" in source
    assert "baseItem.SetDefaults(item.type)" in source
    assert "prefixIgnored" in source
    assert "originalPrefix" in source
    assert "base_item_defaults_without_reforge_prefix" in source
    assert "player_inventory_ammo_candidate_base_no_prefix" in source
    assert 'BeginCraft(request, $"{request.ParentA} + {request.ParentB}")' in player_source


def _check_csharp_vfx_light_and_audio_guards_are_configurable() -> None:
    config_source = (ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "Config" / "InfiniVfxClientConfig.cs").read_text(encoding="utf-8")
    options_source = (ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "VFX" / "InfiniVfxClientOptions.cs").read_text(encoding="utf-8")
    vfx_source = (ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "VFX" / "VfxFoundation.cs").read_text(encoding="utf-8")
    projectile_source = read_text_with_partial_bundles(ROOT / "ModSources" / "InfiniCrafterLocal" / "Content" / "Projectiles" / "GeneratedProjectile.cs")
    player_source = read_text_with_partial_bundles(ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "Players" / "InfiniCraftPlayer.cs")
    assert "ParticleAlphaMultiplier" in config_source
    assert "PresentationLightMultiplier" in config_source
    assert "EnableParticleLibraryBackend" in config_source
    assert "InfiniVfxClientOptions.ParticleAlphaMultiplier" in vfx_source
    assert "EnableParticleLibraryBackend && ParticleLibrary.Available" in vfx_source
    assert "InfiniVfxClientOptions.PresentationLightMultiplier" in projectile_source
    assert "PostCraftAudioGuardTicks" in player_source
    assert "TickCraftAudioGuard" in player_source
    assert "RememberPositiveAudioSettings" in player_source


def _check_csharp_vfx_defaults_are_stock_and_light_words_do_not_create_light_cues() -> None:
    config_source = (ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "Config" / "InfiniVfxClientConfig.cs").read_text(encoding="utf-8")
    options_source = (ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "VFX" / "InfiniVfxClientOptions.cs").read_text(encoding="utf-8")
    registry_source = (ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "VFX" / "VfxRendererRegistry.cs").read_text(encoding="utf-8")
    runtime_source = (ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "VFX" / "InfiniVfxRuntime.cs").read_text(encoding="utf-8")
    projectile_source = read_text_with_partial_bundles(ROOT / "ModSources" / "InfiniCrafterLocal" / "Content" / "Projectiles" / "GeneratedProjectile.cs")

    assert "public float ParticleAlphaMultiplier = 1f;" in config_source
    assert "public float PresentationLightMultiplier = 1f;" in config_source
    assert "Config?.ParticleAlphaMultiplier ?? 1f" in options_source
    assert "Config?.PresentationLightMultiplier ?? 1f" in options_source
    assert "public bool EnableParticleLibraryBackend = true;" in config_source
    assert "public bool ForceVanillaDustFallback = false;" in config_source

    # A visual renderer named lightFlash/highlightFlash must not become a real Lighting.AddLight cue.
    assert 'r.Contains("light")) return InfiniVfxRendererKind.LightCue' not in registry_source
    assert '.Contains(' not in registry_source
    assert '"impactRing" => InfiniVfxRendererKind.ImpactRing' in registry_source
    assert '"lightCue" => InfiniVfxRendererKind.LightCue' in registry_source
    assert "InfiniVfxClientOptions.PresentationLightMultiplier" in runtime_source

    # Generated sprite draw should use Terraria's vanilla lightColor, not an always-white/self-lit merge tint.
    assert "Color tint = lightColor;" in projectile_source
    assert "Color.Lerp(lightColor, Color.White" not in projectile_source
    assert "public bool EnableGeneratedSpriteSilhouette = false;" in config_source
    assert "Config?.EnableGeneratedSpriteSilhouette ?? false" in options_source


def _check_csharp_vfx_keeps_steady_light_but_rejects_flicker_flash_routing() -> None:
    registry_source = (ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "VFX" / "VfxRendererRegistry.cs").read_text(encoding="utf-8")
    runtime_source = (ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "VFX" / "InfiniVfxRuntime.cs").read_text(encoding="utf-8")
    projectile_source = read_text_with_partial_bundles(ROOT / "ModSources" / "InfiniCrafterLocal" / "Content" / "Projectiles" / "GeneratedProjectile.cs")

    assert "proseLightFlash" not in registry_source
    assert "lightflash" not in registry_source.lower()
    assert '"lightCue" => InfiniVfxRendererKind.LightCue' in registry_source
    assert "_ => InfiniVfxRendererKind.None" in registry_source
    assert 'IsLiveEvent(slot.Event) && (slot.Channel == "light" || kind == InfiniVfxRendererKind.LightCue)' in runtime_source
    assert "do not emit hit/kill world-light pulses" in runtime_source
    assert "no sine pulse here" in runtime_source
    # Keep the good constant projectile light path.
    assert "Projectile.light" in projectile_source
    assert "Lighting.AddLight(Projectile.Center" in projectile_source


def _check_generated_projectile_sprite_rotation_is_side_on_not_vanilla_upward_offset() -> None:
    source = read_text_with_partial_bundles(ROOT / "ModSources" / "InfiniCrafterLocal" / "Content" / "Projectiles" / "GeneratedProjectile.cs")
    assert "SideOnGeneratedSpriteRotation" in source
    assert "sprites pointing left-to-right (+X)" in source
    assert "makes arrows/bolts fly sideways" in source
    assert "Projectile.rotation = SideOnGeneratedSpriteRotation(dir);" in source
    assert "? SideOnGeneratedSpriteRotation(Projectile.velocity)" in source
    assert "Projectile.rotation = dir.ToRotation() + MathHelper.PiOver2;" not in source
    assert "Projectile.velocity.ToRotation() + MathHelper.PiOver2" not in source


def _check_particlelibrary_does_not_allocate_alpha_blend_magicpixel_quads_for_stock_torch_safety() -> None:
    registry_source = (ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "VFX" / "VfxParticleSystemRegistry.cs").read_text(encoding="utf-8")
    vfx_source = (ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "VFX" / "VfxFoundation.cs").read_text(encoding="utf-8")

    assert "stock Torch" in registry_source or "stock Torch" in vfx_source
    assert "BlendState.AlphaBlend" not in registry_source
    assert "ParticleBuffer<InfiniV3ParticleBehavior>" in registry_source
    assert "SetBlendState(BlendState.Additive)" in registry_source
    assert "Main.QueueMainThreadAction" in registry_source
    assert "EnsureReady()" in registry_source
    assert "Do not allocate particle buffers per projectile" in registry_source
    assert "Dust.NewDustPerfect" in vfx_source

def _check_multiplayer_network_json_is_ready_state_only_for_radmin() -> None:
    source = read_text_with_partial_bundles(ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "Models" / "GeneratedItemData.cs")
    assert "Multiplayer/Radmin handoff is ready-runtime state only" in source
    assert "clone.SourceRepresentation = Array.Empty<SourceRepresentationSpec>()" in source
    assert "clone.Inheritance = Array.Empty<InheritanceSpec>()" in source
    assert "clone.ItemKnowledge = new ItemKnowledgeSpec()" in source
    assert "clone.PresentationGenome = new PresentationGenomeSpec()" in source
    assert "clone.Debug = new Dictionary<string, JsonElement>()" in source
    assert "clone.RecipeMeta.AssetBaseUrl = SafeText" in source
    assert "clone.RecipeMeta.AssetFiles = SafeTextArray" in source
    assert "clone.Visual.ImagePrompt = \"\"" in source
    assert "clone.Attack.ProjectileSpritePrompt = \"\"" in source


def _check_projectile_empty_first_mp_packet_defers_instead_of_killing_as_legacy() -> None:
    source = read_text_with_partial_bundles(ROOT / "ModSources" / "InfiniCrafterLocal" / "Content" / "Projectiles" / "GeneratedProjectile.cs")
    assert "_pendingNetworkSpecTicks" in source
    assert "DeferUnconfiguredNetworkProjectile" in source
    assert "initial projectile entity before the mod" in source
    assert "Projectile.damage = 0" in source
    assert "if (!_configured)" in source and "DeferUnconfiguredNetworkProjectile();" in source


def _check_swing_secondary_projectiles_are_explicit_and_capped() -> None:
    source = (ROOT / "ModSources" / "InfiniCrafterLocal" / "Content" / "Items" / "GeneratedItem.cs").read_text(encoding="utf-8")
    assert "HasExplicitSwingSecondaryProjectile" in source
    assert "SecondaryProjectileShape" in source and "SecondaryMaterial" in source
    assert "Math.Clamp(Data.Attack.SplitCount > 0 ? Data.Attack.SplitCount : Data.Attack.MaxChildProjectiles, 0, 3)" in source
    assert "SecondaryDamageMultiplier, 0.02f, 0.35f" in source


def _check_csharp_projectile_executes_blink_to_projectile_impact_from_authored_fields() -> None:
    data_source = read_text_with_partial_bundles(ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "Models" / "GeneratedItemData.cs")
    projectile_source = read_text_with_partial_bundles(ROOT / "ModSources" / "InfiniCrafterLocal" / "Content" / "Projectiles" / "GeneratedProjectile.cs")
    server_source = (ROOT / "LocalGenerator" / "infini_local" / "pipelines" / "combine_gameplay.py").read_text(encoding="utf-8")
    assert "public string MobilityMode" in data_source
    assert "public int MobilityRangeTiles" in data_source
    assert "public int MobilityCooldownTicks" in data_source
    assert "public bool MobilitySafeTileOnly" in data_source
    assert "writer.Write(ShortNet(_spec.MobilityMode" in projectile_source
    assert "_spec.MobilityMode = reader.ReadString()" in projectile_source
    assert "TryRunImpactMobility(target.Center)" in projectile_source
    assert "TryRunImpactMobility(Projectile.Center)" in projectile_source
    assert 'mode != "blink_to_projectile_impact"' in projectile_source
    assert '"mobilityMode": str(gp.get(' in server_source


def _check_network_authority_versioned_sync_and_public_api_contract() -> None:
    authority = (ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "Services" / "InfiniRuntimeAuthority.cs").read_text(encoding="utf-8")
    projectile = read_text_with_partial_bundles(ROOT / "ModSources" / "InfiniCrafterLocal" / "Content" / "Projectiles" / "GeneratedProjectile.cs")
    item = (ROOT / "ModSources" / "InfiniCrafterLocal" / "Content" / "Items" / "GeneratedItem.cs").read_text(encoding="utf-8")
    player = read_text_with_partial_bundles(ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "Players" / "InfiniCraftPlayer.cs")
    mod = (ROOT / "ModSources" / "InfiniCrafterLocal" / "InfiniCrafterLocal.cs").read_text(encoding="utf-8")

    assert "ShouldRunProjectileGameplay" in authority
    assert "ShouldRunPlayerGameplay" in authority
    assert "ShouldRunLocalPlayerAction" in authority
    assert "SyncTeleport" in authority
    assert "ProjectileSyncVersion" in projectile
    assert "writer.Write(ProjectileSyncVersion)" in projectile
    assert "reader.ReadUInt16()" in projectile
    assert "SyncFlagMobility" in projectile
    assert "InfiniRuntimeAuthority.ShouldRunProjectileGameplay" in projectile
    assert "GeneratedItemNetPayloadVersion" in item
    assert "Item.NetStateChanged()" in item
    assert "public override object? Call" in mod
    assert "TryGetGeneratedItemData" in mod
    assert "GetGeneratedSummary" in mod
    assert "RegisterGeneratedParentHint" in mod
    assert "PacketSyncGeneratedUtilityBuff = InfiniNetPacketIds.SyncGeneratedUtilityBuff" in player
    assert "SyncGeneratedUtilityBuff = 7" in (ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "InfiniNetPacketIds.cs").read_text(encoding="utf-8")
    assert "public override void SyncPlayer" in player
    assert "public override void CopyClientState" in player
    assert "public override void SendClientChanges" in player
    assert "HandleGeneratedUtilityBuffSyncPacket" in player


def _check_generated_item_alt_hold_extractinator_hooks_are_explicit_and_guarded() -> None:
    item = (ROOT / "ModSources" / "InfiniCrafterLocal" / "Content" / "Items" / "GeneratedItem.cs").read_text(encoding="utf-8")
    proxy = (ROOT / "ModSources" / "InfiniCrafterLocal" / "Content" / "Items" / "GeneratedExtractinatorMaterial.cs").read_text(encoding="utf-8")
    data = read_text_with_partial_bundles(ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "Models" / "GeneratedItemData.cs")
    assert "public override bool AltFunctionUse" in item
    assert "public override bool CanUseItem" in item
    assert "public override void HoldItem" in item
    assert "public override void ExtractinatorUse" not in item
    assert "AltGeneratedBuff" in item and "HoldGeneratedBuff" in item
    assert "TryRunGeneratedMobility(gp.AltMobilityMode" in item
    assert "ItemID.Sets.ExtractinatorMode[Type]" not in item
    assert "public static bool CanRepresent(GeneratedItemData? data)" in proxy
    assert "public override bool CanStack(Item source)" in proxy
    assert "public override void ExtractinatorUse" in proxy
    assert "ItemID.Sets.ExtractinatorMode[Type] = Type;" in proxy
    assert "public string AltUseMode" in data
    assert "public float HoldLightStrength" in data
    assert "public int ExtractinatorOutputItemType" in data
    assert "public string UseConditionMode" in data


def _check_network_authority_keeps_projectile_side_effects_owner_only() -> None:
    authority = (ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "Services" / "InfiniRuntimeAuthority.cs").read_text(encoding="utf-8")
    body = authority.split("public static bool ShouldRunProjectileGameplay", 1)[1].split("public static bool ShouldRunPlayerGameplay", 1)[0]
    assert "if (IsServer) return false" in body
    assert "return IsLocalProjectileOwner(projectile)" in body
    assert "if (IsServer) return true" not in body


def _check_generated_buff_sync_does_not_send_every_countdown_tick() -> None:
    player = read_text_with_partial_bundles(ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "Players" / "InfiniCraftPlayer.cs")
    body = player.split("private bool GeneratedBuffStateDiffers", 1)[1].split("private void SendGeneratedBuffState", 1)[0]
    assert "Do not sync every countdown tick" in body
    assert "activeNow != activeOld" in body
    assert "Math.Abs(_generatedBuffTicks - other._generatedBuffTicks) > 30" in body
    assert "_generatedBuffTicks != other._generatedBuffTicks" not in body
    assert "_generatedMobilityCooldownTicks != other._generatedMobilityCooldownTicks" not in body


def _check_impact_blink_is_owner_authoritative_not_server_replayed() -> None:
    projectile = read_text_with_partial_bundles(ROOT / "ModSources" / "InfiniCrafterLocal" / "Content" / "Projectiles" / "GeneratedProjectile.cs")
    body = projectile.split("private void TryRunImpactMobility", 1)[1].split("private static bool IsSafeOwnerTeleportDestination", 1)[0]
    assert "InfiniRuntimeAuthority.ShouldRunProjectileGameplay(Projectile)" in body
    assert "Main.netMode != NetmodeID.Server" not in body


def _check_local_player_actions_do_not_run_on_server_or_remote_clients() -> None:
    authority = (ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "Services" / "InfiniRuntimeAuthority.cs").read_text(encoding="utf-8")
    item = (ROOT / "ModSources" / "InfiniCrafterLocal" / "Content" / "Items" / "GeneratedItem.cs").read_text(encoding="utf-8")
    player = read_text_with_partial_bundles(ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "Players" / "InfiniCraftPlayer.cs")
    body = authority.split("public static bool ShouldRunLocalPlayerAction", 1)[1].split("public static bool ShouldRunVisuals", 1)[0]
    assert "if (IsServer) return false" in body
    assert "return IsLocalPlayer(player.whoAmI)" in body
    assert "bool runLocalAction = InfiniRuntimeAuthority.ShouldRunLocalPlayerAction(player)" in item
    assert "bool runPlayerGameplay = InfiniRuntimeAuthority.ShouldRunPlayerGameplay(player)" in item
    assert "runPlayerGameplay && gp?.GeneratedBuff" in item
    assert "runLocalAction && gp is not null" in item
    assert "ShouldRunLocalPlayerAction(Player)" in player



def _check_runtime_state_cleanup_bounce_and_child_depth_policy_is_centralized() -> None:
    projectile = read_text_with_partial_bundles(ROOT / "ModSources" / "InfiniCrafterLocal" / "Content" / "Projectiles" / "GeneratedProjectile.cs")
    assert "InitialBounceBudget(_spec)" in projectile
    assert "DefaultBounceBudgetForMovement" in projectile
    assert "_remainingBounces <= 0" in projectile
    assert "movement == 6" not in projectile and "movement == 14" not in projectile and "movement == 16" not in projectile
    assert "private int RuntimeChildCount(int requested)" in projectile
    assert "private bool CanRunChildEffect(bool rootOnly = false)" in projectile
    assert "InfiniRuntimeAuthority.ShouldRunProjectileGameplay(Projectile)" in projectile
    assert "return depth < Math.Max(0, _spec.MaxChildDepth);" in projectile
    assert "if (depth > Math.Max(0, _spec.MaxChildDepth)) return;" in projectile
    assert "CountOwnedGeneratedProjectiles(rootId) >= Math.Max(0, _spec.MaxChildProjectiles)" in projectile
    assert "RemainingGameplayChildBudget()" in projectile
    assert "return Math.Clamp(requested, 1, remaining);" in projectile
    assert "_spawnedGameplayChildCount++" in projectile
    assert "rootOnly: true" in projectile
    assert "Projectile.localAI[1] > 1f" not in projectile
    assert "Projectile.localAI[1] > 0f" not in projectile
    mini = projectile.split("private void MiniMissiles", 1)[1].split("private void", 1)[0]
    vortex = projectile.split("private void VortexSpawn", 1)[1].split("private void", 1)[0]
    assert "CanRunChildEffect(rootOnly: true)" in mini
    assert "CanRunChildEffect(rootOnly: true)" in vortex


def _check_generated_buff_sync_rejects_client_spoof_and_clamps_network_state() -> None:
    player = read_text_with_partial_bundles(ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "Players" / "InfiniCraftPlayer.cs")
    assert "if (Main.netMode == NetmodeID.Server && playerId != whoAmI) return" in player
    assert "ClampGeneratedBuffState" in player
    assert "_generatedBuffTicks = Math.Clamp(_generatedBuffTicks, 0, 21600)" in player
    assert "_generatedMobilityCooldownTicks = Math.Clamp(_generatedMobilityCooldownTicks, 0, 36000)" in player
    model = read_text_with_partial_bundles(ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "Models" / "GeneratedItemData.cs")
    runtime_authoring = (ROOT / "LocalGenerator" / "infini_local" / "core" / "runtime_authoring" / "__init__.py").read_text(encoding="utf-8")
    runtime_schema = (ROOT / "LocalGenerator" / "infini_local" / "core" / "runtime_authoring" / "schema.py").read_text(encoding="utf-8")
    assert "OreSenseEnabled => OreSenseRadiusTiles > 0" in model
    assert "bool-backed" in model and "findTreasure" in player
    assert "radius debug-only" in runtime_schema
    assert "from infini_local.core.runtime_authoring.schema import" in runtime_authoring


def _check_blink_safe_destination_rejects_world_edges_and_lava() -> None:
    player = read_text_with_partial_bundles(ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "Players" / "InfiniCraftPlayer.cs")
    projectile = read_text_with_partial_bundles(ROOT / "ModSources" / "InfiniCrafterLocal" / "Content" / "Projectiles" / "GeneratedProjectile.cs")
    assert "target.Left < 16" in player and "LiquidID.Lava" in player
    assert "target.Left < 16" in projectile and "LiquidID.Lava" in projectile

# Coarse test bundle: the checks below used to be separate pytest items.
# Keeping them as helper checks cuts collection/runtime noise while preserving
# the same assertions inside one scenario-level contract per file.
def _run_coarse_contracts(tmp_path):
    import inspect as _inspect
    import pytest as _pytest

    for _name in [
    '_check_csharp_generated_item_data_keeps_runtime_api_and_debug_delivery_guards',
    '_check_csharp_projectile_runtime_is_authored_only_and_logs_network_failures',
    '_check_csharp_generated_item_no_legacy_toy_string_routing',
    '_check_csharp_projectile_no_legacy_noop_or_free_text_runtime_tables',
    '_check_csharp_projectile_children_keep_authored_presentation_without_prompt_inheritance',
    '_check_csharp_has_spear_thrust_holdout_runtime_without_legacy_routing',
    '_check_server_source_has_family_movement_codes_for_runtime_validation',
    '_check_projectile_network_carries_family_state_not_prose_scripts',
    '_check_csharp_swing_is_melee_core_and_dummy_command_exists',
    '_check_csharp_craft_inputs_ignore_terraria_prefixes',
    '_check_csharp_vfx_light_and_audio_guards_are_configurable',
    '_check_csharp_vfx_defaults_are_stock_and_light_words_do_not_create_light_cues',
    '_check_csharp_vfx_keeps_steady_light_but_rejects_flicker_flash_routing',
    '_check_generated_projectile_sprite_rotation_is_side_on_not_vanilla_upward_offset',
    '_check_particlelibrary_does_not_allocate_alpha_blend_magicpixel_quads_for_stock_torch_safety',
    '_check_multiplayer_network_json_is_ready_state_only_for_radmin',
    '_check_projectile_empty_first_mp_packet_defers_instead_of_killing_as_legacy',
    '_check_swing_secondary_projectiles_are_explicit_and_capped',
    '_check_csharp_projectile_executes_blink_to_projectile_impact_from_authored_fields',
    '_check_network_authority_versioned_sync_and_public_api_contract',
    '_check_generated_item_alt_hold_extractinator_hooks_are_explicit_and_guarded',
    '_check_network_authority_keeps_projectile_side_effects_owner_only',
    '_check_generated_buff_sync_does_not_send_every_countdown_tick',
    '_check_impact_blink_is_owner_authoritative_not_server_replayed',
    '_check_local_player_actions_do_not_run_on_server_or_remote_clients',
    '_check_runtime_state_cleanup_bounce_and_child_depth_policy_is_centralized',
    '_check_generated_buff_sync_rejects_client_spoof_and_clamps_network_state',
    '_check_blink_safe_destination_rejects_world_edges_and_lava'
    ]:
        _fn = globals()[_name]
        _sig = _inspect.signature(_fn)
        _kwargs = {}
        if "tmp_path" in _sig.parameters:
            _case_dir = tmp_path / _name
            _case_dir.mkdir(parents=True, exist_ok=True)
            _kwargs["tmp_path"] = _case_dir
        if "monkeypatch" in _sig.parameters:
            with _pytest.MonkeyPatch.context() as _mp:
                _kwargs["monkeypatch"] = _mp
                _fn(**_kwargs)
        else:
            _fn(**_kwargs)


def test_csharp_delivery_contract_source_coarse_contract(tmp_path):
    _run_coarse_contracts(tmp_path)

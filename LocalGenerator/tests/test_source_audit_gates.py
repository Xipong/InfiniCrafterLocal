"""Canonical source gates: valid controls and isolated mistakes, never edited production."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def gates():
    modules = []
    for name in ("check_project_hygiene", "check_csharp_contracts"):
        spec = importlib.util.spec_from_file_location(name + "_source_audit_test", ROOT / "tools" / (name + ".py"))
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        modules.append(module)
    return modules


def test_python_gate_accepts_repository(gates):
    hygiene, _ = gates
    sources = {str(p.relative_to(ROOT)): p.read_text(encoding="utf-8-sig")
               for directory in (ROOT / "LocalGenerator/infini_local", ROOT / "tools")
               for p in directory.rglob("*.py")}
    assert hygiene.python_source_issues(sources) == []
    from infini_local.pipelines import pipeline_runtime_constants, result_identity_policy
    assert result_identity_policy.BAD_NAME_PATTERNS is pipeline_runtime_constants.BAD_NAME_PATTERNS


@pytest.mark.parametrize("source,code", [
    ('values = {"name": 1, "name": 2}\n', "duplicate_dict_key"),
    ('def f():\n    x = 1\n    x = 1\n', "duplicate_assignment"),
    ('__all__ = [name for name in globals()]\n', "dynamic_exports"),
    ('import os\nx = os.getenv("INFINI_DIRECT")\n', "raw_environment_read"),
    ('import os as system\nx = system.environ.get("INFINI_DIRECT")\n', "raw_environment_read"),
    ('from os import environ as environment\nx = environment["INFINI_DIRECT"]\n', "raw_environment_read"),
    ('from os import getenv as read_env\nx = read_env("INFINI_DIRECT")\n', "raw_environment_read"),
    ('BAD_NAME_PATTERNS = ()\n', "constant_owner"),
], ids=["duplicate-key", "duplicate-write", "globals-export", "getenv", "os-alias", "environ-alias", "getenv-alias", "shadow-owner"])
def test_python_gate_rejects_source_mutants(gates, source, code):
    hygiene, _ = gates
    owner = "LocalGenerator/infini_local/pipelines/pipeline_runtime_constants.py"
    control = {owner: "BAD_NAME_PATTERNS = ()\n",
               "LocalGenerator/infini_local/probe.py": '# os.getenv("COMMENT")\nimport os\nsnapshot = os.environ.copy()\nos.environ.setdefault("X", "1")\n'}
    assert hygiene.python_source_issues(control) == []
    mutant = dict(control, **{"LocalGenerator/infini_local/probe.py": source})
    assert any(code in issue for issue in hygiene.python_source_issues(mutant))


def test_python_gate_rejects_import_cycle(gates):
    hygiene, _ = gates
    sources = {"LocalGenerator/infini_local/pipelines/pipeline_runtime_constants.py": "BAD_NAME_PATTERNS = ()\n",
               "LocalGenerator/infini_local/a.py": "import infini_local.b\n",
               "LocalGenerator/infini_local/b.py": "value = 1\n"}
    assert hygiene.python_source_issues(sources) == []
    sources["LocalGenerator/infini_local/b.py"] = "import infini_local.a\n"
    assert any("import_cycle" in issue for issue in hygiene.python_source_issues(sources))


@pytest.fixture
def csharp_sources():
    root = ROOT / "ModSources/InfiniCrafterLocal"
    return {str(p.relative_to(root)): p.read_text(encoding="utf-8") for pattern in ("*.cs", "*.hjson") for p in root.rglob(pattern)}


def test_csharp_policy_accepts_repository(gates, csharp_sources):
    _, scanner = gates
    assert scanner.source_policy_issues(csharp_sources) == []


@pytest.mark.parametrize("path,addition,code", [
    ("Common/Models/GeneratedItemData.Model.cs", "public string Tooltip { get; set; }", "authored_tooltip"),
    ("Content/Items/GeneratedItem.cs", "public void ModifyTooltips() {}", "authored_tooltip"),
    ("Common/Models/GeneratedItemData.Model.cs", "public string SetBonusText { get; set; }", "authored_tooltip"),
    ("Common/Models/GeneratedItemData.Apply.cs", "private void Bad() { item.useStyle = 0; }", "numeric_sentinel"),
    ("Common/Services/GeneratorClient.cs", "private bool Bad() => projectileType <= 0;", "numeric_sentinel"),
    ("Common/Commands/InfiniDumpCommand.cs", "private bool Bad() => item.shoot > 0;", "numeric_sentinel"),
    ("Content/Items/GeneratedItem.cs", "#pragma warning disable CS0246", "warning_suppression"),
], ids=["tooltip-property", "tooltip-hook", "set-bonus-prose", "use-style-zero", "projectile-zero", "dump-zero", "disable-warning"])
def test_csharp_policy_rejects_source_mutants(gates, csharp_sources, path, addition, code):
    _, scanner = gates
    source = csharp_sources[path]
    control = dict(csharp_sources, **{path: source + "\n// " + addition})
    assert scanner.source_policy_issues(control) == []
    mutant = dict(csharp_sources, **{path: source.rsplit("}", 1)[0] + addition + "\n}"})
    assert any(code in issue for issue in scanner.source_policy_issues(mutant))


@pytest.fixture
def authored_sources():
    schemas = ROOT / "contracts/schemas"
    return {str(p.relative_to(ROOT)): p.read_text(encoding="utf-8") for p in schemas.glob("*.json")} | {
        "LocalGenerator/infini_local/core/runtime_authoring/compiler.py":
            (ROOT / "LocalGenerator/infini_local/core/runtime_authoring/compiler.py").read_text(encoding="utf-8")}


def test_authored_policy_accepts_repository(gates, authored_sources):
    hygiene, _ = gates
    assert hygiene.authored_contract_issues(authored_sources) == []


@pytest.mark.parametrize("path,old,new,code", [
    ("author_item_response.schema.json", '"name":', '"tooltip":', "forbidden_author_field"),
    ("capability_inventory.generated.json", '"configure_armor"', '"setBonusText"', "forbidden_author_field"),
    ("visual_runtime_entities.schema.json", '"prompt":', '"impactPrompt":', "foreign_visual_prompt"),
    ("vfx_runtime_events.schema.json", '"spritePrompt"', '"retiredPrompt"', "missing_vfx_prompt"),
    ("author_item_response.schema.json", '"runtimeProgram": {', '"runtimeProgram": {"tooltip": {},', "forbidden_author_field"),
], ids=["authored-tooltip", "armor-prose", "visual-impact-ownership", "missing-vfx-sprite-prompt", "nested-tooltip"])
def test_authored_policy_rejects_schema_mutants(gates, authored_sources, path, old, new, code):
    hygiene, _ = gates
    assert hygiene.authored_contract_issues(authored_sources) == []
    name = "contracts/schemas/" + path
    assert old in authored_sources[name]
    mutant = dict(authored_sources, **{name: authored_sources[name].replace(old, new)})
    assert any(code in issue for issue in hygiene.authored_contract_issues(mutant))


def test_packet_wire_id_is_stable_not_only_unique(gates, monkeypatch):
    _, scanner = gates
    reader = scanner.read
    scanner.check_packet_ids()
    assert scanner.ERRORS == []
    source = reader("Common/InfiniNetPacketIds.cs")
    mutant = source.replace("SyncGeneratedProjectileVfxEvent = 9", "SyncGeneratedProjectileVfxEvent = 222")
    assert mutant != source
    monkeypatch.setattr(scanner, "read", lambda _name: mutant)
    scanner.check_packet_ids()
    assert any("stable packet id" in issue for issue in scanner.ERRORS)


def test_csharp_scopes_ignore_decoys_and_do_not_extend_to_next_method(gates):
    _, scanner = gates
    source = '''class Probe {
// private void Target() { Wrong(); }
private void Target(string name) {
    string decoy = "https://host/{ Wrong(); }";
    if (name.Length > 0) { Real(); }
}
private void Other() { Wrong(); }
}'''
    code = scanner.stripped(scanner.method_body(source, "Target"))
    assert "Real();" in code
    assert "Wrong();" not in code
    assert scanner.ERRORS == []


@pytest.mark.parametrize("locale", ["en-US", "ru-RU"])
def test_proxy_localization_rejects_authored_tooltip(gates, csharp_sources, locale):
    _, scanner = gates
    assert scanner.source_policy_issues(csharp_sources) == []
    path = "Localization/" + locale + "_Mods.InfiniCrafterLocal.hjson"
    source = csharp_sources[path]
    assert "GeneratedItem: {" in source
    mutant = dict(csharp_sources, **{path: source.replace("GeneratedItem: {", 'GeneratedItem: {\nTooltip: ""')})
    assert any("proxy_tooltip" in issue for issue in scanner.source_policy_issues(mutant))


@pytest.mark.parametrize("forbidden", ["tooltip", "setBonusText"])
def test_live_author_surfaces_forbid_extra_prose(forbidden):
    import json
    from infini_local.core.runtime_authoring import CAPABILITY_REGISTRY
    from infini_local.core.runtime_authoring.program_schema import author_item_response_schema, author_item_repair_schema
    from infini_local.pipelines.author_item_contract import author_item_prompt_shape_card
    from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
    surfaces = [author_item_response_schema(), author_item_repair_schema(), author_item_prompt_shape_card(),
                build_runtime_fixture("workbench_blade"), list(CAPABILITY_REGISTRY["configure_armor"].params)]
    assert json.dumps(forbidden) not in json.dumps(surfaces)

@pytest.mark.parametrize("gate,path,old,new,diagnostic", [
    pytest.param('check_runtime_contract', 'Common/Models/GeneratedItemData.Apply.cs', 'item.potion = enabled && effects.Potion;', 'item.potion = Gameplay.HealLife > 0;', 'item.potion', id='inferred-potion'),
    pytest.param('check_runtime_contract', 'Common/Models/TerrariaRuntimeVocabulary.cs', 'ModContent.TryFind<DamageClass>(exact', 'ModContent.TryFind<DamageClass>(guessed', 'ModContent.TryFind', id='loose-class-lookup'),
    pytest.param('check_runtime_contract', 'Common/Services/GeneratorClient.cs', '=> TerrariaRuntimeVocabulary.CanonicalDamageClassToken', '=> LegacyDamageClassToken', 'CanonicalDamageClassToken', id='shadow-class-owner'),
    pytest.param('check_runtime_contract', 'Common/Models/GeneratedItemData.Normalize.cs', 'Gameplay.DamageClass = SafeText(Gameplay.DamageClass, 129);', 'Gameplay.DamageClass = SafeText(Gameplay.DamageClass, 129).ToLowerInvariant();', 'DamageClass', id='lowercased-class'),
    pytest.param('check_runtime_contract', 'Common/Models/GeneratedItemData.Normalize.cs', 'RarityLoader.RarityCount', 'ItemRarityID.Count', 'RarityLoader.RarityCount', id='vanilla-rarity-ceiling'),
    pytest.param('check_runtime_contract', 'Common/Models/RuntimeProgramSpec.cs', 'TileLoader.TileCount', 'TileID.Count', 'TileLoader.TileCount', id='vanilla-tile-ceiling'),
    pytest.param('check_runtime_contract', 'Common/Models/RuntimeProgramSpec.cs', 'BuffId <= 0', 'BuffId < 0', 'BuffId <= 0', id='zero-buff'),
    pytest.param('check_network_boundaries', 'Common/Runtime/RuntimeProgramExecutor.cs', 'if (!HasActionAuthority(action, owner))', 'if (false) /* if (!HasActionAuthority(action, owner)) */', 'ExecuteAction', id='dispatch-authority-cannot-be-comment'),
    pytest.param('check_network_boundaries', 'Common/Runtime/RuntimeDelayedActionScheduler.cs', 'if (!RuntimeProgramExecutor.HasActionAuthority(action, owner))', 'if (false)', 'TrySchedule', id='delayed-authority-preflight'),
    pytest.param('check_network_boundaries', 'Common/Runtime/RuntimeProgramExecutor.cs', 'RuntimeEventActionCode.HealOwner or', '', 'HasActionAuthority', id='canonical-heal-authority'),
    pytest.param('check_world_transactions', 'Common/Systems/GeneratedPlacementLedgerSystem.cs', 'GeneratedItemData.FromJson(pending.DefinitionJson)', 'GeneratedItemData.Placeholder()', 'TrySpawnPendingReturnCore', id='durable-definition-not-placeholder'),
    pytest.param('check_world_transactions', 'Common/Systems/GeneratedPlacementLedgerSystem.cs', 'Claim = ReturnClaim(pending)', 'Claim = new TagCompound()', 'PostUpdateWorld', id='quarantine-preserves-raw-claim'),
    pytest.param('check_world_transactions', 'Common/Systems/GeneratedPlacementLedgerSystem.cs', 'QuarantinedReturns.Select(QuarantineEnvelope)', 'QuarantinedReturns.Select(_ => new TagCompound())', 'SaveWorldData', id='quarantine-envelope-writer-is-reachable'),
    pytest.param('check_world_transactions', 'Common/Systems/GeneratedPlacementLedgerSystem.cs', 'record.Claim.Clone()', 'new TagCompound()', 'QuarantineEnvelope', id='quarantine-envelope-keeps-claim'),
    pytest.param('check_world_transactions', 'Common/Players/InfiniCraftPlayer.CraftState.cs', 'RestoreScopedRemoteStationClaim(retained);', '/* RestoreScopedRemoteStationClaim(retained); */', 'EnsureRemoteStationAuthority', id='scoped-restore-is-reachable'),
    pytest.param('check_network_boundaries', 'Common/Services/GeneratedAssetSyncService.cs', 'Main.netMode != NetmodeID.Server', 'Main.netMode == NetmodeID.Server', 'HandleAssetRequestPacket', id='asset-authority'),
    pytest.param('check_network_boundaries', 'Common/Services/GeneratedAssetSyncService.cs', 'ComputeSha256Hex(complete)', 'ComputeSha256Hex(Array.Empty<byte>())', 'HandleAssetChunkPacket', id='wrong-chunk-hash'),
    pytest.param('check_network_boundaries', 'Content/Projectiles/GeneratedProjectile.NetSync.cs', 'runtimeVersion is not 2 && runtimeVersion != RuntimeNetVersion', 'runtimeVersion is not 2 && runtimeVersion == RuntimeNetVersion', 'ReceiveExtraAI', id='net-version'),
    pytest.param('check_network_boundaries', 'Common/Runtime/RuntimeInitialNpcExclusion.cs', 'if (generation == 0) return false', 'if (generation == 1) return false', 'TryCapture', id='initial-exclusion-unknown-incarnation'),
    pytest.param('check_network_boundaries', 'Common/Runtime/RuntimeInitialNpcExclusion.cs', 'RuntimeHitNpcGeneration.Get(npc) == Generation', 'RuntimeHitNpcGeneration.Get(npc) != Generation', 'AppliesTo', id='initial-exclusion-reused-slot'),
    pytest.param('check_network_boundaries', 'Content/Projectiles/GeneratedProjectile.cs', 'if (childDepth > 0) activationBudget.Return(remainingSpawnBudget - spawned)', 'if (childDepth > 0) activationBudget.Return(remainingSpawnBudget)', 'SpawnRuntimeEntity', id='spawn-exception-refund-only-unused'),
    pytest.param('check_network_boundaries', 'Content/Projectiles/GeneratedProjectile.cs', 'projectile.active = false;', 'projectile.active = true;', 'SpawnRuntimeEntity', id='spawn-configure-exception-deactivate'),
    pytest.param('check_network_boundaries', 'Common/Runtime/RuntimeProgramExecutor.cs', 'previous = next;', 'previous = initialTarget;', 'PlanTargetEmissions', id='hop-anchor-must-advance'),
    pytest.param('check_network_boundaries', 'Common/Runtime/RuntimeProgramExecutor.cs', 'action.SelectionAnchor == "previous_target"', 'action.SelectionAnchor == "event_target"', 'PlanTargetEmissions', id='hop-anchor-enum-value'),
    pytest.param('check_network_boundaries', 'Common/Runtime/RuntimeProgramExecutor.cs', 'action.RepeatPolicy == "exclude_visited"', 'action.RepeatPolicy == "allow_revisits"', 'PlanTargetEmissions', id='hop-repeat-enum-value'),
    pytest.param('check_network_boundaries', 'Common/Runtime/RuntimeProgramExecutor.cs', 'distanceSquared > radiusSquared', 'distanceSquared >= radiusSquared', 'PlanTargetEmissions', id='hop-inclusive-range'),
    pytest.param('check_network_boundaries', 'Common/Runtime/RuntimeProgramExecutor.cs', 'initialNpcExclusion: step.Exclusion', 'initialNpcExclusion: null', 'SelectTargetsAndEmit', id='hop-exact-initial-exclusion'),
    pytest.param('check_network_boundaries', 'Common/Runtime/RuntimeProgramExecutor.cs', 'finally { budget.Return(unattempted); }', 'finally { budget.Return(granted); }', 'SelectTargetsAndEmit', id='hop-return-only-undispatched-reservations'),
    pytest.param('check_network_boundaries', 'Common/Runtime/RuntimeDelayedActionScheduler.cs', 'RuntimeHitNpcGeneration.Get(target) == 0', 'RuntimeHitNpcGeneration.Get(target) == 1', 'TrySchedule', id='hop-delayed-unknown-target-refused'),
    pytest.param('check_network_boundaries', 'Common/Models/RuntimeProgramSpec.cs', '|| !_delayTicksPresent', '', 'NormalizeAndValidate', id='hop-no-hidden-zero-delay'),
    pytest.param('check_network_boundaries', 'Common/Models/RuntimeProgramSpec.cs', '_offsetPresent && _aimPresent && _placementPresent', '_offsetPresent && _aimPresent', 'HasExactTargetEmissionOrigin', id='hop-no-hidden-child-placement'),
    pytest.param('check_network_boundaries', 'Common/Models/RuntimeProgramSpec.cs', 'if (action?.ActionCode != RuntimeEventActionCode.SelectTargetsAndEmit) continue', 'if (action?.ActionCode != RuntimeEventActionCode.MoveOwner) continue', 'NormalizeAndValidate', id='hop-raw-reference-before-normalize'),
    pytest.param('check_network_boundaries', 'Content/Projectiles/GeneratedProjectile.cs', 'if (_runtimePayloadRejected) return false', 'if (_runtimePayloadRejected) return true', 'TryHydrate', id='initial-exclusion-no-red-rehydration'),
    pytest.param('check_network_boundaries', 'Content/Projectiles/GeneratedProjectile.cs', 'Projectile.timeLeft = Math.Max(1, syncedTimeLeft)', 'Projectile.timeLeft = 999', 'Configure', id='rehydration-age'),
    pytest.param('check_network_boundaries', 'Common/Runtime/RuntimeProgramExecutor.cs', 'ShouldRunLocalPlayerAction(owner)', 'ShouldRunPlayerGameplay(owner)', 'ShouldRunNpcEvent', id='owner-hit-authority'),
    pytest.param('check_network_boundaries', 'Common/Players/InfiniCraftPlayer.Multiplayer.cs', 'DiscardGeneratedBuffState(reader);', '/* DiscardGeneratedBuffState(reader); */', 'utility_payload_consumed', id='unread-rejected-payload'),
    pytest.param('check_network_boundaries', 'Common/Players/InfiniCraftPlayer.Multiplayer.cs', 'int firstInputIndex = laneIndex * 2', 'int firstInputIndex = laneIndex', 'HandleRequestServerCraftPacket', id='cross-lane-reservation'),
    pytest.param('check_delivery_metadata', 'Common/Models/GeneratedItemData.Model.cs', 'public string Identity { get; set; }', 'public string Fantasy { get; set; }', 'parent_summary_dto', id='shadow-parent-shape'),
    pytest.param('check_delivery_metadata', 'Common/Services/GeneratorClient.cs', 'GeneratedItemData.IsPlayerSaveReferenceOnly(existing)', 'false', 'ToWireItem', id='unhydrated-parent'),
    pytest.param('check_delivery_metadata', 'Common/Models/GeneratedItemData.Normalize.cs', 'Armor.Enabled && Armor.Slot is not', 'false && Armor.Slot is not', 'armor_slot', id='implicit-armor-slot'),
    pytest.param('check_delivery_metadata', 'Common/Services/GeneratedAssetSyncService.cs', 'MaxAssetFiles = 32', 'MaxAssetFiles = 16', 'asset_roster_capacity', id='truncated-asset-capacity'),
    pytest.param('check_world_transactions', 'Content/Items/GeneratedItem.cs', 'StackCost == 1 && ConsumeAcceptedPlacementReceipt(player)', 'StackCost == 1', 'ConsumeItem', id='intent-debit'),
    pytest.param('check_world_transactions', 'Common/Systems/GeneratedPlacementLedgerSystem.cs', 'Main.netMode != NetmodeID.Server', 'Main.netMode == NetmodeID.Server', 'HandlePlacementPacket', id='client-ledger-authority'),
    pytest.param('check_world_transactions', 'Common/Systems/GeneratedPlacementLedgerSystem.cs', 'PendingAuthorizations.Count', '0', 'AuthorizePlacement', id='unreserved-concurrent-placement'),
    pytest.param('check_world_transactions', 'Common/Players/InfiniCraftPlayer.CraftState.cs', 'if (!_stationEscrowUsesRemoteAuthority)', 'if (_stationEscrowUsesRemoteAuthority)', 'guarded_refund', id='double-refund'),
    pytest.param('check_world_transactions', 'Common/Players/InfiniCraftPlayer.CraftState.cs', 'ItemIO.Save(_pendingStationEscrowItem)', 'ItemIO.Save(NewAirItem())', 'SaveData', id='lost-pending-item'),
    pytest.param('check_world_transactions', 'Common/Players/InfiniCraftPlayer.Multiplayer.cs', 'packet.Write(_stationEscrowClientId);', '/* packet.Write(_stationEscrowClientId); */', 'FlushPendingStationEscrowRequest', id='ephemeral-escrow-identity'),
    pytest.param('check_world_transactions', 'Common/Players/InfiniCraftPlayer.Multiplayer.cs', 'RefundOne(slot);', '/* RefundOne(slot); */', 'ApplyStationEscrowResult', id='lost-return-mirror'),
    pytest.param('check_visual_vfx_contract', 'Common/Models/VfxManifestSpec.cs', 'TextureRole == "none"', 'TextureRole == "item"', 'authored texture role admission', id='sprite-none-accepted'),
    pytest.param('check_visual_vfx_contract', 'Common/Models/VfxManifestSpec.cs', '!impactEntityIds.Add(slot.EntityId)', 'true', 'authored texture role admission', id='duplicate-impact-accepted'),
    pytest.param('check_visual_vfx_contract', 'Common/Models/GeneratedItemData.cs', 'entity.Visual.ImpactSpritePath = FileNameOnly', 'entity.Visual.ImpactSpritePath = identity', 'impact wire path', id='unprojected-impact-path'),
    pytest.param('check_visual_vfx_contract', 'Common/Services/GeneratedAssetSyncService.cs', 'yield return entity.Visual.ImpactSpritePath', 'yield return entity.Visual.SpritePath', 'impact asset roster', id='missing-impact-roster'),
    pytest.param('check_explicit_body_scale', 'Content/Projectiles/GeneratedProjectile.Visuals.cs', '_entity?.HitboxCurve?.MirrorToSprite == true', 'false', 'explicit body scale opt-in', id='mirror-opt-in-lost'),
    pytest.param('check_explicit_body_scale', 'Content/Projectiles/GeneratedProjectile.Visuals.cs', '? Projectile.scale : Math.Clamp', '? Math.Clamp(Projectile.scale, 0.1f, 8f) : Math.Clamp', 'explicit body scale PNG consumer', id='explicit-mirror-png-clamped'),
    pytest.param('check_explicit_body_scale', 'Content/Projectiles/GeneratedProjectile.Visuals.cs', 'exactScale ? _entity.Hitbox.WidthPx * Projectile.scale', 'false ? _entity.Hitbox.WidthPx * Projectile.scale', 'explicit body scale primitive consumer', id='explicit-mirror-length-floored'),
    pytest.param('check_explicit_body_scale', 'Content/Projectiles/GeneratedProjectile.Visuals.cs', 'exactScale ? _entity.Hitbox.HeightPx * Projectile.scale * 0.35f', 'false ? _entity.Hitbox.HeightPx * Projectile.scale * 0.35f', 'explicit body scale primitive consumer', id='explicit-mirror-width-floored'),
    pytest.param('check_explicit_body_scale', 'Content/Projectiles/GeneratedProjectile.Visuals.cs', 'preserveWidth: exactScale', 'preserveWidth: false', 'explicit body scale primitive consumer', id='explicit-mirror-line-policy-lost'),
    pytest.param('check_explicit_body_scale', 'Common/VFX/InfiniVfxRuntime.cs', 'preserveWidth ? width : Math.Max(1f, width)', 'Math.Max(1f, width)', 'explicit body scale final line consumer', id='explicit-mirror-final-width-floored'),
    pytest.param('check_explicit_body_scale', 'Common/VFX/InfiniVfxRuntime.cs', 'preserveWidth ? 0f : 0.01f', '0.01f', 'explicit body scale final line consumer', id='explicit-mirror-small-segment-suppressed'),
    pytest.param('check_explicit_body_scale', 'Common/VFX/InfiniVfxRuntime.cs', '!float.IsFinite(width) || width <= 0f', 'width < 0f', 'explicit body scale final line consumer', id='explicit-line-invalid-width-not-refused'),
    pytest.param('check_vfx_sound_contract', 'Common/Models/VfxManifestSpec.cs', '"Item169" => SoundID.Item169', '"Item169" => SoundID.Item1', 'exact palette', id='restored-sound-sample-substitution'),
    pytest.param('check_vfx_sound_contract', 'Common/Models/VfxSoundSpec.cs', 'PitchVariance = PitchVariance', 'PitchVariance = sample.PitchVariance', 'exact controls', id='native-jitter-overrides-authored-zero'),
    pytest.param('check_vfx_sound_contract', 'Common/Models/VfxSoundSpec.cs', 'new SoundStyle(sample.SoundPath, sample.Variants, sample.Type)', 'sample with', 'independent pitch', id='hidden-native-music-pitch'),
    pytest.param('check_vfx_sound_contract', 'Common/Models/VfxSoundSpec.cs', 'MaxInstances = sample.MaxInstances', 'MaxInstances = 1', 'native playback policy', id='sound-instance-policy-substitution'),
    pytest.param('check_vfx_sound_contract', 'Common/VFX/InfiniItemVfxRuntime.cs', 'if (sound.Volume > 0f) SoundEngine.PlaySound(sound, center);', 'SoundEngine.PlaySound(sound, center);', 'explicit silence', id='sound-zero-spends-native-instance'),
    pytest.param('check_vfx_sound_contract', 'Common/VFX/InfiniVfxRuntime.cs', 'SoundStyle sound = slot.ResolveSoundStyle();', 'SoundStyle sound = SoundID.Item1;', 'shared playback projection', id='projectile-sound-fallback'),
    pytest.param('check_client_source_contracts', 'Common/Config/InfiniGameplayQolConfig.cs', 'RuntimeSpriteCacheMaxTextures = 512', 'RuntimeSpriteCacheMaxTextures = 600', 'runtime cache config parity', id='cache-config-drift'),
    pytest.param('check_client_source_contracts', 'Common/Players/InfiniCraftPlayer.cs', '!config.EnableInventoryAssetPrefetch', 'config.EnableInventoryAssetPrefetch', 'inventory prefetch', id='prefetch-optout-inverted'),
    pytest.param('check_client_source_contracts', 'Common/Players/InfiniCraftPlayer.cs', 'if (ensured >= maxItems)', 'if (ensured < maxItems)', 'inventory prefetch', id='unbounded-prefetch'),
    pytest.param("check_world_transactions", "Common/Models/GeneratedItemData.Apply.cs", "item.healLife = enabled ? Math.Max(0, effects.HealLife) : 0;", "item.healLife = enabled ? Math.Max(0, effects.HealLife) : 1;", "binding-scoped use effects", id="disabled-heal-leak"),
    pytest.param("check_world_transactions", "Content/Items/GeneratedItem.cs", "|| Data.Gameplay.AmmoCategory.Length > 0", "|| false", "ammo remains vanilla consumable", id="ammo-not-consumable"),
    pytest.param("check_world_transactions", "Common/Models/GeneratedItemData.Apply.cs", "activeSpawn && RuntimeProgram.WeaponAmmo", "RuntimeProgram.WeaponAmmo", "explicit weapon ammo use lane", id="ammo-leaks-to-non-shot-use"),
    pytest.param("check_world_transactions", "Content/Items/GeneratedItem.cs", 'rootSpeedOverride: Data.RuntimeProgram.WeaponAmmo?.SpeedBasis == "native_shot" ? velocity.Length() : null', "rootSpeedOverride: velocity.Length()", "ammo shot speed policy", id="ammo-speed-overwrites-authored-choice"),
    pytest.param("check_world_transactions", "Content/Items/GeneratedItem.cs", "StackCost == 1 && ConsumeAcceptedPlacementReceipt(player)", 'StackCost == 1; string decoy = "StackCost == 1 && ConsumeAcceptedPlacementReceipt(player)"', "ConsumeItem", id="string-decoy-is-not-receipt-code"),
    pytest.param("check_delivery_metadata", "Common/Models/GeneratedItemData.Model.cs", "public string Identity { get; set; }", "public bool Fantasy { get; set; } public string Identity { get; set; }", "parent_summary_dto", id="foreign-nonstring-summary-field"),
    pytest.param("check_delivery_metadata", "Common/Models/GeneratedItemData.Model.cs", "public string Identity { get; set; }", 'public string Fantasy => "invented"; public string Identity { get; set; }', "parent_summary_dto", id="foreign-computed-summary-property"),
],)
def test_csharp_gate_rejects_source_mutants(gates, monkeypatch, gate, path, old, new, diagnostic):
    _, scanner = gates
    reader = scanner.read
    check = getattr(scanner, gate)
    check()
    assert scanner.ERRORS == []
    source = reader(path)
    assert old in source
    monkeypatch.setattr(scanner, "read", lambda name: source.replace(old, new) if name == path else reader(name))
    check()
    assert any(diagnostic in issue for issue in scanner.ERRORS)

@pytest.mark.parametrize("check,changes", [
    ("check_client_source_contracts", {
        "Common/Services/RuntimeSpriteCache.cs": [("DefaultMaxCachedTextures = 512", "DefaultMaxCachedTextures = 600")],
        "Common/Config/InfiniGameplayQolConfig.cs": [("[DefaultValue(512)]", "[DefaultValue(600)]"), ("RuntimeSpriteCacheMaxTextures = 512", "RuntimeSpriteCacheMaxTextures = 600")],
    }),
    ("check_delivery_metadata", {"Common/Services/GeneratedAssetSyncService.cs": [("MaxAssetFiles = 32", "MaxAssetFiles = 64")]}),
], ids=["consistent-cache-default-change", "larger-complete-roster"])
def test_source_gate_accepts_consistent_refactors(gates, monkeypatch, check, changes):
    _, scanner = gates
    reader = scanner.read
    sources = {}
    for path, replacements in changes.items():
        sources[path] = reader(path)
        for old, new in replacements:
            assert old in sources[path]
            sources[path] = sources[path].replace(old, new)
    monkeypatch.setattr(scanner, "read", lambda name: sources.get(name, reader(name)))
    getattr(scanner, check)()
    assert scanner.ERRORS == []

@pytest.mark.parametrize("path,old,new,diagnostic", [
    ("ModSources/InfiniCrafterLocal/Common/Models/GeneratedItemData.Normalize.cs", "Gameplay.AxePower = ClampInt(Gameplay.AxePower, 0, 100);", "Gameplay.AxePower = ClampInt(Gameplay.AxePower, 0, 50);", "axe_tooltip_percent_parity"),
    ("ModSources/InfiniCrafterLocal/Common/Models/GeneratedItemData.Normalize.cs", "Gameplay.DamageClass = SafeText(Gameplay.DamageClass, 129);", "Gameplay.DamageClass = SafeText(Gameplay.DamageClass, 129).ToLowerInvariant();", "modded_damage_class_case_preserved"),
    ("ModSources/InfiniCrafterLocal/Common/Models/GeneratedItemData.Apply.cs", "item.potion = enabled && effects.Potion;", "item.potion = Gameplay.HealLife > 0;", "potion_flag_is_authored"),
    ("lowery.md", "Gameplay Author-visible semantic aliases: **нет**", "Gameplay Author-visible semantic aliases: **allowed**", "lowery:Gameplay Author-visible "),
], ids=["axe-domain-drift", "case-normalized-modded-owner", "inferred-potion-authority", "restored-gameplay-aliases"])
def test_machine_standardization_audit_rejects_source_mutants(monkeypatch, tmp_path, path, old, new, diagnostic):
    spec = importlib.util.spec_from_file_location("standardization_source_probe", ROOT / "tools/audit_terraria_standardization.py")
    assert spec is not None and spec.loader is not None
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    control = audit.report()
    assert control["ok"] is True
    source = (ROOT / path).read_text(encoding="utf-8")
    assert old in source
    changed = source.replace(old, new)
    monkeypatch.setattr(audit, "read", lambda name: changed if name == path else (ROOT / name).read_text(encoding="utf-8"))
    if path == "lowery.md":
        (tmp_path / path).write_text(changed, encoding="utf-8")
        monkeypatch.setattr(audit, "ROOT", tmp_path)
    assert diagnostic in {row["code"] for row in audit.report()["issues"]}

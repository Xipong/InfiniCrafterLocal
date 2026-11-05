using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Content.Items;
using Terraria.ModLoader.IO;

internal static partial class EngineRuntimeChecks
{
    private static void AuditProjectionsDoNotNormalizeSource()
    {
        foreach (string projection in new[] { "full", "network", "instance" })
        {
            var data = GeneratedPrefixFixture(); StampParentMetadata(data);
            data.Name = "  literal source  "; data.Tags = new[] { "a", "a", " b " };
            data.Gameplay.Width = 1;
            var gameplay = data.Gameplay; var tags = data.Tags;
            string before = JsonSerializer.Serialize(data);
            GeneratedItemData copy = projection switch {
                "full" => GeneratedItemData.FromJson(data.ToJson())!,
                "network" => GeneratedItemData.FromJson(data.ToNetworkJson())!,
                _ => data.CloneForItemInstance(),
            };
            Equal(true, copy is not null, projection + " still passes strict admission");
            Equal(true, before == JsonSerializer.Serialize(data), projection + " source graph unchanged");
            Equal(true, ReferenceEquals(gameplay, data.Gameplay) && ReferenceEquals(tags, data.Tags), projection + " source owners unchanged");
            Equal("literal source", copy!.Name, projection + " retains declared normalization on owned projection");
            Equal(8, copy.Gameplay.Width, projection + " retains engine bound");
            copy.RecipeMeta.ParentIdentities[0] = "generated:copy-only";
            Equal("generated:exact-parent-id", data.RecipeMeta.ParentIdentities[0], projection + " deep independence");
        }
        var invalid = GeneratedPrefixFixture(); invalid.SchemaVersion = 4;
        string invalidBefore = JsonSerializer.Serialize(invalid);
        bool refused = false;
        try { _ = invalid.ToNetworkJson(); } catch (InvalidDataException) { refused = true; }
        Equal(true, refused, "invalid projection remains refused");
        Equal(invalidBefore, JsonSerializer.Serialize(invalid), "failed projection cannot partially normalize source");
    }

    private static void AuditNetworkCopyFailureNeverAliasesOriginal()
    {
        var data = GeneratedPrefixFixture();
        data.RecipeMeta.AssetTransport = "http"; data.RecipeMeta.AssetBaseUrl = "https://offline.invalid";
        string before = JsonSerializer.Serialize(data);
        using var refusal = new MonoMod.RuntimeDetour.Hook(typeof(GeneratedItemData).GetMethod("FromJson")!,
            (Func<string?, GeneratedItemData?>)(_ => null));
        bool failed = false;
        try { typeof(GeneratedItemRegistryService).GetMethod("PrepareForNetworkSync", BindingFlags.Static | BindingFlags.NonPublic)!.Invoke(null, new object[] { data, true }); }
        catch (TargetInvocationException error) when (error.InnerException is InvalidDataException) { failed = true; }
        Equal(true, failed, "failed network readback has explicit refusal, never source alias");
        Equal(true, before == JsonSerializer.Serialize(data), "failed network preparation cannot stamp source metadata");
    }

    private static void AuditAtlasAllSkipsEffectTraversal()
    {
        var data = GeneratedPrefixFixture(); data.RuntimeProgram = null!;
        Equal(true, InfiniCrafterLocal.Common.UI.RecipeJournalView.MatchesEffect(data,
            InfiniCrafterLocal.Common.UI.RecipeJournalView.EffectFilter.All), "All does not inspect or allocate effect projections");
        data = GeneratedPrefixFixture();
        Equal(false, InfiniCrafterLocal.Common.UI.RecipeJournalView.MatchesEffect(data,
            InfiniCrafterLocal.Common.UI.RecipeJournalView.EffectFilter.Healing), "specific filters still inspect effects");
        data.Gameplay.PickPower = 50;
        Equal(true, InfiniCrafterLocal.Common.UI.RecipeJournalView.MatchesEffect(data,
            InfiniCrafterLocal.Common.UI.RecipeJournalView.EffectFilter.Mining), "specific filter positive retained");
    }

    private static void AuditDiskFailureCannotProduceCompactOnlySave()
    {
        WithGeneratedPrefixScope(() => {
            using var serializer = WithPersistenceBoolSerializer();
            var registryProperty = typeof(InfiniCrafterLocal.InfiniCrafterLocalMod).GetProperty("GeneratedItems")!;
            object? previous = registryProperty.GetValue(null);
            int world = Terraria.Main.worldID;
            try {
                Terraria.Main.worldID = 713259;
                using var registry = new GeneratedItemRegistryService(); registryProperty.SetValue(null, registry);
                var data = GeneratedPrefixFixture(); data.Id = "audit-durable"; StampParentMetadata(data);
                GeneratedItemRegistryService.StampCurrentWorld(data);
                data.Debug["durableDiagnostic"] = JsonSerializer.SerializeToElement("full local definition");
                registry.RegisterLocal(data, ensureAssets: false);
                string file = Directory.GetFiles(registry.StoreRoot, "*.json", SearchOption.AllDirectories).Single();
                DateTime timestamp = File.GetLastWriteTimeUtc(file);
                var item = GeneratedPrefixHost(data);
                var tag = new TagCompound(); item.SaveData(tag);
                Equal(timestamp, File.GetLastWriteTimeUtc(file), "identical full projection does not rewrite disk");
                var loaded = GeneratedItemData.FromLocalCacheJson(File.ReadAllText(file))!;
                Equal("full local definition", loaded.Debug["durableDiagnostic"].GetString()!, "durable projection retains local diagnostics");
                EqualParentMetadata(data, loaded, "durable full definition");
                data.Debug["extraLocalOnly"] = JsonSerializer.SerializeToElement("changed full projection");
                Equal(GeneratedDefinitionPersistenceStatus.Written, registry.PersistOne(data).Status, "network-equivalent but different full diagnostics must persist");
                Equal(GeneratedDefinitionPersistenceStatus.Unchanged, registry.PersistOne(data).Status, "only exact stored projection skips write");
                File.Delete(file); Directory.CreateDirectory(file); // Atomic rename must fail on every host, including root.
                var failed = registry.PersistOne(data);
                Equal(GeneratedDefinitionPersistenceStatus.Failed, failed.Status, "disk failure has explicit outcome");
                Equal(true, failed.Error is IOException or UnauthorizedAccessException, "disk failure retains the native filesystem cause");
                var unhydrated = GeneratedPrefixHost(GeneratedItemData.FromPlayerSaveJson(data.ToPlayerSaveJson())!);
                var unhydratedTag = new TagCompound(); unhydrated.SaveData(unhydratedTag);
                Equal(true, unhydratedTag.ContainsKey("infiniDefinitionV5"), "compact item also protects full registry-only definition when disk fails");
                var failedTag = new TagCompound(); item.SaveData(failedTag);
                Equal(true, failedTag.ContainsKey("infiniDefinitionV5"), "disk failure retains recoverable full definition, not compact-only save");
                var corruptTag = PersistenceNbtRoundtrip(failedTag); corruptTag["infiniDefinitionV5"] = 13;
                var corrupt = GeneratedPrefixHost(GeneratedItemData.Placeholder()); corrupt.LoadData(corruptTag);
                Equal(data.Id, corrupt.Data.Id, "malformed optional recovery never destroys valid compact identity");
                var recovered = GeneratedPrefixHost(GeneratedItemData.Placeholder()); recovered.LoadData(PersistenceNbtRoundtrip(failedTag));
                Equal(false, GeneratedItemData.IsPlayerSaveReferenceOnly(recovered.Data), "failed disk save/reload recovers accepted definition");
                EqualParentMetadata(data, recovered.Data, "inline disk-failure recovery");
                Equal("full local definition", recovered.Data.Debug["durableDiagnostic"].GetString()!, "inline recovery keeps full diagnostics");
                Terraria.Main.worldID++;
                var foreign = GeneratedPrefixHost(GeneratedItemData.Placeholder()); foreign.LoadData(PersistenceNbtRoundtrip(failedTag));
                Equal(true, GeneratedItemData.IsPlayerSaveReferenceOnly(foreign.Data), "foreign recovery cannot activate in another world");
                var foreignTag = new TagCompound(); foreign.SaveData(foreignTag);
                Equal(true, foreignTag.ContainsKey("infiniDefinitionV5"), "unresolved foreign save preserves recovery bytes");
                Terraria.Main.worldID--;
                var home = GeneratedPrefixHost(GeneratedItemData.Placeholder()); home.LoadData(PersistenceNbtRoundtrip(foreignTag));
                EqualParentMetadata(data, home.Data, "return to owning world retains recovery");
                Equal(0, Directory.GetFiles(Path.GetDirectoryName(file)!, "*.tmp").Length, "failed atomic write cleans owned temp file");
                Directory.Delete(file);
                item.SaveData(tag);
                registry.ReloadLocalCacheForCurrentWorld();
                Equal(true, registry.TryGet(data.Id, out loaded!), "same definition is recoverable after retry/reload");
                EqualParentMetadata(data, loaded, "retry/reload");
                var restored = GeneratedPrefixHost(GeneratedItemData.Placeholder()); restored.LoadData(PersistenceNbtRoundtrip(tag));
                Equal(data.Id, restored.Data.Id, "existing compact save wire remains readable");
                Equal(true, GeneratedItemData.IsPlayerSaveReferenceOnly(restored.Data), "save remains reference-only");
                registryProperty.SetValue(null, null);
                var large = GeneratedItemData.FromJson(data.ToJson())!;
                large.Id = new string('界', 64); large.RecipeKey = new string('界', 120);
                large.Name = large.ParentA = large.ParentB = string.Concat(Enumerable.Repeat("😀", 80));
                var compact = GeneratedItemData.FromPlayerSaveJson(large.ToPlayerSaveJson())!;
                Equal("", compact.RecipeKey, "fixture reaches existing lossy 4KiB reference projection");
                var largeTag = new TagCompound(); GeneratedPrefixHost(large).SaveData(largeTag);
                var largeRestored = GeneratedPrefixHost(GeneratedItemData.Placeholder()); largeRestored.LoadData(PersistenceNbtRoundtrip(largeTag));
                Equal(large.RecipeKey, largeRestored.Data.RecipeKey, "inline recovery binds the actual compact projection, preserving omitted full recipe key");
            } finally { registryProperty.SetValue(null, previous); Terraria.Main.worldID = world; }
        });
    }

    private static void AuditCraftKeepsManualMute()
    {
        float sound = Terraria.Main.soundVolume, music = Terraria.Main.musicVolume, ambient = Terraria.Main.ambientVolume;
        try {
            var owner = new InfiniCraftPlayer();
            var capture = typeof(InfiniCraftPlayer).GetMethod("CaptureAudioSettingsSnapshot", CraftFields);
            foreach (bool mutedBefore in new[] { true, false }) {
                Terraria.Main.soundVolume = Terraria.Main.musicVolume = Terraria.Main.ambientVolume = mutedBefore ? 0f : .7f;
                capture?.Invoke(owner, null); // Baseline guard setup; removed guard has no operation to seed.
                Terraria.Main.soundVolume = Terraria.Main.musicVolume = Terraria.Main.ambientVolume = 0f;
                typeof(InfiniCraftPlayer).GetMethod("ClearCraft", CraftFields)!.Invoke(owner, null);
                Equal(0f, Terraria.Main.soundVolume, "manual SFX mute survives craft retirement");
                Equal(0f, Terraria.Main.musicVolume, "manual music mute survives craft retirement");
                Equal(0f, Terraria.Main.ambientVolume, "manual ambient mute survives craft retirement");
            }
        } finally { Terraria.Main.soundVolume = sound; Terraria.Main.musicVolume = music; Terraria.Main.ambientVolume = ambient; }
    }

    private static void AuditDrawQueuesColdTexturePreparation()
    {
        WithLighting((_, __) => {
            using var peers = new ReviewPeers(); using var probe = new AssetInvalidationProbe();
            string path = Path.Combine(Terraria.Program.SavePath, "audit-queued.png");
            File.WriteAllBytes(path, AssetOwnerCanonical);
            var item = probe.Item("audit-queued", path);
            peers.Registry.RegisterLocal(item.Data, persist: false, ensureAssets: false);
            typeof(GeneratedItem).GetField("_lastHydrationTick", AssetOwnerInstance)!.SetValue(item, -9999);
            int validations = 0;
            using var validation = new MonoMod.RuntimeDetour.Hook(typeof(GeneratedAssetSyncService).GetMethod("IsValidCachedAsset", BindingFlags.Static | BindingFlags.NonPublic)!,
                (AssetValidateHook)((original, file, descriptor) => { validations++; return original(file, descriptor); }));
            item.PreDrawInInventory(probe.Batch, Microsoft.Xna.Framework.Vector2.Zero, new Microsoft.Xna.Framework.Rectangle(0, 0, 32, 32), Microsoft.Xna.Framework.Color.White, Microsoft.Xna.Framework.Color.White, Microsoft.Xna.Framework.Vector2.Zero, 1);
            item.PreDrawInInventory(probe.Batch, Microsoft.Xna.Framework.Vector2.Zero, new Microsoft.Xna.Framework.Rectangle(0, 0, 32, 32), Microsoft.Xna.Framework.Color.White, Microsoft.Xna.Framework.Color.White, Microsoft.Xna.Framework.Vector2.Zero, 1);
            Equal(0, validations, "cold draw does not validate PNG bodies or hashes");
            Equal(0, probe.Loads.Count, "cold draw never decodes or uploads a texture");
            Equal(2, probe.QueuedActions, "one coalesced hydration and one coalesced texture preparation callback");
            probe.Batch.End(); probe.DrainOwnerQueue();
            Equal(1, probe.Loads.Count, "existing Main.Update queue prepares texture once");
            Equal(true, validations > 0, "queued hydration still executes mandatory asset integrity validation");
            Equal(probe.OwnerThread, probe.Loads[0].Thread, "texture preparation stays on graphics owner");
            probe.Batch.Begin(); probe.Draw(item);
            Equal(1, probe.Loads.Count, "warm draw reuses prepared texture");
            probe.Cache.Clear();
            System.Threading.Tasks.Task.Run(() => probe.Cache.TryGetReady(path)).GetAwaiter().GetResult();
            int world = Terraria.Main.worldID;
            try {
                Terraria.Main.worldID++;
                probe.Batch.End(); probe.DrainOwnerQueue();
                Equal(1, probe.Loads.Count, "old-world queued preparation cannot publish into another world");
            } finally { Terraria.Main.worldID = world; }
            probe.Cache.TryGetReady(path); probe.DrainOwnerQueue();
            Equal(2, probe.Loads.Count, "canceled preparation can be requested again in owning world");
            probe.Batch.Begin(); probe.Draw(item); probe.Cache.Clear();
            System.Threading.Tasks.Task.Run(() => probe.Cache.TryGetReady(path)).GetAwaiter().GetResult();
            Equal(2, probe.Loads.Count, "worker request performs no decode/upload");
            probe.Cache.Dispose(); probe.Batch.End(); probe.DrainOwnerQueue();
            Equal(2, probe.Loads.Count, "queued preparation cannot resurrect disposed cache");
        });
    }
}

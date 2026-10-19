using System;
using System.IO;
using System.Linq;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Content.Items;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;

internal static partial class EngineRuntimeChecks
{
    // Linked canonical sources, actual delivery JSON and bytes, real FNA CPU
    // queues; only GPU decode/upload/dispose/flush are intercepted by the probe.
    private static void DocxReadyQueryAliasReachesInventoryAndWorld()
    {
        WithLighting((_, __) => {
            using var peers = new ReviewPeers(); using var probe = new AssetInvalidationProbe();
            var data = GeneratedItemData.FromJson(File.ReadAllText("tools/fixtures/docx-image-ready-delivered.json"))
                ?? throw new Exception("retained final Python delivery must be admitted by native DTO");
            GeneratedItemRegistryService.StampCurrentWorld(data);
            string file = GeneratedAssetSyncService.FileNameFromPath(data.Visual.SpritePath);
            byte[] expected = File.ReadAllBytes("tools/fixtures/docx-image-ready.png");
            Equal(true, data.Visual.SpritePath.Contains("?revision=2#cached"), "fixture retains URL query selector");
            CommitAssetOwner(probe.Sync, data.Id, file, expected);
            probe.Batch.End(); probe.DrainOwnerQueue(); probe.Batch.Begin();
            peers.Registry.RegisterLocal(data, persist: false, ensureAssets: false);
            var item = ReviewItem(data);
            typeof(GeneratedItem).GetField("_lastHydrationTick", AssetOwnerInstance)!.SetValue(item, (int)Terraria.Main.GameUpdateCount);
            string before = item.Data.ToJson();
            Texture2D texture = probe.Draw(item);
            Equal(true, expected.SequenceEqual(probe.Loads.Single().Bytes), "inventory opens exact delivered PNG bytes");
            int count = probe.QueuedSprites; float rotation = .25f, scale = 1f;
            Equal(false, item.PreDrawInWorld(probe.Batch, Color.White, Color.White, ref rotation, ref scale, 0), "world suppresses native proxy");
            Equal(count + 1, probe.QueuedSprites, "world submits actual image to FNA queue");
            Equal(true, ReferenceEquals(texture, probe.Cache.TryGet(data.Visual.SpritePath)), "both draws share exact selected hot generation");
            Equal(1, probe.Loads.Count, "hot query alias does not decode again");
            Equal(before, item.Data.ToJson(), "drawing never rewrites accepted definition");
            Equal(0, probe.Sync.GetDebugSnapshot().DownloadStartedCount, "no HTTP/provider traffic in this fixture");
        });
    }

    private static void DocxMissingImageSuppressesProxyAndVerifiedCommitRecovers()
    {
        WithLighting((_, __) => {
            using var peers = new ReviewPeers(); using var probe = new AssetInvalidationProbe();
            string file = "docx_missing_" + Guid.NewGuid().ToString("N") + ".png";
            var item = probe.Item("docx_missing", Path.Combine(probe.Sync.CacheRoot, file));
            void NoProxy(string label) {
                int before = probe.QueuedSprites; float rotation = 0, scale = 1;
                Equal(false, item.PreDrawInInventory(probe.Batch, Vector2.Zero, new Rectangle(0, 0, 32, 32), Color.White, Color.White, Vector2.Zero, 1), label + " inventory vetoes proxy");
                Equal(false, item.PreDrawInWorld(probe.Batch, Color.White, Color.White, ref rotation, ref scale, 0), label + " world vetoes proxy");
                Equal(before, probe.QueuedSprites, label + " does not fabricate replacement art");
            }
            NoProxy("missing"); NoProxy("negative cache");
            Equal(1, probe.Cache.GetDebugSnapshot().MissingOrBadCount, "one real missing-file failure");
            Equal(0, probe.Attempts, "missing file never reaches decode");
            CommitAssetOwner(probe.Sync, item.Data.Id, file, AssetOwnerCanonical);
            probe.Batch.End(); probe.DrainOwnerQueue(); probe.Batch.Begin();
            probe.Draw(item); Equal(1, probe.Loads.Count, "verified delivery clears negative cache and recovers immediately");
            probe.FailDecode = true; probe.Cache.Invalidate(item.Data.Visual.SpritePath);
            NoProxy("decode failure"); NoProxy("failure backoff");
            Equal(2, probe.Attempts, "one failed decode then shared inventory/world backoff");
            probe.FailDecode = false; probe.Cache.Invalidate(item.Data.Visual.SpritePath);
            probe.Draw(item); Equal(3, probe.Attempts, "explicit invalidation enables one real recovery decode");
            item.Data.Visual.RenderSizePx = null;
            int count = probe.QueuedSprites; float rotation = 0, scale = 1;
            Equal(false, item.PreDrawInWorld(probe.Batch, Color.White, Color.White, ref rotation, ref scale, 0), "absent world metadata cannot expose proxy");
            Equal(count, probe.QueuedSprites, "absent metadata does not invent scale");
            Equal(true, item.Data.Visual.RenderSizePx is null, "absence remains absence");
        });
    }

    private static void DocxNativeItemReadyDomainRejectsUnfinishedProducer()
    {
        var wire = System.Text.Json.Nodes.JsonNode.Parse(File.ReadAllText("tools/fixtures/docx-image-ready-delivered.json"))!;
        foreach (string status in new[] { "pending", "generating", "skipped_disabled_by_settings", "not_required", "future_unknown" }) {
            wire["visual"]!["spriteStatus"] = status;
            Equal(true, GeneratedItemData.FromJson(wire.ToJsonString()) is null, "unfinished root producer refused: " + status);
        }
        foreach (string status in new[] { "generated", "generated_warn_invalid", "fallback", "fallback_after_failed_generation" }) {
            wire["visual"]!["spriteStatus"] = status;
            var data = GeneratedItemData.FromJson(wire.ToJsonString());
            Equal(true, data is not null, "existing completed producer admitted: " + status);
        }
    }

    private static void DocxNativeSiblingProducerStatusesMatchDelivery()
    {
        string json = File.ReadAllText("tools/fixtures/docx-image-ready-delivered.json");
        foreach (string status in new[] { "generated", "generated_warn_invalid", "fallback", "fallback_after_failed_generation", "pending", "generating", "not_required", "future_unknown", "" })
        {
            bool expected = status is "generated" or "generated_warn_invalid" or "fallback" or "fallback_after_failed_generation";
            var wire = System.Text.Json.Nodes.JsonNode.Parse(json)!;
            var visual = wire["runtimeProgram"]!["entities"]![2]!["visual"]!;
            visual["assetMode"] = "baked_sprite";
            visual["renderSizePx"] = 16;
            visual["forwardAngleDegrees"] = 0;
            visual["spriteStatus"] = status;
            Equal(expected, GeneratedItemData.FromJson(wire.ToJsonString()) is not null,
                "baked entity completion status matches final delivery: " + status);

            var equipment = GeneratedItemData.FromJson(json)!;
            equipment.Accessory.Enabled = true;
            equipment.Visual.EquipOverlayPath = "offline-equipment-overlay.png";
            equipment.Visual.EquipOverlayStatus = status;
            bool accepted = true;
            try { equipment.Normalize(); }
            catch (InvalidDataException) { accepted = false; }
            Equal(expected, accepted, "equipment overlay completion status matches final delivery: " + status);
        }
    }

    private static void DocxExplicitUnavailableAndFixtureKeepDiagnosticProxy()
    {
        WithLighting((_, __) => {
            using var peers = new ReviewPeers(); using var probe = new AssetInvalidationProbe();
            foreach (string sourceMode in new[] { "corrupt_reference", "test_fixture", "developer_fixture" }) {
                var data = GeneratedItemData.Placeholder(); data.SourceMode = sourceMode;
                var item = ReviewItem(data); float rotation = 0, scale = 1;
                Equal(true, item.PreDrawInInventory(probe.Batch, Vector2.Zero, new Rectangle(0, 0, 32, 32), Color.White, Color.White, Vector2.Zero, 1), sourceMode + " retains explicit diagnostic proxy");
                Equal(true, item.PreDrawInWorld(probe.Batch, Color.White, Color.White, ref rotation, ref scale, 0), sourceMode + " retains world diagnostic proxy");
            }
            Equal(0, probe.Loads.Count, "no invented diagnostic texture");
        });
    }
}

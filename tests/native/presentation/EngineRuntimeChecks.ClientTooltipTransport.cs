using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Common.Players;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader.IO;

internal static partial class EngineRuntimeChecks
{
    private static void ClientTooltipWireBoundsAndPersistence()
    {
        var report = new ClientTooltipObservation(new[] { "два", "", "🦊" }, "ru-RU");
        var frozen = ClientTooltipWire.Freeze(report)!;
        report.Lines[0] = "mutated";
        var roundtrip = ClientTooltipWire.Restore(ClientTooltipWire.Save(frozen))!;
        Equal("два", roundtrip.Lines[0], "snapshot copied before mutation");
        Equal("🦊", roundtrip.Lines[2], "UTF-8 preserves non-BMP text");
        Equal("observed", roundtrip.Status, "verified wire reports unverified observed status");
        Equal(true, ClientTooltipWire.Restore(ClientTooltipWire.Save(null)) is null, "absent observation stays absent");
        var empty = ClientTooltipWire.Restore(ClientTooltipWire.Save(new ClientTooltipObservation(Array.Empty<string>(), "en-US")))!;
        Equal(0, empty.Lines.Length, "observed empty differs from absent");
        Equal("observed", empty.Status, "empty stays observed");
        var large = ClientTooltipWire.Freeze(new ClientTooltipObservation(new[] { new string('я', 9000) }, "ru-RU"))!;
        Equal("refused_utf8_bound", large.Status, "optional oversized unicode refused without clipping");
        Equal(0, ClientTooltipWire.Restore(ClientTooltipWire.Save(large))!.Lines.Length, "refusal still serializes");
        var malformed = ClientTooltipWire.Freeze(new ClientTooltipObservation(new[] { "\ud800" }, "en-US"))!;
        Equal("refused_invalid_encoding", malformed.Status, "invalid UTF-16 not silently replaced");
        foreach (byte[] bytes in new[] {
            new byte[] { 1 },                                  // truncated block length
            new byte[] { 1, 0, 255 },                         // unknown status
            new byte[] { 255, 255 },                          // blocked before allocation
            new byte[] { 1, 0 },                              // missing block
            new byte[] { 0, 0, 123 },                         // trailing saved bytes
            new byte[] { 5, 0, 1, 1, 0, 255, 0 },            // invalid UTF-8 language
        })
        {
            try { ClientTooltipWire.Restore(bytes); throw new InvalidOperationException("invalid tooltip accepted"); }
            catch (Exception e) when (e is EndOfStreamException or InvalidDataException or System.Text.DecoderFallbackException) { }
        }
        // Every lane freezes the same observations across a save/reconnect.
        using var serializer = WithPersistenceBoolSerializer();
        WithPlayer((player, owner) => {
            owner.Initialize();
            var rows = new List<TagCompound>();
            var add = typeof(InfiniCraftPlayer).GetMethod("AddPendingRemoteCraftTag", BindingFlags.Instance | BindingFlags.NonPublic)!;
            for (int lane = 0; lane < 3; lane++) {
                var request = new GeneratorClient.PreparedGenerationRequest {
                    RefundA = new Item(ItemID.Wood, 1), RefundB = new Item(ItemID.StoneBlock, 1),
                    ClientTooltipA = frozen, ClientTooltipB = large,
                };
                add.Invoke(owner, new object[] { rows, lane, new string((char)('a' + lane), 32), request });
            }
            WithPlayer((nextPlayer, restored) => {
                restored.Initialize();
                typeof(InfiniCraftPlayer).GetMethod("RestorePendingRemoteCrafts", BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(restored, new object[] { rows });
                var saved = (List<TagCompound>)typeof(InfiniCraftPlayer).GetMethod("SavePendingRemoteCrafts", BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(restored, null)!;
                Equal(3, saved.Count, "all lanes restored");
                for (int lane = 0; lane < 3; lane++) {
                    var row = saved.Single(x => x.GetInt("laneIndex") == lane);
                    Equal(new string((char)('a' + lane), 32), row.GetString("requestId"), "same request identity");
                    Equal("два", ClientTooltipWire.Restore(row.GetByteArray("clientTooltipA"))!.Lines[0], "observed snapshot preserved");
                    Equal("refused_utf8_bound", ClientTooltipWire.Restore(row.GetByteArray("clientTooltipB"))!.Status, "refused snapshot preserved");
                }
            });
        });
    }
}

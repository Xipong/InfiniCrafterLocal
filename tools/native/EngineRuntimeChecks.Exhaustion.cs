#nullable enable
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.Services;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    // Check-only patch compiles against the old DTO/consumer. Candidate-only
    // members are discovered, never statically referenced. Fixtures and native
    // consumers are the existing NamedItemEffects/QuickUtilityActivation owners.
    private static GeneratedItemData ExhaustionData(string id, int? ticks, bool named = false)
    {
        var data = named ? NamedItemEffectsFixture() : MobilityConsumptionFixture("", 0);
        data.Id = id; data.Name = "Source " + id; data.SourceMode = "test_fixture";
        data.Gameplay.GeneratedBuff = new GeneratedBuffSpec { DurationTicks = 60, JumpBoost = 1f };
        GeneratedItemRegistryService.StampCurrentWorld(data);
        var root = JsonNode.Parse(data.ToNetworkJson())!;
        if (ticks.HasValue)
        {
            root["gameplay"]!["generatedBuff"]!["exhaustionTicks"] = ticks.Value;
            if (named)
            {
                root["runtimeProgram"]!["effectGroups"]![0]!["generatedBuff"]!["exhaustionTicks"] = ticks.Value;
                root["runtimeProgram"]!["effectGroups"]![1]!["generatedBuff"]!["exhaustionTicks"] = 0;
            }
        }
        return GeneratedItemData.FromJson(root.ToJsonString())
            ?? throw new InvalidOperationException("native reader refused valid exhaustionTicks=" + ticks);
    }

    private static List<(string Id, string Definition, string Name, int Ticks)> ExhaustionRows(InfiniCraftPlayer player)
    {
        var method = typeof(InfiniCraftPlayer).GetMethod("CaptureGeneratedItemExhaustion", MobilityConsumptionFlags)
            ?? throw new InvalidOperationException("native status capture API missing");
        var rows = new List<(string, string, string, int)>();
        foreach (object row in (IEnumerable)method.Invoke(player, null)!)
        {
            object Value(string name) => row.GetType().GetProperty(name)!.GetValue(row)!;
            rows.Add(((string)Value("ItemId"), (string)Value("DefinitionIdentity"), (string)Value("ItemName"), (int)Value("RemainingTicks")));
        }
        return rows;
    }
    private static bool ExhaustionApply(InfiniCraftPlayer player, GeneratedBuffSpec? buff, GeneratedItemData? source, uint? tick = null)
    {
        var method = typeof(InfiniCraftPlayer).GetMethod(nameof(InfiniCraftPlayer.ApplyGeneratedUtilityBuff))!;
        if (method.GetParameters().Length != 4 || method.ReturnType != typeof(bool))
            throw new InvalidOperationException("native buff-only acceptance/source/activationTick API missing");
        return (bool)method.Invoke(player, new object?[] { buff, false, source, tick })!;
    }
    private static int ExhaustionBuffTicks(InfiniCraftPlayer player)
        => (int)typeof(InfiniCraftPlayer).GetField("_generatedBuffTicks", MobilityConsumptionFlags)!.GetValue(player)!;
    private static void ExhaustionBuffTick(InfiniCraftPlayer player)
        => typeof(InfiniCraftPlayer).GetMethod("TickGeneratedUtilityBuff", MobilityConsumptionFlags)!.Invoke(player, null);

    private static void EX01DtoPresenceRawScopeAndIdentity()
    {
        foreach (bool named in new[] { false, true })
        {
            var old = ExhaustionData("ex-old", null, named);
            string oldJson = old.ToNetworkJson(), oldIdentity = GeneratedItemRegistryService.DefinitionIdentity(old);
            Equal(false, oldJson.Contains("exhaustionTicks", StringComparison.Ordinal), "omission is not a zero backfill");
            Equal(oldIdentity, GeneratedItemRegistryService.DefinitionIdentity(GeneratedItemData.FromJson(oldJson)!), "old identity stable across reader");
            foreach (int ticks in new[] { 0, 1, 21600 })
            {
                var data = ExhaustionData("ex-valid", ticks, named);
                var round = GeneratedItemData.FromJson(data.ToLocalCacheJson())!;
                var root = JsonNode.Parse(round.ToNetworkJson())!;
                Equal(ticks, (int)root["gameplay"]!["generatedBuff"]!["exhaustionTicks"]!, "default policy survives full/cache/network readers");
                if (named) Equal(ticks, (int)root["runtimeProgram"]!["effectGroups"]![0]!["generatedBuff"]!["exhaustionTicks"]!, "named policy survives readers");
            }
            foreach (string literal in new[] { "null", "true", "\"60\"", "1.5", "1.0", "1e1", "-1", "21601", "2147483648", "[]", "{}" })
            {
                var root = JsonNode.Parse(oldJson)!;
                JsonNode buff = named ? root["runtimeProgram"]!["effectGroups"]![0]!["generatedBuff"]! : root["gameplay"]!["generatedBuff"]!;
                buff["exhaustionTicks"] = JsonNode.Parse(literal);
                Equal(true, GeneratedItemData.FromJson(root.ToJsonString()) is null, "present raw invalid " + literal + " named=" + named);
            }
            var wrongScope = JsonNode.Parse(oldJson)!;
            wrongScope["gameplay"]!["exhaustionTicks"] = 60;
            Equal(true, GeneratedItemData.FromJson(wrongScope.ToJsonString()) is null, "policy cannot escape generatedBuff scope");
        }
        var neutral = new GeneratedBuffSpec { DurationTicks = 60 };
        var policy = typeof(GeneratedBuffSpec).GetProperty("ExhaustionTicks")
            ?? throw new InvalidOperationException("nullable exhaustion DTO missing");
        Equal(typeof(int?), policy.PropertyType, "nullable integer, no authored default");
        policy.SetValue(neutral, 60);
        Equal(false, neutral.HasAnyEffect, "policy alone is not an executable buff");
    }

    private static void EX02ConsumerSourceGateAndLegacyControls()
    {
        using var scope = new MobilityConsumptionNativeScope();
        WithPlayer((player, mp) => {
            PrepareMobilityConsumptionPlayer(player); MaterialClock(100);
            var source = ExhaustionData("ex-gate", 120, true);
            var primary = source.RuntimeProgram.EffectGroups![0].GeneratedBuff!;
            Equal(false, ExhaustionApply(mp, primary, null), "positive policy requires source");
            var foreign = GeneratedItemData.FromJson(source.ToNetworkJson())!;
            foreign.RecipeMeta.WorldId = "foreign";
            Equal(false, ExhaustionApply(mp, primary, foreign), "positive policy requires current world");
            var savedRef = GeneratedItemData.FromPlayerSaveJson(source.ToPlayerSaveJson())!;
            Equal(false, ExhaustionApply(mp, primary, savedRef), "positive policy cannot fabricate identity from saved reference");
            Equal(false, ExhaustionApply(mp, null, source), "null cannot start fatigue");
            Equal(false, ExhaustionApply(mp, new GeneratedBuffSpec { DurationTicks = 60 }, source), "inert cannot start fatigue");
            Equal(0, ExhaustionRows(mp).Count, "failed attempts leave no timer");
            Equal(true, ExhaustionApply(mp, primary, source), "real buff accepted");
            MaterialClock(110); ExhaustionBuffTick(mp);
            Equal(false, ExhaustionApply(mp, primary, GeneratedItemData.FromJson(source.ToNetworkJson())!), "hydrated definition shares timer");
            Equal(false, ExhaustionApply(mp, source.RuntimeProgram.EffectGroups[1].GeneratedBuff, source), "explicit-zero alternate group cannot bypass active source timer");
            Equal(59, ExhaustionBuffTicks(mp), "refusal does not refresh existing equal buff");
            Equal(110, ExhaustionRows(mp).Single().Ticks, "refusal does not restart timer");
            var old = ExhaustionData("ex-other-legacy", null);
            Equal(true, ExhaustionApply(mp, old.Gameplay.GeneratedBuff, old), "different legacy item is not globally blocked");
            Equal(true, ExhaustionApply(mp, old.Gameplay.GeneratedBuff, null), "unrelated timer does not globally gate source-less legacy calls");
            MaterialClock(220);
            Equal(0, ExhaustionRows(mp).Count, "world tick expiry without drawing/advancement");
            Equal(true, ExhaustionApply(mp, primary, source), "exact expiry admits");
        });
        WithPlayer((_, mp) => {
            var old = ExhaustionData("ex-old-direct", null);
            Equal(true, ExhaustionApply(mp, old.Gameplay.GeneratedBuff, null), "old source-less call unchanged when no fatigue");
            var zero = ExhaustionData("ex-explicit-zero", 0);
            Equal(true, ExhaustionApply(mp, zero.Gameplay.GeneratedBuff, null), "explicit zero starts no timer and requires no invented identity");
            Equal(0, ExhaustionRows(mp).Count, "no hidden three-minute timer");
        });
    }

    private static void EX03FiveLabeledSourcesCopiesAndImmutableCapture()
    {
        using var scope = new MobilityConsumptionNativeScope();
        WithPlayer((player, mp) => {
            PrepareMobilityConsumptionPlayer(player); MaterialClock(400);
            var sources = Enumerable.Range(0, 5).Select(i => ExhaustionData("ex-five-" + i, 60 + i * 30)).ToArray();
            foreach (var data in sources) Equal(true, ExhaustionApply(mp, data.Gameplay.GeneratedBuff, data), "independent source accepted");
            var before = ExhaustionRows(mp); Equal(5, before.Count, "five distinct status data rows");
            Equal(5, before.Select(r => r.Id).Distinct().Count(), "five labels, not one global status");
            foreach (var data in sources)
            {
                var row = before.Single(r => r.Id == data.Id);
                Equal(data.Name, row.Name, "source label retained");
                Equal(GeneratedItemRegistryService.DefinitionIdentity(data), row.Definition, "exact canonical identity");
                Equal(false, ExhaustionApply(mp, data.Gameplay.GeneratedBuff, GeneratedItemData.FromJson(data.ToNetworkJson())!), "copy/slot cannot bypass");
            }
            MaterialClock(410); Equal(60, before[0].Ticks, "previous capture is immutable value copy");
            Equal(50, ExhaustionRows(mp)[0].Ticks, "capture uses numeric world tick");
            var changed = GeneratedItemData.FromJson(sources[0].ToNetworkJson())!;
            changed.Gameplay.GeneratedBuff.JumpBoost = 2f;
            Equal(true, ExhaustionApply(mp, changed.Gameplay.GeneratedBuff, changed), "same ID with different canonical definition is independent");
            Equal(6, ExhaustionRows(mp).Count, "definition identity participates in key");
            WithPlayer((_, other) => {
                Equal(true, ExhaustionApply(other, sources[0].Gameplay.GeneratedBuff, sources[0]), "another player has independent timer");
                Equal(1, ExhaustionRows(other).Count, "another player never borrows table");
            });
            MaterialClock(470);
            Equal(4, ExhaustionRows(mp).Count, "first original and changed short definition expire without removing later item timers");
            Equal(false, ExhaustionApply(mp, sources[1].Gameplay.GeneratedBuff, sources[1]), "another source remains blocked after first expiry");
            Equal(true, ExhaustionApply(mp, sources[0].Gameplay.GeneratedBuff, sources[0]), "only expired item can reapply");
        });
    }

    private static void EX04ActiveNativeUseKeepsHealCostAndTiming()
    {
        using var scope = new MobilityConsumptionNativeScope();
        WithPlayer((player, mp) => {
            PrepareMobilityConsumptionPlayer(player); MaterialClock(500);
            var source = ExhaustionData("ex-native", 120, true);
            source.RuntimeProgram.Bindings[0].UsePolicy.StackCost = 1;
            source.Gameplay.MaxStack = 9999;
            var host = MobilityConsumptionHost(source); host.Item.stack = 3;
            player.inventory[0] = host.Item;
            Equal(true, host.CanUseItem(player), "first native use admission"); scope.RunNativeSuffix(player);
            Equal(77, player.statLife, "native primary heal once"); Equal(2, host.Item.stack, "first cost unchanged");
            MaterialClock(510); ExhaustionBuffTick(mp);
            player.itemTime = 0; player.itemAnimation = 20;
            Equal(true, host.CanUseItem(player), "fatigue is not a whole-use gate"); scope.RunNativeSuffix(player);
            Equal(97, player.statLife, "exhausted attempt still heals natively"); Equal(1, host.Item.stack, "exhausted attempt still pays authored cost");
            Equal(2, host.UseCalls, "no changed native retry cadence");
            Equal(59, ExhaustionBuffTicks(mp), "active-use caller suppressed generated buff only");
            Equal(110, ExhaustionRows(mp).Single().Ticks, "active-use caller retained timer");
        });
    }

    private static void EX05HeldSourceAndAlternateCannotBypass()
    {
        using var scope = new MobilityConsumptionNativeScope();
        WithPlayer((player, mp) => {
            PrepareMobilityConsumptionPlayer(player); MaterialClock(600);
            var data = ExhaustionData("ex-held", 90, true);
            data.RuntimeProgram.HeldEffectGroupId = "primary_effects";
            data.RuntimeProgram.EffectGroups![0].HealLife = 0;
            data.RuntimeProgram.EffectGroups[0].Potion = false;
            var host = MobilityConsumptionHost(data); player.inventory[0] = host.Item;
            host.HoldItem(player); Equal(1, ExhaustionRows(mp).Count, "held caller starts source fatigue");
            MaterialClock(610); ExhaustionBuffTick(mp); host.HoldItem(player);
            Equal(59, ExhaustionBuffTicks(mp), "held caller cannot equal-effect refresh");
            var copy = MobilityConsumptionHost(GeneratedItemData.FromJson(data.ToNetworkJson())!);
            player.inventory[0] = copy.Item; copy.HoldItem(player);
            Equal(59, ExhaustionBuffTicks(mp), "copy and switched slot retain source fatigue");
            player.altFunctionUse = 2;
            Equal(true, copy.CanUseItem(player), "alternate admission remains independent"); copy.UseItem(player);
            Equal(59, ExhaustionBuffTicks(mp), "alternate group has no buff bypass");
            Equal(80, ExhaustionRows(mp).Single().Ticks, "failed held/copy/alternate never reset fatigue");
        });
    }

    private static void EX06CapacityLifecycleAndActivationAnchor()
    {
        using var scope = new MobilityConsumptionNativeScope();
        WithPlayer((player, mp) => {
            PrepareMobilityConsumptionPlayer(player); MaterialClock(1000);
            var data = ExhaustionData("ex-anchor", 100);
            Equal(true, ExhaustionApply(mp, data.Gameplay.GeneratedBuff, data, 970), "accepted utility uses Prepare anchor");
            Equal(70, ExhaustionRows(mp).Single().Ticks, "fatigue elapsed deducted independently of remaining buff");
            var limitField = typeof(InfiniCraftPlayer).GetField("MaxGeneratedItemExhaustionEntries", MobilityConsumptionFlags)
                ?? throw new InvalidOperationException("explicit bounded native timer capacity missing");
            int limit = (int)limitField.GetRawConstantValue()!;
            Equal(true, limit >= 5 && limit <= 128, "small table still supports five independent sources");
            for (int i = 1; i < limit; i++)
            {
                var other = ExhaustionData("ex-cap-" + i, 100);
                Equal(true, ExhaustionApply(mp, other.Gameplay.GeneratedBuff, other), "fill capacity");
            }
            var overflow = ExhaustionData("ex-overflow", 100);
            Equal(false, ExhaustionApply(mp, overflow.Gameplay.GeneratedBuff, overflow), "full table refuses without evicting active timer");
            Equal(false, ExhaustionApply(mp, data.Gameplay.GeneratedBuff, data), "original source remains blocked after pressure");
            Equal(limit, ExhaustionRows(mp).Count, "bounded table");
            player.dead = true; mp.UpdateDead(); Equal(0, ExhaustionRows(mp).Count, "explicit death clears session state");
            player.dead = false; Equal(true, ExhaustionApply(mp, data.Gameplay.GeneratedBuff, data), "respawn can apply anew");
            mp.Initialize(); Equal(0, ExhaustionRows(mp).Count, "Initialize clears");
            Equal(true, ExhaustionApply(mp, data.Gameplay.GeneratedBuff, data), "reinitialize source accepted");
            mp.OnEnterWorld(); Equal(0, ExhaustionRows(mp).Count, "OnEnterWorld clears");
            Equal(true, ExhaustionApply(mp, data.Gameplay.GeneratedBuff, data), "world retirement precondition");
            var lifecycle = typeof(InfiniCraftPlayer).Assembly.GetType("InfiniCrafterLocal.Common.Players.GeneratedItemExhaustionLifecycleSystem")
                ?? throw new InvalidOperationException("world retirement owner missing");
            object system = Activator.CreateInstance(lifecycle)!;
            Player? oldRetiredSlot = Terraria.Main.player[0];
            var retired = new Player();
            typeof(Player).GetField("modPlayers", BindingFlags.Instance | BindingFlags.NonPublic)!
                .SetValue(retired, Array.Empty<Terraria.ModLoader.ModPlayer>());
            Terraria.Main.player[0] = retired;
            int retiredLookupThrows = 0;
            EventHandler<System.Runtime.ExceptionServices.FirstChanceExceptionEventArgs> observe = (_, e) => {
                if (e.Exception is IndexOutOfRangeException) retiredLookupThrows++;
            };
            AppDomain.CurrentDomain.FirstChanceException += observe;
            try { lifecycle.GetMethod("OnWorldUnload")!.Invoke(system, null); }
            finally {
                AppDomain.CurrentDomain.FirstChanceException -= observe;
                Terraria.Main.player[0] = oldRetiredSlot!;
            }
            Equal(0, ExhaustionRows(mp).Count, "explicit world retirement clears after retired native roster slot");
            Equal(0, retiredLookupThrows, "retired native roster is queried without caught exception/log spam");
            MaterialClock(uint.MaxValue - 20);
            Equal(true, ExhaustionApply(mp, data.Gameplay.GeneratedBuff, data), "wrap timer accepted");
            MaterialClock(10); Equal(69, ExhaustionRows(mp).Single().Ticks, "uint world clock wraps without expiry restart");
            MaterialClock(80); Equal(0, ExhaustionRows(mp).Count, "wrap timer expiry exact");
            var expired = ExhaustionData("ex-elapsed-policy", 10);
            Equal(true, ExhaustionApply(mp, expired.Gameplay.GeneratedBuff, expired, 50), "fatigue already elapsed before delayed commit is not restarted");
            Equal(0, ExhaustionRows(mp).Count, "short fatigue not stretched to remaining buff duration");
        });
    }

    private static byte[] ExhaustionSnapshot(InfiniCraftPlayer mp)
    {
        using var stream = new MemoryStream();
        typeof(InfiniCraftPlayer).GetMethod("WriteGeneratedBuffState", MobilityConsumptionFlags)!.Invoke(mp, new object[] { new BinaryWriter(stream) });
        return stream.ToArray();
    }
    private static void EX07RealUtilityCodecFiveRowsDiscardAndOwnerCorrection()
    {
        using var f = new QuickUtilityPeers(cost: 0);
        f.Mode(2); MaterialClock(2000);
        for (int i = 0; i < 5; i++)
        {
            var data = ExhaustionData("ex-wire-" + i, 120 + i);
            Equal(true, ExhaustionApply(f.ServerBuff, data.Gameplay.GeneratedBuff, data), "server data row");
        }
        var savedCopy = new InfiniCraftPlayer(); f.ServerBuff.CopyClientState(savedCopy);
        Equal(false, (bool)typeof(InfiniCraftPlayer).GetMethod("GeneratedBuffStateDiffers", MobilityConsumptionFlags)!.Invoke(f.ServerBuff, new object[] { savedCopy })!, "copied timer state equal");
        MaterialClock(2001);
        Equal(false, (bool)typeof(InfiniCraftPlayer).GetMethod("GeneratedBuffStateDiffers", MobilityConsumptionFlags)!.Invoke(f.ServerBuff, new object[] { savedCopy })!, "countdown does not request a per-tick timer snapshot");
        byte[] bytes = ExhaustionSnapshot(f.ServerBuff);
        using (var wire = new MemoryStream(bytes))
        {
            var reader = new BinaryReader(wire); reader.ReadByte();
            typeof(InfiniCraftPlayer).GetMethod("DiscardGeneratedBuffState", MobilityConsumptionFlags)!.Invoke(null, new object[] { reader });
            Equal(wire.Length, wire.Position, "discard consumes exact current payload including initial durations and timer rows");
        }
        byte[] packet = new byte[bytes.Length + 1]; packet[0] = InfiniCrafterLocal.Common.InfiniNetPacketIds.SyncGeneratedUtilityBuff;
        bytes.CopyTo(packet, 1);
        f.Mode(3); f.Peers.Receive(packet, 256); Equal(5, ExhaustionRows(f.RemoteBuff).Count, "real handler/reader exposes five remote statuses");
        f.Mode(1); f.Peers.Receive(packet, 256); Equal(5, ExhaustionRows(f.OwnerBuff).Count, "real handler corrects owner");
        var poison = ExhaustionData("ex-client-untrusted", 21600);
        Equal(true, ExhaustionApply(f.OwnerBuff, poison.Gameplay.GeneratedBuff, poison), "client can predict extra row");
        byte[] forged = ExhaustionSnapshot(f.OwnerBuff); byte[] claim = new byte[forged.Length + 1]; claim[0] = packet[0]; forged.CopyTo(claim, 1);
        f.ReceiveServer(claim);
        Equal(5, ExhaustionRows(f.ServerBuff).Count, "untrusted client row never applied");
        var correction = f.Peers.Sent.Single(p => p[0] == packet[0]);
        f.Mode(1); f.Peers.Receive(correction, 256);
        Equal(5, ExhaustionRows(f.OwnerBuff).Count, "server resync removes owner speculative row");
        // Reader guard must reject length BEFORE ReadBytes allocates (all state
        // strings use the existing BinaryWriter 7-bit UTF8 string convention).
        using var malformed = new MemoryStream(); using var writer = new BinaryWriter(malformed);
        writer.Write((byte)7); writer.Write(0); writer.Write(1f); writer.Write(0f);
        writer.Write7BitEncodedInt(1000000); malformed.Position = 0;
        bool rejected = false;
        try { typeof(InfiniCraftPlayer).GetMethod("ReadGeneratedBuffState", MobilityConsumptionFlags)!.Invoke(f.RemoteBuff, new object[] { new BinaryReader(malformed) }); }
        catch (TargetInvocationException error) when (error.InnerException is InvalidDataException) { rejected = true; }
        Equal(true, rejected, "oversized variable string rejected before allocation");
        Equal(5, ExhaustionRows(f.RemoteBuff).Count, "malformed snapshot leaves previously accepted rows untouched");
    }


    private static void EX09AuthoritativeRepeatedSnapshotDoesNotEcho()
    {
        using var f = new QuickUtilityPeers(cost: 0);
        f.Mode(2); MaterialClock(4000);
        var data = ExhaustionData("ex-no-echo", 180);
        Equal(true, ExhaustionApply(f.ServerBuff, data.Gameplay.GeneratedBuff, data), "server starts source timer");
        byte[] bytes = ExhaustionSnapshot(f.ServerBuff);
        byte[] packet = new byte[bytes.Length + 1];
        packet[0] = InfiniCrafterLocal.Common.InfiniNetPacketIds.SyncGeneratedUtilityBuff;
        bytes.CopyTo(packet, 1);
        f.Mode(1); f.Peers.Receive(packet, 256);
        var previous = new InfiniCraftPlayer();
        f.OwnerBuff.CopyClientState(previous);
        f.Peers.Sent.Clear();
        // A repeated authoritative snapshot reanchors the same remaining rows.
        // That receive is not a locally authored timer change requesting resync.
        MaterialClock(4001); f.Peers.Receive(packet, 256);
        f.OwnerBuff.SendClientChanges(previous);
        Equal(0, f.Peers.Sent.Count, "server snapshot receive does not echo a utility resync");
        f.OwnerBuff.CopyClientState(previous);
        var predicted = ExhaustionData("ex-local-new", 180);
        Equal(true, ExhaustionApply(f.OwnerBuff, predicted.Gameplay.GeneratedBuff, predicted), "new local application still works");
        Equal(2, ExhaustionRows(f.OwnerBuff).Count, "receive guard never globally blocks prediction");
        f.OwnerBuff.SendClientChanges(previous);
        Equal(1, f.Peers.Sent.Count, "fresh local change still requests existing authority resync");
    }

    private static void EX08QuickCommitCanonicalPolicyAnchorAndRefusal()
    {
        foreach (byte kind in new byte[] { 1, 2 })
        {
            using var f = new QuickUtilityPeers(kind, cost: 0);
            var field = typeof(GeneratedBuffSpec).GetProperty("ExhaustionTicks")
                ?? throw new InvalidOperationException("nullable exhaustion DTO missing");
            field.SetValue(f.Data.Gameplay.GeneratedBuff, 180);
            f.ApplyEquipmentSync = true; // recopy the now policy-bearing native Item witness
            MaterialClock(3000); byte[] prepare = f.Prepare(), ready = f.Ready(prepare), commit = f.Commit(ready);
            MaterialClock(3030); f.ReceiveServer(commit);
            Equal(90, f.Ticks(f.ServerBuff), "quick buff expiry anchored to Prepare");
            Equal(150, ExhaustionRows(f.ServerBuff).Single().Ticks, "quick fatigue independently anchored to Prepare");
            Equal(0, f.ServerItem.UseCalls, "no replayed native use/heal/cost/events");
            f.Owner.statLife = 57; f.Owner.statMana = 20; f.Owner.potionDelay = 0;
            MaterialClock(3040); byte[] secondPrepare = f.Prepare(), secondReady = f.Ready(secondPrepare), secondCommit = f.Commit(secondReady);
            int oldBuff = f.Ticks(f.ServerBuff); f.ReceiveServer(secondCommit);
            Equal(oldBuff, f.Ticks(f.ServerBuff), "quick refusal does not refresh existing buff");
            Equal(140, ExhaustionRows(f.ServerBuff).Single().Ticks, "quick refusal does not refresh fatigue");
            byte[] correction = f.Peers.Sent.Single(p => p[0] == InfiniCrafterLocal.Common.InfiniNetPacketIds.SyncGeneratedUtilityBuff);
            f.Mode(1); f.Peers.Receive(correction, 256);
            Equal(140, ExhaustionRows(f.OwnerBuff).Single().Ticks, "owner receives refusal correction through existing snapshot");
        }
    }

    private static void EX10QuickCommitExpiredBuffRetainsIndependentExhaustion()
    {
        foreach (byte kind in new byte[] { 1, 2 })
        foreach (int? policy in new int?[] { 180, 10, 0, null })
        {
            using var f = new QuickUtilityPeers(kind, cost: 0);
            f.Data.Gameplay.GeneratedBuff.DurationTicks = 10;
            f.Data.Gameplay.GeneratedBuff.ExhaustionTicks = policy;
            f.ApplyEquipmentSync = true;
            MaterialClock(5000);
            byte[] prepare = f.Prepare(), ready = f.Ready(prepare), commit = f.Commit(ready);
            MaterialClock(5030); f.ReceiveServer(commit);
            Equal(0, f.Ticks(f.ServerBuff), "expired quick buff never replays a contribution");
            var rows = ExhaustionRows(f.ServerBuff);
            Equal(policy == 180 ? 1 : 0, rows.Count, "delayed exhaustion expiry is independent of buff expiry");
            if (policy == 180) Equal(150, rows.Single().Ticks, "long fatigue keeps Prepare anchor after short buff expires");
            byte[] correction = f.Peers.Sent.Single(p => p[0] == InfiniCrafterLocal.Common.InfiniNetPacketIds.SyncGeneratedUtilityBuff);
            f.Mode(1); f.Peers.Receive(correction, 256);
            Equal(0, f.Ticks(f.OwnerBuff), "expired prediction is corrected without replay");
            Equal(rows.Count, ExhaustionRows(f.OwnerBuff).Count, "owner keeps exact independent authoritative timer count");
            if (policy == 180) Equal(150, ExhaustionRows(f.OwnerBuff).Single().Ticks, "owner correction retains long fatigue");
            Equal(1, f.OwnerItem.UseCalls, "native owner use still executes once");
            Equal(0, f.ServerItem.UseCalls, "delayed commit never replays native use");
        }
    }

    private static void EX11QuickCommitCannotReviveAnExhaustedAttempt()
    {
        foreach (byte kind in new byte[] { 1, 2 })
        {
            using var f = new QuickUtilityPeers(kind, cost: 0);
            f.Data.Gameplay.GeneratedBuff.ExhaustionTicks = 180;
            // This test advances the owner as well as the server; keep its
            // utility CPU-only rather than entering the headless light renderer.
            f.Data.Gameplay.GeneratedBuff.EmitLightStrength = 0f;
            f.ApplyEquipmentSync = true;
            MaterialClock(6000);
            byte[] firstPrepare = f.Prepare(), firstReady = f.Ready(firstPrepare), firstCommit = f.Commit(firstReady);
            f.ReceiveServer(firstCommit);
            // Advance actual buff consumers, not just the world clock, so the
            // original short utility has expired before the refused second use.
            for (uint tick = 6001; tick <= 6170; tick++)
            {
                MaterialClock(tick); f.Mode(1); ExhaustionBuffTick(f.OwnerBuff);
                f.Mode(2); ExhaustionBuffTick(f.ServerBuff);
            }
            Equal(10, ExhaustionRows(f.ServerBuff).Single().Ticks, "source is exhausted at second Prepare");
            f.Owner.statLife = 57; f.Owner.statMana = 20; f.Owner.potionDelay = 0;
            byte[] prepare = f.Prepare();
            Equal(0, f.Ticks(f.OwnerBuff), "native second use correctly suppresses only generated buff");
            byte[] ready = f.Ready(prepare), commit = f.Commit(ready);
            // Delivery crosses the old timer's boundary, still within the valid
            // ticket lifetime and well before the second buff would expire.
            MaterialClock(6190); f.ReceiveServer(commit);
            Equal(0, f.Ticks(f.ServerBuff), "Commit cannot turn an exhausted occurrence into a new buff");
            Equal(0, ExhaustionRows(f.ServerBuff).Count, "refused occurrence cannot restart expired exhaustion");
            byte[] correction = f.Peers.Sent.Single(p => p[0] == InfiniCrafterLocal.Common.InfiniNetPacketIds.SyncGeneratedUtilityBuff);
            f.Mode(1); f.Peers.Receive(correction, 256);
            Equal(0, f.Ticks(f.OwnerBuff), "owner receives refusal, not an unrequested fresh buff");
            Equal(0, ExhaustionRows(f.OwnerBuff).Count, "owner receives no refreshed fatigue");
            Equal(2, f.OwnerItem.UseCalls, "both independent native healing attempts execute");
            Equal(0, f.ServerItem.UseCalls, "neither Commit replays native healing");
        }
    }

    private static void EX12QueuedQuickAttemptsKeepConfirmedExhaustionDecision()
    {
        foreach (byte kind in new byte[] { 1, 2 })
        {
            using var f = new QuickUtilityPeers(kind, cost: 0);
            f.Data.Gameplay.GeneratedBuff.ExhaustionTicks = 60;
            f.ApplyEquipmentSync = true;
            MaterialClock(7000);
            byte[] firstPrepare = f.Prepare(), firstReady = f.Ready(firstPrepare);
            MaterialClock(7010);
            f.Owner.statLife = 57; f.Owner.statMana = 20; f.Owner.potionDelay = 0;
            byte[] secondPrepare = f.Prepare(), secondReady = f.Ready(secondPrepare);
            Equal(0, ExhaustionRows(f.ServerBuff).Count, "both tickets precede first authoritative Commit");
            byte[] firstCommit = f.Commit(firstReady), secondCommit = f.Commit(secondReady);
            MaterialClock(7020); f.ReceiveServer(firstCommit);
            Equal(40, ExhaustionRows(f.ServerBuff).Single().Ticks, "first confirmation keeps its original interval");
            for (uint tick = 7021; tick <= 7070; tick++)
            {
                MaterialClock(tick); f.Mode(2); ExhaustionBuffTick(f.ServerBuff);
            }
            int remaining = f.Ticks(f.ServerBuff);
            Equal(50, remaining, "first contribution still active after its short fatigue expires");
            f.ReceiveServer(secondCommit);
            Equal(remaining, f.Ticks(f.ServerBuff), "queued exhausted attempt cannot refresh the original buff");
            Equal(0, ExhaustionRows(f.ServerBuff).Count, "queued exhausted attempt cannot restart fatigue");
            Equal(2, f.OwnerItem.UseCalls, "queued generated-buff refusals preserve independent native uses");
        }
    }
}

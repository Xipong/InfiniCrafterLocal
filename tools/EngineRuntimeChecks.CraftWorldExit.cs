using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Threading.Tasks;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Common.Systems;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader.IO;

internal static partial class EngineRuntimeChecks
{
    // Real per-player owners and HTTP workers; no world loop, sockets to peers or provider inference.
    private static void CraftWorldUnloadRetiresServerOwnersWithoutRefundingEscrow()
    {
        CraftWorldUnloadServerOwnerCase(dedicated: false);
        CraftWorldUnloadServerOwnerCase(dedicated: true);
    }

    private static void CraftWorldUnloadServerOwnerCase(bool dedicated)
    {
        int mode = Terraria.Main.netMode, local = Terraria.Main.myPlayer;
        var players = Terraria.Main.player;
        string? recovery = Environment.GetEnvironmentVariable("INFINI_CRAFT_CACHE_RECOVERY_SECONDS");
        string? attempts = Environment.GetEnvironmentVariable("INFINI_CRAFT_HTTP_ATTEMPTS");
        var requests = new List<GeneratorClient.PreparedGenerationRequest>();
        var workers = new List<Task<GeneratedItemData?>>();
        var servers = new List<CraftHttpFixture>();
        var world = new GeneratedStationEscrowStateSystem();
        using var serializer = WithPersistenceBoolSerializer();
        try
        {
            Environment.SetEnvironmentVariable("INFINI_CRAFT_CACHE_RECOVERY_SECONDS", "0");
            Environment.SetEnvironmentVariable("INFINI_CRAFT_HTTP_ATTEMPTS", "2");
            Terraria.Main.netMode = NetmodeID.Server;
            Terraria.Main.myPlayer = dedicated ? 255 : 0; // Dedicated sentinel vs listen-host-shaped LocalPlayer.
            Terraria.Main.player = new Player[Terraria.Main.maxPlayers];
            world.ClearWorld();
            WithPlayer((host, hostOwner) => WithPlayer((first, firstOwner) => WithPlayer((second, secondOwner) =>
            {
                host.whoAmI = 0; host.active = true;
                first.whoAmI = 2; first.active = true;
                second.whoAmI = 3; second.active = false; // Disconnect can precede world unload.
                Terraria.Main.player[0] = host;
                Terraria.Main.player[1] = new Player(); // Unattached modPlayers must not prevent later retirement.
                Terraria.Main.player[2] = first;
                Terraria.Main.player[3] = second;
                var owners = new[] { hostOwner, firstOwner, secondOwner };
                Type jobType = typeof(InfiniCraftPlayer).GetNestedType("MultiDevCraftJob", BindingFlags.NonPublic)!;
                for (int index = 0; index < owners.Length; index++)
                {
                    InfiniCraftPlayer owner = owners[index];
                    owner.Initialize();
                    foreach (var item in owner.Player.inventory) item.TurnToAir();
                    string clientId = new string((char)('a' + index), 32);
                    typeof(InfiniCraftPlayer).GetField("_stationEscrowClientId", CraftFields)!.SetValue(owner, clientId);
                    typeof(InfiniCraftPlayer).GetField("_stationEscrowUsesRemoteAuthority", CraftFields)!.SetValue(owner, true);
                    // Admit the real registered session while live; disconnect only after durable capture.
                    owner.Player.active = true;
                    Equal(true, GeneratedStationEscrowStateSystem.RestoreOwnerState(clientId, owner), "live fixture owner admitted before material capture");
                    Equal(true, GeneratedStationEscrowStateSystem.IsBoundOwner(clientId, owner), "fixture owns the exact admitted session");
                    owner.RestoreServerStationEscrowSlots(Enumerable.Range(0, 6)
                        .Select(slot => new Item(slot % 2 == 0 ? ItemID.CopperShortsword : ItemID.WoodenSword, 1)).ToArray());
                    GeneratedStationEscrowStateSystem.CaptureOwnerState(clientId, owner);
                    if (index == 2) owner.Player.active = false; // Retain the disconnected-owner unload control.
                    for (int lane = 0; lane < 3; lane++)
                    {
                        string requestId = new string((char)('1' + index * 3 + lane), 32);
                        Equal(true, GeneratedStationEscrowStateSystem.TryBeginCraft(clientId, requestId, lane), "world owns pending transaction");
                        var request = new GeneratorClient.PreparedGenerationRequest {
                            RefundA = new Item(ItemID.CopperShortsword, 1),
                            RefundB = new Item(ItemID.WoodenSword, 1),
                        };
                        var server = new CraftHttpFixture(2) { RejectSecondGeneration = true };
                        var client = new GeneratorClient { Endpoint = server.Endpoint };
                        requests.Add(request); servers.Add(server);
                        Task<GeneratedItemData?> worker = Task.Run(() => client.GeneratePreparedBlocking(request));
                        workers.Add(worker);
                        if (lane == 0)
                        {
                            typeof(InfiniCraftPlayer).GetField("_request", CraftFields)!.SetValue(owner, request);
                            typeof(InfiniCraftPlayer).GetField("_task", CraftFields)!.SetValue(owner, worker);
                            typeof(InfiniCraftPlayer).GetField("_serverRequestId", CraftFields)!.SetValue(owner, requestId);
                        }
                        else
                        {
                            object job = Activator.CreateInstance(jobType, nonPublic: true)!;
                            jobType.GetField("Request", CraftFields)!.SetValue(job, request);
                            jobType.GetField("Task", CraftFields)!.SetValue(job, worker);
                            jobType.GetField("RequestId", CraftFields)!.SetValue(job, requestId);
                            jobType.GetField("LaneIndex", CraftFields)!.SetValue(job, lane);
                            ((Array)typeof(InfiniCraftPlayer).GetField("_multiDevJobs", CraftFields)!.GetValue(owner)!).SetValue(job, lane - 1);
                        }
                        server.Held.Task.WaitAsync(TimeSpan.FromSeconds(5)).GetAwaiter().GetResult();
                    }
                }
                var before = new TagCompound(); world.SaveWorldData(before);
                var durableOwners = before.GetList<TagCompound>("infiniStationEscrowOwnersV1");
                Equal(owners.Length, durableOwners.Count, "saved authority contains every material owner, not an empty journal-only fixture");
                for (int index = 0; index < owners.Length; index++)
                {
                    var slots = durableOwners.Single(row => row.GetString("clientId") == new string((char)('a' + index), 32))
                        .GetList<TagCompound>("slots");
                    Equal(6, slots.Count, "each durable owner contains all six material slots before unload");
                    for (int slot = 0; slot < 6; slot++)
                    {
                        Item material = ItemIO.Load(slots.Single(row => row.GetInt("index") == slot).GetCompound("item"));
                        Equal(slot % 2 == 0 ? (int)ItemID.CopperShortsword : (int)ItemID.WoodenSword,
                            material.type, "native saved material retains the exact slot item");
                        Equal(1, material.stack, "native saved material retains the sole input stack");
                    }
                }
                Equal(9, before.GetList<TagCompound>("infiniStationCraftTransactionsV1").Count, "saved journal includes every pending craft lane");
                string beforeBytes = PersistenceRawBytes(before);
                new InfiniCraftWorldExitSystem().OnWorldUnload();
                // Assert remote first so baseline RED identifies the confirmed caller bug.
                Equal(true, requests[3].CancellationToken.IsCancellationRequested,
                    "server world unload synchronously cancels active remote owner's exact request");
                foreach (var request in requests)
                    Equal(true, request.CancellationToken.IsCancellationRequested, "all ordinary/extra host and remote requests retired");
                foreach (var owner in owners)
                {
                    Equal(false, owner.HasAnyCraftLanePending, "synchronous unload drops result/retry consumers");
                    Equal(true, typeof(InfiniCraftPlayer).GetField("_task", CraftFields)!.GetValue(owner) is null, "ordinary task ownership dropped");
                    Equal(0, owner.Player.inventory.Sum(item => item.IsAir ? 0 : item.stack), "server never refunds canonical escrow or request copies to inventory");
                    Equal(6, owner.SnapshotServerStationEscrowSlots().Count(item => !item.IsAir), "six live escrow slots unchanged");
                }
                foreach (var worker in workers)
                    Equal(true, worker.WaitAsync(TimeSpan.FromSeconds(2)).GetAwaiter().GetResult() is null,
                        "worker retires asynchronously while response remains withheld");
                foreach (var server in servers)
                    Equal("cache,generate", string.Join(",", server.Requests), "no recovery or generation after unload");
                new InfiniCraftWorldExitSystem().OnWorldUnload(); // Retirement is repeatable without refund/outcome mutation.
                var after = new TagCompound(); world.SaveWorldData(after);
                Equal(beforeBytes, PersistenceRawBytes(after), "world authority, escrow and pending journal are byte-identical after repeated unload");
                for (int index = 0; index < owners.Length; index++)
                {
                    Equal(new string((char)('a' + index), 32), (string)typeof(InfiniCraftPlayer)
                        .GetField("_stationEscrowClientId", CraftFields)!.GetValue(owners[index])!, "owner session token retained");
                    Equal(true, (bool)typeof(InfiniCraftPlayer).GetField("_stationEscrowUsesRemoteAuthority", CraftFields)!
                        .GetValue(owners[index])!, "server retains remote-authority classification");
                }
                string scope = GeneratedStationEscrowStateSystem.AuthorityScope;
                world.LoadWorldData(PersistenceNbtRoundtrip(after));
                Equal(scope, GeneratedStationEscrowStateSystem.AuthorityScope, "native reload preserves exact world authority scope");
                WithPlayer((replacement, restored) => {
                    restored.Initialize();
                    replacement.whoAmI = 2; replacement.active = true;
                    Terraria.Main.player[replacement.whoAmI] = replacement;
                    Equal(true, GeneratedStationEscrowStateSystem.RestoreOwnerState(new string('b', 32), restored), "same durable owner restores on new player");
                    Equal(true, GeneratedStationEscrowStateSystem.IsBoundOwner(new string('b', 32), restored), "reload binds the exact registered replacement session");
                    Equal(6, restored.SnapshotServerStationEscrowSlots().Count(item => !item.IsAir), "reload retains sole six-slot material authority");
                    Equal(0, replacement.inventory.Sum(item => item.IsAir ? 0 : item.stack), "reconnect does not also refund inventory");
                });
                for (int index = 0; index < owners.Length; index++)
                for (int lane = 0; lane < 3; lane++)
                {
                    string clientId = new string((char)('a' + index), 32);
                    string requestId = new string((char)('1' + index * 3 + lane), 32);
                    Equal(true, GeneratedStationEscrowStateSystem.TryReplayCraft(clientId, requestId, out var outcome), "existing restart policy resolves saved pending transaction");
                    Equal(false, outcome.Success, "retired craft cannot become committed success");
                    Equal(false, GeneratedStationEscrowStateSystem.TryBeginCraft(clientId, requestId, lane), "same session/request cannot debit again");
                }
            })));
        }
        finally
        {
            foreach (var request in requests) request.Cancel();
            foreach (var server in servers) server.Release();
            try { Task.WhenAll(workers).WaitAsync(TimeSpan.FromSeconds(5)).GetAwaiter().GetResult(); }
            finally
            {
                foreach (var server in servers) server.DisposeAsync().AsTask().GetAwaiter().GetResult();
                world.ClearWorld(); Terraria.Main.player = players; Terraria.Main.netMode = mode; Terraria.Main.myPlayer = local;
                Environment.SetEnvironmentVariable("INFINI_CRAFT_CACHE_RECOVERY_SECONDS", recovery);
                Environment.SetEnvironmentVariable("INFINI_CRAFT_HTTP_ATTEMPTS", attempts);
            }
        }
    }
}

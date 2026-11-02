using System;
using System.IO;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Projectiles;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Content.Items;
using Terraria;
using Terraria.DataStructures;
using Terraria.ID;
using Terraria.ModLoader.IO;
using InfiniMod = InfiniCrafterLocal.InfiniCrafterLocalMod;

internal static partial class EngineRuntimeChecks
{
    private static byte[] FishingWitnessWire(GeneratedFishingReadiness guard, Projectile projectile)
    {
        using var payload = new MemoryStream(); var bits = new BitWriter();
        guard.SendExtraAI(projectile, bits, new BinaryWriter(payload));
        using var wire = new MemoryStream(); bits.Flush(new BinaryWriter(wire)); payload.WriteTo(wire); return wire.ToArray();
    }
    private static void FishingWitnessRead(GeneratedFishingReadiness guard, Projectile projectile, byte[] wire)
    {
        using var reader = new BinaryReader(new MemoryStream(wire)); var bits = new BitReader(reader);
        guard.ReceiveExtraAI(projectile, bits, reader);
    }
    private static void NativeFishingReadinessWitnessAndBounds()
    {
        using var actors = new MobilityConsumptionNativeScope(); using var peers = new ReviewPeers();
        using var send = PersistenceObserveNetworkSend((_, __) => { });
        foreach (string mode in new[] { "late", "timeout", "switch", "death", "input", "token", "hash", "id", "truncated", "flag", "version", "kill", "rewind", "repeat", "vanilla" }) {
        var data = NativeFishingFixture(true); data.Id = "native_pending_fishing_" + mode; data.Visual.SpritePath = "valid.png"; data.Normalize();
        GeneratedItemRegistryService.StampCurrentWorld(data); peers.Registry.RegisterLocal(data, false, false);
        byte[] itemWire = Array.Empty<byte>(), witnessWire = Array.Empty<byte>();
        WithPlayer((owner, _) => {
            NativeUsePreparePlayer(owner); NativeUsePeerMode(peers, NetmodeID.MultiplayerClient, 0);
            var item = MobilityConsumptionHost(data); owner.inventory[0] = item.Item; owner.altFunctionUse = 2;
            Equal(true, item.CanUseItem(owner), "source uses declared alternate fishing"); itemWire = NativeUseWire(item);
            var projectile = new Projectile { active = true, type = ProjectileID.BobberWooden, owner = 0, timeLeft = 600 };
            var guard = new GeneratedFishingReadiness(); guard.OnSpawn(projectile, new EntitySource_ItemUse(owner, item.Item));
            witnessWire = FishingWitnessWire(guard, projectile);
            Equal(true, witnessWire.Length > 40, "actual accepted item source produces bounded witness");
            Equal(true, guard.PreAI(projectile), "local owner never waits for replica readiness");
            owner.altFunctionUse = 0; Equal(true, item.CanUseItem(owner), "ordinary binding source control");
            var ordinary = new GeneratedFishingReadiness(); ordinary.OnSpawn(projectile, new EntitySource_ItemUse(owner, item.Item));
            Equal(true, FishingWitnessWire(ordinary, projectile).Length < witnessWire.Length, "non-fishing action cannot create association");
        });
            WithPlayer((remote, state) => {
                NativeUsePreparePlayer(remote); NativeUsePeerMode(peers, NetmodeID.MultiplayerClient, 1);
                var registry = typeof(InfiniMod).GetField("<GeneratedItems>k__BackingField", BindingFlags.Static | BindingFlags.NonPublic)!;
                using var lateRegistry = new GeneratedItemRegistryService(); registry.SetValue(null, lateRegistry);
                try {
                    MaterialClock(1000);
                    var item = MobilityConsumptionHost(GeneratedItemData.Placeholder()); item.NetReceive(new BinaryReader(new MemoryStream(itemWire)));
                    remote.inventory[0] = item.Item;
                    Equal(true, GeneratedItemData.IsPlayerSaveReferenceOnly(item.Data), "missing peer contains actual compact reference");
                    var projectile = new Projectile { active = true, type = ProjectileID.BobberWooden, owner = 0, timeLeft = 600 };
                    var guard = new GeneratedFishingReadiness();
                    if (mode != "vanilla") FishingWitnessRead(guard, projectile, witnessWire);
                    if (mode == "vanilla") { Equal(true, guard.PreAI(projectile), "unassociated native bobber never borrows held identity"); return; }
                    Equal(false, guard.PreAI(projectile), "unresolved source waits without native AI");
                    Equal(false, guard.ShouldUpdatePosition(projectile), "unresolved source has no position integration");
                    Equal(600, projectile.timeLeft, "readiness does not alter native lifetime");
                    Equal(0, item.UseCalls, "pending never activates effects");
                    if (mode == "late") {
                        peers.Mod.HandlePacket(new BinaryReader(new MemoryStream(AssetLifecycleDefinitionPacket(data))), 256);
                        MaterialClock(1120); Equal(true, item.CanUseItem(remote), "real definition response hydrates source"); state.PreItemCheck();
                        Equal(true, guard.PreAI(projectile), "same bobber resumes native AI after hydration");
                        Equal(true, guard.ShouldUpdatePosition(projectile), "same bobber resumes native position");
                        Equal(true, projectile.active, "no replacement or premature kill"); Equal(600, projectile.timeLeft, "no lifetime extension on resume");
                    } else {
                        switch (mode) {
                            case "timeout": MaterialClock(1300); break;
                            case "repeat": MaterialClock(1299); FishingWitnessRead(guard, projectile, witnessWire); Equal(false, guard.PreAI(projectile), "repeat preserves pending"); MaterialClock(1300); break;
                            case "switch": remote.selectedItem = 1; break;
                            case "death": remote.dead = true; break;
                            case "input": item.SetNativeUseProjection(item.NativeUseProjection!.Value with { Input = 0, Revision = 2 }); break;
                            case "token": item.SetNativeUseProjection(item.NativeUseProjection!.Value with { Token = item.PresentationToken + 1 }); break;
                            case "hash": item.SetNativeUseProjection(item.NativeUseProjection!.Value with { Definition = new string('0', 64) }); break;
                            case "id": item.Data.Id = "unrelated_reference"; break;
                            case "truncated": FishingWitnessRead(guard, projectile, witnessWire[..^1]); break;
                            case "flag": { using var empty = new MemoryStream(); new BitWriter().Flush(new BinaryWriter(empty)); FishingWitnessRead(guard, projectile, empty.ToArray()); break; }
                            case "version": { var bad = (byte[])witnessWire.Clone(); using var parser = new BinaryReader(new MemoryStream(bad)); _ = new BitReader(parser); bad[parser.BaseStream.Position] = 99; FishingWitnessRead(guard, projectile, bad); break; }
                            case "kill": projectile.active = false; break;
                            case "rewind": MaterialClock(999); break;
                        }
                        Equal(false, guard.PreAI(projectile), mode + " refuses native AI");
                        Equal(false, projectile.active, mode + " retires rather than rebinding or resurrecting");
                    }
                    Equal(100, remote.statMana, "replica readiness never pays resources");
                } finally { registry.SetValue(null, peers.Registry); }
            });
        }
    }
}
